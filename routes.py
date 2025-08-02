import asyncio
import datetime
import logging
import os
import secrets
import time
from functools import wraps
from typing import Dict, Any, Optional

from flask import request, jsonify, render_template, redirect, url_for, flash
from app import app, limiter, db
from models import ApiKey, ApiLog, TelegramCache, DownloadHistory
from telegram_bot import telegram_storage
from youtube_api import youtube_extractor
from search import query_matcher
from utils import (
    validate_query, cleanup_temp_file, generate_api_key, 
    log_api_usage, format_file_size
)
from config import ADMIN_API_KEY, API_VERSION

logger = logging.getLogger(__name__)

def require_api_key(f):
    """Decorator to require valid API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        key_obj = ApiKey.query.filter_by(key=api_key).first()
        
        if not key_obj:
            return jsonify({'error': 'Invalid API key'}), 401
        
        if key_obj.is_expired():
            return jsonify({'error': 'API key expired'}), 401
        
        if key_obj.remaining_requests() <= 0:
            return jsonify({'error': 'API key quota exceeded'}), 429
        
        # Update usage count
        if datetime.datetime.now() > key_obj.reset_at:
            key_obj.count = 1
            key_obj.reset_at = datetime.datetime.now() + datetime.timedelta(days=1)
        else:
            key_obj.count += 1
        
        db.session.commit()
        
        # Store key object for use in route
        setattr(request, 'api_key', key_obj)
        
        return f(*args, **kwargs)
    
    return decorated_function

def require_admin(f):
    """Decorator to require admin API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key != ADMIN_API_KEY:
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

@app.route('/')
def index():
    """Main page with API documentation"""
    return render_template('index.html', api_version=API_VERSION)

@app.route('/admin')
def admin_panel():
    """Admin panel for API key management"""
    return render_template('admin.html')

@app.route('/api/v1/extract', methods=['GET', 'POST'])
@limiter.limit("50 per minute")
@require_api_key
async def extract_media():
    """Main endpoint for media extraction"""
    start_time = time.time()
    
    try:
        # Get parameters
        if request.method == 'POST':
            data = request.get_json() or {}
            query = data.get('query', '')
            format_type = data.get('format', 'audio')
            force_download = data.get('force_download', False)
        else:
            query = request.args.get('query', '')
            format_type = request.args.get('format', 'audio')
            force_download = request.args.get('force_download', '').lower() == 'true'
        
        # Validate input
        if not validate_query(query):
            return jsonify({'error': 'Invalid query'}), 400
        
        if format_type not in ['audio', 'video']:
            return jsonify({'error': 'Format must be audio or video'}), 400
        
        # Log the request
        api_key_obj = getattr(request, 'api_key', None)
        if api_key_obj:
            log_api_usage(
                api_key_obj.id, 
                'extract', 
                query, 
                request.remote_addr or ''
            )
        
        # Check Telegram cache first (unless force download)
        cached_result = None
        if not force_download:
            # Try comprehensive search
            search_result = query_matcher.comprehensive_search(query)
            if search_result:
                cached_result = search_result['cache_entry']
                
                # Update access statistics
                cached_result.access_count += 1
                cached_result.last_accessed = datetime.datetime.now()
                db.session.commit()
                
                processing_time = time.time() - start_time
                
                return jsonify({
                    'status': 'success',
                    'cached': True,
                    'match_type': search_result['match_type'],
                    'confidence': search_result['confidence'],
                    'data': {
                        'title': cached_result.title,
                        'file_id': cached_result.file_id,
                        'file_unique_id': cached_result.file_unique_id,
                        'file_type': cached_result.file_type,
                        'duration': cached_result.duration,
                        'telegram_message_id': cached_result.telegram_message_id,
                        'query': query,
                        'processing_time': round(processing_time, 2),
                        'access_count': cached_result.access_count
                    }
                })
        
        # If not cached or force download, extract from YouTube
        async with youtube_extractor as extractor:
            extraction_result = await extractor.extract_media(query, format_type)
        
        if not extraction_result:
            return jsonify({
                'status': 'error',
                'error': 'Failed to extract media from YouTube'
            }), 404
        
        # Upload to Telegram for caching
        upload_result = await telegram_storage.upload_media(
            extraction_result['file_path'],
            extraction_result
        )
        
        # Cleanup temporary file
        cleanup_temp_file(extraction_result['file_path'])
        
        if not upload_result:
            return jsonify({
                'status': 'error',
                'error': 'Failed to upload to Telegram storage'
            }), 500
        
        # Log download history
        try:
            api_key_obj = getattr(request, 'api_key', None)
            if api_key_obj:
                download_entry = DownloadHistory(
                    api_key_id=api_key_obj.id,
                    query=query,
                    youtube_url=extraction_result.get('youtube_url', ''),
                    youtube_id=extraction_result.get('youtube_id', ''),
                    title=extraction_result['title'],
                    file_type=format_type,
                    file_size=extraction_result.get('file_size', 0),
                    duration=extraction_result.get('duration', ''),
                    source=extraction_result['source'],
                    processing_time=int(time.time() - start_time),
                    telegram_uploaded=True
                )
                db.session.add(download_entry)
                db.session.commit()
        except Exception as e:
            logger.error(f"Error logging download history: {e}")
        
        processing_time = time.time() - start_time
        
        return jsonify({
            'status': 'success',
            'cached': False,
            'data': {
                'title': extraction_result['title'],
                'youtube_id': extraction_result.get('youtube_id', ''),
                'youtube_url': extraction_result.get('youtube_url', ''),
                'duration': extraction_result.get('duration', ''),
                'file_id': upload_result['file_id'],
                'file_unique_id': upload_result['file_unique_id'],
                'file_type': upload_result['file_type'],
                'file_size': extraction_result.get('file_size', 0),
                'file_size_formatted': format_file_size(extraction_result.get('file_size', 0)),
                'source': extraction_result['source'],
                'telegram_message_id': upload_result['message_id'],
                'processing_time': round(processing_time, 2),
                'query': query
            }
        })
        
    except Exception as e:
        logger.error(f"Error in extract_media: {e}")
        return jsonify({
            'status': 'error',
            'error': 'Internal server error'
        }), 500

@app.route('/api/v1/search', methods=['GET'])
@limiter.limit("30 per minute")
@require_api_key
def search_cache():
    """Search cached media"""
    query = request.args.get('query', '')
    
    if not validate_query(query):
        return jsonify({'error': 'Invalid query'}), 400
    
    # Perform comprehensive search
    search_result = query_matcher.comprehensive_search(query)
    
    if search_result:
        cache_entry = search_result['cache_entry']
        return jsonify({
            'status': 'success',
            'found': True,
            'match_type': search_result['match_type'],
            'confidence': search_result['confidence'],
            'data': {
                'title': cache_entry.title,
                'file_id': cache_entry.file_id,
                'file_type': cache_entry.file_type,
                'duration': cache_entry.duration,
                'created_at': cache_entry.created_at.isoformat(),
                'access_count': cache_entry.access_count
            }
        })
    else:
        return jsonify({
            'status': 'success',
            'found': False,
            'message': 'No cached media found for this query'
        })

@app.route('/api/v1/admin/keys', methods=['GET'])
@require_admin
def list_api_keys():
    """List all API keys (admin only)"""
    keys = db.session.query(ApiKey).all()
    
    keys_data = []
    for key in keys:
        keys_data.append({
            'id': key.id,
            'name': key.name,
            'key': key.key[:8] + '...',  # Show only first 8 characters
            'is_admin': key.is_admin,
            'created_at': key.created_at.isoformat(),
            'valid_until': key.valid_until.isoformat(),
            'daily_limit': key.daily_limit,
            'current_count': key.count,
            'remaining_requests': key.remaining_requests()
        })
    
    return jsonify({
        'status': 'success',
        'keys': keys_data
    })

@app.route('/api/v1/admin/keys', methods=['POST'])
@require_admin
def create_api_key():
    """Create new API key (admin only)"""
    data = request.get_json() or {}
    
    name = data.get('name', '')
    days_valid = data.get('days_valid', 30)
    daily_limit = data.get('daily_limit', 100)
    is_admin = data.get('is_admin', False)
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    # Generate new API key
    new_key = generate_api_key()
    valid_until = datetime.datetime.now() + datetime.timedelta(days=days_valid)
    
    api_key = ApiKey(
        key=new_key,
        name=name,
        is_admin=is_admin,
        valid_until=valid_until,
        daily_limit=daily_limit
    )
    
    db.session.add(api_key)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'key': {
            'id': api_key.id,
            'key': new_key,
            'name': name,
            'valid_until': valid_until.isoformat(),
            'daily_limit': daily_limit,
            'is_admin': is_admin
        }
    })

@app.route('/api/v1/admin/keys/<int:key_id>', methods=['DELETE'])
@require_admin
def delete_api_key(key_id):
    """Delete API key (admin only)"""
    api_key = db.session.get(ApiKey, key_id)
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404
    
    db.session.delete(api_key)
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'message': 'API key deleted successfully'
    })

@app.route('/api/v1/admin/stats', methods=['GET'])
@require_admin
def get_stats():
    """Get system statistics (admin only)"""
    
    # API Key stats
    total_keys = db.session.query(ApiKey).count()
    active_keys = db.session.query(ApiKey).filter(ApiKey.valid_until > datetime.datetime.now()).count()
    
    # Cache stats
    total_cached = db.session.query(TelegramCache).count()
    cache_size = db.session.query(db.func.sum(TelegramCache.access_count)).scalar() or 0
    
    # Download stats
    total_downloads = db.session.query(DownloadHistory).count()
    today_downloads = db.session.query(DownloadHistory).filter(
        DownloadHistory.created_at >= datetime.datetime.now().date()
    ).count()
    
    # Most popular queries
    popular_queries = db.session.query(
        TelegramCache.original_query,
        TelegramCache.access_count
    ).order_by(TelegramCache.access_count.desc()).limit(10).all()
    
    return jsonify({
        'status': 'success',
        'stats': {
            'api_keys': {
                'total': total_keys,
                'active': active_keys
            },
            'cache': {
                'total_items': total_cached,
                'total_accesses': cache_size
            },
            'downloads': {
                'total': total_downloads,
                'today': today_downloads
            },
            'popular_queries': [
                {'query': query, 'count': count} 
                for query, count in popular_queries
            ]
        }
    })

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': API_VERSION,
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': str(e.description)
    }), 429

@app.errorhandler(404)
def not_found_handler(e):
    return jsonify({
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error_handler(e):
    return jsonify({
        'error': 'Internal server error'
    }), 500
