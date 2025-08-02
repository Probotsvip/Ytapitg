import logging
import os
import random
import re
import tempfile
from typing import Dict, Any, Optional
from urllib.parse import parse_qs, urlparse

import requests
import yt_dlp

from config import (
    YTAPII_API_URL, YTAPII_API_KEY, USER_AGENTS, PROXY_LIST,
    REQUEST_TIMEOUT, AUDIO_QUALITY, AUDIO_FORMAT, VIDEO_QUALITY, VIDEO_FORMAT
)
from utils import sanitize_filename, format_duration, extract_youtube_id

logger = logging.getLogger(__name__)

class YouTubeExtractorSync:
    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = REQUEST_TIMEOUT
        
    def extract_media(self, query: str, format_type: str = 'audio') -> Optional[Dict[str, Any]]:
        """Extract media using ytapii API with yt-dlp fallback"""
        
        # Try ytapii API first
        result = self._try_ytapii_api(query, format_type)
        if result:
            return result
            
        # Fallback to yt-dlp
        logger.info(f"Falling back to yt-dlp for query: {query}")
        return self._try_ytdlp(query, format_type)
    
    def _try_ytapii_api(self, query: str, format_type: str) -> Optional[Dict[str, Any]]:
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
            
            response = self.session.get(YTAPII_API_URL, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'success' and data.get('stream_url'):
                    return self._process_ytapii_response(data, query, format_type)
                else:
                    logger.warning(f"ytapii API returned no results for: {query}")
                    
        except Exception as e:
            logger.error(f"ytapii API error: {e}")
            
        return None
    
    def _process_ytapii_response(self, data: Dict[str, Any], query: str, format_type: str) -> Dict[str, Any]:
        """Process ytapii API response and download file"""
        try:
            stream_url = data['stream_url']
            title = data.get('title', 'Unknown Title')
            youtube_id = data.get('video_id', '')
            duration = data.get('duration', '')
            
            # Download the file
            response = self.session.get(stream_url, stream=True)
            response.raise_for_status()
            
            # Create temporary file
            file_extension = 'mp3' if format_type == 'audio' else 'mp4'
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=f'.{file_extension}',
                prefix=f'ytapii_{sanitize_filename(title)}_'
            )
            
            # Write content to file
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            
            temp_file.close()
            
            file_size = os.path.getsize(temp_file.name)
            
            return {
                'title': title,
                'youtube_id': youtube_id,
                'youtube_url': f'https://youtube.com/watch?v={youtube_id}' if youtube_id else '',
                'duration': duration,
                'file_path': temp_file.name,
                'file_size': file_size,
                'source': 'ytapii'
            }
            
        except Exception as e:
            logger.error(f"Error processing ytapii response: {e}")
            return None
    
    def _try_ytdlp(self, query: str, format_type: str) -> Optional[Dict[str, Any]]:
        """Extract using yt-dlp as fallback"""
        try:
            # Configure yt-dlp options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extractaudio': format_type == 'audio',
                'audioformat': AUDIO_FORMAT if format_type == 'audio' else None,
                'audioquality': AUDIO_QUALITY if format_type == 'audio' else None,
                'format': 'bestaudio' if format_type == 'audio' else f'best[height<={VIDEO_QUALITY[:-1]}]',
                'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
            }
            
            # If query looks like a URL, use it directly
            if self._is_youtube_url(query):
                search_query = query
            else:
                # Search YouTube for the query
                search_query = f"ytsearch1:{query}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info
                info = ydl.extract_info(search_query, download=False)
                
                if not info:
                    return None
                
                # Get the first entry if it's a search result
                if 'entries' in info and info['entries']:
                    video_info = info['entries'][0]
                else:
                    video_info = info
                
                if not video_info:
                    return None
                
                # Download the file
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=f'.{AUDIO_FORMAT if format_type == "audio" else VIDEO_FORMAT}',
                    prefix=f'ytdlp_{sanitize_filename(video_info.get("title", "unknown"))}_'
                )
                temp_file.close()
                
                ydl_opts['outtmpl'] = temp_file.name.replace(f'.{AUDIO_FORMAT if format_type == "audio" else VIDEO_FORMAT}', '.%(ext)s')
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_info['webpage_url']])
                
                # Find the downloaded file (yt-dlp might change the extension)
                base_name = temp_file.name.replace(f'.{AUDIO_FORMAT if format_type == "audio" else VIDEO_FORMAT}', '')
                actual_file = None
                
                for ext in [AUDIO_FORMAT, VIDEO_FORMAT, 'webm', 'm4a', 'mp4', 'mp3']:
                    potential_file = f"{base_name}.{ext}"
                    if os.path.exists(potential_file):
                        actual_file = potential_file
                        break
                
                if not actual_file or not os.path.exists(actual_file):
                    logger.error("Downloaded file not found")
                    return None
                
                file_size = os.path.getsize(actual_file)
                
                return {
                    'title': video_info.get('title', 'Unknown Title'),
                    'youtube_id': video_info.get('id', ''),
                    'youtube_url': video_info.get('webpage_url', ''),
                    'duration': format_duration(video_info.get('duration', 0)),
                    'file_path': actual_file,
                    'file_size': file_size,
                    'source': 'yt-dlp'
                }
                
        except Exception as e:
            logger.error(f"yt-dlp extraction error: {e}")
            return None
    
    def _is_youtube_url(self, url: str) -> bool:
        """Check if the given string is a YouTube URL"""
        youtube_patterns = [
            r'youtube\.com/watch\?v=',
            r'youtu\.be/',
            r'youtube\.com/embed/',
            r'youtube\.com/v/'
        ]
        
        return any(re.search(pattern, url) for pattern in youtube_patterns)

# Create global instance
youtube_extractor_sync = YouTubeExtractorSync()