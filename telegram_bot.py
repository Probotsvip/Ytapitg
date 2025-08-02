import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import requests
import httpx

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MAX_AUDIO_SIZE, 
    MAX_VIDEO_SIZE, MAX_DOCUMENT_SIZE, MAX_CACHE_AGE
)
from models import TelegramCache, db
from utils import sanitize_filename, format_duration

logger = logging.getLogger(__name__)

class TelegramStorage:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.channel_id = TELEGRAM_CHANNEL_ID or ""
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        
    async def search_existing_media(self, query: str, youtube_id: str = None, title: str = None) -> Optional[Dict[str, Any]]:
        """Search for existing media in Telegram channel"""
        if not self.base_url:
            logger.info("Telegram bot not configured - using database cache only")
            return None
            
        # First check database cache
        query_hash = hashlib.md5(query.lower().encode()).hexdigest()
        cached_result = TelegramCache.query.filter_by(query_hash=query_hash).first()
        
        if cached_result:
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
                'cached': True
            }
        
        # Search in Telegram channel if not in cache
        try:
            search_terms = [query.lower()]
            if youtube_id:
                search_terms.append(youtube_id.lower())
            if title:
                search_terms.append(title.lower())
            
            # Get recent messages from channel
            async with self.bot:
                chat = await self.bot.get_chat(self.channel_id)
                
                # Search through recent messages (limit to avoid rate limits)
                offset = 0
                limit = 100
                
                while offset < 500:  # Search last 500 messages
                    try:
                        updates = await self.bot.get_updates(
                            offset=offset,
                            limit=limit,
                            timeout=10
                        )
                        
                        if not updates:
                            break
                            
                        for update in updates:
                            if update.channel_post and update.channel_post.chat.id == int(self.channel_id):
                                message = update.channel_post
                                if self._message_matches_query(message, search_terms):
                                    result = self._extract_file_info(message)
                                    if result:
                                        # Cache the result
                                        await self._cache_result(query, result, message.message_id)
                                        return result
                        
                        offset += limit
                        
                    except Exception as e:
                        logger.error(f"Error searching Telegram messages: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"Error searching Telegram channel: {e}")
            
        return None
    
    def _message_matches_query(self, message, search_terms: List[str]) -> bool:
        """Check if message matches any of the search terms"""
        if not message.caption:
            return False
            
        caption_lower = message.caption.lower()
        return any(term in caption_lower for term in search_terms)
    
    def _extract_file_info(self, message) -> Optional[Dict[str, Any]]:
        """Extract file information from Telegram message"""
        file_info = None
        file_type = None
        
        if message.audio:
            file_info = message.audio
            file_type = 'audio'
        elif message.video:
            file_info = message.video
            file_type = 'video'
        elif message.document:
            file_info = message.document
            file_type = 'document'
        
        if file_info:
            return {
                'file_id': file_info.file_id,
                'file_unique_id': file_info.file_unique_id,
                'file_type': file_type,
                'title': getattr(file_info, 'title', 'Unknown'),
                'duration': getattr(file_info, 'duration', None),
                'message_id': message.message_id,
                'cached': False
            }
        
        return None
    
    async def _cache_result(self, query: str, result: Dict[str, Any], message_id: int):
        """Cache the search result in database"""
        try:
            query_hash = hashlib.md5(query.lower().encode()).hexdigest()
            
            cache_entry = TelegramCache(
                query_hash=query_hash,
                original_query=query,
                title=result['title'],
                duration=str(result.get('duration', '')),
                file_id=result['file_id'],
                file_unique_id=result['file_unique_id'],
                file_type=result['file_type'],
                telegram_message_id=message_id,
                access_count=1
            )
            
            db.session.add(cache_entry)
            db.session.commit()
            logger.info(f"Cached search result for query: {query}")
            
        except Exception as e:
            logger.error(f"Error caching result: {e}")
            db.session.rollback()
    
    async def upload_media(self, file_path: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upload media file to Telegram channel"""
        if not self.base_url or not os.path.exists(file_path):
            return None
        
        try:
            # Determine file type and prepare upload
            file_extension = os.path.splitext(file_path)[1].lower()
            is_audio = file_extension in ['.mp3', '.m4a', '.ogg', '.wav']
            
            # Prepare file for upload
            with open(file_path, 'rb') as file:
                files = {'audio' if is_audio else 'document': file}
                data = {
                    'chat_id': self.channel_id,
                    'caption': f"🎵 {metadata.get('title', 'Unknown Title')}\n⏱️ {metadata.get('duration', 'Unknown duration')}\n🔗 {metadata.get('original_url', '')}"
                }
                
                # Choose appropriate endpoint
                endpoint = 'sendAudio' if is_audio else 'sendDocument'
                url = f"{self.base_url}/{endpoint}"
                
                # Upload to Telegram
                response = requests.post(url, data=data, files=files, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        message = result['result']
                        file_info = message.get('audio') or message.get('document')
                        
                        return {
                            'file_id': file_info['file_id'],
                            'file_unique_id': file_info['file_unique_id'],
                            'file_type': 'audio' if is_audio else 'document',
                            'message_id': message['message_id'],
                            'title': metadata.get('title', 'Unknown'),
                            'duration': metadata.get('duration', ''),
                            'uploaded': True
                        }
                    else:
                        logger.error(f"Telegram API error: {result}")
                else:
                    logger.error(f"HTTP error {response.status_code}: {response.text}")
                    
        except Exception as e:
            logger.error(f"Error uploading to Telegram: {e}")
        
        return None
    
    async def get_file_url(self, file_id: str) -> Optional[str]:
        """Get direct download URL for a Telegram file"""
        if not self.base_url:
            return None
            
        try:
            # Get file info from Telegram
            url = f"{self.base_url}/getFile"
            response = requests.get(url, params={'file_id': file_id}, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    file_path = result['result']['file_path']
                    return f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                    
        except Exception as e:
            logger.error(f"Error getting file URL: {e}")
            
        return None
        
    def cleanup_cache(self):
        """Clean up old cache entries"""
        try:
            cutoff_time = time.time() - MAX_CACHE_AGE
            cutoff_datetime = datetime.fromtimestamp(cutoff_time)
            
            deleted_count = db.session.query(TelegramCache).filter(
                TelegramCache.created_at < cutoff_datetime
            ).delete()
            
            db.session.commit()
            logger.info(f"Cleaned up {deleted_count} old cache entries")
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            db.session.rollback()

# Global instance
telegram_storage = TelegramStorage()
