#!/usr/bin/env python3
"""
TSEGA PERSONAL ACCOUNT STAR EARNING SYSTEM
This runs on your second Render account but still uses Tsega's personal account
NO BOT TOKEN NEEDED - Uses Telethon like your server.py
"""

import os
import asyncio
import logging
import sqlite3
import json
import random
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# ==================== CONFIGURATION ====================

# Your Telegram API credentials (same as in server.py)
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Tsega's account session (you'll add this via web login)
# This will be stored in database after first login

# Channel to deposit Stars
CHANNEL_USERNAME = "@Abe_army"
CHANNEL_ID = CHANNEL_USERNAME  # Can be @username

# Star pricing
STAR_PRICES = {
    "message": 10,           # Stars to send a message
    "photo_preview": 5,       # Stars for preview photo
    "photo_full": 50,         # Stars for full photo
    "photo_pack": 200,        # Stars for 5 photos
    "video_preview": 10,       # Stars for video preview
    "video_full": 100,         # Stars for full video
}

# ==================== SETUP LOGGING ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== FLASK APP ====================

app = Flask(__name__)

@app.route('/')
def home():
    return "Tsega Star Earning System is running! ✨", 200

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'time': datetime.now().isoformat(),
        'account': 'Tsega Personal Account'
    }), 200

@app.route('/stats')
def stats():
    """Show star earnings stats"""
    try:
        conn = sqlite3.connect('tsega_stars.db')
        c = conn.cursor()
        c.execute("SELECT SUM(amount) FROM star_transactions")
        total = c.fetchone()[0] or 0
        c.execute("SELECT SUM(amount) FROM star_transactions WHERE date(timestamp) = date('now')")
        today = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(DISTINCT user_id) FROM star_transactions")
        users = c.fetchone()[0] or 0
        conn.close()
        
        return jsonify({
            'success': True,
            'total_stars': total,
            'today_stars': today,
            'total_users': users,
            'channel': CHANNEL_USERNAME
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== DATABASE SETUP ====================

def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect('tsega_stars.db')
    c = conn.cursor()
    
    # Sessions table (store Tsega's login session)
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY,
                  session_string TEXT,
                  phone TEXT,
                  last_login TIMESTAMP)''')
    
    # Star transactions
    c.execute('''CREATE TABLE IF NOT EXISTS star_transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount INTEGER,
                  chat_id TEXT,
                  message TEXT,
                  timestamp TIMESTAMP,
                  forwarded_to_channel INTEGER DEFAULT 0)''')
    
    # Channel earnings
    c.execute('''CREATE TABLE IF NOT EXISTS channel_earnings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  amount INTEGER,
                  timestamp TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def save_session(session_string, phone):
    """Save Tsega's session to database"""
    conn = sqlite3.connect('tsega_stars.db')
    c = conn.cursor()
    c.execute("DELETE FROM sessions")  # Only one session
    c.execute("INSERT INTO sessions (session_string, phone, last_login) VALUES (?, ?, ?)",
              (session_string, phone, datetime.now()))
    conn.commit()
    conn.close()
    logger.info("✅ Session saved")

def load_session():
    """Load Tsega's session from database"""
    conn = sqlite3.connect('tsega_stars.db')
    c = conn.cursor()
    c.execute("SELECT session_string, phone FROM sessions ORDER BY last_login DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

def record_star_payment(user_id, amount, chat_id, message):
    """Record a Star payment in database"""
    conn = sqlite3.connect('tsega_stars.db')
    c = conn.cursor()
    c.execute('''INSERT INTO star_transactions 
                 (user_id, amount, chat_id, message, timestamp)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, amount, chat_id, message, datetime.now()))
    conn.commit()
    conn.close()
    logger.info(f"💰 Recorded {amount} stars from user {user_id}")

def mark_as_forwarded(transaction_id):
    """Mark transaction as forwarded to channel"""
    conn = sqlite3.connect('tsega_stars.db')
    c = conn.cursor()
    c.execute("UPDATE star_transactions SET forwarded_to_channel = 1 WHERE id = ?", (transaction_id,))
    conn.commit()
    conn.close()

# ==================== TELEGRAM CLIENT ====================

class TsegaStarClient:
    def __init__(self):
        self.client = None
        self.is_running = False
        self.channel_entity = None
    
    async def start(self, session_string=None):
        """Start the Telegram client"""
        if session_string:
            self.client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        else:
            self.client = TelegramClient('tsega_star_session', API_ID, API_HASH)
        
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            logger.info("❌ Not authorized. Please login first.")
            return False
        
        me = await self.client.get_me()
        logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
        
        # Get channel entity
        try:
            self.channel_entity = await self.client.get_entity(CHANNEL_USERNAME)
            logger.info(f"✅ Channel found: {CHANNEL_USERNAME}")
        except Exception as e:
            logger.error(f"❌ Cannot find channel {CHANNEL_USERNAME}: {e}")
            logger.info("Make sure Tsega's account is ADMIN in the channel!")
        
        # Register handler for Star payments
        @self.client.on(events.NewMessage)
        async def handler(event):
            await self.handle_star_payment(event)
        
        self.is_running = True
        return True
    
    async def handle_star_payment(self, event):
        """Handle incoming Star payments"""
        try:
            # Skip own messages
            if event.out:
                return
            
            message = event.message
            sender = await event.get_sender()
            chat = await event.get_chat()
            
            # Check if this is a private chat
            if hasattr(chat, 'title') and chat.title:
                return  # Skip groups/channels
            
            # Check if message has Stars
            if hasattr(message, 'paid_stars') and message.paid_stars:
                stars_amount = message.paid_stars
                user_id = sender.id
                username = sender.username or sender.first_name or "Unknown"
                
                logger.info(f"💰 Star payment detected: {stars_amount} stars from {username}")
                
                # Record in database
                record_star_payment(user_id, stars_amount, str(chat.id), message.text or "")
                
                # Forward to channel
                await self.forward_to_channel(sender, stars_amount, message)
                
                # Thank the user
                thank_you = (
                    f"✅ **Thank you for your support!**\n\n"
                    f"You sent **{stars_amount} ⭐**\n"
                    f"All Stars go to {CHANNEL_USERNAME} channel!\n\n"
                    f"❤️ Love you baby!"
                )
                await event.reply(thank_you)
            
        except Exception as e:
            logger.error(f"Error handling star payment: {e}")
    
    async def forward_to_channel(self, sender, stars_amount, original_message):
        """Forward Star payment info to channel"""
        if not self.channel_entity:
            logger.warning("⚠️ Channel not available, skipping forward")
            return
        
        try:
            # Get sender info
            name = sender.first_name or "User"
            username = f"@{sender.username}" if sender.username else "No username"
            user_id = sender.id
            
            # Create message for channel
            channel_msg = (
                f"💰 **NEW STAR PAYMENT!**\n\n"
                f"**Amount:** {stars_amount} ⭐\n"
                f"**From:** {name}\n"
                f"**Username:** {username}\n"
                f"**User ID:** `{user_id}`\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"📝 **Message:** {original_message.text or 'No message'}"
            )
            
            # Send to channel
            await self.client.send_message(self.channel_entity, channel_msg)
            logger.info(f"✅ Forwarded {stars_amount} stars info to channel")
            
            # Record channel earning
            conn = sqlite3.connect('tsega_stars.db')
            c = conn.cursor()
            c.execute("INSERT INTO channel_earnings (amount, timestamp) VALUES (?, ?)",
                     (stars_amount, datetime.now()))
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error forwarding to channel: {e}")
    
    async def run_until_disconnected(self):
        """Keep the client running"""
        await self.client.run_until_disconnected()
    
    def stop(self):
        """Stop the client"""
        self.is_running = False
        if self.client:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.client.disconnect())
            loop.close()

# ==================== LOGIN HANDLER (for web) ====================

# Temporary storage for login flow
login_sessions = {}

@app.route('/login', methods=['GET'])
def login_page():
    """Simple login page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tsega Login</title>
        <style>
            body { background: #0e1621; color: white; font-family: Arial; padding: 20px; }
            .container { max-width: 400px; margin: 50px auto; }
            input, button { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; }
            input { background: #17212b; border: 1px solid #2b3945; color: white; }
            button { background: #4c9ce0; color: white; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Tsega Login</h1>
            <p>Login with your phone number to start earning Stars</p>
            <input type="text" id="phone" placeholder="+251912345678" value="+251">
            <button onclick="sendCode()">Send Code</button>
            <div id="codeDiv" style="display:none;">
                <input type="text" id="code" placeholder="Enter 5-digit code">
                <button onclick="verifyCode()">Verify</button>
            </div>
            <div id="result"></div>
        </div>
        <script>
            let phoneHash = {};
            
            async function sendCode() {
                const phone = document.getElementById('phone').value;
                const res = await fetch('/api/send-code', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                if (data.success) {
                    phoneHash = data;
                    document.getElementById('codeDiv').style.display = 'block';
                    document.getElementById('result').innerHTML = '✅ Code sent!';
                } else {
                    document.getElementById('result').innerHTML = '❌ ' + data.error;
                }
            }
            
            async function verifyCode() {
                const code = document.getElementById('code').value;
                const res = await fetch('/api/verify-code', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        phone: phoneHash.phone,
                        code: code,
                        phone_code_hash: phoneHash.phone_code_hash
                    })
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('result').innerHTML = '✅ Login successful! Starting bot...';
                    setTimeout(() => window.location.href = '/', 2000);
                } else {
                    document.getElementById('result').innerHTML = '❌ ' + data.error;
                }
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/send-code', methods=['POST'])
def send_code():
    """Send login code to phone"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone required'})
    
    async def _send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_id = str(int(time.time()))
            login_sessions[session_id] = {
                'phone': phone,
                'phone_code_hash': result.phone_code_hash,
                'client': client
            }
            return {
                'success': True,
                'session_id': session_id,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_send_code())
    loop.close()
    return jsonify(result)

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify login code"""
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    phone_code_hash = data.get('phone_code_hash')
    
    if not all([phone, code, phone_code_hash]):
        return jsonify({'success': False, 'error': 'Missing data'})
    
    async def _verify():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            
            # Save session
            session_string = client.session.save()
            save_session(session_string, phone)
            
            # Start the main client with this session
            global star_client
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(star_client.start(session_string))
            loop.close()
            
            return {'success': True, 'user': me.first_name}
        except SessionPasswordNeededError:
            return {'success': False, 'error': '2FA password required (not implemented in this simple version)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_verify())
    loop.close()
    return jsonify(result)

# ==================== MAIN ====================

star_client = TsegaStarClient()

def run_telegram_client():
    """Run the Telegram client in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Try to load existing session
    session = load_session()
    if session:
        session_string, phone = session
        loop.run_until_complete(star_client.start(session_string))
        logger.info(f"✅ Loaded existing session for {phone}")
    else:
        logger.info("⚠️ No session found. Please login at /login first")
    
    if star_client.is_running:
        loop.run_until_complete(star_client.run_until_disconnected())

def start_telegram_thread():
    """Start Telegram client in background thread"""
    thread = threading.Thread(target=run_telegram_client, daemon=True)
    thread.start()
    return thread

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))  # Use different port from main server
    
    print("\n" + "="*60)
    print("✨ TSEGA STAR EARNING SYSTEM (PERSONAL ACCOUNT)")
    print("="*60)
    print(f"API_ID: {API_ID}")
    print(f"Channel: {CHANNEL_USERNAME}")
    print(f"Port: {port}")
    print("\n💰 Star Pricing:")
    for item, price in STAR_PRICES.items():
        print(f"   • {item}: {price} ⭐")
    print("\n📱 Login at: http://localhost:{}/login".format(port))
    print("="*60 + "\n")
    
    # Initialize database
    init_database()
    
    # Start Telegram client in background
    start_telegram_thread()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
