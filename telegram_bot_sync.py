import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any

import requests

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MAX_AUDIO_SIZE, 
    MAX_VIDEO_SIZE, MAX_DOCUMENT_SIZE
)
from models import TelegramCache, db
from utils import sanitize_filename, format_duration

logger = logging.getLogger(__name__)

class TelegramStorageSync:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.channel_id = TELEGRAM_CHANNEL_ID or ""
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        
    def upload_media(self, file_path: str, media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upload media file to Telegram channel"""
        if not self.base_url or not os.path.exists(file_path):
            logger.warning("Telegram not configured or file doesn't exist")
            return None
            
        try:
            file_size = os.path.getsize(file_path)
            file_type = self._determine_file_type(file_path, file_size)
            
            # Check file size limits
            if not self._check_file_size(file_size, file_type):
                logger.error(f"File size {file_size} exceeds limits for {file_type}")
                return None
            
            # Prepare caption
            caption = self._format_caption(media_info)
            
            # Upload based on file type
            if file_type == 'audio':
                result = self._upload_audio(file_path, caption, media_info)
            elif file_type == 'video':
                result = self._upload_video(file_path, caption, media_info)
            else:
                result = self._upload_document(file_path, caption, media_info)
            
            if result:
                # Save to cache database
                self._save_to_cache(media_info, result, file_type)
                
            return result
            
        except Exception as e:
            logger.error(f"Error uploading to Telegram: {e}")
            return None
    
    def _determine_file_type(self, file_path: str, file_size: int) -> str:
        """Determine the appropriate file type for Telegram upload"""
        extension = os.path.splitext(file_path)[1].lower()
        
        if extension in ['.mp3', '.m4a', '.wav', '.flac']:
            return 'audio'
        elif extension in ['.mp4', '.avi', '.mkv', '.webm'] and file_size <= MAX_VIDEO_SIZE:
            return 'video'
        else:
            return 'document'
    
    def _check_file_size(self, file_size: int, file_type: str) -> bool:
        """Check if file size is within Telegram limits"""
        limits = {
            'audio': MAX_AUDIO_SIZE,
            'video': MAX_VIDEO_SIZE,
            'document': MAX_DOCUMENT_SIZE
        }
        
        return file_size <= limits.get(file_type, MAX_DOCUMENT_SIZE)
    
    def _format_caption(self, media_info: Dict[str, Any]) -> str:
        """Format caption for Telegram message"""
        title = media_info.get('title', 'Unknown Title')
        duration = media_info.get('duration', '')
        source = media_info.get('source', 'unknown')
        youtube_url = media_info.get('youtube_url', '')
        
        caption = f"🎵 {title}"
        
        if duration:
            caption += f"\n⏱️ {duration}"
        
        if youtube_url:
            caption += f"\n🔗 {youtube_url}"
        
        caption += f"\n📡 Source: {source}"
        
        return caption[:1024]  # Telegram caption limit
    
    def _upload_audio(self, file_path: str, caption: str, media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upload audio file to Telegram"""
        try:
            url = f"{self.base_url}/sendAudio"
            
            with open(file_path, 'rb') as audio_file:
                files = {'audio': audio_file}
                data = {
                    'chat_id': self.channel_id,
                    'caption': caption,
                    'title': media_info.get('title', 'Unknown Title'),
                    'duration': self._parse_duration(media_info.get('duration', ''))
                }
                
                response = requests.post(url, files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        audio = result['result']['audio']
                        return {
                            'file_id': audio['file_id'],
                            'file_unique_id': audio['file_unique_id'],
                            'file_type': 'audio',
                            'message_id': result['result']['message_id']
                        }
                        
        except Exception as e:
            logger.error(f"Error uploading audio: {e}")
        
        return None
    
    def _upload_video(self, file_path: str, caption: str, media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upload video file to Telegram"""
        try:
            url = f"{self.base_url}/sendVideo"
            
            with open(file_path, 'rb') as video_file:
                files = {'video': video_file}
                data = {
                    'chat_id': self.channel_id,
                    'caption': caption,
                    'duration': self._parse_duration(media_info.get('duration', ''))
                }
                
                response = requests.post(url, files=files, data=data, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        video = result['result']['video']
                        return {
                            'file_id': video['file_id'],
                            'file_unique_id': video['file_unique_id'],
                            'file_type': 'video',
                            'message_id': result['result']['message_id']
                        }
                        
        except Exception as e:
            logger.error(f"Error uploading video: {e}")
        
        return None
    
    def _upload_document(self, file_path: str, caption: str, media_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Upload file as document to Telegram"""
        try:
            url = f"{self.base_url}/sendDocument"
            
            with open(file_path, 'rb') as document_file:
                files = {'document': document_file}
                data = {
                    'chat_id': self.channel_id,
                    'caption': caption
                }
                
                response = requests.post(url, files=files, data=data, timeout=120)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        document = result['result']['document']
                        return {
                            'file_id': document['file_id'],
                            'file_unique_id': document['file_unique_id'],
                            'file_type': 'document',
                            'message_id': result['result']['message_id']
                        }
                        
        except Exception as e:
            logger.error(f"Error uploading document: {e}")
        
        return None
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string to seconds"""
        if not duration_str:
            return 0
        
        try:
            # Handle formats like "3:45" or "1:23:45"
            parts = duration_str.split(':')
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return int(duration_str)
        except (ValueError, TypeError):
            return 0
    
    def _save_to_cache(self, media_info: Dict[str, Any], upload_result: Dict[str, Any], file_type: str):
        """Save uploaded media info to cache database"""
        try:
            query = media_info.get('original_query', media_info.get('title', ''))
            query_hash = hashlib.md5(query.lower().encode()).hexdigest()
            
            cache_entry = TelegramCache(
                query_hash=query_hash,
                original_query=query,
                youtube_id=media_info.get('youtube_id', ''),
                title=media_info.get('title', 'Unknown Title'),
                duration=media_info.get('duration', ''),
                file_id=upload_result['file_id'],
                file_unique_id=upload_result['file_unique_id'],
                file_type=file_type,
                telegram_message_id=upload_result['message_id']
            )
            
            db.session.add(cache_entry)
            db.session.commit()
            
            logger.info(f"Saved to cache: {media_info.get('title', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")

# Create global instance
telegram_storage_sync = TelegramStorageSync()