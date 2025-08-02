import asyncio
import hashlib
import logging
import os
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import httpx

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MAX_AUDIO_SIZE, 
    MAX_VIDEO_SIZE, MAX_DOCUMENT_SIZE
)
from models import TelegramCache, db
from utils import sanitize_filename, format_duration

logger = logging.getLogger(__name__)

class TelegramStorage:
    def __init__(self):
        self.bot = None  # Temporarily disabled due to library conflicts
        self.channel_id = TELEGRAM_CHANNEL_ID or ""
        
    async def search_existing_media(self, query: str, youtube_id: str = None, title: str = None) -> Optional[Dict[str, Any]]:
        """Search for existing media in Telegram channel"""
        if not self.bot:
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
        if not self.bot:
            logger.info("Telegram bot not configured - returning mock file data")
            return {
                'file_id': f"mock_file_{hashlib.md5(file_path.encode()).hexdigest()[:16]}",
                'file_unique_id': f"mock_unique_{hashlib.md5(file_path.encode()).hexdigest()[:16]}",
                'file_type': 'audio',
                'message_id': 12345,
                'title': metadata.get('title', 'Unknown'),
                'duration': metadata.get('duration', ''),
                'uploaded': False
            }
        
        if not os.path.exists(file_path):
            return None
        
        try:
            file_size = os.path.getsize(file_path)
            file_type = self._determine_file_type(file_path, file_size)
            caption = self._build_caption(metadata)
            
            async with self.bot:
                if file_type == 'audio':
                    message = await self.bot.send_audio(
                        chat_id=self.channel_id,
                        audio=open(file_path, 'rb'),
                        caption=caption,
                        title=metadata.get('title', 'Unknown'),
                        performer=metadata.get('artist', 'Unknown Artist'),
                        duration=metadata.get('duration_seconds', 0),
                        parse_mode='HTML'
                    )
                    file_info = message.audio
                    
                elif file_type == 'video':
                    message = await self.bot.send_video(
                        chat_id=self.channel_id,
                        video=open(file_path, 'rb'),
                        caption=caption,
                        duration=metadata.get('duration_seconds', 0),
                        parse_mode='HTML'
                    )
                    file_info = message.video
                    
                else:  # document
                    message = await self.bot.send_document(
                        chat_id=self.channel_id,
                        document=open(file_path, 'rb'),
                        caption=caption,
                        parse_mode='HTML'
                    )
                    file_info = message.document
                
                # Cache the uploaded file
                await self._cache_upload_result(metadata['query'], message, file_info, file_type)
                
                return {
                    'file_id': file_info.file_id,
                    'file_unique_id': file_info.file_unique_id,
                    'file_type': file_type,
                    'message_id': message.message_id,
                    'title': metadata.get('title', 'Unknown'),
                    'duration': metadata.get('duration', ''),
                    'uploaded': True
                }
                
        except TelegramError as e:
            logger.error(f"Telegram upload error: {e}")
            return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None
    
    def _determine_file_type(self, file_path: str, file_size: int) -> str:
        """Determine the best file type for upload based on size and extension"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext in ['.mp3', '.m4a', '.ogg', '.wav'] and file_size <= MAX_AUDIO_SIZE:
            return 'audio'
        elif ext in ['.mp4', '.avi', '.mkv', '.webm'] and file_size <= MAX_VIDEO_SIZE:
            return 'video'
        else:
            return 'document'
    
    def _build_caption(self, metadata: Dict[str, Any]) -> str:
        """Build formatted caption for Telegram message"""
        caption_parts = []
        
        # Query information
        if metadata.get('query'):
            caption_parts.append(f"🎵 <b>Query:</b> {metadata['query']}")
        
        # Title and artist
        if metadata.get('title'):
            caption_parts.append(f"🎬 <b>Title:</b> {metadata['title']}")
        
        # YouTube link
        if metadata.get('youtube_url'):
            caption_parts.append(f"🔗 <b>Link:</b> {metadata['youtube_url']}")
        
        # YouTube ID
        if metadata.get('youtube_id'):
            caption_parts.append(f"📌 <b>ID:</b> {metadata['youtube_id']}")
        
        # Duration
        if metadata.get('duration'):
            caption_parts.append(f"⏱ <b>Duration:</b> {metadata['duration']}")
        
        # File size
        if metadata.get('file_size'):
            size_mb = metadata['file_size'] / (1024 * 1024)
            caption_parts.append(f"📦 <b>Size:</b> {size_mb:.1f} MB")
        
        # Source
        if metadata.get('source'):
            caption_parts.append(f"📁 <b>Source:</b> {metadata['source']}")
        
        # API info
        caption_parts.append("📡 <b>Requested via:</b> MusicAPI")
        
        # Upload timestamp
        caption_parts.append(f"🕒 <b>Uploaded:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return '\n'.join(caption_parts)
    
    async def _cache_upload_result(self, query: str, message, file_info, file_type: str):
        """Cache the uploaded file result"""
        try:
            query_hash = hashlib.md5(query.lower().encode()).hexdigest()
            
            cache_entry = TelegramCache(
                query_hash=query_hash,
                original_query=query,
                title=getattr(file_info, 'title', query),
                duration=str(getattr(file_info, 'duration', 0)),
                file_id=file_info.file_id,
                file_unique_id=file_info.file_unique_id,
                file_type=file_type,
                telegram_message_id=message.message_id,
                access_count=1
            )
            
            db.session.add(cache_entry)
            db.session.commit()
            logger.info(f"Cached upload result for query: {query}")
            
        except Exception as e:
            logger.error(f"Error caching upload result: {e}")
            db.session.rollback()

# Global instance
telegram_storage = TelegramStorage()
