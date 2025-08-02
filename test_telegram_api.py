#!/usr/bin/env python3

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

def test_telegram_config():
    """Test if Telegram bot token and channel ID are working"""
    print("🔧 Testing Telegram Configuration...")
    print(f"Bot Token: {TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"Channel ID: {TELEGRAM_CHANNEL_ID}")
    
    # Test bot info
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    response = requests.get(url)
    
    if response.status_code == 200:
        bot_info = response.json()
        if bot_info.get('ok'):
            print(f"✅ Bot Info: {bot_info['result']['username']}")
        else:
            print(f"❌ Bot Error: {bot_info}")
    else:
        print(f"❌ HTTP Error: {response.status_code}")
    
    # Test getting updates
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    response = requests.get(url, params={'limit': 5})
    
    if response.status_code == 200:
        updates = response.json()
        if updates.get('ok'):
            print(f"✅ Recent Updates: {len(updates.get('result', []))} messages")
            
            # Check for messages from our channel
            for update in updates.get('result', []):
                message = update.get('message', {})
                chat = message.get('chat', {})
                if str(chat.get('id', '')) == str(TELEGRAM_CHANNEL_ID):
                    print(f"✅ Found message from our channel: {chat.get('title', 'Unknown')}")
                    print(f"   Message: {message.get('caption', 'No caption')[:50]}...")
        else:
            print(f"❌ Updates Error: {updates}")
    else:
        print(f"❌ Updates HTTP Error: {response.status_code}")

if __name__ == "__main__":
    test_telegram_config()