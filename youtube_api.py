import asyncio
import hashlib
import logging
import os
import random
import re
import tempfile
from typing import Dict, Any, Optional, List
from urllib.parse import parse_qs, urlparse

import httpx
import yt_dlp

from config import (
    YTAPII_API_URL, YTAPII_API_KEY, USER_AGENTS, PROXY_LIST,
    REQUEST_TIMEOUT, AUDIO_QUALITY, AUDIO_FORMAT, VIDEO_QUALITY, VIDEO_FORMAT
)
from utils import sanitize_filename, format_duration, extract_youtube_id

logger = logging.getLogger(__name__)

class YouTubeExtractor:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.aclose()
    
    async def extract_media(self, query: str, format_type: str = 'audio') -> Optional[Dict[str, Any]]:
        """Extract media using ytapii API with yt-dlp fallback"""
        
        # Try ytapii API first
        result = await self._try_ytapii_api(query, format_type)
        if result:
            return result
            
        # Fallback to yt-dlp
        logger.info(f"Falling back to yt-dlp for query: {query}")
        return await self._try_ytdlp(query, format_type)
    
    async def _try_ytapii_api(self, query: str, format_type: str) -> Optional[Dict[str, Any]]:
        """Try to extract using ytapii API"""
        try:
            params = {
                'query': query,
                'video': format_type == 'video',
                'api_key': YTAPII_API_KEY
            }
            
            headers = {
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            response = await self.session.get(YTAPII_API_URL, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'success' and data.get('stream_url'):
                    return await self._process_ytapii_response(data, query, format_type)
                else:
                    logger.warning(f"ytapii API returned no results for: {query}")
                    
        except Exception as e:
            logger.error(f"ytapii API error: {e}")
            
        return None
    
    async def _process_ytapii_response(self, data: Dict[str, Any], query: str, format_type: str) -> Dict[str, Any]:
        """Process ytapii API response and download file"""
        try:
            stream_url = data['stream_url']
            title = data.get('title', query)
            youtube_id = data.get('id', '')
            duration = data.get('duration', '')
            thumbnail_url = data.get('thumbnail', '')
            
            # Generate safe filename
            safe_title = sanitize_filename(title)
            ext = 'mp3' if format_type == 'audio' else 'mp4'
            filename = f"{safe_title}_{youtube_id}.{ext}"
            file_path = os.path.join(tempfile.gettempdir(), filename)
            
            # Download the stream
            async with self.session.stream('GET', stream_url) as response:
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                    
                    file_size = os.path.getsize(file_path)
                    
                    return {
                        'title': title,
                        'youtube_id': youtube_id,
                        'youtube_url': f"https://youtube.com/watch?v={youtube_id}",
                        'duration': duration,
                        'duration_seconds': self._parse_duration(duration),
                        'thumbnail_url': thumbnail_url,
                        'file_path': file_path,
                        'file_size': file_size,
                        'format_type': format_type,
                        'source': 'ytapii',
                        'query': query
                    }
                    
        except Exception as e:
            logger.error(f"Error processing ytapii response: {e}")
            
        return None
    
    async def _try_ytdlp(self, query: str, format_type: str) -> Optional[Dict[str, Any]]:
        """Extract using yt-dlp as fallback"""
        try:
            # Configure yt-dlp options
            ydl_opts = self._get_ytdlp_options(format_type)
            
            # Search for the video
            search_query = query
            if not self._is_youtube_url(query):
                search_query = f"ytsearch1:{query}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading first
                info = ydl.extract_info(search_query, download=False)
                
                if 'entries' in info and info['entries']:
                    video_info = info['entries'][0]
                else:
                    video_info = info
                
                if not video_info:
                    return None
                
                # Now download the file
                ydl_opts['outtmpl'] = self._get_output_template(video_info, format_type)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                    ydl_download.download([video_info['webpage_url']])
                
                # Get the downloaded file path
                file_path = self._get_downloaded_file_path(video_info, format_type)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    
                    return {
                        'title': video_info.get('title', query),
                        'youtube_id': video_info.get('id', ''),
                        'youtube_url': video_info.get('webpage_url', ''),
                        'duration': format_duration(video_info.get('duration', 0)),
                        'duration_seconds': video_info.get('duration', 0),
                        'thumbnail_url': video_info.get('thumbnail', ''),
                        'file_path': file_path,
                        'file_size': file_size,
                        'format_type': format_type,
                        'source': 'yt-dlp',
                        'query': query,
                        'uploader': video_info.get('uploader', ''),
                        'view_count': video_info.get('view_count', 0)
                    }
                    
        except Exception as e:
            logger.error(f"yt-dlp extraction error: {e}")
            
        return None
    
    def _get_ytdlp_options(self, format_type: str) -> Dict[str, Any]:
        """Get yt-dlp configuration options"""
        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractaudio': format_type == 'audio',
            'writeinfojson': False,
            'writedescription': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
        }
        
        if format_type == 'audio':
            base_opts['audioformat'] = AUDIO_FORMAT
            base_opts['audioquality'] = AUDIO_QUALITY
            base_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': AUDIO_FORMAT,
                'preferredquality': AUDIO_QUALITY,
            }]
        else:
            base_opts['format'] = f'best[height<={VIDEO_QUALITY[:-1]}]'
            base_opts['merge_output_format'] = VIDEO_FORMAT
        
        # Add proxy if available
        if PROXY_LIST:
            base_opts['proxy'] = random.choice(PROXY_LIST)
        
        return base_opts
    
    def _get_output_template(self, video_info: Dict[str, Any], format_type: str) -> str:
        """Generate output template for yt-dlp"""
        safe_title = sanitize_filename(video_info.get('title', 'unknown'))
        video_id = video_info.get('id', 'unknown')
        ext = AUDIO_FORMAT if format_type == 'audio' else VIDEO_FORMAT
        
        return os.path.join(
            tempfile.gettempdir(),
            f"{safe_title}_{video_id}.{ext}"
        )
    
    def _get_downloaded_file_path(self, video_info: Dict[str, Any], format_type: str) -> Optional[str]:
        """Get the path of the downloaded file"""
        safe_title = sanitize_filename(video_info.get('title', 'unknown'))
        video_id = video_info.get('id', 'unknown')
        ext = AUDIO_FORMAT if format_type == 'audio' else VIDEO_FORMAT
        
        file_path = os.path.join(
            tempfile.gettempdir(),
            f"{safe_title}_{video_id}.{ext}"
        )
        
        return file_path if os.path.exists(file_path) else None
    
    def _is_youtube_url(self, query: str) -> bool:
        """Check if query is a YouTube URL"""
        youtube_patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)',
            r'youtube\.com'
        ]
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in youtube_patterns)
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse duration string to seconds"""
        if not duration_str:
            return 0
            
        try:
            # Handle formats like "3:20", "1:23:45", etc.
            parts = duration_str.split(':')
            if len(parts) == 2:  # MM:SS
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:  # HH:MM:SS
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return int(duration_str)
        except (ValueError, IndexError):
            return 0

# Global instance
youtube_extractor = YouTubeExtractor()
