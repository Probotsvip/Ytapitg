import os
import re
import logging
import hashlib
import tempfile
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    # Remove or replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'\s+', '_', filename)
    filename = filename.strip('._')
    
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename or 'unknown'

def format_duration(seconds: int) -> str:
    """Format duration from seconds to HH:MM:SS or MM:SS"""
    if not seconds or seconds <= 0:
        return "0:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL"""
    if not url:
        return None
    
    # Regular YouTube URL patterns
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # If it's already a video ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    return None

def generate_api_key() -> str:
    """Generate a secure API key"""
    return hashlib.sha256(os.urandom(32)).hexdigest()

def validate_query(query: str) -> bool:
    """Validate if query is acceptable"""
    if not query or len(query.strip()) < 2:
        return False
    
    # Check for potentially harmful content
    harmful_patterns = [
        r'<script',
        r'javascript:',
        r'data:',
        r'vbscript:',
    ]
    
    query_lower = query.lower()
    return not any(re.search(pattern, query_lower) for pattern in harmful_patterns)

def cleanup_temp_file(file_path: str):
    """Safely cleanup temporary file"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

def calculate_file_hash(file_path: str) -> Optional[str]:
    """Calculate MD5 hash of file"""
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating file hash: {e}")
        return None

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size_float = float(size_bytes)
    while size_float >= 1024 and i < len(size_names) - 1:
        size_float /= 1024.0
        i += 1
    
    return f"{size_float:.1f} {size_names[i]}"

def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def extract_artist_from_title(title: str) -> str:
    """Extract artist name from title using common patterns"""
    # Common patterns for artist extraction
    patterns = [
        r'(.+?)\s*-\s*(.+)',  # Artist - Song
        r'(.+?)\s*–\s*(.+)',  # Artist – Song (em dash)
        r'(.+?)\s*by\s*(.+)',  # Song by Artist
        r'(.+?)\s*ft\.?\s*(.+)',  # Artist ft. Artist
        r'(.+?)\s*feat\.?\s*(.+)',  # Artist feat. Artist
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return "Unknown Artist"

def create_temp_directory() -> str:
    """Create a temporary directory for downloads"""
    temp_dir = os.path.join(tempfile.gettempdir(), "youtube_api_downloads")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def log_api_usage(api_key_id: int, endpoint: str, query: str, ip_address: str, status: int = 200):
    """Log API usage for analytics"""
    try:
        from models import ApiLog, db
        
        log_entry = ApiLog(
            api_key_id=api_key_id,
            endpoint=endpoint,
            query=query,
            ip_address=ip_address,
            response_status=status
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error logging API usage: {e}")
