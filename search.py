import difflib
import hashlib
import logging
import re
from typing import List, Dict, Any, Optional

from models import TelegramCache

logger = logging.getLogger(__name__)

class QueryMatcher:
    def __init__(self):
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'song', 'music', 'video', 'audio', 'mp3', 'mp4'
        }
    
    def sanitize_query(self, query: str) -> str:
        """Sanitize and normalize query for better matching"""
        # Remove special characters and extra spaces
        query = re.sub(r'[^\w\s-]', ' ', query)
        query = re.sub(r'\s+', ' ', query)
        
        # Convert to lowercase and strip
        query = query.lower().strip()
        
        # Remove common stop words
        words = query.split()
        filtered_words = [word for word in words if word not in self.stop_words]
        
        return ' '.join(filtered_words) if filtered_words else query
    
    def generate_query_hash(self, query: str) -> str:
        """Generate consistent hash for query"""
        sanitized = self.sanitize_query(query)
        return hashlib.md5(sanitized.encode()).hexdigest()
    
    def find_similar_queries(self, query: str, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """Find similar cached queries using fuzzy matching"""
        sanitized_query = self.sanitize_query(query)
        
        # Get all cached queries
        cached_results = TelegramCache.query.all()
        similar_results = []
        
        for cache_entry in cached_results:
            sanitized_cached = self.sanitize_query(cache_entry.original_query)
            
            # Calculate similarity
            similarity = difflib.SequenceMatcher(None, sanitized_query, sanitized_cached).ratio()
            
            if similarity >= threshold:
                similar_results.append({
                    'cache_entry': cache_entry,
                    'similarity': similarity,
                    'original_query': cache_entry.original_query
                })
        
        # Sort by similarity (highest first)
        similar_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return similar_results
    
    def extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query"""
        sanitized = self.sanitize_query(query)
        words = sanitized.split()
        
        # Filter out very short words and stop words
        keywords = [word for word in words if len(word) > 2 and word not in self.stop_words]
        
        return keywords
    
    def match_by_keywords(self, query: str, min_matches: int = 2) -> List[Dict[str, Any]]:
        """Match queries based on keyword overlap"""
        keywords = self.extract_keywords(query)
        
        if len(keywords) < min_matches:
            return []
        
        cached_results = TelegramCache.query.all()
        keyword_matches = []
        
        for cache_entry in cached_results:
            cached_keywords = self.extract_keywords(cache_entry.original_query)
            
            # Count matching keywords
            matches = set(keywords) & set(cached_keywords)
            
            if len(matches) >= min_matches:
                match_ratio = len(matches) / len(keywords)
                keyword_matches.append({
                    'cache_entry': cache_entry,
                    'match_ratio': match_ratio,
                    'matched_keywords': list(matches),
                    'original_query': cache_entry.original_query
                })
        
        # Sort by match ratio (highest first)
        keyword_matches.sort(key=lambda x: x['match_ratio'], reverse=True)
        
        return keyword_matches
    
    def match_by_title(self, title: str, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Match by title similarity"""
        sanitized_title = self.sanitize_query(title)
        
        cached_results = TelegramCache.query.all()
        title_matches = []
        
        for cache_entry in cached_results:
            sanitized_cached_title = self.sanitize_query(cache_entry.title)
            
            # Calculate title similarity
            similarity = difflib.SequenceMatcher(None, sanitized_title, sanitized_cached_title).ratio()
            
            if similarity >= threshold:
                title_matches.append({
                    'cache_entry': cache_entry,
                    'similarity': similarity,
                    'cached_title': cache_entry.title
                })
        
        # Sort by similarity
        title_matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        return title_matches
    
    def comprehensive_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Perform comprehensive search using multiple matching strategies"""
        
        # 1. Exact hash match (fastest)
        query_hash = self.generate_query_hash(query)
        exact_match = TelegramCache.query.filter_by(query_hash=query_hash).first()
        
        if exact_match:
            return {
                'cache_entry': exact_match,
                'match_type': 'exact',
                'confidence': 1.0
            }
        
        # 2. High similarity match
        similar_queries = self.find_similar_queries(query, threshold=0.9)
        if similar_queries:
            return {
                'cache_entry': similar_queries[0]['cache_entry'],
                'match_type': 'high_similarity',
                'confidence': similar_queries[0]['similarity']
            }
        
        # 3. Keyword-based match
        keyword_matches = self.match_by_keywords(query, min_matches=2)
        if keyword_matches:
            return {
                'cache_entry': keyword_matches[0]['cache_entry'],
                'match_type': 'keyword',
                'confidence': keyword_matches[0]['match_ratio']
            }
        
        # 4. Lower similarity match as last resort
        similar_queries = self.find_similar_queries(query, threshold=0.7)
        if similar_queries:
            return {
                'cache_entry': similar_queries[0]['cache_entry'],
                'match_type': 'low_similarity',
                'confidence': similar_queries[0]['similarity']
            }
        
        return None

# Global instance
query_matcher = QueryMatcher()
