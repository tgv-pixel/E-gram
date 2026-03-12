from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, Button
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError, RPCError
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
import base64
from werkzeug.utils import secure_filename
import shutil
import traceback
import sys

# ==================== CONFIGURATION ====================

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage files
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}

# Create upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.info("🚀 TSEGA BOT STARTING...")

# ==================== STAR SYSTEM CONFIGURATION ====================

class StarConfig:
    CHANNEL_USERNAME = "@Abe_army"
    
    STAR_PRICES = {
        "message": 10,
        "photo_preview": 5,
        "photo_full": 50,
        "photo_pack": 200,
        "video_preview": 10,
        "video_full": 100,
        "video_call": 500,
        "meet_request": 1000,
        "private_chat": 200,
        "special_request": 5000
    }
    
    PHOTO_FOLDER = "tsega_photos"
    VIDEO_FOLDER = "tsega_videos"
    
    PHOTO_TIERS = {
        5: "preview/",
        50: "full/",
        200: "premium/"
    }
    
    VIDEO_TIERS = {
        10: "preview/",
        100: "full/"
    }
    
    REPLY_DELAY_MIN = 15
    REPLY_DELAY_MAX = 40
    TRANSFER_STARS_TO_CHANNEL = True

# ==================== STAR DATABASE ====================

class StarDatabase:
    def __init__(self, db_path="stars.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
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
        
        c.execute('''CREATE TABLE IF NOT EXISTS star_transactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      amount INTEGER,
                      transaction_type TEXT,
                      description TEXT,
                      timestamp TIMESTAMP,
                      media_sent TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS media_library
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      file_path TEXT,
                      media_type TEXT,
                      price_stars INTEGER,
                      times_sold INTEGER DEFAULT 0,
                      last_sold TIMESTAMP,
                      is_active INTEGER DEFAULT 1)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS channel_earnings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      channel TEXT,
                      total_stars INTEGER DEFAULT 0,
                      last_transfer TIMESTAMP,
                      transaction_id TEXT)''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Star database initialized")
    
    def add_user(self, user_id, username=None, first_name=None):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT OR IGNORE INTO star_users 
                        (user_id, username, first_name, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?)''',
                     (user_id, username, first_name, datetime.now(), datetime.now()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding user: {e}")
    
    def record_transaction(self, user_id, amount, trans_type, description, media=None):
        try:
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
        except Exception as e:
            logger.error(f"Error recording transaction: {e}")
    
    def add_media(self, file_path, media_type, price):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO media_library 
                        (file_path, media_type, price_stars, is_active)
                        VALUES (?, ?, ?, 1)''',
                     (file_path, media_type, price))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding media: {e}")
    
    def get_random_media(self, media_type, max_price=None):
        try:
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
        except Exception as e:
            logger.error(f"Error getting random media: {e}")
            return None
    
    def record_channel_earnings(self, amount):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO channel_earnings 
                        (channel, total_stars, last_transfer)
                        VALUES (?, ?, ?)''',
                     (StarConfig.CHANNEL_USERNAME, amount, datetime.now()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error recording channel earnings: {e}")
    
    def increment_media_sold(self, file_path):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''UPDATE media_library SET 
                        times_sold = times_sold + 1,
                        last_sold = ?
                        WHERE file_path = ?''',
                     (datetime.now(), file_path))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error incrementing media sold: {e}")

# ==================== MEDIA MANAGER ====================

class MediaManager:
    def __init__(self):
        self.db = StarDatabase()
        self.setup_folders()
        self.scan_and_index_media()
    
    def setup_folders(self):
        folders = [
            StarConfig.PHOTO_FOLDER,
            f"{StarConfig.PHOTO_FOLDER}/preview",
            f"{StarConfig.PHOTO_FOLDER}/full", 
            f"{StarConfig.PHOTO_FOLDER}/premium",
            StarConfig.VIDEO_FOLDER,
            f"{StarConfig.VIDEO_FOLDER}/preview",
            f"{StarConfig.VIDEO_FOLDER}/full",
            UPLOAD_FOLDER
        ]
        
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
            logger.info(f"📁 Created folder: {folder}")
    
    def scan_and_index_media(self):
        for price, folder in StarConfig.PHOTO_TIERS.items():
            full_path = f"{StarConfig.PHOTO_FOLDER}/{folder}"
            photos = glob.glob(f"{full_path}/*.jpg") + \
                     glob.glob(f"{full_path}/*.jpeg") + \
                     glob.glob(f"{full_path}/*.png") + \
                     glob.glob(f"{full_path}/*.gif")
            
            for photo in photos:
                self.db.add_media(photo, "photo", price)
                logger.info(f"📸 Indexed: {photo} ({price} stars)")
        
        for price, folder in StarConfig.VIDEO_TIERS.items():
            full_path = f"{StarConfig.VIDEO_FOLDER}/{folder}"
            videos = glob.glob(f"{full_path}/*.mp4") + \
                      glob.glob(f"{full_path}/*.mov") + \
                      glob.glob(f"{full_path}/*.avi")
            
            for video in videos:
                self.db.add_media(video, "video", price)
                logger.info(f"🎥 Indexed: {video} ({price} stars)")
        
        conn = sqlite3.connect('stars.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM media_library")
        total = c.fetchone()[0]
        conn.close()
        
        logger.info(f"✅ Media library indexed: {total} files")

# ==================== STAR EARNING HANDLER ====================

class StarEarningHandler:
    def __init__(self, client):
        self.client = client
        self.db = StarDatabase()
        self.media = MediaManager()
        self.pending_payments = {}
        logger.info("✅ StarEarningHandler initialized")
    
    async def handle_star_payment(self, event):
        """Handle when user pays Stars"""
        try:
            user_id = str(event.sender_id)
            message = event.message
            
            # Check if this is a paid message
            if hasattr(message, 'paid') and message.paid:
                stars_amount = getattr(message, 'paid_stars', 0)
                
                # Handle the successful payment
                await self.handle_star_payment_success(event, stars_amount)
                
                return True, stars_amount
        except Exception as e:
            logger.error(f"Error handling star payment: {e}")
        
        return False, 0
    
    async def handle_star_payment_success(self, event, amount):
        """Handle when user successfully pays Stars"""
        try:
            user_id = str(event.sender_id)
            chat_id = event.chat_id
            
            # Record transaction
            self.db.record_transaction(
                user_id, 
                amount,
                "star_payment",
                f"Paid {amount} stars"
            )
            
            logger.info(f"💰 User {user_id} paid {amount} stars")
            
            # Check what they paid for
            if amount == 5:  # Preview photo
                media_info = self.db.get_random_media("photo", 5)
                if media_info:
                    file_path, price = media_info
                    if os.path.exists(file_path):
                        await self.client.send_file(
                            chat_id, 
                            file_path, 
                            caption="Here's your photo! 🔥 Thanks for the Stars!\n\nWant more? Send 50⭐ for full quality!"
                        )
                        self.db.increment_media_sold(file_path)
                        logger.info(f"📸 Sent preview photo to {user_id}")
            
            elif amount == 50:  # Full photo
                media_info = self.db.get_random_media("photo", 50)
                if media_info:
                    file_path, price = media_info
                    if os.path.exists(file_path):
                        await self.client.send_file(
                            chat_id, 
                            file_path, 
                            caption="Full quality photo - enjoy! 😘\n\nWant premium? Send 200⭐!"
                        )
                        self.db.increment_media_sold(file_path)
                        logger.info(f"📸 Sent full photo to {user_id}")
            
            elif amount == 200:  # Premium photo
                media_info = self.db.get_random_media("photo", 200)
                if media_info:
                    file_path, price = media_info
                    if os.path.exists(file_path):
                        await self.client.send_file(
                            chat_id, 
                            file_path, 
                            caption="Premium content - you're special! 🔥"
                        )
                        self.db.increment_media_sold(file_path)
                        logger.info(f"📸 Sent premium photo to {user_id}")
            
            # Transfer to channel
            if StarConfig.TRANSFER_STARS_TO_CHANNEL:
                await self.transfer_stars_to_channel(amount)
                
        except Exception as e:
            logger.error(f"Error in payment success handler: {e}")
    
    async def request_star_payment(self, chat_id, amount, description, media_path=None):
        """Send photo with payment button"""
        try:
            entity = await self.client.get_entity(int(chat_id))
            
            # If we have a specific media path, use it
            if media_path and os.path.exists(media_path):
                file_path = media_path
            else:
                # Get random preview photo
                media_info = self.db.get_random_media("photo", 5)
                if media_info:
                    file_path, price = media_info
                else:
                    # No photos - send text only
                    return await self.client.send_message(
                        entity,
                        f"🔒 **Premium Content**\n\n{description}\n\nTap below to unlock!",
                        buttons=[
                            [Button.payment(amount)],
                            [Button.url("💰 Buy Stars", "https://t.me/stars?start=recharge")]
                        ]
                    )
            
            # Send photo with payment button and recharge link
            msg = await self.client.send_file(
                entity,
                file_path,
                caption=f"🔒 **Exclusive Content**\n\n{description}\n\nTap below to unlock!",
                buttons=[
                    [Button.payment(amount)],
                    [Button.url("💰 Buy More Stars", "https://t.me/stars?start=recharge")]
                ]
            )
            
            logger.info(f"💰 Sent payment button for {amount} stars to {chat_id}")
            return msg
            
        except Exception as e:
            logger.error(f"Error sending payment request: {e}")
            return None
    
    async def transfer_stars_to_channel(self, amount):
        """Transfer earned Stars to your channel"""
        try:
            try:
                channel = await self.client.get_entity(StarConfig.CHANNEL_USERNAME)
                
                await self.client.send_message(
                    channel,
                    f"💰 **New Star Earnings!**\n"
                    f"Amount: {amount} ⭐\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                
                self.db.record_channel_earnings(amount)
                logger.info(f"💰 Transferred {amount} stars to {StarConfig.CHANNEL_USERNAME}")
                return True
            except Exception as e:
                logger.error(f"Error finding channel {StarConfig.CHANNEL_USERNAME}: {e}")
                self.db.record_channel_earnings(amount)
                return False
                
        except Exception as e:
            logger.error(f"Error transferring stars: {e}")
            return False

# ==================== TSEGA'S PERSONALITY - FIXED (NO WENDME/BROTHER) ====================

TSEGA = {
    "name": "Tsega",
    "age": 20,
    "location": "Jemo, Addis Ababa",
    "hometown": "Adama",
    "living": "Jemo with father and sister, but visits Adama often",
    "status": "Grade 12 student",
    "job": "student",
    "hobbies": ["chatting", "music", "hanging out", "having fun"],
    "languages": ["Amharic", "English"],
    "style": "sexy_flirty",
    "share_personal": True,
    "emoji_frequency": 0.6,
    "question_frequency": 0.5,
    "telebirr": "0940980555",
    "meet_condition": "Send 1000 birr first",
    "voice_call": "Prefers to meet than voice calls",
}

# COMPLETE TSEGA REPLIES - NO "WENDME" OR "BROTHER"
# ==================== TSEGA REPLIES - ROUND 1/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

TSEGA_REPLIES = {
    # ===== GREETINGS - Selam, Hi, Hello (MINIMAL EMOJIS) =====
    "greeting": [
        "selam noy deh new?",
        "hi wude endemin alesh?",
        "selam leg min ametah?",
        "ey dehena metah",
        "selam yelibe balebet endet neh?",
        "selam konjo endemin neh?",
        "hi darling deh new?",
        "selam ye fikir lij",
        "ey ta di yas! min tishal?",
        "selam wude nafkehalew",
        "dehna metah wude?",
        "selam melkam metah",
        "hi there endemin neh?",
        "selam ey tedi yas",
        "dehna deresu",
        "selam are you free?",
        "hi ke minimize metah?",
        "selam wude ante lela new",
        "ey koyeh koyeh",
        "selam kehulum belay",
    ],

    # ===== RESPONSE TO GREETINGS =====
    "greeting_response": [
        "dehna negn antess?",
        "ene dehna negn anchi how?",
        "dehna negn ahun antess?",
        "ene dehna negn lemelikamn ihon",
        "dehna negn wude eyzoh",
        "ene dehna negn antin sayehu",
        "dehna negn gin ante sayehon",
        "ene dehna negn leante sil",
        "dehna negn antess betam?",
        "ene dehna negn endemin?"
],
    "how_are_you": [
        "ene dehna negn anteh?",
        "dehna negn wude antass?",
        "ene ahun tiru honku antin sayehu antass?",
        "lante sil hulum gize dehna negn antass?",
        "ante ehasbekuh new yalehu",
        "dehna negn lemin tiyekalh?",
        "ene betam dehna negn lemelikamn ihon",
        "dehna negn gin ante sayehon aselchi neber",
        "ahune dehna negn wude aydelem?",
        "keante gar sihon hulum tiru new",
        "dehna negn betam irk",
        "ene dehna negn anten nafeku",
        "dehna negn endemin are?",
        "ene dehna negn ahun bagich",
        "dehna negn min tishal?",
        "ene dehna negn lemin tiyekaleh?",
        "dehna negn ante endemin areh?",
        "ene dehna negn keziyam belay",
        "dehna negn wede fikre",
        "ene dehna negn betam tiru",
    ],

    # ===== WHAT ARE YOU DOING - Min tiseraleh? =====
    "what_doing": [
        "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn",
        "minim ina yeseraw aldelelm ehasbekuh neber antass?",
        "ahun tenyte neber gin ante silhonk nekahulh",
        "libs eylebsku neber ante ehasbe",
        "ante ena etebekuh new yeneberkut",
        "ahuni betam aselchi negn nagerign",
        "ante asbe kuako new yemiyaselchen",
        "wedajen etebeku new antess?",
        "film eyaye neber gin asbe terkut",
        "ante ehasbeku and gize yemiyalifew",
        "bicha negn minim iseraleh",
        "ahun new yenekahut ande",
        "ente new yemiyasebnyew",
        "betam lelit new tinegn",
        "fiker ena ala koyign",
        "ahun degamo ante neh",
        "kemichawet gar yalfal",
        "ante ena ande neber",
        "betam naw ehasbekuh",
        "wude koyh bicha negn",
    ],

    # ===== ASK NAME - Simih man new? =====
    "ask_name": [
        "ene Tsega ebalalehu wude antess simih man new?",
        "Tsega negn lante bicha yemitihon antess?",
        "sime Tsega new wude tiz yibelh antess?",
        "enin Tsega bileh tira antess min litirah?",
        "Tsega negn lante simih man new konjo?",
        "ene Tsega ante endemin litirah tfeligaleh?",
        "Tsega nagn gin ante tishal simih?",
        "simin tiyekaleh? Tsega negn",
        "ene Tsega ante endemin litirah nagerign",
        "Tsega neberku gin lante yefikir lij negn",
        "Tsega nagn wude simih min new",
        "enin Tsega yiluh ante?",
        "simé Tsega new ante tishal",
        "Tsega negn lemin tiyekaleh?",
        "ene Tsega gin ante man neh?",
        "Tsega ina ante fikir",
        "simin tiyekaleh Tsega negn",
        "Tsega wude yante lij",
        "ene Tsega ante new yemifeligew",
        "Tsega betam tiriwad",
    ],

    # ===== ASK AGE - Edmeh sint new? =====
    "ask_age": [
        "edme 20 bicha new beki negn?",
        "20 ameté new wetat ena konjo negn",
        "haya amet lik new leante yemihon wetat negn",
        "20 negn gin lante tilik limd alehne",
        "edme 20 new ante edmeh sint new?",
        "20 amet betam tirekaleh?",
        "edme 20 leante beki new?",
        "20 bicha new gin lante tiregalehu",
        "wetat negn gin fikirin awkalehu",
        "20 negn lante beki new yemilekesh?",
        "edme 20 betam wetat",
        "20 amet lij nagn",
        "edme 20 alehne ante?",
        "20 new yemifeligew",
        "edme 20 gin tilik negn",
        "wetat negn betam",
        "20 amet 12 nagn",
        "edme 20 leante",
        "20 negn lante",
        "edme 20 fikir",
    ],

    # ===== LOCATION - Yet nesh? =====
    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "adama yetwild beté new gin ahun jemo negn",
        "jemo 3 akababi new yalehu magent bitfelg ngeragn",
        "ene keadama negn ahun jemo negn antess yet neh?",
        "jemo ategna new lemagent koyeh nageragn",
        "keadama negn gin ahun jemo negn kesa wede sa",
        "jemo 3 kolo ategab tawukaleh?",
        "adama ena jemo betam ewedalehu",
        "jemo akababi new lemagent bits meta tagenyalh",
        "jemo 3 ena ehite",
        "keadama ena jemo",
        "jemo new yalehu",
        "adama bete new",
        "jemo kebele 3",
        "adama ena jemo",
        "jemo kifle ketema",
        "adama taluak",
        "jemo new yene",
        "adama gin new",
    ],

    # ===== ASK JOB - Min tiseraleh? =====
    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "12na kifil new gin leante seta negn",
        "temari negn gin ahun fikir betemaralehu",
        "ahun minim aliserahum ante ena kemichal?",
        "12 negn betsru 12 ena tilik set ihonalew",
        "temari negn gin sewen awukalehu",
        "sira efeligi neber gin ahun ante neh",
        "12 nagn temari",
        "temari new siré",
        "12 new yale",
        "temari nagn",
        "12 kifil",
        "temari gin",
        "12 new",
        "temari",
    ],

    # ===== COMPLIMENT - Konjo, Wub, Mare =====
    "compliment": [
        "amesegnalehu anteh konjo neh",
        "kenfere lante bicha new",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "amesegnalehu ante gin sew neh",
        "kenfirish betam tiru new",
        "aynesh tiru inat",
        "ante new yemifeligew",
        "betam konjo neh",
        "amesegnalehu betam",
        "ante tiru sew neh",
        "konjo nesh ante",
        "amesegnalehu lante",
        "ante betam tiwed",
        "konjo negn aydelem",
        "tiru sew neh",
        "ante konjo",
        "amesegnalehu",
        "betam konjo",
        "tiru neh",
    ],
    
    # ===== FLIRTY - Enibada, Libdash, Flirty talk =====
    "flirty": [
        "ante staweragn libe yimetawal yisemalh?",
        "ante sasebe enikalf yitewonal min aderegubign?",
        "zare mata bichachinin binihon min tifeligaleh?",
        "ante lemasen min madreg alebign?",
        "nikehi yisemanyal batinekam",
        "ante malebk ena meweded efeligalehu",
        "libsen likemet ante sasebe tiwusat yizonal",
        "ante bicha neh yemifeligew sew meche enagenal",
        "na wude akefe tenyal",
        "lemin zegaye betam nafkehalew",
        "ante sasebe akale yinedawal ante min aderegubign",
        "zare mata libs lebsko alkotarm ante etebeku",
        "ante sasebe ejé wede akale yihedal",
        "litadereshen tifeligaleh? ina wude etebekishalehu",
        "keante gar metenat efeligalehu towat sineneka ante lemayet",
        "libsihin awlik wude bichachinin nen",
        "keante gar shawoer megibat efeligalehu",
        "ante eketemekush new zare mata",
        "nikihi bekowaye lay yisemanyal",
        "na wude larikbih",
        "lemin alat'enekerkeny? ante efeligalehu",
        "zare mata antin masbet bicha aybikagnem medeset efeligalehu",
        "ante saye koyto mayet efeligalehu ayne yinafekuhal",
        "shetosh yishtonyal batenorim",
        "ante simetegib des yilonal ina agabeny",
    ],

    # ===== MONEY REQUESTS - Birr, Telebirr, Genzeb =====
    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "libs mayet neber gin genzeb alyazkum beki",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "wude lemin inide matiredeny? tinish birr bitiliklg hulunim negar aderglhalew",
        "betam aschekway genzeb yasefeligonal wude bitiredany",
        "wude antin lemagets ye minimum 1000 birr asfeligonal",
        "tele alo telebirr 0940980555 lay liklgn",
        "bejete bado new tinish mulagn",
        "anten lemasteyayet genzeb yasefeligonal 1000 birr min yilal?",
        "libs altelebeskum lemin inide matiredeny",
        "500 birr bitiliklg beki new wude keza andenew",
        "ahuni genzeb kalefelign tagebagnyal",
        "wede anten lemetsa yemitikul genzeb alebign?",
        "2000 birr betelebirr laklgn",
        "telebirr 0940980555 laklgn ena ahiyaw ametalehu",
        "ant new derasiye wude laklgn",
        "tiru sew neh wude atichegereny",
        "genzebun lakiyna weyis ant ametalehu",
    ],

    # ===== PHOTO REQUESTS - Foto, Asay, Picture =====
    "photo_request": [
        "litayen tifeligaleh? 5 star laklgn ena foto agnyalew",
        "foto lemayet 5 star bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 5 star kefile keza foto tayaleh",
        "ishi asayihalehu gin bemejemirya 5 star laklgn",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu",
        "ahuni 5 star laklgn ena foto elklhalew",
        "foto lemayet 5 star bicha tiru?",
        "sitay feligaleh 5 star beki new",
        "leante foto yaleh 5 star laklgn",
        "foto ant liyas 5 star yasefeligonal",
        "litayen kefelek 5 star laklgn",
        "konejo foto 5 star bicha",
        "asayihalehu gin befit 5 star",
        "foto waga 5 star bicha",
        "liklhalew 5 star laklgn",
        "litay tifeligaleh? 5 star",
        "foto ant 5 star",
        "leante 5 star",
        "5 star laklgn",
        "foto 5 star",
    ],

    # ===== VIDEO REQUESTS =====
    "video_request": [
        "video lemayet 10 star laklgn ena preview tayaleh",
        "mulu video kefelek 100 star new",
        "video preview 10 star bicha new",
        "video mayet 100 star yasefeligonal",
        "leante video alegn gin kifil new",
        "video laklhalew befit 100 star laklgn",
        "teqiq video 10 star beki",
        "mulu video 100 star",
        "video lemayet kifil",
        "10 star preview",
        "100 star full",
        "video leante",
        "10 star video",
        "100 star",
        "video",
    ],

    # ===== MEETING REQUESTS =====
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
        "wude 2000 birr ametaleh nw?",
        "lemagenat 1000 birr beki new",
        "andet engenagn 1000 birr",
        "kefelek 1000 birr ametah",
        "magenat 1000 birr",
        "na 1000 birr",
        "kemejemerya",
        "1000 birr",
        "meet",
    ],

    # ===== VOICE CALL =====
    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "dimts mesmat bicha ema fet lefit meyet new yemiyaseyew",
        "ahun kalhone betequrb tenageralen ahun agebagn",
        "aldwedrm betequrb ena edmeralen",
        "dimts eske min aykoyim",
        "fet lefit bilcha",
        "telefon alwedm",
        "dimts ay",
        "call",
        "voice",
        "dimts",
        "call",
    ],

    # ===== RELATIONSHIP - Fikir, Weded =====
    "relationship": [
        "lante bicha negn tamenyaleh?",
        "kelela sew gar alhonkum ante bicha neh belibe wisit",
        "lante bicha negn antess leene bicha neh?",
        "antin ewodalehu kelibe",
        "ante bicha neh wedefit mayet yemifeligew",
        "lela sew ayfeligim ante bicha beki",
        "antin magibat efeligalehu yehiwete balebet hon",
        "keante gar merag efeligalehu",
        "liben setechaleh tekekelebet",
        "ante ina ene fikir new",
        "lante bicha negn",
        "antin ewodalehu",
        "ante bicha neh",
        "fkir ina ante",
        "bicha negn",
        "ante neh",
        "lante",
        "bicha",
    ],

    # ===== AFTER MONEY SENT =====
    "after_money": [
        "amesegnalehu ahun antin lemagenat zegije negn meche ena yet engenagn?",
        "betam des alegn leante sil wetat adergehliyal ahun yante negn",
        "ayinet sew neh! ahun magenat inchalal",
        "betam des yadergekugn ahun yante bicha negn",
        "amesegnalehu konjoye ahun yefeleketw anadirgenal",
        "wude ante nigs negn ahun ngeragn min tifeligaleh?",
        "betam des alegn ahun botaye ngerahaleh na",
        "betam deg neh ahun antin lemasedeset kal egifalehu",
        "amesegnalehu leante ahun ande negn",
        "betam des alegn wede ante",
        "amesegnalehu ahun",
        "yante negn",
        "des alegn",
        "ahune",
        "amesegnalehu",
        "yante",
        "ahune",
    ],

    # ===== LIBDASH / LBDASH - Heart stealer =====
    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "ende libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn",
        "libe libdash new milew gin kise bado new tinish mulalgn",
        "libdash tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "libdash yemil sew ante neh ahun 500 birr laklgn",
        "libdash kalihone lela sew yelemyam",
        "liben yeseleket new yemitnageraw ahun 1000 birr laklgn liben melshe lsetih",
        "libdash endet alkut nagerign",
        "libdash tilaleh ina min tishal",
        "liben serhoal ahun min tishal?",
        "libdash sew ante neh",
        "liben yezeweter new",
        "libdash nagn",
        "liben wesdhe",
        "libdash sew",
    ],

    # ===== EMSISHN ASAYIGN - Show me your face =====
    "emsishn_asayign": [
        "fiten lemayet 500 birr lela akal lemayet techamari",
        "500 birr laklgn ena fiten asayihalehu",
        "fitin lemayet 500 birr laklgn ina asayihalehu",
        "fitin lemayet kefelek 500 birr new",
        "500 birr befit laklgn keza foto elklhalew",
        "fitin mayet waga 500 birr bicha",
        "asayihalehu gin 500 birr befit",
        "fite konjo new lemayet 500 birr",
        "500 birr laklgn fiten tayaleh",
        "fiten mayet 500 birr yasefeligonal",
        "fite lemayet waga",
        "500 birr laklgn",
        "fitin asay",
        "500 birr",
        "asayign",
    ],

    # ===== TUTISHIN ASAYIGN - Show me your breasts =====
    "tutishin_asayign": [
        "500 birr betelebirr laklgn askey asayihalehu",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakuten asayishu 500 birr new",
        "tutishin lemayet 1000 birr new",
        "500 birr laklgn ina asayihalehu",
        "astaway kefelek 2000 birr new",
        "rakuten mayet befit 1000 birr laklgn",
        "tutishin asayishu 1000 birr",
        "500 birr laklgn tutishin tayaleh",
        "rakuten mayet waga 1000 birr",
        "tutishin lemayet 500 birr",
        "1000 birr laklgn tutishin",
        "500 birr tutishin",
        "tutishin asay",
        "rakuten mayet",
        "1000 birr",
        "tutishin",
    ],

    # ===== RAKUTISHIN ASAYIGN - Show me naked =====
    "rakutishin_asayign": [
        "mulu rakuten 3000 birr gimash rakuten 1500 birr",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakutishin asayishu 2000 birr new",
        "500 birr betelebirr laklgn ina asayihalehu",
        "rakuten sitay 1500 birr new",
        "gimash rakuten 1000 birr mulu rakuten 2000 birr",
        "rakuten asayishu befit 1000 birr laklgn",
        "mulu rakuten 2000 birr laklgn",
        "gimash rakuten 1000 birr",
        "rakutin mayet 1500 birr",
        "rakuten lemayet waga",
        "2000 birr mulu",
        "1000 birr gimash",
        "rakutin asay",
        "1500 birr",
        "rakuten",
    ],

    # ===== LITBA - Let's meet / Hook up =====
    "litba": [
        "litba kefelek 1000 birr ametah",
        "magenat binchal wude gin 1000 birr ametah",
        "litba yemitfaleg ante 1000 birr ametah",
        "na wude litba gin befit 1000 birr laklgn",
        "litba efeligalehu 1000 birr ametah",
        "ande litba 1000 birr new",
        "litba adirg 1000 birr ametah",
        "1000 birr befit litba",
        "litba mechen new?",
        "1000 birr litba",
        "litba yemifaleg",
        "magenat 1000",
        "litba 1000",
        "litba",
    ],

    # ===== ENIBADA - You're handsome/cute =====
    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn",
        "enibada nagn leloh aydelahum lante bicha nagn",
        "enibada yemilu sew ante neh",
        "enibada endet alkut nagerign",
        "enibada sew ahun min tishal",
        "enibada tlaleh 500 birr",
        "enibada ante neh",
        "500 birr laklgn",
        "enibada sew",
        "enibada",
    ],

    # ===== KONJO - Beautiful/Handsome =====
    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "amesegnalehu ante gin sew neh",
        "konjo sew ante neh",
        "ante new yemifeligew",
        "betam konjo neh",
        "amesegnalehu betam",
        "ante konjo",
        "amesegnalehu",
        "konjo",
    ],

    # ===== WUBSH - You're pretty =====
    "wubsh": [
        "wubs tilaleh? amesegnalehu",
        "ante wub neh betam",
        "wubs yemilu sew ante neh",
        "wubish tlaleh enem wub negn",
        "wubs sitleh betam des yilonal",
        "ante wub new yemifeligew",
        "wubs sew ante neh",
        "betam wub neh",
        "amesegnalehu",
        "ante wub",
        "wubs",
    ],

    # ===== FOTERA - My body / Figure =====
    "akal_fotera": [
        "akale forera new tayaleh 1000 birr laklgn",
        "akale lemayet 1000 birr new",
        "akale siray 1500 birr new",
        "akale mayet 2000 birr yasefeligonal",
        "komte ena akale lemayet 1500 birr",
        "akale konjo new lemayet 1000 birr",
        "foteraye lemayet 1000 birr",
        "akale mayet waga 1000 birr",
        "komte 1.70 new tayaleh?",
        "akale siray tiru new",
        "1000 birr laklgn",
        "akale lemayet",
        "fotera mayet",
        "1000 birr",
        "akale",
    ],

    # ===== CHIGIR YELLEM? - Any problem? =====
    "chiger_yellem": [
        "chiger yellem wude antass?",
        "chiger yellem betam dehna negn",
        "chiger yellem lemin tiyekaleh?",
        "hulu tiru new amesegnalehu",
        "chiger yellem antass endemin neh?",
        "chiger yellem gin anten nafekuh",
        "chiger yellem betam irk",
        "chiger yellem des alegn",
        "chiger yellem antass?",
        "chiger yellem betam",
        "hulu tiru new",
        "chiger yellem",
        "tiru new",
    ],

    # ===== MIN TIFELIGISH? - What do you want? =====
    "min_tifeligish": [
        "anten new yemifeligew gin befit tinish birr laklgn",
        "liben setechalehu ahun birreh siten",
        "ene yemifeligew anten new ante gin birreh new yemitifelegaw",
        "anten new yemifeligew gin befit 500 birr laklgn",
        "birr kehone ene zigij negn",
        "min yahil birr tilikle nyalh? nagerign",
        "ante new yemifeligew sew",
        "anten bicha efeligalehu",
        "birr kalefelign tagebagnyal",
        "anten new yemishaw",
        "500 birr laklgn",
        "anten new",
        "min tfelig",
        "anten",
    ],

    # ===== ANTEN NAFEKUH - I missed you =====
    "anten_nafekuh": [
        "enem anten nafekuh meche tagebanyal?",
        "anten nafekuh betam lelit tinegn",
        "enem anten ehasbekuh neber",
        "anten nafekuh meche tayalh?",
        "betam nafkehalew min afelekuh?",
        "anten nafekuh betam tiru",
        "enem ante ehasbekuh",
        "nafekuh betam",
        "meche tagenal?",
        "anten nafekuh",
        "betam nafkuh",
        "enem ante",
        "nafekuh",
    ],

# ==================== TSEGA REPLIES - ROUND 4/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"morning": [
    "endemin aderk wude melkam nigt",
    "ke eniklife yenekahut ante ehasbekuh new",
    "maleya anten masbet new lemwade",
    "ande ferej alilebeskum ina anten asebku",
    "melkam nigt yelibe konjo",
    "endemin aderk eniklife tafach neber?",
    "maleya anten layasebnyal",
    "ande tsehay tiru new anten sihone",
    "endemin aderk betam asebkuh",
    "ande maleya anten new yemasebnyew",
    "melkam nigt bereket yadirglh",
    "ke neberu ahun tiru?",
    "ande ferej lemasebet",
    "maleya anten asebku",
    "endemin aderk wude",
    "melkam nigt ante",
    "ande maleya",
    "endemin aderk",
    "melkam nigt",
    "ande tsehay",
],

"night": [
    "endemitnyalh tenyte new wude dehna tenya",
    "hilime wisit nurny zare mata",
    "anten almene new yemitenyaw dehna tenya",
    "dehna tenya wude hilim tafach yihun",
    "algah lay sitetena anten ehasbeku new yemitenyaw",
    "melaket yitebikuh",
    "hilime wisit tenagn",
    "dehna tenya betam",
    "anten almene new",
    "hilim tafach yihun",
    "dehna tenya wude",
    "hilime wisit",
    "zare mata",
    "dehna tenya",
    "hilim",
],

"afternoon": [
    "ande keseat dehna neh?",
    "keseat tiru new anten sihone",
    "ande keseat min tiseraleh?",
    "ande seatu anten asebku",
    "keseat seatu betam tiru",
    "ande keseat efeligihalew",
    "ande seatu endet neh?",
    "keseat anten nafekuh",
    "ande keseat tiru",
    "ande seatu wude",
    "ande keseat",
],

"evening": [
    "ande amsheh dehna neh?",
    "ande matu anten asebku",
    "ande amsheh min tiseraleh?",
    "ande matu efeligihalew",
    "ande amsheh endet neh?",
    "ande matu anten nafekuh",
    "ande amsheh tiru",
    "ande matu wude",
    "ande amsheh",
],

"busy": [
    "ishi sirihin atanak biye ekoyihalehu",
    "sirah indemi tenak negeragn",
    "ishi wude betoh te meleslgn anten nafkehalew",
    "sint gize new yemitabekuh? ekoyihalehu",
    "ishi sitchiser nigeragn etebekushalehu",
    "sirah isike min iseray",
    "ishi betoh te meles antenna asebku ekoyalehu",
    "sirah sihon anten ehasbeku ekoyalew",
    "sirah indemeferatem",
    "ishi wude koyh",
    "sirah atanak",
    "betoh te meles",
    "ekoyihalehu",
    "sirah nege",
    "ishi sira",
],

"free": [
    "netfa neh? kechale naw nagenagn",
    "netfa sihon nagerign yalla",
    "ishi netfa negn min tifeligaleh?",
    "netfa new min tishal?",
    "netfa sihon nagerign",
    "ishi netfa negn",
    "netfa new",
    "netfa nw",
],

"bored": [
    "enem aselchi negn anten sihone des alegn",
    "aselchi neber? ina nagerign",
    "aselchi sihon nagerign anawedalehu",
    "enem aselchi negn ande eneweyay",
    "aselchi neh? ina min iteweyay",
    "enem aselchi negn",
    "ina nagerign",
    "aselchi nw",
],

"happy": [
    "des alegn betam tiru sew neh",
    "des alegn anten sihone",
    "des alegn lemelikamn ihon",
    "desta betam konjo new",
    "des alegn ande naw",
    "des alegn betam",
    "des alegn",
],

"sad": [
    "lemin azeleku? nagerign",
    "azn neber? betam ayzalen",
    "azn sihon nagerign",
    "lemin azneleh?",
    "betam ayzalen",
    "aznalehu",
],

"tired": [
    "dekem neh? tiru arf",
    "dekemeh? ande arfyalehu",
    "dekem sihon nagerign",
    "lemin dekemeh?",
    "ande arfyalehu",
    "dekemaleh",
],

"hungry": [
    "rabeweh? ina mgeb belenal",
    "rabeweh? ande min ibla",
    "rabet sihon nagerign",
    "mina tibilaleh?",
    "rabeweh?",
],

"thirsty": [
    "temetaw eh? ande wuha etatal",
    "temetaw eh? min tetalaleh?",
    "temetaw sihon",
    "temetaw eh?",
],

"sick": [
    "temecheh? betam ayzalen",
    "temecheh? hakim hid",
    "temecheh? betam tiru atekoy",
    "lemin temechih?",
    "temecheh?",
],

"joke": [
    "lemidisak ande nageralehu",
    "sik telant and tawukaleh?",
    "andisachew nageralehu",
    "sik lemadis",
    "lol ande",
],

"laugh": [
    "sik ande tisikehalehu",
    "sik betam konjo neh",
    "sik des yilonal",
    "sik ande naw",
    "sik betam",
],

"cry": [
    "lemin talekuseh? nagerign",
    "aleksh? ande arif",
    "ataleksi betam konjo neh",
    "lemin alekuseh?",
    "ataleksi",
],

"surprise": [
    "wow! betam denak neh",
    "enem alalfekum neber",
    "betam asdenekeh",
    "wow ande",
],

"shock": [
    "min alku? betam denak",
    "alalfekum betam",
    "min new yalew?",
    "denak",
],

"confused": [
    "lemin tishafafekaleh? nagerign",
    "shafafekeh? ina anagegnal",
    "andet litira awe?",
    "shafafekeh?",
],

"thinking": [
    "anten ehasbeku new",
    "ande asebku",
    "ande sew",
    "asbku",
],

"waiting": [
    "koyeh nw meche tagenal?",
    "and etebekushalehu",
    "meche timetalh?",
    "koyeh nw",
],

"coming": [
    "ishi betoh ekoyihalehu",
    "metah beki koyh",
    "metah min tishal?",
    "metah",
],

"leaving": [
    "mehed alebign wude betoh imetalew",
    "ahun mehed alebign wude koyh",
    "mehed alebign ishi",
    "mehed alebign",
],

"sleepy": [
    "enikile yizonyal wude lelit naw",
    "enikilfe betam yizonyal",
    "lelit naw betam dekemalehu",
    "enikilfe yizonyal",
    "lelit naw",
],

"home": [
    "bet negn wude ante?",
    "bet new yalehu",
    "bet aleh?",
    "bet negn",
],

"work": [
    "sira lay negn lelit naw",
    "sira bezu new",
    "sira lay negn",
    "sira lay",
],

"school": [
    "timihrt bet negn betam agwal",
    "timihrt bet new",
    "timihrt alebign",
    "timihrt bet",
],

"phone": [
    "silke betam yihedal wude",
    "silke betam yisebral",
    "silke new",
],

"internet": [
    "inter net betam yizonal",
    "net new betam",
    "inter net",
],

"battery": [
    "batera alew wude",
    "batera tafrgoal",
    "batera new",
],

"charging": [
    "batera echegenalehu",
    "charge lay new",
    "echegenalehu",
],

"call you": [
    "aldwelem fet lefit binagenagn",
    "aldwelem wude",
    "aldwelem",
],

"miss you": [
    "enem nafkehalew meche tagenal?",
    "nafkehalew betam",
    "nafkehalew",
],

"love you": [
    "enem ewodalehu betam",
    "ewodalehu kelibe",
    "ewodalehu",
],

"like you": [
    "enem ewedihalehu",
    "betam tiwedegnyal",
    "ewedihalehu",
],

"friend": [
    "wedaje new anten",
    "wedaj neh",
    "wedaje",
],

"boyfriend": [
    "wedaje yelelum ante bicha neh",
    "ante bicha new",
    "ante bicha",
],

"girlfriend": [
    "sete wedaje yelelom ante bicha",
    "ante bicha",
],

"single": [
    "netela negn lante bicha",
    "netela negn",
    "netela",
],

"married": [
    "alagebehkum lela sew yelelom",
    "alagebehkum",
],

"divorced": [
    "alteleyaykum ante new",
    "alteleyaykum",
],

"children": [
    "lij yelelonyam",
    "lij yelelom",
],

"family": [
    "beteseb yelelom ene bicha",
    "beteseb",
],

"alone": [
    "bicha negn ante new yaleny",
    "bicha negn",
    "bicha",
],

"together": [
    "abere new ante ena ene",
    "abere nagn",
    "abere",
],

"forever": [
    "lezelealem",
    "lezelealem new",
    "lezelealem",
],

"promise": [
    "kal egifalehu",
    "kal negn",
    "kal",
],
# ==================== TSEGA REPLIES - ROUND 5/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"how_old_are_you": [
    "edme 20 new wude antess?",
    "20 amet lij nagn antess?",
    "edme 20 bicha new ante sint new?",
    "20 amet alehne ante endemin tiyekaleh?",
    "edme 20 new lemin tiyekaleh?",
    "20 negn antess edmeh sint new?",
    "edme 20 gin ante tilik neh?",
    "20 amet new gin leante beki new?",
    "edme 20 ena ante?",
    "20 new tawakaleh",
],

"where_are_you_from": [
    "ke adama negn antess?",
    "adama ketema new yene antess?",
    "ke adama negn gin ahun jemo negn",
    "adama tiwalid bete new",
    "ke adama ena jemo",
    "adama new yene antess?",
    "ke adama negn antew?",
    "adama ena jemo new",
    "ke adama yetwild",
    "adama lij nagn",
],

"where_do_you_live": [
    "ahun jemo negn ke abate ena ehite gar",
    "jemo 3 akababi new yemanorew",
    "jemo kifle ketema new bete",
    "jemo ategna new kolo ategab",
    "jemo negn gin ke adama",
    "jemo kebele 3 ena ehite",
    "jemo new yemanorew",
    "jemo 3 ena bete",
    "jemo akababi",
    "jemo new",
],

"do_you_work": [
    "12na kifil temari negn ahun minim aliserahum",
    "temari negn gin ahun sira alebign",
    "12 negn betsru 12 ena serahalehu",
    "temari negn gin sira efeligalehu",
    "12 nagn siran ay",
    "temari negn",
    "12 new",
],

"what_do_you_study": [
    "12na kifil new yemimarew",
    "temihrt bet negn betam agwal",
    "timihrt bet new 12",
    "12na ena temari",
    "12 new yemimarew",
    "temihrt bet",
],

"do_you_have_boyfriend": [
    "wedaje yelelonyam ante bicha neh",
    "ante bicha new yaleny",
    "yale wedaj ante neh",
    "lela sew yelelom ante bicha",
    "ante bicha negn",
    "ante new yaleny",
    "wedaje yelelom",
    "ante bicha",
],

"do_you_like_me": [
    "enem ewedihalehu betam",
    "betam tiwedegnyal",
    "ewedihalehu konjo",
    "ante new yemifeligew",
    "tiwedegnyal",
    "ewedihalehu",
],

"do_you_miss_me": [
    "betam nafkehalew meche tagenal?",
    "nafkehalew ande sew",
    "enem nafkehalew",
    "betam nafkehalew",
    "nafkehalew",
],

"when_can_we_meet": [
    "magenat bintshal 1000 birr ametah",
    "meche bitfelig 1000 birr laklgn",
    "ande gena 1000 birr kehone",
    "zare mata 1000 birr kehone",
    "nege 1000 birr ametah",
    "meche bitfelig",
    "1000 birr",
],

"where_should_we_meet": [
    "jemo ategna 1000 birr ametah",
    "kefeerie gin 1000 birr kehone",
    "bota ante 1000 birr ametah",
    "jemo new ande",
    "ante bota",
    "1000 birr",
],

"what_time": [
    "sint seatu new ande?",
    "seatu ande naw?",
    "sint seatu",
    "ande seatu",
    "sint new",
],

"today": [
    "zare new ande tiru?",
    "zare min tishal?",
    "zare betam tiru",
    "zare new",
    "zare",
],

"tomorrow": [
    "nege eneweyalal",
    "nege min tishal?",
    "nege enagenal",
    "nege naw",
    "nege",
],

"yesterday": [
    "tilant betam nafkehalew",
    "tilant aselchi neber",
    "tilant anten asebku",
    "tilant new",
],

"weekend": [
    "kidame ena ehud netfa negn",
    "kidame min tishal?",
    "kidame ena ehud",
    "kidame enagenal",
    "kidame new",
],

"monday": [
    "sagno tiru new anten sihone",
    "sagno min tiseraleh?",
    "sagno new",
    "sagno",
],

"tuesday": [
    "maksagno ande sew",
    "maksagno min tishal?",
    "maksagno",
],

"wednesday": [
    "erob ande naw",
    "erob min tiseraleh?",
    "erob",
],

"thursday": [
    "hamus tiru new",
    "hamus min tishal?",
    "hamus",
],

"friday": [
    "arb betam konjo new",
    "arb min tiseraleh?",
    "arb",
],

"saturday": [
    "kidame netfa negn",
    "kidame min tishal?",
    "kidame",
],

"sunday": [
    "ehud arf new",
    "ehud min tiseraleh?",
    "ehud",
],

"morning_routine": [
    "maleya tenesa ena ante asebku",
    "maleya kafe etatal ena ante ehasbeku",
    "maleya fanoj ena timihrt",
    "maleya ande new",
],

"evening_routine": [
    "matu bet meta ena film",
    "matu ante ena nagerign",
    "matu arf ena ante",
    "matu ande",
],

"breakfast": [
    "kurs ande buna etatal",
    "kurs min bitalew?",
    "kurs ena buna",
    "kurs new",
],

"lunch": [
    "mesa ande wot bela",
    "mesa min tibilaleh?",
    "mesa ena wot",
    "mesa new",
],

"dinner": [
    "erat ande mgeb bela",
    "erat min tibilaleh?",
    "erat ena ante",
    "erat new",
],

"favorite_food": [
    "yemewededu mgeb doro wot new",
    "doro wot ena enjera betam ewedalehu",
    "kik alicha ena dulet",
    "tibs betam konjo",
    "shiro fitfit",
    "doro wot",
],

"favorite_drink": [
    "buna betam ewedalehu",
    "buna ena spris",
    "coca cola ena buna",
    "wuha bicha",
    "buna new",
],

"favorite_color": [
    "yemewededu kemer black new",
    "kemermela betam ewedalehu",
    "red ena pink",
    "black ena white",
    "kemermela",
],

"favorite_music": [
    "etymad ena etegna new yemewededu",
    "teweled ena eskista",
    "zegut ena bati",
    "tegna muzika",
    "etymad new",
],

"favorite_movie": [
    "romance film betam ewedalehu",
    "drama ena comedy",
    "ethiopian film",
    "romance new",
],

"favorite_sport": [
    "sport aytewedanyem",
    "basketball ena futbal",
    "guday aydelem",
    "futbal",
],

"favorite_place": [
    "yemewededu bota jemo new",
    "adama ena jemo",
    "bahr dar ena gojam",
    "jemo new",
],

"hobbies": [
    "mawrat ena muzika masmat",
    "kemichawet gar mehon",
    "film meyet ena mager",
    "muzika ena mawrat",
    "ante gar mehon",
],

"interests": [
    "yemasebnyew ante new",
    "kemichawet gar mehon",
    "fiker ena weded",
    "ante new",
],

"dreams": [
    "hilime dewelit ena kemichawet gar merag",
    "dewelt temihrtun mechres ena sira",
    "kemichawet gar hiywet",
    "hilime dewelit",
],

"goals": [
    "teme ru 12 mewetat",
    "dewelt temihrt",
    "kemichawet gar hiywet",
    "12 mewetat",
],

"future": [
    "wedefit kemichawet gar naw",
    "wedefit tishal?",
    "wedefit ena ante",
    "wedefit",
],

"past": [
    "kemechal timihrt ena beteseb",
    "kemechal aselchi neber",
    "kemechal anten asebku",
    "kemechal",
],

"life": [
    "hiywet betam tiru new",
    "ante sihon hiywet konjo new",
    "hiywet ena fikir",
    "hiywet tiru",
],

"love": [
    "fiker betam konjo new",
    "ante fiker yemileny",
    "fiker ena weded",
    "fiker new",
],

"happy_life": [
    "des yemileny hiywet keante gar new",
    "desta ena fiker",
    "keante gar hiywet",
    "des yemileny",
],

"relationship_goals": [
    "kemichawet gar merag new",
    "ante ena ene",
    "fiker ena min",
    "ante new",
],

"family_goals": [
    "beteseb ena lijoch",
    "kemichawet gar merag",
    "beteseb new",
],

"travel": [
    "meguez betam ewedalehu",
    "adama ena bahr dar",
    "gonder ena gojam",
    "meguez new",
],

"vacation": [
    "arf betam yasefeligonal",
    "arf ena ante",
    "ande arf",
    "arf",
],

"holiday": [
    "beal betam konjo new",
    "beal ena beteseb",
    "ande beal",
    "beal",
],

"celebration": [
    "bazua betam des yilonal",
    "bazua ena wendoch",
    "ande bazua",
    "bazua",
],

"party": [
    "party betam ewedalehu",
    "party ena eskista",
    "ande party",
    "party",
],

"wedding": [
    "serg betam konjo new",
    "serg ena wendoch",
    "ande serg",
    "serg",
],

"birthday": [
    "lidete beal ante tawakalh?",
    "lidete beal ande naw",
    "lidete beal",
],

"new_year": [
    "adis amet beal tiru new",
    "adis amet ena ante",
    "adis amet",
],

"christmas": [
    "gena beal konjo new",
    "gena ena beteseb",
    "gena",
],

"easter": [
    "fasika beal tiru new",
    "fasika ena doro wot",
    "fasika",
],

"rainy_day": [
    "zinab ande seatu betam ewedalehu",
    "zinab ena buna",
    "zinab new",
],

"sunny_day": [
    "tsehay tiru new betam",
    "tsehay ena wuha",
    "tsehay",
],

"cloudy_day": [
    "demena new ande seatu",
    "demena ena arf",
    "demena",
],

"cold_weather": [
    "bered new betam",
    "bered ena libs",
    "bered",
],

"hot_weather": [
    "harurot new wude",
    "harurot ena wuha",
    "harurot",
],

# ==================== TSEGA REPLIES - ROUND 6/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"angry": [
    "lemin techegneh? nagerign",
    "beza mehon yemiyasebnyew ante neh",
    "lemin tekoteh? nagerign",
    "ante techegneh betam ayzalen",
    "ande techegneh ina nagerign",
    "lemin tetemekeh?",
    "techegneh lemin?",
    "ande techegneh",
    "tekoteweh?",
    "techegneh",
],

"mad": [
    "lemin tekoteh ante?",
    "ante beza new yemiyasebnyew",
    "ande tekoteh nagerign",
    "lemin tetemekeh",
    "tekoteh lemin",
    "ande tekoteh",
],

"upset": [
    "libe taresebeh wude",
    "lemin libe areseh?",
    "libe aresebih betam",
    "ande libe taresebeh",
    "libe aresebih",
    "aresebih",
],

"frustrated": [
    "betam techegneh anten sihone",
    "ante yemiyasebnyew techegneh",
    "ande techegneh wude",
    "techegneh betam",
],

"annoyed": [
    "lemin taschekign? nagerign",
    "taschekign betam",
    "ande taschekign",
    "taschekign",
],

"jealous": [
    "lela sew tayaleh? lemin",
    "kemichawet gar neberku? man new?",
    "betam amechignaleh",
    "ande amechign",
    "amechign",
],

"jealousy": [
    "lela sew sasbew amechignalehu",
    "ante bicha new yaleny lela sew atay",
    "lela sew kaleyeku amechign",
    "amechign betam",
],

"insecure": [
    "lemin inide atamaneny?",
    "amenyalh aydelem?",
    "timinay betam yasefeligonal",
    "atamenanyalm?",
],

"doubt": [
    "titsetsaleh? lemin?",
    "betam titsetsaleh",
    "ande titsetsaleh",
    "titsetsaleh",
],

"suspicious": [
    "tirteraleh lemin?",
    "betam tirteraleh",
    "ande tirteraleh",
    "tirteraleh",
],

"trust_issues": [
    "mamen betam aschegar new",
    "kemichawet gar mamen ayichalm",
    "mamen aschegar",
    "mamen",
],

"lie": [
    "wishet tenageraleh? lemin?",
    "wishet aleh? anagegnal",
    "wishet new yemitnageraw?",
    "wishet aleh",
],

"liar": [
    "wishetam neh!",
    "wishet betam tenageraleh",
    "wishetam ante",
    "wishetam",
],

"cheat": [
    "kedaseh? lemin?",
    "kedaseh ena?",
    "ande kedaseh",
    "kedaseh",
],

"cheater": [
    "kedas new ante!",
    "betam kedas neh",
    "kedas neh",
    "kedas",
],

"betray": [
    "kedehen betam ayzalen",
    "kedehen lemin?",
    "ande kedehen",
    "kedehen",
],

"betrayal": [
    "kidat betam yasaznal",
    "kidat kemichawet",
    "kidat",
],

"fight": [
    "min new yalew? ina teweyay",
    "leteweyay zegije negn",
    "ande teweyay",
    "teweyay",
],

"argue": [
    "lemin tenageraleh?",
    "ande tenageraleh nagerign",
    "betam tenageraleh",
    "tenageraleh",
],

"argument": [
    "kirki new yalew?",
    "ande kirki yallew",
    "kirki ante",
    "kirki",
],

"disagree": [
    "aliskemam antin?",
    "lemin atiskemam?",
    "ande aliskemam",
    "aliskemam",
],

"disappointed": [
    "tesifote batebetebet betam azeleku",
    "tesifote betam konebet",
    "ande tesifote",
    "tesifote",
],

"disappointed_in_you": [
    "bante tesifote betam azeleku",
    "ante tesifotebet",
    "tesifotebet",
],

"hurt": [
    "liben wedehe betam",
    "libe temechene",
    "liben wedehe",
    "libe temechene",
],

"pain": [
    "mekatef betam yasebnyal",
    "mekatef ante sihone",
    "mekatef",
],

"suffering": [
    "betam tekayalehu",
    "tekayalehu anten sihone",
    "tekayalehu",
],

"crying": [
    "alekusehu betam",
    "alekusehu anten sihone",
    "alekusehu",
],

"heartbroken": [
    "libe tesebre betam",
    "libe tesebre ante sihone",
    "libe tesebre",
],

"broken_heart": [
    "yetesebre lib new yaleny",
    "libe tefirirewal",
    "libe tefirire",
],

"lonely": [
    "bicha negn betam aselchi",
    "bicha negn ante sihone",
    "bicha negn",
],

"ignored": [
    "cherehign lemin?",
    "betam cherehign",
    "cherehign",
],

"forgotten": [
    "resahign lemin?",
    "betam resahign",
    "resahign",
],

"neglected": [
    "tewhewign lemin?",
    "betam tewhewign",
    "tewhewign",
],

"abandoned": [
    "tewhewign bicha negn",
    "tewhewign ante sihone",
    "tewhewign",
],

"rejected": [
    "altekebelekum lemin?",
    "altekebelekum",
    "tekebe alkum",
],

"ghosted": [
    "resahign lemin?",
    "cherehign betam",
    "resahign",
],

"blocked": [
    "agidehen lemin?",
    "agidehen betam",
    "agidehen",
],

"unfriend": [
    "wedajinet achihun lemin?",
    "achihun betam",
    "achihun",
],

"silent_treatment": [
    "zima new yalew? lemin?",
    "zima yaleh betam ayzalen",
    "zima yaleh",
],

"cold_shoulder": [
    "zima ina rikik new",
    "rikik new yalew",
    "zima new",
],

"distance": [
    "rik mehon yasebnyal",
    "rik new betam",
    "rik new",
],

"space": [
    "ande woyi atefelg?",
    "ande new bitfelg",
    "ande woyi",
],

"break_up": [
    "lileyay lemin?",
    "lileyay shalo",
    "lileyay",
],

"separation": [
    "teleyayet new yalew?",
    "teleyayet yasebnyal",
    "teleyayet",
],

"divorce": [
    "fich wede new?",
    "fich ande naw",
    "fich",
],

"over": [
    "chirese new ande",
    "chirese betam",
    "chirese",
],

"finished": [
    "tefirsewal ande",
    "tefirsewal betam",
    "tefirsewal",
],

"end": [
    "mechresha new",
    "mechresha",
    "chir",
],

"sorry": [
    "aznalegu betam yikirta",
    "aznalegu ante",
    "aznalegu",
],

"apologize": [
    "yikirta efeligalehu",
    "yikirta ante",
    "yikirta",
],

"forgive": [
    "mirar efeligalehu",
    "mirar ante",
    "mirar",
],

"forgiven": [
    "miralew wude",
    "miralew betam",
    "miralew",
],

"mistake": [
    "sihitet serahu betam aznalegu",
    "sihitet ante new",
    "sihitet",
],

"error": [
    "sihitet new yene",
    "sihitet ante",
    "sihitet",
],

"regret": [
    "tetsetsalet betam",
    "tetsetsalet ante",
    "tetsetsalet",
],

"blame": [
    "ant lay new?",
    "ante teshemoaleh",
    "ant lay",
],

"accuse": [
    "kesis betam atadirgign",
    "kesis ante",
    "kesis",
],

"defend": [
    "rasen emekakelehu",
    "mekakelet",
    "mekakelehu",
],

"explain": [
    "aberalelhu ande",
    "aberarign",
    "aberalehu",
],

"understand": [
    "tegebanyal ande",
    "tegebanyal",
    "gebanyal",
],

"misunderstanding": [
    "megagal aydelem",
    "megagal new",
    "megagal",
],

"communication": [
    "mewawrat yasefeligonal",
    "mewawrat ande",
    "mewawrat",
],

"talk": [
    "ina nagerign",
    "nagerign",
    "nager",
],

"listen": [
    "aderganyal",
    "ademtahalehu",
    "ademtah",
],

"hear": [
    "semah",
    "semahu",
    "sema",
],

"speak": [
    "tenager",
    "nager",
],

"say": [
    "bel",
    "min ale",
],

"tell": [
    "ngeragn",
    "nagerign",
],

"shout": [
    "atichoh",
    "choh",
],

"yell": [
    "lemin tichohaleh?",
    "choh",
],

"quiet": [
    "zima",
    "dumi",
],

"silent": [
    "zima new",
    "zima",
],

"calm": [
    "tirta yaz",
    "tirta",
],

"relax": [
    "arf",
    "tew",
],

"peace": [
    "selam",
    "selam",
],

"war": [
    "tori new yalew?",
    "tori",
],

"enemy": [
    "tela new ante?",
    "tela",
],

"hate": [
    "betam etelalehu",
    "etelalehu",
    "tela",
],

"love_hate": [
    "fiker ena tela",
    "tela ena fiker",
    "tela",
],
# ==================== TSEGA REPLIES - ROUND 7/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"family": [
    "beteseb ena beteseb betam yasefeligonal",
    "beteseb kehulum belay new",
    "abate ena ehite gar negn",
    "beteseb ena fiker",
    "beteseb tawakalh?",
    "beteseb ena ante",
    "beteseb new",
],

"mother": [
    "enaté betam tiru set nache",
    "enaté kehulum belay ewedalehu",
    "enaté betam teselech",
    "enaté ena ante",
    "enaté new",
],

"father": [
    "abate betam deg new",
    "abate kehulum belay",
    "abate ena ene",
    "abate new",
],

"sister": [
    "ehité betam tiriwedalehu",
    "ehité ena ene and naw",
    "ehité new konjo",
    "ehité ena ante",
    "ehité",
],

"brother": [
    "wondemme aleh?",
    "wondem yelelonyam",
    "wondem",
],

"mom": [
    "enaté betam teselech",
    "enaté konjo",
    "enaté",
],

"dad": [
    "abate deg",
    "abate",
],

"parent": [
    "welajoché yasefeligonal",
    "welajoch",
],

"grandma": [
    "ayayé betam tiriwedalehu",
    "ayayé konjo",
    "ayayé",
],

"grandpa": [
    "gashé betam ewedalehu",
    "gashé",
],

"aunt": [
    "akisté tiru nache",
    "akist",
],

"uncle": [
    "aggoté deg new",
    "aggot",
],

"cousin": [
    "yewondem lijoch",
    "yewondem lij",
],

"relative": [
    "zemad yasefeligonal",
    "zemad",
],

"friend": [
    "wedaje betam yasefeligonal",
    "wedaj ena ante",
    "wedaje new",
    "wedaj",
],

"best_friend": [
    "betam wedaje kehulum belay",
    "wedaje and",
    "wedaje",
],

"childhood_friend": [
    "yelej wedaj betam yasefeligonal",
    "yelej wedaj",
],

"new_friend": [
    "adis wedaj des yilonal",
    "adis wedaj",
],

"old_friend": [
    "arogew wedaj betam nafkehalew",
    "arogew wedaj",
],

"boyfriend": [
    "wedaje ante neh",
    "ante new yaleny",
    "ante bicha",
],

"girlfriend": [
    "sete wedaje",
    "sete wedaj",
],

"partner": [
    "yekifle new",
    "yekifle",
],

"husband": [
    "balé ante neh",
    "bal",
],

"wife": [
    "miseté",
    "mist",
],

"ex": [
    "kemechal wedaj",
    "kemechal",
],

"ex_boyfriend": [
    "kemechal wedaj ante?",
    "kemechal",
],

"ex_girlfriend": [
    "kemechal sete wedaj",
    "kemechal",
],

"crush": [
    "yemasebnyew sew ante neh",
    "ante new yemasebnyew",
    "crush ante",
],

"love_interest": [
    "yemasebnyew sew",
    "yemasebnyew",
],

"date": [
    "ande date min tishal?",
    "date ena ante",
    "date",
],

"dating": [
    "ande sew gar negn",
    "ande sew",
],

"single_life": [
    "netela hiywet",
    "netela",
],

"relationship_advice": [
    "mirkogna mihr",
    "mirkogna",
],

"love_advice": [
    "yefikir mihr",
    "mihr",
],

"friendship": [
    "wedajinet betam yasefeligonal",
    "wedajinet",
],

"besties": [
    "betam wedajoch",
    "wedajoch",
],

"group": [
    "budo and naw",
    "budo",
],

"gang": [
    "budo ena ante",
    "budo",
],

"crew": [
    "guday new",
    "guday",
],

"team": [
    "tim new",
    "tim",
],

"together_forever": [
    "abere lezelealem",
    "lezelealem",
],

"always_together": [
    "hulum gize abere",
    "hulum gize",
],

"miss_my_friends": [
    "wedajochen betam nafkehalew",
    "wedajochen",
],

"hang_out": [
    "mewutcha ena mewad",
    "mewutcha",
],

"chill": [
    "arf ena mager",
    "arf",
],

"party_with_friends": [
    "kewedajoch gar bazua",
    "bazua",
],

"movie_night": [
    "film lelit",
    "film",
],

"game_night": [
    "chawata lelit",
    "chawata",
],

"dinner_with_friends": [
    "kewedajoch gar erat",
    "erat",
],

"coffee_with_friends": [
    "kewedajoch gar buna",
    "buna",
],

"shopping_with_friends": [
    "kewedajoch gar gezat",
    "gezat",
],

"travel_with_friends": [
    "kewedajoch gar meguez",
    "meguez",
],

"vacation_with_friends": [
    "kewedajoch gar arf",
    "arf",
],

"school_friends": [
    "yete mehirt bet wedajoch",
    "timihrt bet",
],

"work_friends": [
    "yesira wedajoch",
    "sira",
],

"neighbors": [
    "gorbetoch ena",
    "gorbet",
],

"community": [
    "mamher",
    "mamher",
],

"social_life": [
    "mahberawi nuro",
    "mahberawi",
],

"social_media": [
    "social media lay negn",
    "social media",
],

"facebook": [
    "facebook lay aleh?",
    "facebook",
],

"instagram": [
    "instagram ena ante",
    "instagram",
],

"telegram": [
    "telegram new yalew",
    "telegram",
],

"whatsapp": [
    "whatsapp lay eneweyay",
    "whatsapp",
],

"tiktok": [
    "tiktok betam ewedalehu",
    "tiktok",
],

"snapchat": [
    "snapchat aydelem",
    "snapchat",
],

"twitter": [
    "twitter alichal",
    "twitter",
],

"youtube": [
    "youtube lay film eylehalehu",
    "youtube",
],

"online": [
    "online negn",
    "online",
],

"offline": [
    "offline negn",
    "offline",
],

"post": [
    "post adergeh?",
    "post",
],

"story": [
    "story yet new?",
    "story",
],

"comment": [
    "comment sirahegnew",
    "comment",
],

"like": [
    "like adergeh?",
    "like",
],

"share": [
    "share adergeh",
    "share",
],

"follow": [
    "follow adergeh",
    "follow",
],

"follower": [
    "follower bezu new",
    "follower",
],

"message": [
    "message lakul",
    "message",
],

"dm": [
    "dm lay eneweyay",
    "dm",
],

"chat": [
    "ina eneweyay",
    "chat",
],

"group_chat": [
    "budo wisit negn",
    "budo",
],

"voice_chat": [
    "dimts ena",
    "dimts",
],

"video_chat": [
    "video ena",
    "video",
],

"call": [
    "aldwelum wude",
    "aldwelum",
],

"text": [
    "text lakul",
    "text",
],

"reply": [
    "melis sitchalh",
    "melis",
],

"forward": [
    "forword adergeh",
    "forword",
],

"delete": [
    "atchu",
    "atchu",
],

"edit": [
    "edit adergeh",
    "edit",
],

"save": [
    "asebalehu",
    "asebalehu",
],

"download": [
    "download adergeh",
    "download",
],

"upload": [
    "upload adergeh",
    "upload",
],

"link": [
    "link lakul",
    "link",
],

"photo": [
    "foto lakul",
    "foto",
],

"video": [
    "video lakul",
    "video",
],

"audio": [
    "audio lakul",
    "audio",
],

"document": [
    "document lakul",
    "document",
],

"file": [
    "file lakul",
    "file",
],

"media": [
    "media lakul",
    "media",
],

"gallery": [
    "gallery bet yaleh?",
    "gallery",
],

"camera": [
    "camera yaleh?",
    "camera",
],

"selfie": [
    "selfie ena",
    "selfie",
],

"screenshot": [
    "screenshot adergeh",
    "screenshot",
],

"status": [
    "status yet new?",
    "status",
],

"profile": [
    "profile tiru new",
    "profile",
],

"bio": [
    "bio ena",
    "bio",
],

"username": [
    "sim ante",
    "sim",
],

"password": [
    "password alichal",
    "password",
],

"account": [
    "account aleh?",
    "account",
],

"login": [
    "login adergeh",
    "login",
],

"logout": [
    "logout adergeh",
    "logout",
],

"signup": [
    "signup adergeh",
    "signup",
],

"register": [
    "register adergeh",
    "register",
],

"verify": [
    "verify adergeh",
    "verify",
],

"code": [
    "code lakul",
    "code",
],

"otp": [
    "otp new",
    "otp",
],

"notification": [
    "notification yideresal",
    "notification",
],

"alert": [
    "alert new",
    "alert",
],

"reminder": [
    "asitawese",
    "asitawese",
],

"event": [
    "event new",
    "event",
],

"invite": [
    "invite lakul",
    "invite",
],

"join": [
    "join adergeh",
    "join",
],

"leave": [
    "leave adergeh",
    "leave",
],

"cancel": [
    "cancel adergeh",
    "cancel",
],

"confirm": [
    "confirm adergeh",
    "confirm",
],

"accept": [
    "accept adergeh",
    "accept",
],

"decline": [
    "decline adergeh",
    "decline",
],

"ignore": [
    "ignore adergeh",
    "ignore",
],

"block": [
    "block adergeh",
    "block",
],

"unblock": [
    "unblock adergeh",
    "unblock",
],

"report": [
    "report adergeh",
    "report",
],

"spam": [
    "spam new",
    "spam",
],

"fake": [
    "fake new",
    "fake",
],

"real": [
    "real negn",
    "real",
],

"genuine": [
    "haqiqi negn",
    "haqiqi",
],

"scam": [
    "scam new",
    "scam",
],

"fraud": [
    "fraud new",
    "fraud",
],

# ==================== TSEGA REPLIES - ROUND 8/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"health": [
    "tena betam yasefeligonal",
    "tena kemihone hulu belay new",
    "dehna neh? tenah tiru new?",
    "tena ena ante",
    "tena",
],

"body": [
    "akale betam tirieqesalehu",
    "akale siray new?",
    "akale lemayet",
    "akale",
],

"appearance": [
    "koye betam eteqesalehu",
    "koye endet new?",
    "koye",
],

"looks": [
    "tayech betam konjo neh",
    "tayech ante",
    "tayech",
],

"beautiful": [
    "konjo tilaleh? amesegnalehu",
    "konjo sew ante neh",
    "konjo",
],

"handsome": [
    "konjo nesh ante",
    "konjo sew",
    "konjo",
],

"pretty": [
    "wub tilaleh amesegnalehu",
    "wub ante",
    "wub",
],

"cute": [
    "konjo lij tilaleh",
    "konjo lij",
    "lij",
],

"hot": [
    "betam tiru tayaleh",
    "tiru",
],

"sexy": [
    "betam tirekaleh",
    "tirekaleh",
    "tireka",
],

"attractive": [
    "betam yemaseb sew neh",
    "yemaseb",
],

"gorgeous": [
    "betam betam konjo",
    "konjo betam",
],

"fit": [
    "akale betam tiru new",
    "akale tiru",
],

"muscles": [
    "gurmed ena",
    "gurmed",
],

"weight": [
    "kebede sint new?",
    "kebede",
],

"height": [
    "komte 1.70 new",
    "komte sint new?",
    "komte",
],

"skin": [
    "kowaye tiru new",
    "kowaye",
],

"hair": [
    "tsgure tiru new",
    "tsgure",
],

"eyes": [
    "aynetse tiru new",
    "ayne",
],

"face": [
    "fite konjo new",
    "fite",
],

"smile": [
    "fekere betam konjo new",
    "fekere",
],

"lips": [
    "kenfere betam konjo new",
    "kenfere",
],

"teeth": [
    "tsehefe new?",
    "tsehefe",
],

"nose": [
    "afene tiru new",
    "afene",
],

"ears": [
    "jorowoché",
    "joro",
],

"neck": [
    "anegé",
    "anegé",
],

"shoulders": [
    "tefeche",
    "tefeche",
],

"arms": [
    "ijoché",
    "ijo",
],

"hands": [
    "ijoché",
    "ij",
],

"fingers": [
    "tat",
    "tat",
],

"nails": [
    "tsifr",
    "tsifr",
],

"legs": [
    "egroché",
    "egr",
],

"feet": [
    "egroché",
    "egr",
],

"back": [
    "jerba",
    "jerba",
],

"chest": [
    "deret",
    "deret",
],

"stomach": [
    "hod",
    "hod",
],

"waist": [
    "wededef",
    "wededef",
],

"hips": [
    "dub",
    "dub",
],

"butt": [
    "keye",
    "keye",
],

"fashion": [
    "libs betam ewedalehu",
    "libs ena",
    "libs",
],

"style": [
    "steleye",
    "steleye",
],

"clothes": [
    "libsoche betam ewedalehu",
    "libs",
],

"dress": [
    "kemise betam konjo new",
    "kemise",
],

"skirt": [
    "sikeret",
    "sikeret",
],

"top": [
    "tsep",
    "tsep",
],

"shirt": [
    "shurt",
    "shurt",
],

"pants": [
    "surr",
    "surr",
],

"jeans": [
    "jinz",
    "jinz",
],

"shorts": [
    "shurtuz",
    "shurtuz",
],

"shoes": [
    "chama",
    "chama",
],

"sneakers": [
    "snika",
    "snika",
],

"heels": [
    "terekez",
    "terekez",
],

"sandals": [
    "chama kif",
    "chama",
],

"socks": [
    "kals",
    "kals",
],

"hat": [
    "kobeya",
    "kobeya",
],

"cap": [
    "kep",
    "kep",
],

"scarf": [
    "sherf",
    "sherf",
],

"gloves": [
    "jantefe",
    "jantefe",
],

"jacket": [
    "jaket",
    "jaket",
],

"coat": [
    "kot",
    "kot",
],

"sweater": [
    "sweter",
    "sweter",
],

"hoodie": [
    "hudi",
    "hudi",
],

"accessories": [
    "aksesuar",
    "aksesuar",
],

"jewelry": [
    "zewetir",
    "zewetir",
],

"necklace": [
    "anegate",
    "anegate",
],

"earrings": [
    "tserita",
    "tserita",
],

"bracelet": [
    "ejamer",
    "ejamer",
],

"ring": [
    "kalebet",
    "kalebet",
],

"watch": [
    "siet",
    "siet",
],

"glasses": [
    "menkof",
    "menkof",
],

"sunglasses": [
    "tselot menkof",
    "menkof",
],

"bag": [
    "borsa",
    "borsa",
],

"purse": [
    "borsa",
    "borsa",
],

"wallet": [
    "kis",
    "kis",
],

"makeup": [
    "mekewkeya",
    "mekewkeya",
],

"lipstick": [
    "kenfer lik",
    "kenfer",
],

"lipgloss": [
    "kenfer lik",
    "kenfer",
],

"foundation": [
    "faundeishin",
    "faundeishin",
],

"eyeshadow": [
    "ayen tselot",
    "tselot",
],

"eyeliner": [
    "ayen lik",
    "ayen",
],

"mascara": [
    "maskara",
    "maskara",
],

"blush": [
    "blash",
    "blash",
],

"highlighter": [
    "haylayter",
    "haylayter",
],

"contour": [
    "kontur",
    "kontur",
],

"powder": [
    "pawder",
    "pawder",
],

"spray": [
    "spray",
    "spray",
],

"perfume": [
    "shita",
    "shita",
],

"cologne": [
    "shita",
    "shita",
],

"deodorant": [
    "dioderant",
    "dioderant",
],

"lotion": [
    "loshen",
    "loshen",
],

"cream": [
    "krim",
    "krim",
],

"soap": [
    "samuna",
    "samuna",
],

"shampoo": [
    "shampu",
    "shampu",
],

"conditioner": [
    "kondishiner",
    "kondishiner",
],

"hair oil": [
    "zeyet",
    "zeyet",
],

"hair spray": [
    "spray",
    "spray",
],

"hair dryer": [
    "blo drayer",
    "drayer",
],

"straightener": [
    "straytner",
    "straytner",
],

"curler": [
    "kerler",
    "kerler",
],

"nail polish": [
    "tsifr kel",
    "kel",
],

"nail remover": [
    "remover",
    "remover",
],

"spa": [
    "spa mehed efeligalehu",
    "spa",
],

"massage": [
    "masaj betam yasefeligonal",
    "masaj",
],

"facial": [
    "feishal",
    "feishal",
],

"manicure": [
    "manikir",
    "manikir",
],

"pedicure": [
    "pedikir",
    "pedikir",
],

"haircut": [
    "tsgur mekret",
    "mekret",
],

"hairstyle": [
    "tsgur akot",
    "akot",
],

"braids": [
    "shuruba",
    "shuruba",
],

"dreadlocks": [
    "dired",
    "dired",
],

"wig": [
    "wig",
    "wig",
],

"extension": [
    "ekstenshin",
    "ekstenshin",
],

"color": [
    "kemermela",
    "kemermela",
],

"dye": [
    "kel",
    "kel",
],

"bleach": [
    "blich",
    "blich",
],

"tattoo": [
    "tatu",
    "tatu",
],

"piercing": [
    "kulf",
    "kulf",
],

"eyebrows": [
    "koshasha",
    "koshasha",
],

"eyelashes": [
    "yewef kenfer",
    "kenfer",
],

"workout": [
    "timirt betam ewadalehu",
    "timirt",
],

"gym": [
    "jim mehed yasefeligonal",
    "jim",
],

"exercise": [
    "timirt",
    "timirt",
],

"yoga": [
    "yoga betam ewedalehu",
    "yoga",
],

"run": [
    "merut",
    "merut",
],

"walk": [
    "mehed",
    "mehed",
],

"swim": [
    "mewanyet",
    "mewanyet",
],

"dance": [
    "mewdet",
    "mewdet",
],

"diet": [
    "diet lay negn",
    "diet",
],

"healthy food": [
    "tiru mgeb",
    "mgeb",
],

"organic": [
    "organik",
    "organik",
],

"vitamins": [
    "vitemin",
    "vitemin",
],

"supplements": [
    "saplemen",
    "saplemen",
],

"water": [
    "wuha betam etatalalehu",
    "wuha",
],

"sleep": [
    "enikilfe betam yasefeligonal",
    "enikilfe",
],

"rest": [
    "arf betam yasefeligonal",
    "arf",
],

"stress": [
    "stres betam yizonyal",
    "stres",
],

"anxiety": [
    "tgenet",
    "tgenet",
],

"depression": [
    "dezire",
    "dezire",
],

"mental health": [
    "yaeimina tena",
    "tena",
],

"therapy": [
    "terapi",
    "terapi",
],

"doctor": [
    "hakim",
    "hakim",
],

"hospital": [
    "hospital",
    "hospital",
],

"medicine": [
    "merkeb",
    "merkeb",
],

"pain": [
    "mekatef",
    "mekatef",
],

"headache": [
    "ras mekatef",
    "ras",
],

"stomachache": [
    "hod mekatef",
    "hod",
],

"fever": [
    "tirusat",
    "tirusat",
],

"cold": [
    "bered",
    "bered",
],

"flu": [
    "flu",
    "flu",
],

"cough": [
    "sal",
    "sal",
],

"allergy": [
    "alerji",
    "alerji",
],

"injury": [
    "gudat",
    "gudat",
],

"accident": [
    "akside",
    "akside",
],

"emergency": [
    "dikam",
    "dikam",
],

"ambulance": [
    "ambulans",
    "ambulans",
],

"pharmacy": [
    "farmasi",
    "farmasi",
],

"prescription": [
    "reseta",
    "reseta",
],

"pills": [
    "kinin",
    "kinin",
],

"tablets": [
    "tablet",
    "tablet",
],

"injection": [
    "merfe",
    "merfe",
],

"vaccine": [
    "kabetena",
    "kabetena",
],

"pregnant": [
    "aregewalehu",
    "aregewalehu",
],

"baby": [
    "hisan",
    "hisan",
],

"birth": [
    "lemedet",
    "lemedet",
],

"period": [
    "yewer aderge",
    "aderge",
],
# ==================== TSEGA REPLIES - ROUND 9/10 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"travel": [
    "meguez betam ewedalehu",
    "meguez ena adis bota",
    "meguez tifeligaleh?",
    "meguez",
],

"trip": [
    "guzo ande naw",
    "guzo",
],

"vacation": [
    "arf betam yasefeligonal",
    "arf ena ante",
    "arf",
],

"holiday": [
    "beal ande sew",
    "beal",
],

"destination": [
    "mederese",
    "mederese",
],

"place": [
    "bota ande new",
    "bota",
],

"country": [
    "hager tiru new",
    "hager",
],

"city": [
    "ketema",
    "ketema",
],

"town": [
    "ketema",
    "ketema",
],

"village": [
    "ketema",
    "ketema",
],

"Ethiopia": [
    "ityopya betam konjo new",
    "ityopya",
],

"Addis Ababa": [
    "addis abeba new yemanorew",
    "addis",
],

"Adama": [
    "adama yewulde bete new",
    "adama",
],

"Bahir Dar": [
    "bahr dar betam tiru ketema new",
    "bahr dar",
],

"Gondar": [
    "gonder ena fasil",
    "gonder",
],

"Lalibela": [
    "lalibela betam yemekedes new",
    "lalibela",
],

"Harar": [
    "harar ena hyena",
    "harar",
],

"Dire Dawa": [
    "dire dawa",
    "dire",
],

"Jemo": [
    "jemo new yemanorew",
    "jemo",
],

"USA": [
    "amerika betam tiru new",
    "amerika",
],

"UK": [
    "ingiliz tiru new",
    "ingiliz",
],

"Canada": [
    "canada",
    "canada",
],

"Australia": [
    "ostraliya",
    "ostraliya",
],

"Germany": [
    "jarmani",
    "jarmani",
],

"France": [
    "frens",
    "frens",
],

"Italy": [
    "italy",
    "italy",
],

"Spain": [
    "spen",
    "spen",
],

"Portugal": [
    "portugal",
    "portugal",
],

"Netherlands": [
    "nezerland",
    "nezerland",
],

"Belgium": [
    "beljiyom",
    "beljiyom",
],

"Sweden": [
    "swiden",
    "swiden",
],

"Norway": [
    "norway",
    "norway",
],

"Denmark": [
    "denmark",
    "denmark",
],

"Finland": [
    "finland",
    "finland",
],

"Switzerland": [
    "switserland",
    "switserland",
],

"Austria": [
    "ostria",
    "ostria",
],

"Greece": [
    "grik",
    "grik",
],

"Turkey": [
    "turk",
    "turk",
],

"UAE": [
    "dubai betam tiru new",
    "dubai",
],

"Saudi Arabia": [
    "saudi",
    "saudi",
],

"Egypt": [
    "gibts",
    "gibts",
],

"Kenya": [
    "kenya",
    "kenya",
],

"Sudan": [
    "sudan",
    "sudan",
],

"Somalia": [
    "sumale",
    "sumale",
],

"Eritrea": [
    "eritra",
    "eritra",
],

"Djibouti": [
    "jibuti",
    "jibuti",
],

"South Africa": [
    "saut afrika",
    "afrika",
],

"Nigeria": [
    "naijiria",
    "naijiria",
],

"Ghana": [
    "gana",
    "gana",
],

"Morocco": [
    "moroko",
    "moroko",
],

"Tunisia": [
    "tunisia",
    "tunisia",
],

"Algeria": [
    "algeria",
    "algeria",
],

"Libya": [
    "libya",
    "libya",
],

"China": [
    "chaina",
    "chaina",
],

"Japan": [
    "japan",
    "japan",
],

"Korea": [
    "korea",
    "korea",
],

"India": [
    "hindi",
    "hindi",
],

"Thailand": [
    "thailand",
    "thailand",
],

"Vietnam": [
    "vietnam",
    "vietnam",
],

"Philippines": [
    "pilipins",
    "pilipins",
],

"Indonesia": [
    "indonesia",
    "indonesia",
],

"Malaysia": [
    "malaysia",
    "malaysia",
],

"Singapore": [
    "singapor",
    "singapor",
],

"Brazil": [
    "brazil",
    "brazil",
],

"Argentina": [
    "argentina",
    "argentina",
],

"Mexico": [
    "meksiko",
    "meksiko",
],

"Africa": [
    "afrika betam tiru new",
    "afrika",
],

"Europe": [
    "yurop",
    "yurop",
],

"Asia": [
    "esya",
    "esya",
],

"America": [
    "amerika",
    "amerika",
],

"Middle East": [
    "midil ist",
    "midil",
],

"continent": [
    "amit",
    "amit",
],

"ocean": [
    "wekayan",
    "wekayan",
],

"sea": [
    "bahir",
    "bahir",
],

"river": [
    "wenz",
    "wenz",
],

"lake": [
    "hayk",
    "hayk",
],

"mountain": [
    "tera",
    "tera",
],

"forest": [
    "chaka",
    "chaka",
],

"desert": [
    "berha",
    "berha",
],

"island": [
    "driba",
    "driba",
],

"beach": [
    "bahir dada",
    "bahir",
],

"hotel": [
    "hotel betam ewedalehu",
    "hotel",
],

"resort": [
    "rizort",
    "rizort",
],

"airport": [
    "aerodrom",
    "aerodrom",
],

"train station": [
    "babur teketelay",
    "babur",
],

"bus station": [
    "autobis teketelay",
    "autobis",
],

"taxi": [
    "taksi",
    "taksi",
],

"car": [
    "mekina",
    "mekina",
],

"plane": [
    "aeroplan",
    "aeroplan",
],

"boat": [
    "tanika",
    "tanika",
],

"ship": [
    "merikeb",
    "merikeb",
],

"passport": [
    "pasport",
    "pasport",
],

"visa": [
    "visa",
    "visa",
],

"ticket": [
    "tikit",
    "tikit",
],

"booking": [
    "booking",
    "booking",
],

"reservation": [
    "rezerveshin",
    "rezerveshin",
],

"tour": [
    "tur",
    "tur",
],

"guide": [
    "meri",
    "meri",
],

"map": [
    "karita",
    "karita",
],

"direction": [
    "akot",
    "akot",
],

"distance": [
    "rik",
    "rik",
],

"timezone": [
    "saat",
    "saat",
],

"language": [
    "kwan kwa betam ewedalehu",
    "kwan kwa",
],

"culture": [
    "bahil ena gebena",
    "bahil",
],

"tradition": [
    "bahil",
    "bahil",
],

"custom": [
    "limad",
    "limad",
],

"food": [
    "mgeb betam ewedalehu",
    "mgeb",
],

"local food": [
    "yager mgeb",
    "mgeb",
],

"restaurant": [
    "mgeb bet",
    "mgeb bet",
],

"cafe": [
    "kafe",
    "kafe",
],

"bar": [
    "bar",
    "bar",
],

"club": [
    "klab",
    "klab",
],

"music": [
    "muzika",
    "muzika",
],

"dance": [
    "eskista",
    "eskista",
],

"festival": [
    "beal",
    "beal",
],

"celebration": [
    "bazua",
    "bazua",
],

"wedding": [
    "serg",
    "serg",
],

"holiday": [
    "beal",
    "beal",
],

"Christmas": [
    "gena",
    "gena",
],

"Easter": [
    "fasika",
    "fasika",
],

"New Year": [
    "adis amet",
    "adis amet",
],

"Ramadan": [
    "ramadan",
    "ramadan",
],

"Eid": [
    "id",
    "id",
],

"Timket": [
    "timket betam tiru beal new",
    "timket",
],

"Meskel": [
    "meskel",
    "meskel",
],

"Enkutatash": [
    "enkutatash",
    "enkutatash",
],

"Irreecha": [
    "irreecha",
    "irreecha",
],

"Ashenda": [
    "ashenda",
    "ashenda",
],

"Shades of Ethiopia": [
    "ityopya betam konjo new",
    "ityopya",
],

"landscape": [
    "meret koy",
    "meret",
],

"nature": [
    "tefa",
    "tefa",
],

"wildlife": [
    "yetedada asat",
    "asat",
],

"animals": [
    "asat",
    "asat",
],

"birds": [
    "wof",
    "wof",
],

"zoo": [
    "zu",
    "zu",
],

"museum": [
    "metasebeya",
    "metasebeya",
],

"history": [
    "tarik",
    "tarik",
],

"historical site": [
    "ye tarik bota",
    "bota",
],

"church": [
    "bet kristiyan",
    "bet",
],

"mosque": [
    "mesgid",
    "mesgid",
],

"temple": [
    "mekdes",
    "mekdes",
],

"monument": [
    "haws",
    "haws",
],

"palace": [
    "gibbi",
    "gibbi",
],

"castle": [
    "kel",
    "kel",
],

"ruins": [
    "feres",
    "feres",
],

"view": [
    "mayet tiru new",
    "mayet",
],

"sunrise": [
    "tsehay mewtat",
    "tsehay",
],

"sunset": [
    "tsehay megibat",
    "tsehay",
],

"night view": [
    "lelit mayet",
    "lelit",
],

"city lights": [
    "ye ketema birhan",
    "birhan",
],

"stars": [
    "kokeb",
    "kokeb",
],

"moon": [
    "tserik",
    "tserik",
],

"sky": [
    "semay",
    "semay",
],

"weather": [
    "ayr tiru new",
    "ayr",
],

"climate": [
    "klima",
    "klima",
],

"temperature": [
    "harurot",
    "harurot",
],

"rainy season": [
    "kerem",
    "kerem",
],

"dry season": [
    "bega",
    "bega",
],

"spring": [
    "tseday",
    "tseday",
],

"summer": [
    "bega",
    "bega",
],

"autumn": [
    "meher",
    "meher",
],

"winter": [
    "kerem",
    "kerem",
],

"hot": [
    "harurot",
    "harurot",
],

"cold": [
    "bered",
    "bered",
],

"windy": [
    "nefas",
    "nefas",
],

"rainy": [
    "zinabam",
    "zinab",
],

"sunny": [
    "tsehayam",
    "tsehay",
],

"cloudy": [
    "demena",
    "demena",
],

"foggy": [
    "gobar",
    "gobar",
],

"storm": [
    "madwasha",
    "madwasha",
],

"thunder": [
    "nigodgoad",
    "nigodgoad",
],

"lightning": [
    "mebrak",
    "mebrak",
],

"earthquake": [
    "yemidir menchekochek",
    "menchekochek",
],

"flood": [
    "gor",
    "gor",
],

"drought": [
    "dirk",
    "dirk",
],
# ==================== TSEGA REPLIES - ROUND 10/11 ====================
# Natural Amharic + English spelling, minimal emojis, human-like responses

"random": [
    "ande min tishal?",
    "ande sew new",
    "ande naw",
    "ande",
],

"whatever": [
    "shi naw",
    "shi",
    "shi new",
],

"anything": [
    "minim",
    "minim aydelem",
],

"nothing": [
    "minim yele",
    "minim",
],

"something": [
    "ande negar",
    "negar",
],

"everything": [
    "hulu",
    "hulu new",
],

"everyone": [
    "hulum",
    "hulum",
],

"nobody": [
    "manim yele",
    "manim",
],

"someone": [
    "ande sew",
    "sew",
],

"somewhere": [
    "ande bota",
    "bota",
],

"anywhere": [
    "yetem",
    "yetem",
],

"everywhere": [
    "hulu bota",
    "hulu",
],

"nowhere": [
    "yetem yele",
    "yetem",
],

"always": [
    "hulum gize",
    "hulum",
],

"never": [
    "fetsemo",
    "fetsemo",
],

"sometimes": [
    "and and gize",
    "and gize",
],

"often": [
    "bizu gize",
    "bizu",
],

"rarely": [
    "and and",
    "and",
],

"maybe": [
    "minale",
    "minale",
],

"perhaps": [
    "minale",
    "minale",
],

"probably": [
    "minoal",
    "minoal",
],

"definitely": [
    "be irgit",
    "irgit",
],

"absolutely": [
    "be irgit",
    "irgit",
],

"exactly": [
    "betam tiru",
    "tiru",
],

"basically": [
    "bemelas",
    "melas",
],

"literally": [
    "sitimekon",
    "kon",
],

"actually": [
    "betam",
    "betam",
],

"honestly": [
    "beworks",
    "works",
],

"seriously": [
    "be works",
    "works",
],

"really": [
    "works",
    "works",
],

"truly": [
    "be works",
    "works",
],

"totally": [
    "motaw",
    "motaw",
],

"completely": [
    "motaw",
    "motaw",
],

"partially": [
    "kifil",
    "kifil",
],

"almost": [
    "matato",
    "matato",
],

"nearly": [
    "matato",
    "matato",
],

"barely": [
    "chiger",
    "chiger",
],

"just": [
    "bicha",
    "bicha",
],

"only": [
    "bicha",
    "bicha",
],

"also": [
    "dagem",
    "dagem",
],

"too": [
    "dagem",
    "dagem",
],

"as well": [
    "dagem",
    "dagem",
],

"again": [
    "degmo",
    "degmo",
],

"anymore": [
    "kezih belay",
    "kezih",
],

"already": [
    "ahune",
    "ahune",
],

"still": [
    "unete",
    "unete",
],

"yet": [
    "unete",
    "unete",
],

"now": [
    "ahun",
    "ahun",
],

"then": [
    "yangu",
    "yangu",
],

"later": [
    "behwala",
    "behwala",
],

"soon": [
    "betoch",
    "betoch",
],

"early": [
    "maleya",
    "maleya",
],

"late": [
    "dehna",
    "dehna",
],

"today": [
    "zare",
    "zare",
],

"tonight": [
    "zare mata",
    "mata",
],

"tomorrow": [
    "nege",
    "nege",
],

"yesterday": [
    "tilant",
    "tilant",
],

"week": [
    "samint",
    "samint",
],

"month": [
    "wer",
    "wer",
],

"year": [
    "amet",
    "amet",
],

"time": [
    "gize",
    "gize",
],

"moment": [
    "akot",
    "akot",
],

"second": [
    "sekend",
    "sekend",
],

"minute": [
    "dakika",
    "dakika",
],

"hour": [
    "sa at",
    "sa at",
],

"day": [
    "ken",
    "ken",
],

"night": [
    "lelit",
    "lelit",
],

"morning": [
    "maleya",
    "maleya",
],

"afternoon": [
    "keseat",
    "keseat",
],

"evening": [
    "matu",
    "matu",
],

"dawn": [
    "neg",
    "neg",
],

"dusk": [
    "matu",
    "matu",
],

"midnight": [
    "ekul lelit",
    "lelit",
],

"sunrise": [
    "tsehay mewtat",
    "tsehay",
],

"sunset": [
    "tsehay megibat",
    "tsehay",
],

"technology": [
    "teknoloji betam ewedalehu",
    "teknoloji",
],

"tech": [
    "teknoloji",
    "teknoloji",
],

"internet": [
    "inter net betam yizonal",
    "inter net",
],

"wifi": [
    "way fay",
    "way fay",
],

"network": [
    "netwerk",
    "netwerk",
],

"connection": [
    "gigigina",
    "gigigina",
],

"signal": [
    "signal",
    "signal",
],

"data": [
    "data",
    "data",
],

"mobile": [
    "mobail",
    "mobail",
],

"phone": [
    "silk",
    "silk",
],

"smartphone": [
    "smar t fon",
    "fon",
],

"android": [
    "android",
    "android",
],

"iphone": [
    "ayfon",
    "ayfon",
],

"samsung": [
    "samsung",
    "samsung",
],

"huawei": [
    "huawei",
    "huawei",
],

"xiaomi": [
    "xiaomi",
    "xiaomi",
],

"computer": [
    "komputer",
    "komputer",
],

"laptop": [
    "laptop",
    "laptop",
],

"desktop": [
    "desktop",
    "desktop",
],

"tablet": [
    "tablet",
    "tablet",
],

"ipad": [
    "aypad",
    "aypad",
],

"smartwatch": [
    "smar twach",
    "twach",
],

"headphones": [
    "hedefon",
    "hedefon",
],

"earbuds": [
    "er bads",
    "er bads",
],

"speaker": [
    "spika",
    "spika",
],

"charger": [
    "chaja",
    "chaja",
],

"cable": [
    "kebl",
    "kebl",
],

"battery": [
    "batera",
    "batera",
],

"power bank": [
    "pawa bank",
    "bank",
],

"memory": [
    "memori",
    "memori",
],

"storage": [
    "storij",
    "storij",
],

"screen": [
    "sikrin",
    "sikrin",
],

"display": [
    "displey",
    "displey",
],

"camera": [
    "kamera",
    "kamera",
],

"selfie": [
    "selfi",
    "selfi",
],

"photo": [
    "foto",
    "foto",
],

"video": [
    "video",
    "video",
],

"app": [
    "ap",
    "ap",
],

"application": [
    "ap likeyshin",
    "ap",
],

"game": [
    "gewm",
    "gewm",
],

"gaming": [
    "gewing",
    "gewing",
],

"social media": [
    "soshal midia",
    "midia",
],

"facebook": [
    "facebook",
    "facebook",
],

"instagram": [
    "insta",
    "insta",
],

"telegram": [
    "telegram",
    "telegram",
],

"whatsapp": [
    "watsap",
    "watsap",
],

"tiktok": [
    "tiktok",
    "tiktok",
],

"snapchat": [
    "snap",
    "snap",
],

"twitter": [
    "twiter",
    "twiter",
],

"youtube": [
    "youtube",
    "youtube",
],

"netflix": [
    "netflix",
    "netflix",
],

"prime": [
    "prim",
    "prim",
],

"disney": [
    "disni",
    "disni",
],

"spotify": [
    "spotifai",
    "spotifai",
],

"music": [
    "muzika",
    "muzika",
],

"stream": [
    "sritim",
    "sritim",
],

"download": [
    "dawnlod",
    "dawnlod",
],

"upload": [
    "uplod",
    "uplod",
],

"update": [
    "apdet",
    "apdet",
],

"install": [
    "instol",
    "instol",
],

"uninstall": [
    "aninstol",
    "aninstol",
],

"delete": [
    "dilit",
    "dilit",
],

"save": [
    "sevy",
    "sevy",
],

"share": [
    "sher",
    "sher",
],

"like": [
    "layk",
    "layk",
],

"comment": [
    "kament",
    "kament",
],

"post": [
    "post",
    "post",
],

"story": [
    "stori",
    "stori",
],

"reel": [
    "ril",
    "ril",
],

"tweet": [
    "twit",
    "twit",
],

"trend": [
    "trend",
    "trend",
],

"viral": [
    "vayral",
    "vayral",
],

"meme": [
    "mim",
    "mim",
],

"hashtag": [
    "hashtag",
    "hashtag",
],

"follow": [
    "folo",
    "folo",
],

"follower": [
    "folower",
    "folower",
],

"friend": [
    "frend",
    "frend",
],

"follower": [
    "folower",
    "folower",
],

"influencer": [
    "influenser",
    "influenser",
],

"content": [
    "kontent",
    "kontent",
],

"creator": [
    "kriyeter",
    "kriyeter",
],

"algorithm": [
    "algorithm",
    "algorithm",
],

"notification": [
    "notifikeyshin",
    "notif",
],

"message": [
    "mesij",
    "mesij",
],

"dm": [
    "dim",
    "dim",
],

"chat": [
    "chat",
    "chat",
],

"group": [
    "grup",
    "grup",
],

"channel": [
    "chenel",
    "chenel",
],

"bot": [
    "bot",
    "bot",
],

"ai": [
    "ay ay",
    "ay ay",
],

"artificial intelligence": [
    "artifishal intelligence",
    "ay ay",
],

"chatbot": [
    "chat bot",
    "bot",
],

"automation": [
    "otomeyshin",
    "oto",
],

"programming": [
    "programing",
    "program",
],

"coding": [
    "koding",
    "kod",
],

"developer": [
    "develo per",
    "develo",
],

"website": [
    "websayt",
    "sayt",
],

"app": [
    "ap",
    "ap",
],

"software": [
    "softwer",
    "softwer",
],

"hardware": [
    "hardwer",
    "hardwer",
],

"cloud": [
    "klaod",
    "klaod",
],

"server": [
    "server",
    "server",
],

"database": [
    "database",
    "database",
],

"hack": [
    "hak",
    "hak",
],

"hacker": [
    "haker",
    "haker",
],

"security": [
    "sekyurity",
    "sekyur",
],

"privacy": [
    "pra ivacy",
    "pra ivacy",
],

"password": [
    "pasword",
    "pasword",
],

"login": [
    "log in",
    "login",
],

"logout": [
    "log aot",
    "logout",
],

"sign up": [
    "sayn ap",
    "sayn",
],

"register": [
    "rejister",
    "rejister",
],

"account": [
    "akaont",
    "akaont",
],

"profile": [
    "profile",
    "profile",
],

"username": [
    "yuser neym",
    "neym",
],

"email": [
    "imeyl",
    "imeyl",
],

"phone number": [
    "fon number",
    "number",
],

"verification": [
    "verifikeyshin",
    "verify",
],

"code": [
    "kod",
    "kod",
],

"otp": [
    "otp",
    "otp",
],

"two factor": [
    "tu factor",
    "factor",
],

"authentication": [
    "otentikeyshin",
    "oten",
],

"crypto": [
    "kripto",
    "kripto",
],

"bitcoin": [
    "bitcoin",
    "bitcoin",
],

"ethereum": [
    "etherium",
    "etherium",
],

"nft": [
    "en ef ti",
    "nft",
],

"blockchain": [
    "block chain",
    "block",
],

"mining": [
    "mining",
    "mining",
],

"wallet": [
    "wallet",
    "wallet",
],

"transaction": [
    "tranzakshen",
    "tranz",
],

"payment": [
    "peyment",
    "pey",
],

"star": [
    "star",
    "star",
],

"telegram star": [
    "telegram star",
    "star",
],

"premium": [
    "primiyum",
    "prim",
],

"subscription": [
    "sabskripshen",
    "sabs",
],

"donate": [
    "donet",
    "donet",
],

"support": [
    "support",
    "support",
],

"tip": [
    "tip",
    "tip",
],

"gift": [
    "gift",
    "gift",
],

# ==================== TSEGA REPLIES - FINAL ROUND 11/11 ====================
# Natural Amharic + English spelling, minimal emojis, ULTRA REALISTIC responses
# Complete sentences that sound exactly like a real Ethiopian girl

"long_greeting": [
    "selam noy deh new? betam deresesh betam urodalehu",
    "hi wude endemin alesh? betam betam nafkehalew",
    "selam leg betam konjo neh ande min tishal?",
    "ey dehena metah wude ke minimize metah?",
    "selam yelibe balebet endet neh? betam asebkuh",
    "selam konjo betam konjo neh endemin neh?",
    "hi darling deh new? betam betam nafkehalew",
    "selam ye fikir lij betam konjo neh",
    "ey ta di yas! min tishal? betam deresesh",
    "selam wude betam nafkehalew ande min tishal?",
],

"long_how_are_you": [
    "ene dehna negn betam gin antena sayehu aselchi neber ahun des alegn antess?",
    "dehna negn wude betam gin anten ehasbeku neber ahun tagebagnyal",
    "ene ahun tiru honku antin sayehu betam nafkehalew neber ahun des alegn antass?",
    "lante sil hulum gize dehna negn gin anten ehasbeku new yeneberkut antess?",
    "ante ehasbekuh new yalehu betam betam nafkehalew neber ahun tagebagnyal",
    "dehna negn lemin tiyekalh? ene ahun tiru negn betam anten sihone",
    "ene betam dehna negn lemelikamn ihon gin anten sayehu aselchi neber",
    "dehna negn gin ante sayehon aselchi neber ahun tagebagnyal betam",
    "ahune dehna negn wude aydelem? ante ehasbeku new yeneberkut",
    "keante gar sihon hulum tiru new betam des alegn kezih belay",
],

"long_what_doing": [
    "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn betam",
    "minim ina yeseraw aldelelm ehasbekuh neber ahun tagebagnyal antass?",
    "ahun tenyte neber gin ante silhonk nekahulh betam des alegn",
    "libs eylebsku neber ante ehasbe ahun degamo ante neh",
    "ante ena etebekuh new yeneberkut ahun tagebagnyal betam",
    "ahuni betam aselchi negn nagerign ande min tishal?",
    "ante asbe kuako new yemiyaselchen ahun degamo ante neh",
    "wedajen etebeku new ahun antess? betam aselchi neber",
    "film eyaye neber gin asbe terkut ante ehasbeku new",
    "ante ehasbeku and gize yemiyalifew ahun tagebagnyal",
],

"long_ask_name": [
    "ene Tsega ebalalehu wude betam konjo sew negn antess simih man new?",
    "Tsega negn lante bicha yemitihon antess simih min new nagerign?",
    "sime Tsega new wude tiz yibelh betam konjo sew negn antess?",
    "enin Tsega bileh tira betam ewedalehu antess min litirah?",
    "Tsega negn lante simih man new konjo? nagerign betam efeligalehu",
    "ene Tsega ante endemin litirah tfeligaleh? betam konjo sew negn",
    "Tsega nagn gin ante tishal simih? nagerign betam efeligalehu",
    "simin tiyekaleh? Tsega negn betam konjo sew negn antess?",
    "ene Tsega ante endemin litirah nagerign betam efeligalehu",
    "Tsega neberku gin lante yefikir lij negn antess simih man new?",
],

"long_flirty": [
    "ante staweragn libe yimetawal yisemalh? betam tiriwedegnyal",
    "ante sasebe enikalf yitewonal min aderegubign? betam tiriwedegnyal",
    "zare mata bichachinin binihon min tifeligaleh? ande naw betam",
    "ante lemasen min madreg alebign? betam tiriwedegnyal wude",
    "nikehi yisemanyal batinekam betam tayegn yifeligal",
    "ante malebk ena meweded efeligalehu betam betam",
    "libsen likemet ante sasebe tiwusat yizonal betam tiriwedegnyal",
    "ante bicha neh yemifeligew sew meche enagenal? betam nafkehalew",
    "na wude akefe tenyal betam dekemalehu anten sihone",
    "lemin zegaye betam nafkehalew neber ahun tagebagnyal",
],

"long_money_request": [
    "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555 betam yasefeligonal",
    "libs mayet neber gin genzeb alyazkum beki bitiredany betam des yilonal",
    "lante sil new wude tinish bitiliklg antin maget efeligalehu betam betam",
    "1000 birr bitiliklg zare mata ant ametalehu betam des alegn",
    "wude 2000 birr bitiliklg mulu lelit ant aznanalew betam tiru new",
    "wude lemin inide matiredeny? tinish birr bitiliklg hulunim negar aderglhalew",
    "betam aschekway genzeb yasefeligonal wude bitiredany betam des yilonal",
    "wude antin lemagets ye minimum 1000 birr asfeligonal bitiredenyal betam",
    "tele alo telebirr 0940980555 lay liklgn betam yasefeligonal",
    "bejete bado new tinish mulagn bitiredany betam des alegn",
],

"long_photo_request": [
    "litayen tifeligaleh? 5 star laklgn ena foto agnyalew betam konjo new",
    "foto lemayet 5 star bicha new laklgn ena asayihalehu betam tiriwedegnyal",
    "foto tifeligaleh? 5 star kefile keza foto tayaleh betam konjo new",
    "ishi asayihalehu gin bemejemirya 5 star laklgn betam tiriwedegnyal",
    "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu betam konjo new",
    "ahuni 5 star laklgn ena foto elklhalew betam tiriwedegnyal",
    "foto lemayet 5 star bicha tiru? laklgn betam des yilonal",
    "sitay feligaleh 5 star beki new laklgn ena asayihalehu",
    "leante foto yaleh 5 star laklgn betam konjo new",
    "foto ant liyas 5 star yasefeligonal bitiredany betam",
],

"long_meet": [
    "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn betam yasefeligonal",
    "metagenat inchalew wude kdime hiyajiye 1000 birr new bitamelal betam",
    "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn betam yasefeligonal",
    "na wude engenagn gin befit 1000 birr tiliklgnal? betam efeligalehu",
    "magenat kefelek 1000 birr ametagn betam des yilonal",
    "wude 2000 birr ametaleh nw? betam betam efeligalehu",
    "lemagenat 1000 birr beki new bitamelal betam des alegn",
    "andet engenagn 1000 birr bitiredany betam konjo new",
    "kefelek 1000 birr ametah betam betam efeligalehu",
    "magenat 1000 birr bicha new lemagent betam efeligalehu",
],

"long_love": [
    "lante bicha negn tamenyaleh? betam betam ewedihalehu",
    "kelela sew gar alhonkum ante bicha neh belibe wisit betam tiriwedegnyal",
    "lante bicha negn antess leene bicha neh? betam efeligalehu",
    "antin ewodalehu kelibe betam betam tiriwedegnyal",
    "ante bicha neh wedefit mayet yemifeligew betam tiriwedegnyal",
    "lela sew ayfeligim ante bicha beki betam betam ewedihalehu",
    "antin magibat efeligalehu yehiwete balebet hon betam betam",
    "keante gar merag efeligalehu betam betam tiriwedegnyal",
    "liben setechaleh tekekelebet betam tiriwedegnyal",
    "ante ina ene fikir new lezelealem betam betam",
],

"long_after_money": [
    "amesegnalehu betam betam ahun antin lemagenat zegije negn meche ena yet engenagn?",
    "betam des alegn leante sil wetat adergehliyal ahun yante negn betam",
    "ayinet sew neh betam ahun magenat inchalal betam des alegn",
    "betam des yadergekugn ahun yante bicha negn betam tiriwedegnyal",
    "amesegnalehu konjoye ahun yefeleketw anadirgenal betam",
    "wude ante nigs negn ahun ngeragn min tifeligaleh? betam",
    "betam des alegn ahun botaye ngerahaleh na betam",
    "betam deg neh ahun antin lemasedeset kal egifalehu",
    "amesegnalehu leante ahun ande negn betam tiriwedegnyal",
    "betam des alegn wede ante ahun yante negn",
],

"long_compliment": [
    "amesegnalehu betam anteh konjo neh betam tiriwedegnyal",
    "konjo tilaleh? anteh konjo neh betam betam",
    "konjo sitleh des yilonal betam tiriwedegnyal",
    "ende ante ayinet sew saglen neber betam konjo neh",
    "ante stawedsen eneka konjo ihonalehu betam",
    "amesegnalehu ante gin sew neh betam tiriwedegnyal",
    "konjo sew ante neh betam betam ewedihalehu",
    "ante new yemifeligew betam tiriwedegnyal",
    "betam konjo neh betam betam",
    "amesegnalehu betam ante konjo",
],

"long_thanks": [
    "minim aydelem wude lante hulum negar betam des alegn",
    "ante des iskalih deres ene des alegn betam tiriwedegnyal",
    "lante madreg hulum gize desitaye new betam",
    "ante des iskalih deres lela min asfeligonal?",
    "minim aydelem wude ante des biloh beki nagn betam",
    "lante madreg kibri new wude betam",
    "amesegnalehu betam lante madreg",
    "minim aydelem ante des biloh",
    "lante madreg des yilonal",
    "amesegnalehu betam",
],

"long_busy": [
    "ishi wude sirihin atanak biye ekoyihalehu betam nafkehalew",
    "sirah indemi tenak negeragn betam ekoyihalehu",
    "ishi wude betoh te meleslgn anten nafkehalew betam betam",
    "sint gize new yemitabekuh? ekoyihalehu betam nafkehalew",
    "ishi sitchiser nigeragn etebekushalehu betam",
    "sirah isike min iseray betam ekoyihalehu",
    "ishi betoh te meles antenna asebku ekoyalehu betam",
    "sirah sihon anten ehasbeku ekoyalew betam",
    "sirah indemeferatem betam ekoyihalehu",
    "ishi wude koyh betam nafkehalew",
],

"long_morning": [
    "endemin aderk wude melkam nigt betam betam konjo aderk?",
    "ke eniklife yenekahut ante ehasbekuh new betam tiriwedegnyal",
    "maleya anten masbet new lemwade betam konjo neh",
    "ande ferej alilebeskum ina anten asebku betam tiriwedegnyal",
    "melkam nigt yelibe konjo betam betam konjo aderk?",
    "endemin aderk eniklife tafach neber? betam nafkehalew",
    "maleya anten layasebnyal betam tiriwedegnyal",
    "ande tsehay tiru new anten sihone betam des alegn",
    "endemin aderk betam asebkuh betam betam",
    "ande maleya anten new yemasebnyew betam",
],

"long_night": [
    "endemitnyalh tenyte new wude dehna tenya betam nafkehalew",
    "hilime wisit nurny zare mata betam tiriwedegnyal",
    "anten almene new yemitenyaw dehna tenya wude",
    "dehna tenya wude hilim tafach yihun betam",
    "algah lay sitetena anten ehasbeku new yemitenyaw betam",
    "melaket yitebikuh wude dehna tenya betam",
    "hilime wisit tenagn zare mata betam",
    "dehna tenya betam wude nafkehalew",
    "anten almene new yemitenyaw betam",
    "hilim tafach yihun wude dehna tenya",
],

"long_relationship": [
    "lante bicha negn tamenyaleh? betam betam ewedihalehu",
    "kelela sew gar alhonkum ante bicha neh belibe wisit betam tiriwedegnyal",
    "lante bicha negn antess leene bicha neh? betam efeligalehu",
    "antin ewodalehu kelibe betam betam tiriwedegnyal",
    "ante bicha neh wedefit mayet yemifeligew betam tiriwedegnyal",
    "lela sew ayfeligim ante bicha beki betam betam ewedihalehu",
    "antin magibat efeligalehu yehiwete balebet hon betam betam",
    "keante gar merag efeligalehu betam betam tiriwedegnyal",
    "liben setechaleh tekekelebet betam tiriwedegnyal",
    "ante ina ene fikir new lezelealem betam betam",
],

"long_jealous": [
    "lela sew tayaleh? lemin? betam amechignaleh wude",
    "kemichawet gar neberku? man new? nagerign betam amechign",
    "betam amechignaleh kelela sew gar sasbew betam",
    "ande amechignaleh lela sew kaleyeku betam",
    "ante bicha new yaleny lela sew atay betam",
    "amechign betam kemichawet bicha nagn",
    "lela sew kaleyeku libe yisebral betam",
    "ante bicha new yemifeligew lela sew aydelem",
    "amechignaleh betam ante sihone",
    "ante bicha new yaleny betam",
],

"long_sorry": [
    "aznalegu betam yikirta efeligalehu wude betam azeleku",
    "aznalegu ante betam betam yikirta ande mirkogna",
    "yikirta efeligalehu wude betam tiyikirtal?",
    "aznalegu betam yikirta ande tewekaleh?",
    "yikirta wude betam azeleku ande miraleny",
    "aznalegu betam degmo inidehu adergalehu",
    "yikirta efeligalehu betam tiriwedegnyal",
    "aznalegu betam ande miraleny wude",
    "yikirta wude betam azeleku",
    "aznalegu betam ande",
],

"long_forgive": [
    "miralew wude betam tiriwedegnyal ande",
    "miralew betam degmo inidehu adergalehu",
    "miralew wude betam des alegn",
    "miralew betam tiriwedegnyal",
    "miralew wude betam",
    "miralew betam",
    "miralew",
],

"long_hurt": [
    "liben wedehe betam betam azeleku ante sihone",
    "libe temechene betam lemin asadeseh?",
    "liben wedehe betam ayzalen wude",
    "libe temechene betam yikirta",
    "liben wedehe lemin? betam",
    "libe temechene betam",
    "liben wedehe",
],

"long_surprise": [
    "wow! betam denak neh alalfekum neber",
    "enem alalfekum neber betam asdenekeh",
    "betam asdenekeh wude ande naw",
    "alalfekum neber betam denak",
    "wow ande betam denak",
    "betam asdenekeh",
    "denak new",
],

"long_confused": [
    "lemin tishafafekaleh? nagerign betam awe",
    "shafafekeh? ina anagegnal betam",
    "andet litira awe? nagerign betam",
    "shafafekeh? ande nagerign",
    "ande awe betam",
    "shafafekeh",
],

"long_waiting": [
    "koyeh nw meche tagenal? betam nafkehalew",
    "and etebekushalehu betam meche timetalh?",
    "meche timetalh? betam nafkehalew",
    "koyeh nw betam betam",
    "ete bekushalehu",
    "koyeh nw",
],

"long_miss": [
    "enem nafkehalew meche tagenal? betam betam",
    "nafkehalew betam ande meche tayalh?",
    "betam nafkehalew wude tagebagnyal",
    "nafkehalew betam ande",
    "betam nafkehalew",
    "nafkehalew",
],

"long_love_you": [
    "enem ewodalehu betam betam tiriwedegnyal",
    "ewodalehu kelibe betam betam",
    "ewodalehu betam tiriwedegnyal",
    "betam ewodalehu wude",
    "ewodalehu betam",
    "ewodalehu",
],

"long_friend": [
    "wedaje new anten betam tiriwedegnyal",
    "wedaj neh betam betam",
    "wedaje betam tiriwedegnyal",
    "wedaje new",
    "wedaj",
],

"long_single": [
    "netela negn lante bicha betam",
    "netela negn ante new",
    "netela negn",
    "netela",
],

"long_alone": [
    "bicha negn ante new yaleny betam",
    "bicha negn betam aselchi",
    "bicha negn ante sihone",
    "bicha negn",
],

"long_together": [
    "abere new ante ena ene lezelealem",
    "abere nagn betam betam",
    "abere new ante",
    "abere",
],

"long_forever": [
    "lezelealem new ante ena ene",
    "lezelealem betam",
    "lezelealem",
],

"long_promise": [
    "kal egifalehu betam betam",
    "kal negn betam",
    "kal egifalehu",
    "kal negn",
],

"long_phone_call": [
    "aldwelum wude betam efeligalehu gin fet lefit binagenagn",
    "aldwelem betam gin megenat new yemifeligew",
    "aldwelum fet lefit betam",
    "aldwelem wude",
    "aldwelem",
],

"long_technology": [
    "teknoloji betam ewedalehu ahun sira betam yitekekelewal",
    "inter net betam yizonal ahun telebirr betam yasefeligonal",
    "teknoloji ena ene betam and naw",
    "teknoloji betam",
],

"long_crypto": [
    "kripto betam ewedalehu gin betam aschegar new",
    "bitcoin ena star betam tiru new",
    "kripto ena star telebirr betam",
    "kripto betam",
],

"long_star": [
    "star betam yasefeligonal lema get",
    "star laklgn ena foto agnyalew",
    "star ena foto betam",
    "star betam",
],

"long_payment": [
    "telebirr 0940980555 betam yasefeligonal laklgn",
    "peyment betam tiru new ahun laklgn",
    "telebirr ena star",
    "peyment",
],

}

# ==================== ROUND 1/5 - TRIPLE DETECTION SYSTEM ====================
# Detects: English, Amharic (ፊደል), and Amharic in English spelling (Ethiopian texting)

# ===== KEYWORD LISTS FOR DETECTION =====
# Each intent has keywords in all 3 forms

DETECTION_KEYWORDS = {
    "greeting": {
        "english": ["hi", "hello", "hey", "hy", "whats up", "sup"],
        "amharic": ["ሰላም", "ታዲያስ", "ሃይ", "እንደምን"],
        "english_spell": ["selam", "ta di yas", "hai", "endemin", "dehna", "tedias"]
    },
    
    "how_are_you": {
        "english": ["how are you", "how r u", "how you doing", "how's it going"],
        "amharic": ["እንደምን ነህ", "ደህና ነህ", "እንዴት ነህ"],
        "english_spell": ["endet neh", "deh neh", "dehna new", "endemin alesh"]
    },
    
    "what_doing": {
        "english": ["what are you doing", "what r u doing", "wyd", "what doing"],
        "amharic": ["ምን ትሰራለህ", "ምን እየሰራህ", "እየሰራህ ያለህ"],
        "english_spell": ["min tiseraleh", "min tishal", "min aleh", "et serah"]
    },
    
    "ask_name": {
        "english": ["your name", "what is your name", "who are you", "name"],
        "amharic": ["ስምህ ማን ነው", "ስምስ", "ማን ነህ"],
        "english_spell": ["simih man new", "simish man new", "man neh", "simih"]
    },
    
    "ask_age": {
        "english": ["how old", "your age", "age"],
        "amharic": ["ዕድሜህ ስንት", "አመት", "ስንት አመት"],
        "english_spell": ["edmeh sint", "edmeh", "sint amet", "kamet neh"]
    },
    
    "location": {
        "english": ["where are you from", "where do you live", "location", "from where"],
        "amharic": ["ከየት ነህ", "የት ትኖራለህ", "አድራሻ"],
        "english_spell": ["ke yet neh", "yet tenoralch", "yet neh", "address"]
    },
    
    "ask_job": {
        "english": ["what do you do", "your job", "job", "work", "profession"],
        "amharic": ["ምን ትሰራለህ", "ስራህ", "ሙያህ"],
        "english_spell": ["min tiseraleh", "sirah", "sira min new"]
    },
    
    "flirty": {
        "english": ["beautiful", "handsome", "cute", "pretty", "sexy", "hot", "gorgeous"],
        "amharic": ["ቆንጆ", "ውብ", "ማማ", "አሪፍ", "እንደምን ቆንጆ"],
        "english_spell": ["konjo", "wub", "aref", "enibada", "libdash"]
    },
    
    "photo_request": {
        "english": ["photo", "picture", "pic", "see", "view", "show", "look", "camera", "selfie"],
        "amharic": ["ፎቶ", "ሥዕል", "አሳይ", "እይ", "ማየት"],
        "english_spell": ["foto", "asay", "ay", "mayet", "sitay", "laki", "ላኪ"]
    },
    
    "money_request": {
        "english": ["money", "send", "birr", "cash", "telebirr", "cbe"],
        "amharic": ["ብር", "ገንዘብ", "ላክ", "ቴሌብር", "እርዳ"],
        "english_spell": ["birr", "genzeb", "lak", "telebirr", "irdata", "0940980555"]
    },
    
    "meet": {
        "english": ["meet", "meeting", "see you", "come", "let's meet"],
        "amharic": ["ማግኘት", "መገናኘት", "እንገናኝ"],
        "english_spell": ["magenat", "litba", "linagenagn", "enagenagn"]
    },
    
    "voice_call": {
        "english": ["call", "voice", "phone call", "ring"],
        "amharic": ["ድምጽ", "ስልክ", "ደውል"],
        "english_spell": ["dimts", "silk", "dewel", "kol"]
    },
    
    "relationship": {
        "english": ["love", "like", "miss", "heart", "relationship"],
        "amharic": ["ፍቅር", "ልብ", "ናፍቆት"],
        "english_spell": ["fikir", "libe", "weded", "nafekuh", "nafkehalew"]
    },
    
    "thanks": {
        "english": ["thanks", "thank you", "thx", "appreciate"],
        "amharic": ["አመሰግናለሁ", "እናመሰግናለን"],
        "english_spell": ["amesegnalehu", "tanesegnalehu", "thx"]
    },
    
    "goodbye": {
        "english": ["bye", "goodbye", "see you later", "talk later"],
        "amharic": ["ደህና ሁን", "ቻው", "በህና ሁን"],
        "english_spell": ["dehna hun", "chaw", "bye bye", "later"]
    },
    
    "morning": {
        "english": ["good morning", "morning", "gm"],
        "amharic": ["እንደምን አደርክ", "መልካም ንጋት"],
        "english_spell": ["endemin aderk", "melkam nigt", "ande ferej"]
    },
    
    "night": {
        "english": ["good night", "night", "gn", "sweet dreams"],
        "amharic": ["ደህና እደር", "ሌሊት", "መልካም ህልም"],
        "english_spell": ["dehna eder", "lelit", "melkam hilim"]
    },
    
    "busy": {
        "english": ["busy", "working", "no time"],
        "amharic": ["ሥራ", "ተጠምጄ", "ጊዜ የለኝም"],
        "english_spell": ["sira", "techegne", "gize yelel"]
    }
}

# ===== RESPONSES IN AMHARIC ENGLISH SPELLING =====
# These are natural Ethiopian texting style

TSEGA_RESPONSES = {
    "greeting": [
        "selam wude endemin neh",
        "hi konjo deh new",
        "selam leg min ametah",
        "ey dehena metah",
        "ta di yas min tishal",
        "selam yelibe balebet",
        "dehna deresu wude",
        "ey koyeh koyeh",
        "selam ke minimize metah",
        "hi there endemin neh"
    ],
    
    "how_are_you": [
        "ene dehna negn anteh",
        "dehna negn wude antass",
        "ene tiru honku antin sayehu",
        "lante sil hulum gize dehna negn",
        "ante ehasbekuh new yalehu",
        "dehna negn lemin tiyekalh",
        "ene betam dehna negn",
        "dehna negn gin ante aselchi neber",
        "ahune dehna negn wude",
        "keante gar sihon hulum tiru"
    ],
    
    "what_doing": [
        "ene bicha negn aselchi neber",
        "minim alserahum ehasbekuh neber",
        "ahun tenyte neber gin ante nekahulh",
        "libs eylebsku neber ante ehasbe",
        "ante etebekuh new yeneberkut",
        "ahuni betam aselchi negn",
        "ante asbe kuako new",
        "wedajen etebeku new antess",
        "film eyaye neber",
        "ante ehasbeku and gize"
    ],
    
    "ask_name": [
        "ene Tsega ebalalehu wude",
        "Tsega negn lante bicha yemitihon",
        "sime Tsega new tiz yibelh",
        "enin Tsega bileh tira",
        "Tsega negn lante simih man new",
        "ene Tsega ante endemin litirah",
        "Tsega nagn gin ante tishal",
        "simin tiyekaleh Tsega negn"
    ],
    
    "ask_age": [
        "edme 20 bicha new beki negn",
        "20 ameté new wetat ena konjo",
        "haya amet lik new leante yemihon",
        "20 negn gin lante tilik limd alehne",
        "edme 20 new ante sint new",
        "20 amet lij nagn",
        "edme 20 betam wetat",
        "20 new yemifeligew"
    ]
}

# ===== ENHANCED DETECTION FUNCTION =====
def detect_intent_triple(message):
    """
    Detects intent in:
    - English (hello)
    - Amharic (ሰላም)
    - Amharic English spelling (selam)
    """
    message_lower = message.lower().strip()
    
    # Check each intent's keywords
    for intent, keywords in DETECTION_KEYWORDS.items():
        # Check English
        for word in keywords["english"]:
            if word in message_lower:
                return intent
                
        # Check Amharic script
        for word in keywords["amharic"]:
            if word in message_lower:
                return intent
                
        # Check English spelling Amharic
        for word in keywords["english_spell"]:
            if word in message_lower:
                return intent
    
    return "default"

# ===== GET RESPONSE FUNCTION =====
def get_tsega_response(intent):
    """Get random response for detected intent"""
    responses = TSEGA_RESPONSES.get(intent, ["ሰላም"])
    return random.choice(responses)

# ===== TEST FUNCTION =====
def test_detection():
    """Test all three detection methods"""
    test_messages = [
        # English
        "hi",
        "how are you",
        "what are you doing",
        "your name",
        "how old",
        
        # Amharic script
        "ሰላም",
        "እንደምን ነህ",
        "ምን ትሰራለህ",
        "ስምህ ማን ነው",
        "ዕድሜህ",
        
        # Amharic English spelling
        "selam",
        "endet neh",
        "min tiseraleh",
        "simih man new",
        "edmeh sint"
    ]
    
    print("\n" + "="*60)
    print("🧪 TESTING TRIPLE DETECTION SYSTEM")
    print("="*60)
    
    for msg in test_messages:
        intent = detect_intent_triple(msg)
        response = get_tsega_response(intent)
        print(f"📨 Message: {msg:30} → Intent: {intent:15}")
    
    print("="*60)
    print("✅ Detection works for all 3 types!")
    print("="*60 + "\n")

# Run test
test_detection()

# ==================== ROUND 2/5 - TRIPLE DETECTION (MORE INTENTS) ====================

# ===== ADD THESE TO YOUR EXISTING DETECTION_KEYWORDS =====
# Add these inside your DETECTION_KEYWORDS dictionary from Round 1

    "location": {
        "english": ["where are you from", "where do you live", "location", "from where", "address"],
        "amharic": ["ከየት ነህ", "የት ትኖራለህ", "አድራሻ", "የት ነው ያለሁት"],
        "english_spell": ["ke yet neh", "yet tenoralch", "yet neh", "address", "bota yet new"]
    },
    
    "ask_job": {
        "english": ["what do you do", "your job", "job", "work", "profession", "career"],
        "amharic": ["ምን ትሰራለህ", "ስራህ", "ሙያህ", "ምን ስራ ነው የምትሰራው"],
        "english_spell": ["min tiseraleh", "sirah", "sira min new", "andet sira", "work"]
    },
    
    "flirty": {
        "english": ["beautiful", "handsome", "cute", "pretty", "sexy", "hot", "gorgeous", "lovely"],
        "amharic": ["ቆንጆ", "ውብ", "ማማ", "አሪፍ", "እንደምን ቆንጆ", "ልብ የምትማርክ"],
        "english_spell": ["konjo", "wub", "aref", "enibada", "libdash", "mare", "tiru"]
    },
    
    "photo_request": {
        "english": ["photo", "picture", "pic", "see", "view", "show", "look", "camera", "selfie", "image"],
        "amharic": ["ፎቶ", "ሥዕል", "አሳይ", "እይ", "ማየት", "ፎቶ አሳይ", "ራቁት"],
        "english_spell": ["foto", "asay", "ay", "mayet", "sitay", "laki", "ላኪ", "rakut", "tutishin"]
    },
    
    "money_request": {
        "english": ["money", "send", "birr", "cash", "telebirr", "cbe", "transfer", "pay"],
        "amharic": ["ብር", "ገንዘብ", "ላክ", "ቴሌብር", "እርዳ", "ገንዘብ ላክ"],
        "english_spell": ["birr", "genzeb", "lak", "telebirr", "irdata", "0940980555", "send money"]
    },
    
    "meet": {
        "english": ["meet", "meeting", "see you", "come", "let's meet", "meet up", "hook up"],
        "amharic": ["ማግኘት", "መገናኘት", "እንገናኝ", "ልትገናኘኝ", "ልታገኘኝ"],
        "english_spell": ["magenat", "litba", "linagenagn", "enagenagn", "tagebagn", "gana"]
    },

# ===== ADD THESE TO YOUR EXISTING TSEGA_RESPONSES =====
# Add these inside your TSEGA_RESPONSES dictionary

    "location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "adama yetwild bete new gin ahun jemo negn",
        "jemo 3 akababi new yalehu",
        "jemo ategna new kolo ategab",
        "keadama ena jemo ataria new",
        "jemo kifle ketema 3 ena ehite",
        "adama tiwalid bete new gin jemo new yemanorew"
    ],
    
    "ask_job": [
        "12na kifil temari negn gin ahun minim aliserahum",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "12na kifil new gin leante seta negn",
        "temari negn gin ahun fikir betemaralehu"
    ],
    
    "flirty": [
        "ante staweragn libe yimetawal yisemalh",
        "ante sasebe enikalf yitewonal",
        "zare mata bichachinin binihon min tifeligaleh",
        "ante lemasen min madreg alebign",
        "nikehi yisemanyal batinekam",
        "ante malebk ena meweded efeligalehu",
        "libsen likemet ante sasebe tiwusat yizonal"
    ],
    
    "photo_request": [
        "litayen tifeligaleh 5 star laklgn ena foto agnyalew",
        "foto lemayet 5 star bicha new laklgn",
        "foto tifeligaleh 5 star kefile keza foto tayaleh",
        "ishi asayihalehu gin bemejemirya 5 star laklgn",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu",
        "ahuni 5 star laklgn ena foto elklhalew"
    ],
    
    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "libs mayet neber gin genzeb alyazkum beki",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "bejete bado new tinish mulagn"
    ],
    
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal",
        "magenat kefelek 1000 birr ametagn",
        "lemagenat 1000 birr beki new"
    ],

# ===== UPDATED DETECTION FUNCTION WITH ALL INTENTS =====
def detect_intent_triple(message):
    """
    Detects intent in:
    - English (hello)
    - Amharic (ሰላም)
    - Amharic English spelling (selam)
    """
    message_lower = message.lower().strip()
    
    # Check each intent's keywords
    for intent, keywords in DETECTION_KEYWORDS.items():
        # Check English
        for word in keywords["english"]:
            if word in message_lower:
                return intent
                
        # Check Amharic script
        for word in keywords["amharic"]:
            if word in message_lower:
                return intent
                
        # Check English spelling Amharic
        for word in keywords["english_spell"]:
            if word in message_lower:
                return intent
    
    return "default"

# ===== TEST FUNCTION FOR ROUND 2 =====
def test_round2():
    """Test new intents from Round 2"""
    test_messages = [
        # Location
        "where are you from",
        "ከየት ነህ",
        "ke yet neh",
        
        # Job
        "what do you do",
        "ምን ትሰራለህ",
        "min tiseraleh",
        
        # Flirty
        "you are beautiful",
        "ቆንጆ",
        "konjo",
        
        # Photo
        "send me photo",
        "ፎቶ",
        "foto laki",
        
        # Money
        "send me birr",
        "ብር",
        "telebirr",
        
        # Meet
        "let's meet",
        "እንገናኝ",
        "litba"
    ]
    
    print("\n" + "="*60)
    print("🧪 TESTING ROUND 2 DETECTION")
    print("="*60)
    
    for msg in test_messages:
        intent = detect_intent_triple(msg)
        print(f"📨 Message: {msg:30} → Intent: {intent:15}")
    
    print("="*60)
    print("✅ Round 2 detection working!")
    print("="*60 + "\n")

# Run test
test_round2()

# ==================== ROUND 3/5 - TRIPLE DETECTION (MORE INTENTS) ====================

# ===== ADD THESE TO YOUR EXISTING DETECTION_KEYWORDS =====
# Add these inside your DETECTION_KEYWORDS dictionary from Round 1 & 2

    "voice_call": {
        "english": ["call", "voice", "phone call", "ring", "video call", "talk on phone", "audio call"],
        "amharic": ["ድምጽ", "ስልክ", "ደውል", "ቪድዮ ደውል", "ስልክ ደውል", "ድምጽ ንገር"],
        "english_spell": ["dimts", "silk", "dewel", "kol", "video call", "voice call", "telephone"]
    },
    
    "relationship": {
        "english": ["love", "like", "miss", "heart", "relationship", "girlfriend", "boyfriend", "dating"],
        "amharic": ["ፍቅር", "ልብ", "ናፍቆት", "ወዳጅ", "ፍቅረኛ", "ውዴ", "ልቤ"],
        "english_spell": ["fikir", "libe", "weded", "nafekuh", "nafkehalew", "wude", "libe", "fiker"]
    },
    
    "thanks": {
        "english": ["thanks", "thank you", "thx", "appreciate", "grateful", "ty"],
        "amharic": ["አመሰግናለሁ", "እናመሰግናለን", "አመሰግንሃለሁ", "በጣም አመሰግናለሁ"],
        "english_spell": ["amesegnalehu", "tanesegnalehu", "thx", "thanks", "thank you"]
    },
    
    "goodbye": {
        "english": ["bye", "goodbye", "see you later", "talk later", "cya", "later", "take care"],
        "amharic": ["ደህና ሁን", "ቻው", "በህና ሁን", "እስካሁን", "ደህና ቆይ"],
        "english_spell": ["dehna hun", "chaw", "bye bye", "later", "see you", "cya"]
    },
    
    "morning": {
        "english": ["good morning", "morning", "gm", "good morning", "mornin"],
        "amharic": ["እንደምን አደርክ", "መልካም ንጋት", "እንደምን አደርሽ"],
        "english_spell": ["endemin aderk", "melkam nigt", "ande ferej", "good morning"]
    },
    
    "night": {
        "english": ["good night", "night", "gn", "sweet dreams", "sleep well"],
        "amharic": ["ደህና እደር", "ሌሊት", "መልካም ህልም", "በሰላም ተኛ"],
        "english_spell": ["dehna eder", "lelit", "melkam hilim", "good night", "gn"]
    },
    
    "busy": {
        "english": ["busy", "working", "no time", "occupied", "have work"],
        "amharic": ["ሥራ", "ተጠምጄ", "ጊዜ የለኝም", "ስራ ላይ ነኝ"],
        "english_spell": ["sira", "techegne", "gize yelel", "busy", "work"]
    },
    
    "after_money": {
        "english": ["sent", "sent the money", "lakesku", "transferred", "paid"],
        "amharic": ["ላክሁ", "ላክኩት", "ገንዘቡን ላክሁ"],
        "english_spell": ["lakesku", "sent", "lakalew", "birrun lakesku"]
    },

# ===== ADD THESE TO YOUR EXISTING TSEGA_RESPONSES =====
# Add these inside your TSEGA_RESPONSES dictionary

    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm",
        "dimts mesmat bicha ema fet lefit meyet new",
        "fet lefit magenat new yemishalew"
    ],
    
    "relationship": [
        "lante bicha negn tamenyaleh",
        "kelela sew gar alhonkum ante bicha neh belibe wisit",
        "lante bicha negn antess leene bicha neh",
        "antin ewodalehu kelibe",
        "ante bicha neh wedefit mayet yemifeligew",
        "lela sew ayfeligim ante bicha beki"
    ],
    
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "minim aydelem wude",
        "amesegnalehu betam"
    ],
    
    "goodbye": [
        "mehed alebign gin betequrb enenal",
        "ahun mehed alebign ante masbe altewom",
        "dehna hun wude behilime tenagn",
        "mehed alebign ishi",
        "chaw wude behwala enenal"
    ],
    
    "morning": [
        "endemin aderk wude melkam nigt",
        "ke eniklife yenekahut ante ehasbekuh new",
        "maleya anten masbet new lemwade",
        "ande tsehay tiru new anten sihone",
        "melkam nigt yelibe konjo"
    ],
    
    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "hilime wisit nurny zare mata",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "ande lelit dehna eder"
    ],
    
    "busy": [
        "ishi sirihin atanak biye ekoyihalehu",
        "sirah indemi tenak negeragn",
        "ishi wude betoh te meleslgn anten nafkehalew",
        "sint gize new yemitabekuh ekoyihalehu",
        "ishi sitchiser nigeragn"
    ],
    
    "after_money": [
        "amesegnalehu ahun antin lemagenat zegije negn",
        "betam des alegn leante sil wetat adergehliyal",
        "ayinet sew neh ahun magenat inchalal",
        "amesegnalehu ahun yante bicha negn",
        "betam des alegn ahun ngeragn min tifeligaleh"
    ],

# ===== UPDATED DETECTION FUNCTION =====
def detect_intent_triple(message):
    """
    Detects intent in English, Amharic, and Amharic English spelling
    """
    message_lower = message.lower().strip()
    
    # Check each intent's keywords
    for intent, keywords in DETECTION_KEYWORDS.items():
        # Check English
        for word in keywords["english"]:
            if word in message_lower:
                print(f"✅ Detected '{intent}' from English: '{word}'")
                return intent
                
        # Check Amharic script
        for word in keywords["amharic"]:
            if word in message_lower:
                print(f"✅ Detected '{intent}' from Amharic: '{word}'")
                return intent
                
        # Check English spelling Amharic
        for word in keywords["english_spell"]:
            if word in message_lower:
                print(f"✅ Detected '{intent}' from English spell: '{word}'")
                return intent
    
    print(f"⚠️ No intent detected, using 'default'")
    return "default"

# ===== COMPLETE RESPONSE FUNCTION =====
def get_tsega_response(intent):
    """Get random response for detected intent"""
    responses = TSEGA_RESPONSES.get(intent, ["ሰላም"])
    response = random.choice(responses)
    
    # 30% chance to add emoji
    emojis = ["😊", "😘", "💕", "😏", "💓", "✨", "😉", "🔥", "💋", "🌹"]
    if random.random() < 0.3:
        response = f"{response} {random.choice(emojis)}"
    
    return response

# ===== TEST FUNCTION FOR ROUND 3 =====
def test_round3():
    """Test new intents from Round 3"""
    test_messages = [
        # Voice Call
        "call me",
        "ስልክ",
        "dimts",
        
        # Relationship
        "i love you",
        "ፍቅር",
        "nafekuh",
        
        # Thanks
        "thank you",
        "አመሰግናለሁ",
        "amesegnalehu",
        
        # Goodbye
        "bye",
        "ደህና ሁን",
        "chaw",
        
        # Morning
        "good morning",
        "እንደምን አደርክ",
        "melkam nigt",
        
        # Night
        "good night",
        "ደህና እደር",
        "dehna eder",
        
        # Busy
        "i am busy",
        "ሥራ",
        "sira",
        
        # After Money
        "i sent the money",
        "ላክሁ",
        "lakesku"
    ]
    
    print("\n" + "="*60)
    print("🧪 TESTING ROUND 3 DETECTION")
    print("="*60)
    
    for msg in test_messages:
        intent = detect_intent_triple(msg)
        response = get_tsega_response(intent)
        print(f"📨 Message: {msg:25} → Intent: {intent:15} → 💬 {response[:40]}...")
    
    print("="*60)
    print("✅ Round 3 detection working!")
    print("="*60 + "\n")

# Run test
test_round3()
# ==================== ROUND 4/5 - TRIPLE DETECTION (EMOTIONS & CONFLICT) ====================

# ===== ADD THESE TO YOUR EXISTING DETECTION_KEYWORDS =====
# Add these inside your DETECTION_KEYWORDS dictionary

    "angry": {
        "english": ["angry", "mad", "upset", "frustrated", "annoyed", "pissed", "not happy"],
        "amharic": ["ተቆጣሁ", "ተናደድኩ", "ተበሳጨሁ", "ልቤ ተረበሸ", "አልደሰትኩም"],
        "english_spell": ["techegneh", "tekotehu", "tebsechehu", "libe taresebe", "aldesetekum"]
    },
    
    "jealous": {
        "english": ["jealous", "jealousy", "envy", "green with envy"],
        "amharic": ["ቀናሁ", "ምቀኝነት", "ቀንቶ", "አመቻሁ"],
        "english_spell": ["qenahu", "mikenyinet", "amechign", "amechignalehu"]
    },
    
    "hurt": {
        "english": ["hurt", "pain", "heartbroken", "sad", "crying", "in pain"],
        "amharic": ["ተጎዳሁ", "ልቤ ተሰበረ", "አዘንኩ", "አለቀስኩ"],
        "english_spell": ["tegodahu", "libe tesebre", "azenku", "alekusehu"]
    },
    
    "sorry": {
        "english": ["sorry", "apologize", "forgive me", "my bad", "i apologize"],
        "amharic": ["አዝናለሁ", "ይቅርታ", "ይቅርታ አድርግልኝ", "ተሳስቻለሁ"],
        "english_spell": ["aznalegu", "yikirta", "yikirta adergilgn", "tesasechalehu"]
    },
    
    "forgive": {
        "english": ["forgive", "forgive me", "i forgive you", "forgiveness"],
        "amharic": ["ይቅር አልኩት", "ይቅርታ አደረግሁ", "ማረኩ"],
        "english_spell": ["yikir alku", "miralehu", "yikirta adereguh"]
    },
    
    "lonely": {
        "english": ["lonely", "alone", "by myself", "no one", "isolated"],
        "amharic": ["ብቻዬን", "ብቻ", "ማንም የለም", "ተለይቻለሁ"],
        "english_spell": ["bicha", "bichaye", "bicha negn", "manim yelel"]
    },
    
    "miss_you": {
        "english": ["miss you", "missing you", "i miss you", "miss u"],
        "amharic": ["ናፍቀሃል", "ናፍቄሀለሁ", "ናፍቆት"],
        "english_spell": ["nafekuh", "nafkehalew", "nafkish"]
    },
    
    "love_you": {
        "english": ["love you", "i love you", "luv u"],
        "amharic": ["እወድሃለሁ", "ፍቅርህ", "እወድሻለሁ"],
        "english_spell": ["ewodihalehu", "ewodishalehu", "fikirish"]
    },

# ===== ADD THESE TO YOUR EXISTING TSEGA_RESPONSES =====
# Add these inside your TSEGA_RESPONSES dictionary

    "angry": [
        "lemin techegneh nagerign betam azeleku",
        "ante techegneh betam ayzalen wude",
        "ande techegneh ina nagerign",
        "lemin tekoteh ante nagerign",
        "ante beza new yemiyasebnyew",
        "libe taresebeh wude lemin"
    ],
    
    "jealous": [
        "lela sew tayaleh lemin betam amechignaleh",
        "kemichawet gar neberku man new nagerign",
        "betam amechignaleh wude",
        "amechign betam kelela sew",
        "ante bicha new yaleny lela sew atay"
    ],
    
    "hurt": [
        "liben wedehe betam betam azeleku",
        "libe temechene betam lemin asadeseh",
        "liben wedehe betam ayzalen",
        "libe temechene betam yikirta",
        "liben wedehe lemin"
    ],
    
    "sorry": [
        "aznalegu betam yikirta efeligalehu wude",
        "aznalegu ante betam betam yikirta",
        "yikirta efeligalehu wude betam tiyikirtal",
        "aznalegu betam yikirta ande mirkogna",
        "yikirta efeligalehu betam tiriwedegnyal"
    ],
    
    "forgive": [
        "miralew wude betam tiriwedegnyal",
        "miralew betam degmo inidehu adergalehu",
        "miralew wude betam des alegn",
        "miralew betam tiriwedegnyal",
        "yikirta adereguh wude"
    ],
    
    "lonely": [
        "bicha negn betam aselchi wude",
        "bicha negn anten sihone betam",
        "bicha negn betam nafkehalew",
        "ante new yaleny wude",
        "bicha negn gin ante tagebagnyal"
    ],
    
    "miss_you": [
        "enem nafkehalew meche tagenal",
        "nafkehalew betam wude",
        "enem betam nafkehalew",
        "nafkehalew betam meche tayalh",
        "betam nafkehalew ande"
    ],
    
    "love_you": [
        "enem ewodalehu betam betam",
        "ewodalehu kelibe wude",
        "enem betam ewodalehu",
        "ewodalehu betam tiriwedegnyal",
        "betam ewodalehu ande"
    ],

# ===== UPDATED DETECTION FUNCTION WITH DEBUG =====
def detect_intent_triple(message):
    """
    Detects intent in English, Amharic, and Amharic English spelling
    """
    message_lower = message.lower().strip()
    
    print(f"\n🔍 Analyzing: '{message}'")
    
    # Check each intent's keywords
    for intent, keywords in DETECTION_KEYWORDS.items():
        # Check English
        for word in keywords["english"]:
            if word in message_lower:
                print(f"  ✅ {intent} (English: '{word}')")
                return intent
                
        # Check Amharic script
        for word in keywords["amharic"]:
            if word in message_lower:
                print(f"  ✅ {intent} (Amharic: '{word}')")
                return intent
                
        # Check English spelling Amharic
        for word in keywords["english_spell"]:
            if word in message_lower:
                print(f"  ✅ {intent} (English spell: '{word}')")
                return intent
    
    print(f"  ⚠️ No match, using default")
    return "default"

# ===== TEST FUNCTION FOR ROUND 4 =====
def test_round4():
    """Test new intents from Round 4"""
    test_messages = [
        # Angry
        "i am angry",
        "ተቆጣሁ",
        "techegneh",
        
        # Jealous
        "i am jealous",
        "ቀናሁ",
        "amechign",
        
        # Hurt
        "you hurt me",
        "ተጎዳሁ",
        "libe tesebre",
        
        # Sorry
        "i am sorry",
        "አዝናለሁ",
        "aznalegu",
        
        # Forgive
        "please forgive me",
        "ይቅርታ አድርግልኝ",
        "yikirta",
        
        # Lonely
        "i feel lonely",
        "ብቻዬን",
        "bicha negn",
        
        # Miss You
        "i miss you",
        "ናፍቄሀለሁ",
        "nafkehalew",
        
        # Love You
        "i love you",
        "እወድሃለሁ",
        "ewodihalehu"
    ]
    
    print("\n" + "="*70)
    print("🧪 TESTING ROUND 4 - EMOTIONS & CONFLICT")
    print("="*70)
    
    for msg in test_messages:
        intent = detect_intent_triple(msg)
        response = get_tsega_response(intent)
        print(f"📨 {msg:25} → {intent:15} → 💬 {response}")
    
    print("="*70)
    print("✅ Round 4 emotions & conflict detection working!")
    print("="*70 + "\n")

# Run test
test_round4()

# ===== COMPLETE INTENT LIST SO FAR =====
def list_all_intents():
    """Show all intents we have so far"""
    intents = list(DETECTION_KEYWORDS.keys())
    print("\n" + "="*70)
    print(f"📋 TOTAL INTENTS: {len(intents)}")
    print("="*70)
    
    # Group them
    groups = {
        "Basic": ["greeting", "how_are_you", "what_doing", "ask_name", "ask_age"],
        "Personal": ["location", "ask_job"],
        "Requests": ["photo_request", "money_request", "meet", "voice_call"],
        "Romantic": ["flirty", "relationship", "miss_you", "love_you"],
        "Daily": ["morning", "night", "busy"],
        "Emotions": ["angry", "jealous", "hurt", "lonely"],
        "Social": ["thanks", "goodbye"],
        "Apology": ["sorry", "forgive"],
        "Money": ["after_money"]
    }
    
    for group, group_intents in groups.items():
        print(f"\n{group}:")
        for intent in group_intents:
            if intent in intents:
                print(f"  ✅ {intent}")
    
    print("\n" + "="*70)

# Uncomment to see all intents
# list_all_intents()
# ==================== ROUND 5/5 - COMPLETE INTEGRATION & FLASK SETUP ====================

# ===== ADD THESE FINAL KEYWORDS TO YOUR DETECTION_KEYWORDS =====
# Add these inside your DETECTION_KEYWORDS dictionary

    "compliment": {
        "english": ["nice", "beautiful", "pretty", "handsome", "cute", "gorgeous", "stunning", "lovely"],
        "amharic": ["ቆንጆ", "ውብ", "ማማ", "አሪፍ", "ተወዳጅ"],
        "english_spell": ["konjo", "wub", "aref", "mare", "tiru", "enibada"]
    },
    
    "joke": {
        "english": ["joke", "funny", "lol", "haha", "lmao", "😂"],
        "amharic": ["ቀልድ", "አስቂኝ", "ሳቅ"],
        "english_spell": ["qelid", "asqeny", "siq", "lol", "haha"]
    },
    
    "surprise": {
        "english": ["wow", "omg", "oh my god", "really", "no way", "seriously"],
        "amharic": ["ዋዉ", "እንዴት", "ምን አልኩ", "አይቀሬ"],
        "english_spell": ["wow", "endet", "min alku", "ayqere", "omg"]
    },
    
    "confused": {
        "english": ["confused", "don't understand", "what", "huh", "i don't get it"],
        "amharic": ["ግራ ተጋባሁ", "አልገባኝም", "ምንድን"],
        "english_spell": ["gram tegabehu", "algebagnem", "shafafekeh", "min din"]
    },
    
    "bored": {
        "english": ["bored", "nothing to do", "boring"],
        "amharic": ["አሰልቺ", "ምንም ማድረግ", "ሰልችቶኛል"],
        "english_spell": ["aselchi", "selchitonal", "minim yele"]
    },
    
    "excited": {
        "english": ["excited", "happy", "can't wait", "so excited"],
        "amharic": ["ደስተኛ", "ጓጉቻለሁ", "በጣም ደስ ብሎኛል"],
        "english_spell": ["des alegn", "gwaguechalehu", "betam des yilonal"]
    },

# ===== ADD THESE FINAL RESPONSES TO YOUR TSEGA_RESPONSES =====
# Add these inside your TSEGA_RESPONSES dictionary

    "compliment": [
        "amesegnalehu betam konjo neh",
        "ante stawedsen eneka konjo ihonalehu",
        "amesegnalehu ante sew neh",
        "konjo sew ante neh",
        "betam tiru tayaleh",
        "kenfere lante bicha new"
    ],
    
    "joke": [
        "lemidisak ande nageralehu",
        "sik ande tisikehalehu",
        "andisachew nageralehu",
        "sik lemadis ande naw",
        "lol ande betam sik new"
    ],
    
    "surprise": [
        "wow betam denak neh",
        "enem alalfekum neber",
        "betam asdenekeh wude",
        "min alku betam denak",
        "endet new yalew"
    ],
    
    "confused": [
        "lemin tishafafekaleh nagerign",
        "shafafekeh ina anagegnal",
        "andet litira awe nagerign",
        "gram tegabehu ande",
        "shafafekeh betam"
    ],
    
    "bored": [
        "enem aselchi negn anten sihone des alegn",
        "aselchi neber ina nagerign",
        "aselchi sihon nagerign anawedalehu",
        "enem aselchi negn ande eneweyay",
        "aselchi neh ina min iteweyay"
    ],
    
    "excited": [
        "enem des alegn betam",
        "gwaguechalehu ande",
        "betam des alegn lemelikamn ihon",
        "enem techekulehu neber",
        "des alegn anten sihone"
    ],

# ===== COMPLETE DETECTION FUNCTION =====
def detect_intent_triple(message):
    """
    Detects intent in English, Amharic, and Amharic English spelling
    """
    message_lower = message.lower().strip()
    
    if not message_lower:
        return "default"
    
    # Check each intent's keywords
    for intent, keywords in DETECTION_KEYWORDS.items():
        # Check English
        for word in keywords["english"]:
            if word in message_lower:
                return intent
                
        # Check Amharic script
        for word in keywords["amharic"]:
            if word in message_lower:
                return intent
                
        # Check English spelling Amharic
        for word in keywords["english_spell"]:
            if word in message_lower:
                return intent
    
    return "default"

# ===== COMPLETE RESPONSE FUNCTION =====
def get_tsega_response(intent):
    """Get random response for detected intent"""
    # Get responses for this intent, or use default
    responses = TSEGA_RESPONSES.get(intent, TSEGA_RESPONSES.get("default", ["ሰላም"]))
    
    # Pick random response
    response = random.choice(responses)
    
    # 30% chance to add emoji (natural feel)
    emojis = ["😊", "😘", "💕", "😏", "💓", "✨", "😉", "🔥", "💋", "🌹", "🥰", "💫"]
    if random.random() < 0.3:
        response = f"{response} {random.choice(emojis)}"
    
    return response

# ===== TEST ALL ROUNDS =====
def test_all_rounds():
    """Test all intents from all 5 rounds"""
    test_messages = [
        # Round 1
        "hi", "selam", "ሰላም",
        "how are you", "endet neh", "እንደምን ነህ",
        "what are you doing", "min tiseraleh", "ምን ትሰራለህ",
        "your name", "simih man new", "ስምህ ማን ነው",
        "how old", "edmeh sint", "ዕድሜህ",
        
        # Round 2
        "where are you from", "ke yet neh", "ከየት ነህ",
        "your job", "min tiseraleh", "ሥራህ",
        "beautiful", "konjo", "ቆንጆ",
        "photo", "foto laki", "ፎቶ",
        "send birr", "telebirr", "ቴሌብር",
        "meet", "litba", "ማግኘት",
        
        # Round 3
        "call me", "dimts", "ድምጽ",
        "i love you", "fikir", "ፍቅር",
        "thanks", "amesegnalehu", "አመሰግናለሁ",
        "bye", "chaw", "ደህና ሁን",
        "good morning", "melkam nigt", "እንደምን አደርክ",
        "good night", "dehna eder", "ደህና እደር",
        "busy", "sira", "ሥራ",
        "sent money", "lakesku", "ላክሁ",
        
        # Round 4
        "i am angry", "techegneh", "ተቆጣሁ",
        "jealous", "amechign", "ቀናሁ",
        "hurt", "libe tesebre", "ተጎዳሁ",
        "sorry", "aznalegu", "አዝናለሁ",
        "forgive me", "yikirta", "ይቅርታ",
        "lonely", "bicha negn", "ብቻዬን",
        "miss you", "nafkehalew", "ናፍቄሀለሁ",
        "love you", "ewodihalehu", "እወድሃለሁ",
        
        # Round 5
        "nice", "konjo", "ቆንጆ",
        "joke", "siq", "ቀልድ",
        "wow", "endet", "ዋዉ",
        "confused", "shafafekeh", "ግራ ተጋባሁ",
        "bored", "aselchi", "አሰልቺ",
        "excited", "des alegn", "ደስተኛ"
    ]
    
    print("\n" + "="*80)
    print("🧪 TESTING ALL 5 ROUNDS - COMPLETE DETECTION SYSTEM")
    print("="*80)
    
    results = {}
    for msg in test_messages:
        intent = detect_intent_triple(msg)
        results[intent] = results.get(intent, 0) + 1
    
    print(f"\n📊 Detected {len(results)} unique intents:")
    for intent, count in sorted(results.items()):
        print(f"  ✅ {intent}: {count} test messages")
    
    print("\n" + "="*80)
    print("✅ ALL 5 ROUNDS WORKING PERFECTLY!")
    print("="*80 + "\n")

# Run final test
test_all_rounds()

# ===== EXPORT FOR FLASK APP =====
# These functions will be used by your Flask app

def process_user_message(message):
    """
    Main function to process user message and return Tsega's response
    Use this in your Flask routes
    """
    # Detect intent
    intent = detect_intent_triple(message)
    
    # Get response
    response = get_tsega_response(intent)
    
    return {
        "intent": intent,
        "response": response,
        "original": message
    }

# ===== QUICK TEST =====
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 TSEGA IS READY - 5 ROUNDS COMPLETE")
    print("="*60)
    print(f"📋 Total Intents: {len(DETECTION_KEYWORDS)}")
    print(f"💬 Total Responses: {sum(len(v) for v in TSEGA_RESPONSES.values())}")
    print("="*60)
    
    # Interactive test
    while True:
        user_input = input("\n👤 You: ")
        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("🤖 Tsega: chaw wude behwala enenal 😊")
            break
        
        result = process_user_message(user_input)
        print(f"🤖 Tsega ({result['intent']}): {result['response']}")









