# YouTube Media API Service

## Overview

This project is a YouTube Media API Service that provides a RESTful API for extracting audio and video content from YouTube. The service features intelligent caching through Telegram storage, rate limiting, API key management, and both direct extraction and fuzzy search capabilities. It's built as a Flask web application with a comprehensive admin panel for monitoring and managing API usage.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask-based REST API with SQLAlchemy ORM for database operations
- **Database**: SQLite default with PostgreSQL support via environment configuration
- **Rate Limiting**: Flask-Limiter with Redis backend support for distributed rate limiting
- **CORS**: Enabled for cross-origin requests to support web-based clients

### API Design Patterns
- **Authentication**: API key-based authentication with hierarchical key management (admin keys can create other keys)
- **Rate Limiting**: Tiered rate limiting with per-key daily quotas (100 requests/day default) and global rate limits (100/minute, 500/hour)
- **Versioning**: API versioning support with current version 2.0.0
- **Error Handling**: Structured JSON error responses with appropriate HTTP status codes

### Media Extraction Pipeline
- **Primary Source**: YTAPII external API service for YouTube content extraction
- **Fallback System**: yt-dlp library as backup when primary API fails
- **Format Support**: Audio (MP3) and video (MP4) extraction with configurable quality settings
- **File Size Limits**: 50MB for audio, 2GB for video/documents

### Caching and Storage Strategy
- **Telegram Integration**: Uses Telegram bot for media storage and retrieval
- **Query Matching**: Fuzzy search algorithm with similarity threshold (0.8) for finding cached content
- **Cache Management**: 30-day cache retention with 24-hour cleanup intervals
- **Query Sanitization**: Stop word removal and normalization for better cache hit rates

### Search and Matching System
- **Fuzzy Matching**: Uses difflib.SequenceMatcher for query similarity detection
- **Query Normalization**: Special character removal, case normalization, and stop word filtering
- **Hash-based Indexing**: MD5 hashing for consistent query identification

### Admin and Monitoring
- **Admin Panel**: Web-based interface for API key management and usage statistics
- **Usage Tracking**: Comprehensive logging of API requests, response status, and usage patterns
- **Key Management**: Hierarchical API key system with expiration dates and usage quotas

### Configuration Management
- **Environment-based**: All sensitive configuration via environment variables
- **Proxy Support**: User agent rotation and proxy list support for resilient requests
- **File Management**: Automatic directory creation and temporary file cleanup

## External Dependencies

### Third-party APIs
- **YTAPII API**: Primary YouTube extraction service (https://ytapii-b7ea33a82028.herokuapp.com/youtube)
- **yt-dlp**: Fallback YouTube extraction library

### Telegram Integration
- **Telegram Bot API**: For media storage and retrieval using bot token and channel ID
- **Storage Channel**: Dedicated Telegram channel for caching extracted media files

### Database Systems
- **SQLite**: Default database for development and simple deployments
- **PostgreSQL**: Production database option via DATABASE_URL environment variable
- **Redis**: Optional caching backend for distributed rate limiting

### External Libraries
- **Flask Ecosystem**: Flask-SQLAlchemy, Flask-CORS, Flask-Limiter for core functionality
- **HTTP Client**: httpx for async HTTP requests with timeout and retry logic
- **Proxy Support**: Configurable proxy rotation for request resilience

### Infrastructure Dependencies
- **File System**: Local storage for temporary downloads with automatic cleanup
- **Environment Variables**: Extensive configuration via environment variables for deployment flexibility
- **Logging**: Python logging framework with configurable levels