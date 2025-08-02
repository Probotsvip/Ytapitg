import hashlib
import logging
import os
import time
import difflib
from datetime import datetime
from typing import Optional, Dict, Any, List

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
        
    def search_telegram_first(self, query: str) -> Optional[Dict[str, Any]]:
        """Search Telegram channel first before processing new downloads"""
        try:
            # First try database cache lookup
            cached_result = self._search_database_cache(query)
            if cached_result:
                logger.info(f"Found in database cache: {query}")
                return self._build_cached_response(cached_result)
            
            # If not in database, search Telegram channel directly
            telegram_result = self._search_telegram_messages(query)
            if telegram_result:
                logger.info(f"Found in Telegram channel: {query}")
                return telegram_result
            
            logger.info(f"Not found in Telegram storage: {query}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching Telegram: {e}")
            return None
    
    def _search_database_cache(self, query: str) -> Optional[TelegramCache]:
        """Search database cache for existing entries"""
        try:
            # Direct query hash match
            query_hash = hashlib.md5(query.lower().encode()).hexdigest()
            cached = TelegramCache.query.filter_by(query_hash=query_hash).first()
            if cached:
                return cached
            
            # YouTube ID match (11 characters)
            if len(query) == 11 and query.isalnum():
                cached = TelegramCache.query.filter_by(youtube_id=query).first()
                if cached:
                    return cached
            
            # URL-based YouTube ID extraction
            video_id = self._extract_video_id(query)
            if video_id:
                cached = TelegramCache.query.filter_by(youtube_id=video_id).first()
                if cached:
                    return cached
            
            # Fuzzy search in titles and queries
            all_entries = TelegramCache.query.all()
            for entry in all_entries:
                if self._calculate_similarity(query.lower(), entry.title.lower()) > 0.6:
                    logger.info(f"Found fuzzy match in title: {entry.title}")
                    return entry
                if self._calculate_similarity(query.lower(), entry.original_query.lower()) > 0.7:
                    logger.info(f"Found fuzzy match in query: {entry.original_query}")
                    return entry
            
            return None
            
        except Exception as e:
            logger.error(f"Database cache search error: {e}")
            return None
    
    def _search_telegram_messages(self, query: str) -> Optional[Dict[str, Any]]:
        """Search Telegram channel messages directly"""
        try:
            # Get chat history (recent messages)
            url = f"{self.base_url}/getUpdates"
            response = requests.get(url, params={'limit': 100}, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if not data.get('ok'):
                return None
            
            # Search through messages
            best_match = None
            best_score = 0
            
            for update in data.get('result', []):
                message = update.get('message', {})
                if not message:
                    continue
                
                # Check if from our channel
                chat = message.get('chat', {})
                if str(chat.get('id', '')) != str(self.channel_id):
                    continue
                
                caption = message.get('caption', '').lower()
                if not caption:
                    continue
                
                # Calculate match score
                score = self._calculate_telegram_match_score(query.lower(), caption)
                if score > best_score and score > 0.6:
                    best_score = score
                    best_match = message
            
            if best_match:
                return self._extract_telegram_file_info(best_match)
            
            return None
            
        except Exception as e:
            logger.error(f"Telegram message search error: {e}")
            return None
    
    def _calculate_telegram_match_score(self, query: str, caption: str) -> float:
        """Calculate match score between query and Telegram caption"""
        try:
            # Perfect substring match
            if query in caption:
                return 0.95
            
            # YouTube ID match (highest priority)
            if len(query) == 11 and query.isalnum() and query in caption:
                return 1.0
            
            # URL match
            video_id = self._extract_video_id(query)
            if video_id and video_id in caption:
                return 1.0
            
            # Word-based similarity
            query_words = set(query.split())
            caption_words = set(caption.split())
            
            if not query_words or not caption_words:
                return 0
            
            # Jaccard similarity
            intersection = query_words.intersection(caption_words)
            union = query_words.union(caption_words)
            jaccard = len(intersection) / len(union) if union else 0
            
            # Sequence similarity
            sequence = difflib.SequenceMatcher(None, query, caption).ratio()
            
            return max(jaccard * 0.8, sequence * 0.6)
            
        except:
            return 0
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        try:
            if 'youtube.com/watch?v=' in url:
                return url.split('v=')[1].split('&')[0]
            elif 'youtu.be/' in url:
                return url.split('youtu.be/')[1].split('?')[0]
            return None
        except:
            return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def _extract_telegram_file_info(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Extract file info from Telegram message and build response"""
        try:
            file_info = None
            file_type = None
            
            # Check for audio
            if 'audio' in message:
                file_info = message['audio']
                file_type = 'audio'
            # Check for document
            elif 'document' in message:
                file_info = message['document']
                file_type = 'document'
            # Check for video
            elif 'video' in message:
                file_info = message['video']
                file_type = 'video'
            
            if not file_info:
                return None
            
            # Get file path for stream URL
            file_path_info = self._get_telegram_file_path(file_info['file_id'])
            stream_url = None
            if file_path_info and file_path_info.get('file_path'):
                stream_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path_info['file_path']}"
            
            # Parse caption for metadata
            caption = message.get('caption', '')
            metadata = self._parse_caption_metadata(caption)
            
            return {
                'status': 'success',
                'cached': True,
                'source': 'telegram',
                'data': {
                    'title': metadata.get('title', file_info.get('title', 'Unknown Title')),
                    'file_id': file_info['file_id'],
                    'file_unique_id': file_info['file_unique_id'],
                    'file_type': file_type,
                    'file_size': file_info.get('file_size', 0),
                    'duration': metadata.get('duration', file_info.get('duration', '')),
                    'youtube_id': metadata.get('youtube_id', ''),
                    'youtube_url': metadata.get('youtube_url', ''),
                    'stream_url': stream_url,
                    'telegram_message_id': message['message_id'],
                    'ready_for_download': True,
                    'processing_time': 0.1  # Instant from cache
                }
            }
            
        except Exception as e:
            logger.error(f"Error extracting Telegram file info: {e}")
            return None
    
    def _get_telegram_file_path(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file path from Telegram for streaming"""
        try:
            url = f"{self.base_url}/getFile"
            response = requests.get(url, params={'file_id': file_id}, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return result['result']
            
            return None
        except:
            return None
    
    def _parse_caption_metadata(self, caption: str) -> Dict[str, Any]:
        """Parse metadata from Telegram caption"""
        metadata = {}
        
        lines = caption.split('\n')
        for line in lines:
            line = line.strip()
            
            if line.startswith('🎵'):
                metadata['title'] = line[2:].strip()
            elif line.startswith('📝 Query:'):
                metadata['query'] = line[9:].strip()
            elif line.startswith('🆔 ID:'):
                metadata['youtube_id'] = line[7:].strip()
            elif line.startswith('🔗') and 'youtube.com' in line:
                metadata['youtube_url'] = line[2:].strip()
            elif line.startswith('⏱️ Duration:'):
                metadata['duration'] = line[13:].strip()
            elif line.startswith('📺 Channel:'):
                metadata['channel'] = line[11:].strip()
        
        return metadata
    
    def _build_cached_response(self, cached: TelegramCache) -> Dict[str, Any]:
        """Build response from cached database entry"""
        # Get stream URL from Telegram
        stream_url = None
        try:
            file_path_info = self._get_telegram_file_path(str(cached.file_id))
            if file_path_info and file_path_info.get('file_path'):
                stream_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path_info['file_path']}"
        except Exception as e:
            logger.warning(f"Could not get Telegram stream URL: {e}")
        
        # Update access statistics
        cached.access_count = (cached.access_count or 0) + 1
        cached.last_accessed = datetime.utcnow()
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error updating access statistics: {e}")
            db.session.rollback()
        
        return {
            'status': 'success',
            'cached': True,
            'source': 'telegram',
            'data': {
                'title': cached.title,
                'file_id': cached.file_id,
                'file_unique_id': cached.file_unique_id,
                'file_type': cached.file_type,
                'duration': cached.duration,
                'youtube_id': cached.youtube_id,
                'youtube_url': f"https://youtube.com/watch?v={cached.youtube_id}" if cached.youtube_id and str(cached.youtube_id).strip() else '',
                'stream_url': stream_url,
                'telegram_message_id': cached.telegram_message_id,
                'access_count': cached.access_count,
                'ready_for_download': True,
                'processing_time': 0.05  # Instant from database
            }
        }
        
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
            
            # Prepare rich caption with all metadata
            caption = self._format_rich_caption(media_info)
            
            # Upload based on file type
            if file_type == 'audio':
                result = self._upload_audio(file_path, caption, media_info)
            elif file_type == 'video':
                result = self._upload_video(file_path, caption, media_info)
            else:
                result = self._upload_document(file_path, caption, media_info)
            
            if result:
                # Save to database cache for future searches
                self._save_to_cache(media_info, result, file_type)
                
                # Get stream URL
                file_path_info = self._get_telegram_file_path(result['file_id'])
                if file_path_info:
                    result['stream_url'] = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path_info['file_path']}"
                
            return result
            
        except Exception as e:
            logger.error(f"Error uploading to Telegram: {e}")
            return None
    
    def _format_rich_caption(self, media_info: Dict[str, Any]) -> str:
        """Format rich caption with all searchable metadata"""
        parts = []
        
        # Title
        title = media_info.get('title', 'Unknown Title')
        parts.append(f"🎵 {title}")
        
        # Original query (for search matching)
        query = media_info.get('original_query', '')
        if query:
            parts.append(f"📝 Query: {query}")
        
        # YouTube information
        youtube_id = media_info.get('youtube_id', '')
        youtube_url = media_info.get('youtube_url', '')
        if youtube_id:
            parts.append(f"🆔 ID: {youtube_id}")
            if youtube_url:
                parts.append(f"🔗 {youtube_url}")
            else:
                parts.append(f"🔗 https://youtube.com/watch?v={youtube_id}")
        
        # Channel name
        channel = media_info.get('channel', '')
        if channel:
            parts.append(f"📺 Channel: {channel}")
        
        # Duration
        duration = media_info.get('duration', '')
        if duration:
            parts.append(f"⏱️ Duration: {duration}")
        
        # Source info
        source = media_info.get('source', 'yt-dlp')
        parts.append(f"📡 Source: {source}")
        
        # Tags for categorization
        file_type = media_info.get('file_type', 'audio')
        if file_type == 'audio':
            parts.append("#ytmusic #audio")
        else:
            parts.append("#ytvideo #video")
        
        return '\n'.join(parts)[:1024]  # Telegram caption limit
    
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
                            'message_id': result['result']['message_id'],
                            'uploaded_to_telegram': True
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
                            'message_id': result['result']['message_id'],
                            'uploaded_to_telegram': True
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
                            'message_id': result['result']['message_id'],
                            'uploaded_to_telegram': True
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
            
            # Check if already exists
            existing = TelegramCache.query.filter_by(query_hash=query_hash).first()
            if existing:
                logger.info(f"Cache entry already exists for: {query}")
                return
            
            cache_entry = TelegramCache()
            cache_entry.query_hash = query_hash
            cache_entry.original_query = query
            cache_entry.youtube_id = media_info.get('youtube_id', '')
            cache_entry.title = media_info.get('title', 'Unknown Title')
            cache_entry.duration = media_info.get('duration', '')
            cache_entry.file_id = upload_result['file_id']
            cache_entry.file_unique_id = upload_result['file_unique_id']
            cache_entry.file_type = file_type
            cache_entry.telegram_message_id = upload_result['message_id']
            cache_entry.access_count = 0
            cache_entry.created_at = datetime.utcnow()
            cache_entry.last_accessed = datetime.utcnow()
            
            db.session.add(cache_entry)
            db.session.commit()
            
            logger.info(f"Saved to database cache: {media_info.get('title', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            db.session.rollback()

# Create global instance
telegram_storage_sync = TelegramStorageSync()