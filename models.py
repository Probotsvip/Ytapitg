import datetime
from app import db
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship

class ApiKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    valid_until = Column(DateTime, nullable=False)
    daily_limit = Column(Integer, default=100)
    reset_at = Column(DateTime, default=lambda: datetime.datetime.now() + datetime.timedelta(days=1))
    count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey('api_keys.id'), nullable=True)

    # Self-referential relationship
    created_keys = relationship("ApiKey", backref="creator", remote_side=[id])
    
    def is_expired(self):
        return datetime.datetime.now() > self.valid_until
    
    def remaining_requests(self):
        now = datetime.datetime.now()
        if now > self.reset_at:
            return self.daily_limit
        return max(0, self.daily_limit - self.count)

class ApiLog(db.Model):
    __tablename__ = 'api_logs'
    
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, ForeignKey('api_keys.id'), nullable=False)
    endpoint = Column(String(255), nullable=False)
    query = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    response_status = Column(Integer, default=200)
    
    # Relationship
    api_key = relationship("ApiKey", backref="logs")

class TelegramCache(db.Model):
    __tablename__ = 'telegram_cache'
    
    id = Column(Integer, primary_key=True)
    query_hash = Column(String(64), unique=True, nullable=False)
    original_query = Column(Text, nullable=False)
    youtube_id = Column(String(20), nullable=True)
    title = Column(Text, nullable=False)
    duration = Column(String(20), nullable=True)
    file_id = Column(String(255), nullable=False)
    file_unique_id = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)  # audio, video, document
    telegram_message_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    last_accessed = Column(DateTime, default=datetime.datetime.now)
    access_count = Column(Integer, default=0)

class DownloadHistory(db.Model):
    __tablename__ = 'download_history'
    
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, ForeignKey('api_keys.id'), nullable=False)
    query = Column(Text, nullable=False)
    youtube_url = Column(String(255), nullable=True)
    youtube_id = Column(String(20), nullable=True)
    title = Column(Text, nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    duration = Column(String(20), nullable=True)
    source = Column(String(50), nullable=False)  # ytapii, yt-dlp
    processing_time = Column(Integer, nullable=True)  # seconds
    telegram_uploaded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    # Relationship
    api_key = relationship("ApiKey", backref="downloads")
