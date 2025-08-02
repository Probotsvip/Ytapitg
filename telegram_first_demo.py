#!/usr/bin/env python3

import requests
import json

def demo_telegram_first_api():
    """Demonstrate the Telegram-first YouTube API"""
    
    base_url = "http://localhost:5000/api/v1/extract"
    api_key = "demo_api_key_123"
    
    print("🎵 YouTube Audio API - Telegram-First Demo")
    print("=" * 50)
    
    # Test different query types
    test_queries = [
        "295 sidhu moosewala",
        "bollywood romantic song", 
        "LrAtBtQnvCE",  # YouTube ID
        "https://youtube.com/watch?v=n_FCrCQ6-bA",  # Full URL
        "simple song"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. Testing: '{query}'")
        print("-" * 30)
        
        # First request - should download and store to Telegram
        response = requests.get(base_url, params={
            'query': query,
            'format': 'audio', 
            'api_key': api_key
        }, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data['status']}")
            print(f"Cached: {data.get('cached', False)}")
            print(f"Source: {data.get('source', 'unknown')}")
            
            if 'data' in data:
                print(f"Title: {data['data'].get('title', 'Unknown')}")
                print(f"Duration: {data['data'].get('duration', 'Unknown')}")
                print(f"Processing: {data['data'].get('processing_time', 0):.2f}s")
                
                if data['data'].get('stream_url'):
                    print(f"Stream URL: Available")
                if data['data'].get('uploaded_to_telegram'):
                    print(f"Telegram: Uploaded ✅")
        else:
            print(f"Error: {response.status_code}")
        
        # Brief pause between tests
        import time
        time.sleep(2)

if __name__ == "__main__":
    demo_telegram_first_api()