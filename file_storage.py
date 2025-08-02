import os
import shutil
import hashlib
import logging
from typing import Optional, Dict, Any
from models import TelegramCache, db
from utils import sanitize_filename

logger = logging.getLogger(__name__)

class LocalFileStorage:
    def __init__(self):
        self.storage_dir = "stored_media"
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
    
    def store_media(self, file_path: str, media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Store media file permanently and save to database"""
        try:
            query = media_info.get('original_query', media_info.get('title', ''))
            query_hash = hashlib.md5(query.lower().encode()).hexdigest()
            
            # Check if already stored
            existing = TelegramCache.query.filter_by(query_hash=query_hash).first()
            if existing:
                logger.info(f"Media already stored: {media_info.get('title', 'Unknown')}")
                return {
                    'file_id': existing.file_id,
                    'file_unique_id': existing.file_unique_id,
                    'file_type': existing.file_type,
                    'message_id': existing.telegram_message_id,
                    'stored_path': existing.file_id  # Using file_id as stored path
                }
            
            # Create permanent file name
            title = sanitize_filename(media_info.get('title', 'unknown'))
            youtube_id = media_info.get('youtube_id', '')
            file_ext = os.path.splitext(file_path)[1]
            
            if youtube_id:
                stored_filename = f"{youtube_id}_{title}{file_ext}"
            else:
                stored_filename = f"{query_hash}_{title}{file_ext}"
            
            stored_path = os.path.join(self.storage_dir, stored_filename)
            
            # Copy file to permanent storage
            shutil.copy2(file_path, stored_path)
            
            file_size = os.path.getsize(stored_path)
            
            # Save to database
            cache_entry = TelegramCache(
                query_hash=query_hash,
                original_query=query,
                youtube_id=youtube_id,
                title=media_info.get('title', 'Unknown Title'),
                duration=media_info.get('duration', ''),
                file_id=stored_path,  # Store local path in file_id
                file_unique_id=query_hash,
                file_type=media_info.get('file_type', 'audio'),
                telegram_message_id=int(file_size)  # Store file size in message_id field
            )
            
            db.session.add(cache_entry)
            db.session.commit()
            
            logger.info(f"Stored media permanently: {title}")
            
            return {
                'file_id': stored_path,
                'file_unique_id': query_hash,
                'file_type': media_info.get('file_type', 'audio'),
                'message_id': file_size,
                'stored_path': stored_path
            }
            
        except Exception as e:
            logger.error(f"Error storing media: {e}")
            return None
    
    def get_stored_media(self, query: str) -> Optional[Dict[str, Any]]:
        """Get stored media from database"""
        query_hash = hashlib.md5(query.lower().encode()).hexdigest()
        cached_result = TelegramCache.query.filter_by(query_hash=query_hash).first()
        
        if cached_result and os.path.exists(cached_result.file_id):
            # Update access statistics
            cached_result.access_count += 1
            cached_result.last_accessed = db.func.now()
            db.session.commit()
            
            return {
                'file_id': cached_result.file_id,
                'file_unique_id': cached_result.file_unique_id,
                'file_type': cached_result.file_type,
                'title': cached_result.title,
                'duration': cached_result.duration,
                'message_id': cached_result.telegram_message_id,
                'stored_path': cached_result.file_id,
                'cached': True
            }
        
        return None

# Create global instance
local_storage = LocalFileStorage()