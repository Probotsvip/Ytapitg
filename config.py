import os
from typing import List

# API Configuration
API_VERSION = "2.0.0"
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 30
STREAM_CHUNK_SIZE = 1024 * 1024  # 1MB
RATE_LIMIT = "100 per minute"
API_RATE_LIMIT = "500 per hour"
CACHE_TIMEOUT = 60 * 60  # 1 hour

# Directory Configuration
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "")

# YouTube API Configuration
YTAPII_API_URL = "https://ytapii-b7ea33a82028.herokuapp.com/youtube"
YTAPII_API_KEY = os.environ.get("YTAPII_API_KEY", "jaydip")

# File Size Limits (in bytes)
MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50MB for audio
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2GB for video
MAX_DOCUMENT_SIZE = 2 * 1024 * 1024 * 1024  # 2GB for documents

# User Agents for rotation
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.48",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/112.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
]

# Proxy Configuration
PROXY_LIST = os.environ.get("PROXY_LIST", "").split(",") if os.environ.get("PROXY_LIST") else []

# Admin Configuration
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "admin_key_change_in_production")

# Cache Configuration
ENABLE_TELEGRAM_CACHE = True
CACHE_CLEANUP_INTERVAL = 24 * 60 * 60  # 24 hours
MAX_CACHE_AGE = 30 * 24 * 60 * 60  # 30 days

# Audio Quality Settings
AUDIO_QUALITY = "192k"  # 192 kbps
AUDIO_FORMAT = "mp3"
VIDEO_QUALITY = "720p"
VIDEO_FORMAT = "mp4"
