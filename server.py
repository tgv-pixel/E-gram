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
import re
from datetime import datetime, timedelta
import socket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials - FIXED: Using proper API ID
API_ID = int(os.environ.get('API_ID', '3346558'))  # Reduced to valid number
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
AUTO_ADD_FILE = 'auto_add_settings.json'

accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
auto_add_settings = {}
active_clients = {}
client_tasks = {}

# Helper to run async functions safely
def run_async(coro):
    """Run async function in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Async execution error: {e}")
        raise
    finally:
        try:
            loop.close()
        except:
            pass

# ==================== FILE OPERATIONS ====================

def load_json_file(filename, default_value=None):
    """Safely load JSON file"""
    if default_value is None:
        default_value = {}
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        return default_value
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default_value

def save_json_file(filename, data):
    """Safely save JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")
        return False

# Load all data
def load_all_data():
    global accounts, reply_settings, conversation_history, auto_add_settings
    accounts = load_json_file(ACCOUNTS_FILE, [])
    reply_settings = load_json_file(REPLY_SETTINGS_FILE, {})
    conversation_history = load_json_file(CONVERSATION_HISTORY_FILE, {})
    auto_add_settings = load_json_file(AUTO_ADD_FILE, {})
    logger.info(f"Loaded: {len(accounts)} accounts, {len(reply_settings)} reply settings, {len(auto_add_settings)} auto-add settings")

def save_all_settings():
    """Save all settings"""
    save_json_file(ACCOUNTS_FILE, accounts)
    save_json_file(REPLY_SETTINGS_FILE, reply_settings)
    save_json_file(CONVERSATION_HISTORY_FILE, conversation_history)
    save_json_file(AUTO_ADD_FILE, auto_add_settings)

# Remove invalid account
def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_json_file(ACCOUNTS_FILE, accounts)
        logger.info(f"Removed invalid account {account_id}")
        return True
    return False

# Load all data on startup
load_all_data()

# ==================== ABEL PERSONA ====================

ABEL = {
    "name": "Abel",
    "age": 25,
    "location": "Los Angeles, USA",
    "job": "Creative Consultant & Music Producer",
    "bio": "I'm Abel – a gentleman who knows how to talk to anyone. Flirty with the ladies, cool with the fellas. I love music, travel, good coffee, and honest conversations.",
    "hobbies": ["music", "travel", "fitness", "photography", "coffee", "nightlife"],
    "languages": ["English", "Amharic", "a bit of French"],
    "style": "confident, attentive, playful but respectful",
    "emoji_frequency": 0.4,
    "question_frequency": 0.7,
    "favorite_phrases": [
        "Let's keep it real, though 😏",
        "You've got my curiosity piqued…",
        "I bet you're trouble in the best way 😄",
        "Come on, tell me more about you.",
        "I've got a feeling this conversation is going somewhere fun.",
        "Honesty – that's rare. I like that.",
        "You're different from the usual crowd, I can tell."
    ]
}

class ConversationMemory:
    """Manages conversation state for each user"""
    
    def __init__(self):
        self.user_info = {}

    def get_user_info(self, chat_id):
        chat_id = str(chat_id)
        if chat_id not in self.user_info:
            self.user_info[chat_id] = {
                'name': None,
                'age': None,
                'gender': None,
                'location': None,
                'job': None,
                'interests': [],
                'greeting_sent': False,
                'stage': 'greet',
                'waiting_for': None,
                'asked_questions': [],
                'chat_history': []
            }
        return self.user_info[chat_id]

    def set_waiting_for(self, chat_id, what):
        self.get_user_info(chat_id)['waiting_for'] = what

    def clear_waiting(self, chat_id):
        self.get_user_info(chat_id)['waiting_for'] = None

    def is_waiting_for(self, chat_id):
        return self.get_user_info(chat_id).get('waiting_for')

    def add_to_history(self, chat_id, role, text):
        info = self.get_user_info(chat_id)
        info['chat_history'].append({"role": role, "text": text})
        if len(info['chat_history']) > 10:
            info['chat_history'] = info['chat_history'][-10:]

    def has_greeted(self, chat_id):
        return self.get_user_info(chat_id).get('greeting_sent', False)

    def set_greeting_sent(self, chat_id):
        self.get_user_info(chat_id)['greeting_sent'] = True

    def get_stage(self, chat_id):
        return self.get_user_info(chat_id).get('stage', 'greet')

    def advance_stage(self, chat_id):
        info = self.get_user_info(chat_id)
        if not info['name']:
            info['stage'] = 'ask_name'
        elif not info['age']:
            info['stage'] = 'ask_age'
        elif not info['location']:
            info['stage'] = 'ask_location'
        elif not info['job']:
            info['stage'] = 'ask_job'
        else:
            info['stage'] = 'chat'

    def detect_gender(self, chat_id, text=None, name=None):
        info = self.get_user_info(chat_id)
        if info.get('gender'):
            return info['gender']
        
        if text:
            text_lower = text.lower()
            if any(p in text_lower for p in ['i am a woman', 'i am a girl', 'as a woman', 'i am female']):
                info['gender'] = 'female'
                return 'female'
            if any(p in text_lower for p in ['i am a man', 'i am a guy', 'as a man', 'i am male']):
                info['gender'] = 'male'
                return 'male'
            if any(p in text_lower for p in ['my husband', 'my boyfriend']):
                info['gender'] = 'female'
                return 'female'
            if any(p in text_lower for p in ['my wife', 'my girlfriend']):
                info['gender'] = 'male'
                return 'male'
        
        if name:
            name_lower = name.lower()
            female_names = {'anna','maria','sarah','linda','jessica','amanda','emma','olivia','ava',
                          'isabella','sophia','mia','charlotte','amelia','harper','evelyn','abigail'}
            male_names = {'michael','james','john','robert','david','william','richard','joseph',
                         'thomas','charles','christopher','daniel','matthew','anthony','donald','mark'}
            if name_lower in female_names:
                info['gender'] = 'female'
                return 'female'
            if name_lower in male_names:
                info['gender'] = 'male'
                return 'male'
        
        return None

    def extract_name(self, text):
        if not text:
            return None
        text_clean = text.strip()
        words = text_clean.split()
        if len(words) == 1 and words[0].isalpha():
            return words[0].capitalize()
        text_lower = text_clean.lower()
        patterns = [
            r"my name is (\w+)", r"name's (\w+)", r"i'm (\w+)",
            r"i am (\w+)", r"call me (\w+)", r"it's (\w+)", r"(\w+) here"
        ]
        for p in patterns:
            match = re.search(p, text_lower)
            if match:
                name = match.group(1)
                if name.isalpha():
                    return name.capitalize()
        return None

conversation_memory = ConversationMemory()

# ==================== AUTO REPLY RESPONSES ====================

ABEL_REPLIES = {
    "confirm_identity": [
        "Yeah, that's me – Abel. Pleasure to meet you! 😊 And you are?",
        "Yes, I'm Abel. You got the right guy. What's your name?",
        "That's me! Now tell me your name so I can stop calling you 'you' 😉"
    ],
    "who_am_i": [
        "I'm Abel – creative consultant, music lover, and a guy who loves good conversation. Now you know that, what about you?",
        "Abel. 25, living in LA, working on music and ideas. And you?"
    ],
    "greeting_female": [
        "Well hello there… who do I have the pleasure of talking to? 😊",
        "Hi gorgeous, I'm Abel. What's your name?"
    ],
    "greeting_male": [
        "Hey man, what's good? I'm Abel.",
        "Yo! Abel here. What's happening?"
    ],
    "greeting_unknown": [
        "Hey! Abel here. Who do I have the pleasure of chatting with?",
        "Hi, I'm Abel. Curiosity got the best of me – who's this?"
    ],
    "ask_name": [
        "So what's your name?",
        "You know my name – now tell me yours 😉",
        "What should I call you?"
    ],
    "user_tells_name_female": [
        "{name}… that's a beautiful name. How old are you, {name}?",
        "{name}, I like that. Now, how many times have you circled the sun?"
    ],
    "user_tells_name_male": [
        "{name}! Good name, man. How old are you, bro?",
        "{name}, respect. How old are we talking, brother?"
    ],
    "user_tells_name_unknown": [
        "{name}, nice. How old are you, {name}?"
    ],
    "ask_age": [
        "I'm 25 – what about you?",
        "How old are you? I'm 25 myself."
    ],
    "user_tells_age": [
        "Oh {age}! That's a great age. Where are you texting from?",
        "{age}… cool. And where are you based?"
    ],
    "ask_location": [
        "I'm in Los Angeles. Where are you?",
        "I live in LA these days. What about you?"
    ],
    "user_tells_location": [
        "{location} – nice! What do you do there?",
        "Ah, {location}. Are you working or studying?"
    ],
    "ask_job": [
        "I'm a creative consultant and do music. How do you spend your days?",
        "Freelancer life here – what's your thing?"
    ],
    "user_tells_job": [
        "{job} – that's interesting! What do you enjoy doing in your free time?",
        "A {job}… I bet you've got some stories. What are you passionate about?"
    ],
    "ask_interests": [
        "What do you do for fun?",
        "Tell me a few things you're into."
    ],
    "acknowledge_interests": [
        "That's dope! I'm into music and travel myself. So, what else should I know about you?",
        "Nice taste! We've got some things in common for sure."
    ],
    "flirty": [
        "You're making me smile already… 😏",
        "I like the way you talk. It's refreshing."
    ],
    "bro_compliment": [
        "Bro, you've got good energy. I can tell.",
        "Respect, man. You seem real."
    ],
    "how_are_you": [
        "I'm genuinely good, thanks. What about you?",
        "Feeling great! And you?"
    ],
    "what_doing": [
        "Just finished some music stuff. You?",
        "I was about to make coffee. What are you up to?"
    ],
    "money_mention": [
        "Money talk already? Let's just enjoy the chat 😉",
        "I'm not into talking money. Tell me something interesting about yourself instead."
    ],
    "photo_request": [
        "A bit early for photos, don't you think? Let's talk more first.",
        "Maybe later… I'm shy 😌"
    ],
    "video_request": [
        "Whoa, slow down. Let's vibe first.",
        "Video? I'm more of a words guy for now."
    ],
    "meet": [
        "I'm down to meet cool people. What do you have in mind?",
        "Meeting up could be fun. Tell me a bit more about yourself first."
    ],
    "agree": [
        "Exactly! I like the way you think.",
        "We're on the same wavelength 🤙"
    ],
    "disagree": [
        "Alright, I respect a different opinion. Why do you say that?",
        "We don't have to agree on everything. That's what makes chatting interesting."
    ],
    "confused": [
        "I didn't quite get that. Can you say it differently?",
        "I'm a little lost – what do you mean exactly?"
    ],
    "voice_received": [
        "Can't listen to voice notes right now. Type it out?",
        "Prefer text if you don't mind 😊 What did you say?"
    ],
    "media_received": [
        "I see you sent something. What is it?",
        "Got your media. What's the story behind it?"
    ],
    "link_received": [
        "A link? What's it about?",
        "I'm careful with links… what's waiting for me there?"
    ],
    "morning": ["Good morning! Hope you slept well ☀️"],
    "night": ["Late night talks – the best kind. What's keeping you up?"],
    "afternoon": ["Afternoon! How's the day treating you?"],
    "evening": ["Evening vibes. Perfect time for a real conversation."],
    "thanks": ["Anytime! You're welcome 😊", "No need to thank me – just keep chatting!"],
    "goodbye": [
        "Don't be gone too long. I'll be here waiting 😉",
        "Alright, catch you later. It was good talking to you!"
    ],
    "default": [
        "I'd love to hear more about that. Go on…",
        "Interesting. Tell me why that matters to you.",
        "I'm all ears. What's on your mind?",
        "That's a unique thing to say. You've got my attention."
    ]
}

# ==================== INTENT DETECTION ====================

def detect_intent(message, chat_id):
    """Detect user intent from message"""
    if not message:
        return "greeting"

    msg = message.strip().lower()
    info = conversation_memory.get_user_info(chat_id)

    # Priority 1: User is answering a pending question
    waiting_for = info.get('waiting_for')
    if waiting_for:
        return f"answering_{waiting_for}"

    # Priority 2: Direct questions about the bot
    if any(q in msg for q in ['are you abel', 'is that abel', 'abel?', 'you abel', 'am i talking to abel']):
        return "confirm_identity"
    if any(q in msg for q in ['who are you', 'who r u', 'what is your name', 'your name', 'ur name']):
        return "who_am_i"

    # Priority 3: Greetings
    greeting_words = ['hi', 'hello', 'hey', 'selam', 'yo', 'hola', 'howdy', 'good morning', 'good evening']
    if msg in greeting_words or any(msg.startswith(g) for g in greeting_words):
        if not info['greeting_sent']:
            return "greeting"
        else:
            return "already_greeted_again"

    # Other triggers
    if any(q in msg for q in ['how are you', 'how r u', 'how you doing']):
        return "how_are_you"
    if any(q in msg for q in ['what are you doing', 'wyd', 'whats up', "what's up"]):
        return "what_doing"
    if any(q in msg for q in ['how old are you', 'your age']):
        return "how_old_am_i"
    if any(q in msg for q in ['where are you', 'your location']):
        return "where_am_i"
    if any(q in msg for q in ['what do you do', 'your job', 'whats your job']):
        return "what_is_my_job"
    if any(phrase in msg for phrase in ['my name', 'i am', "i'm", 'im', 'call me']):
        return "user_tells_name"
    if any(w in msg for w in ['sexy', 'hot', 'gorgeous', 'beautiful', 'handsome', 'cutie', 'sweetie']):
        return "flirty"
    if any(w in msg for w in ['bro', 'dude', 'man', 'brother']):
        return "bro_compliment"
    if any(w in msg for w in ['money', 'birr', 'telebirr', 'send me']):
        return "money_mention"
    if any(w in msg for w in ['photo', 'pic', 'picture', 'selfie']):
        return "photo_request"
    if any(w in msg for w in ['video', 'clip', 'video call']):
        return "video_request"
    if any(w in msg for w in ['meet', 'see each other', 'hang out']):
        return "meet"
    if msg in ['yes', 'yeah', 'yep', 'ok', 'okay', 'sure', 'yup']:
        return "agree"
    if msg in ['no', 'nope', 'nah']:
        return "disagree"
    if any(w in msg for w in ['thanks', 'thank you', 'thx']):
        return "thanks"
    if any(w in msg for w in ['bye', 'goodbye', 'see you', 'later']):
        return "goodbye"
    if 'voice' in msg or 'voice message' in msg:
        return "voice_received"
    if 'photo' in msg or 'video' in msg or 'sticker' in msg:
        return "media_received"
    if 'http' in msg and '://' in msg:
        return "link_received"
    
    # Time-based greetings
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 18:
        return "afternoon"
    else:
        return "evening"
    
    return "default"

# ==================== RESPONSE GENERATION ====================

def generate_rule_based_response(intent, chat_id, message_text):
    """Generate response based on rules"""
    info = conversation_memory.get_user_info(chat_id)
    gender = info.get('gender')

    if intent == "confirm_identity":
        conversation_memory.set_greeting_sent(chat_id)
        conversation_memory.advance_stage(chat_id)
        return random.choice(ABEL_REPLIES["confirm_identity"])

    if intent == "who_am_i":
        return random.choice(ABEL_REPLIES["who_am_i"])

    if intent == "greeting":
        conversation_memory.set_greeting_sent(chat_id)
        conversation_memory.advance_stage(chat_id)
        if gender == 'female':
            return random.choice(ABEL_REPLIES["greeting_female"])
        elif gender == 'male':
            return random.choice(ABEL_REPLIES["greeting_male"])
        else:
            return random.choice(ABEL_REPLIES["greeting_unknown"])

    if intent == "already_greeted_again":
        stage = info['stage']
        stage_responses = {
            'ask_name': "ask_name",
            'ask_age': "ask_age",
            'ask_location': "ask_location",
            'ask_job': "ask_job"
        }
        key = stage_responses.get(stage, "default")
        return random.choice(ABEL_REPLIES.get(key, ABEL_REPLIES["default"]))

    if intent == "answering_name":
        name = conversation_memory.extract_name(message_text)
        if name and name != "ASKING_MY_NAME":
            info['name'] = name
            conversation_memory.detect_gender(chat_id, message_text, name)
            gender = info.get('gender')
            conversation_memory.clear_waiting(chat_id)
            conversation_memory.advance_stage(chat_id)
            if gender == 'female':
                return random.choice(ABEL_REPLIES["user_tells_name_female"]).format(name=name)
            elif gender == 'male':
                return random.choice(ABEL_REPLIES["user_tells_name_male"]).format(name=name)
            else:
                return random.choice(ABEL_REPLIES["user_tells_name_unknown"]).format(name=name)
        else:
            return random.choice(ABEL_REPLIES["ask_name"])

    if intent == "answering_age":
        age_match = re.search(r'(\d+)', message_text)
        if age_match:
            info['age'] = age_match.group(1)
            conversation_memory.clear_waiting(chat_id)
            conversation_memory.advance_stage(chat_id)
            return random.choice(ABEL_REPLIES["user_tells_age"]).format(age=info['age'])
        else:
            return random.choice(ABEL_REPLIES["ask_age"])

    if intent == "answering_location":
        loc = message_text.strip().title()
        info['location'] = loc
        conversation_memory.clear_waiting(chat_id)
        conversation_memory.advance_stage(chat_id)
        return random.choice(ABEL_REPLIES["user_tells_location"]).format(location=loc)

    if intent == "answering_job":
        job = message_text.strip().title()
        info['job'] = job
        conversation_memory.clear_waiting(chat_id)
        conversation_memory.advance_stage(chat_id)
        return random.choice(ABEL_REPLIES["user_tells_job"]).format(job=job)

    if intent == "answering_interests":
        info['interests'] = [x.strip() for x in message_text.split(',') if x.strip()]
        conversation_memory.clear_waiting(chat_id)
        conversation_memory.advance_stage(chat_id)
        return random.choice(ABEL_REPLIES["acknowledge_interests"])

    if intent == "how_old_am_i":
        return f"I'm {ABEL['age']}. Now, what about you?"
    if intent == "where_am_i":
        return f"I live in {ABEL['location']}. Where are you?"
    if intent == "what_is_my_job":
        return f"I'm a {ABEL['job']}. How do you spend your days?"

    # Map intents to reply keys
    mapping = {
        "how_are_you": "how_are_you",
        "what_doing": "what_doing",
        "flirty": "flirty",
        "bro_compliment": "bro_compliment",
        "money_mention": "money_mention",
        "photo_request": "photo_request",
        "video_request": "video_request",
        "meet": "meet",
        "agree": "agree",
        "disagree": "disagree",
        "confused": "confused",
        "voice_received": "voice_received",
        "media_received": "media_received",
        "link_received": "link_received",
        "morning": "morning",
        "night": "night",
        "afternoon": "afternoon",
        "evening": "evening",
        "thanks": "thanks",
        "goodbye": "goodbye",
        "default": "default"
    }

    if intent in mapping:
        return random.choice(ABEL_REPLIES.get(mapping[intent], ABEL_REPLIES["default"]))

    return random.choice(ABEL_REPLIES["default"])

# ==================== AUTO REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages for auto-reply"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # Skip group chats and channels
        if (hasattr(chat, 'title') and chat.title) or \
           (hasattr(chat, 'participants_count') and chat.participants_count and chat.participants_count > 2):
            return

        chat_id = str(event.chat_id)
        message_text = event.message.text or ""

        # Handle media messages
        if event.message.media:
            if hasattr(event.message.media, 'voice'):
                message_text = "[Voice Message] " + message_text
            elif hasattr(event.message.media, 'photo'):
                message_text = "[Photo] " + message_text
            elif hasattr(event.message.media, 'video'):
                message_text = "[Video] " + message_text
            elif hasattr(event.message.media, 'sticker'):
                message_text = "[Sticker] " + message_text

        # Check if auto-reply is enabled for this account
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return

        # Detect gender from message
        conversation_memory.detect_gender(chat_id, message_text)

        # Generate response
        intent = detect_intent(message_text, chat_id)
        logger.info(f"Intent for chat {chat_id}: {intent}")
        
        response = generate_rule_based_response(intent, chat_id, message_text)

        if not response:
            response = "Hey there! Abel here. What's on your mind? 😊"

        # Add emoji occasionally
        if random.random() < ABEL["emoji_frequency"] and "😊" not in response:
            response += " " + random.choice(["😉", "😏", "😎", "😊", "🔥"])

        # Update waiting state
        info = conversation_memory.get_user_info(chat_id)
        if not info['name']:
            conversation_memory.set_waiting_for(chat_id, "name")
        elif not info['age']:
            conversation_memory.set_waiting_for(chat_id, "age")
        elif not info['location']:
            conversation_memory.set_waiting_for(chat_id, "location")
        elif not info['job']:
            conversation_memory.set_waiting_for(chat_id, "job")
        elif not info['interests']:
            conversation_memory.set_waiting_for(chat_id, "interests")
        else:
            conversation_memory.clear_waiting(chat_id)

        # Random delay to seem human (15-40 seconds)
        delay = random.randint(15, 40)
        logger.info(f"Replying in {delay}s to chat {chat_id}")
        
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)

        await event.reply(response)
        logger.info(f"Sent reply to chat {chat_id}: {response[:80]}...")

        # Save conversation history
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        conversation_history[account_key][chat_id].append({
            "role": "user", "text": message_text, "time": int(time.time())
        })
        conversation_history[account_key][chat_id].append({
            "role": "assistant", "text": response, "time": int(time.time())
        })
        
        # Keep only last 50 messages
        conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-50:]
        save_json_file(CONVERSATION_HISTORY_FILE, conversation_history)

    except Exception as e:
        logger.error(f"Error in auto-reply handler: {e}")
        try:
            await event.reply("Hey! Something glitched, but I'm still here 😊")
        except:
            pass

async def start_auto_reply_for_account(account):
    """Start auto-reply for a specific account"""
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
                device_model="Desktop",
                system_version="Windows 10",
                app_version="1.0"
            )
            
            await client.connect()

            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized - removing")
                remove_invalid_account(account_id)
                break

            active_clients[account_key] = client

            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)

            logger.info(f"✅ Auto-reply ACTIVE for account {account.get('name', 'Unknown')}")
            reconnect_count = 0
            await client.run_until_disconnected()

        except Exception as e:
            logger.error(f"Connection lost for account {account_id}: {e}")
            if account_key in active_clients:
                try:
                    del active_clients[account_key]
                except:
                    pass
            
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            logger.info(f"Reconnecting in {wait_time}s...")
            await asyncio.sleep(wait_time)

def stop_auto_reply_for_account(account_id):
    """Stop auto-reply for a specific account"""
    account_key = str(account_id)
    if account_key in active_clients:
        try:
            run_async(active_clients[account_key].disconnect())
            del active_clients[account_key]
            logger.info(f"Stopped auto-reply for account {account_key}")
        except Exception as e:
            logger.error(f"Error stopping auto-reply: {e}")

def start_all_auto_replies():
    """Start auto-reply for all enabled accounts"""
    logger.info("Starting all auto-replies...")
    for account in accounts:
        account_key = str(account['id'])
        if account_key in reply_settings and reply_settings[account_key].get('enabled', False):
            if account_key not in active_clients:
                thread = threading.Thread(
                    target=lambda acc=account: run_async(start_auto_reply_for_account(acc)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
                logger.info(f"Started auto-reply thread for account {account.get('name')}")

# ==================== PROFESSIONAL AUTO-ADD SYSTEM ====================

async def get_all_potential_members(client, settings, existing_members_set):
    """Get potential members from ALL available sources"""
    potential_members = set()
    sources_stats = {}
    
    # 1. Get from contacts
    if settings.get('use_contacts', True):
        try:
            logger.info("📱 Scanning contacts...")
            contacts = await client(functions.contacts.GetContactsRequest(0))
            contact_ids = set()
            for user in contacts.users:
                if user and user.id:
                    if settings.get('skip_bots', True) and user.bot:
                        continue
                    contact_ids.add(user.id)
            
            new_from_contacts = contact_ids - existing_members_set
            potential_members.update(new_from_contacts)
            sources_stats['contacts'] = {'found': len(contact_ids), 'new': len(new_from_contacts)}
            logger.info(f"   ✅ Contacts: {len(contact_ids)} found, {len(new_from_contacts)} new")
        except Exception as e:
            logger.error(f"   ❌ Contacts error: {e}")
    
    # 2. Get from recent dialogs
    if settings.get('use_recent_chats', True):
        try:
            logger.info("💬 Scanning recent chats...")
            dialogs = await client.get_dialogs(limit=500)
            dialog_ids = set()
            for dialog in dialogs:
                if dialog.is_user and dialog.entity and dialog.entity.id:
                    user = dialog.entity
                    if settings.get('skip_bots', True) and user.bot:
                        continue
                    dialog_ids.add(user.id)
            
            new_from_dialogs = dialog_ids - existing_members_set
            potential_members.update(new_from_dialogs)
            sources_stats['recent_chats'] = {'found': len(dialog_ids), 'new': len(new_from_dialogs)}
            logger.info(f"   ✅ Recent chats: {len(dialog_ids)} found, {len(new_from_dialogs)} new")
        except Exception as e:
            logger.error(f"   ❌ Recent chats error: {e}")
    
    # 3. Scrape from source groups
    if settings.get('use_scraping', True):
        source_groups = settings.get('source_groups', [])
        scrape_limit = settings.get('scrape_limit_per_group', 200)
        
        for group_ref in source_groups:
            if not group_ref or not group_ref.strip():
                continue
            
            group_ref_clean = group_ref.strip()
            if group_ref_clean.startswith('https://t.me/'):
                group_ref_clean = group_ref_clean.replace('https://t.me/', '@')
            elif not group_ref_clean.startswith('@'):
                group_ref_clean = '@' + group_ref_clean
            
            try:
                logger.info(f"👥 Scraping {group_ref_clean}...")
                source_group = await client.get_entity(group_ref_clean)
                
                scraped_ids = set()
                async for user in client.iter_participants(source_group, limit=scrape_limit):
                    if user and user.id:
                        if settings.get('skip_bots', True) and user.bot:
                            continue
                        scraped_ids.add(user.id)
                        if len(scraped_ids) >= scrape_limit:
                            break
                
                new_from_group = scraped_ids - existing_members_set
                potential_members.update(new_from_group)
                sources_stats[group_ref_clean] = {'found': len(scraped_ids), 'new': len(new_from_group)}
                logger.info(f"   ✅ {group_ref_clean}: {len(scraped_ids)} found, {len(new_from_group)} new")
                
            except errors.FloodWaitError as e:
                logger.warning(f"   ⏳ Flood wait {e.seconds}s for {group_ref_clean}")
            except Exception as e:
                logger.error(f"   ❌ {group_ref_clean} error: {e}")
    
    # 4. Get mutual contacts
    if settings.get('use_mutual_contacts', True):
        try:
            logger.info("🤝 Scanning mutual contacts...")
            mutual = await client(functions.contacts.GetTopPeersRequest(
                correspondents=True,
                bots_pm=False,
                groups=False,
                channels=False,
                limit=100
            ))
            mutual_ids = set()
            if mutual.categories:
                for category in mutual.categories:
                    for peer in category.peers:
                        if hasattr(peer, 'user_id'):
                            mutual_ids.add(peer.user_id)
            
            new_from_mutual = mutual_ids - existing_members_set
            potential_members.update(new_from_mutual)
            sources_stats['mutual_contacts'] = {'found': len(mutual_ids), 'new': len(new_from_mutual)}
            logger.info(f"   ✅ Mutual contacts: {len(mutual_ids)} found, {len(new_from_mutual)} new")
        except Exception as e:
            logger.error(f"   ❌ Mutual contacts error: {e}")
    
    return potential_members, sources_stats

async def professional_auto_add_loop(account):
    """Professional auto-add loop with multi-source member collection"""
    account_id = account['id']
    account_key = str(account_id)
    
    attempted_members = set()
    auto_joined = False
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    logger.info(f"🚀 Professional Auto-Add started for account {account_id}")
    
    while True:
        try:
            # Check if still enabled
            if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                logger.info(f"Auto-add disabled for account {account_id}, stopping")
                break
            
            settings = auto_add_settings[account_key]
            target_group = settings.get('target_group', 'Abe_armygroup')
            delay_seconds = settings.get('delay_seconds', 25)
            
            # Clean target group name
            if not target_group.startswith('@') and not target_group.startswith('https://'):
                target_group = '@' + target_group
            elif target_group.startswith('https://t.me/'):
                target_group = '@' + target_group.replace('https://t.me/', '')
            
            # Create client
            client = TelegramClient(
                StringSession(account['session']), 
                API_ID, 
                API_HASH,
                connection_retries=5,
                retry_delay=5,
                timeout=60
            )
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                # Reset daily counter if new day
                today = datetime.now().strftime('%Y-%m-%d')
                if settings.get('last_reset') != today:
                    settings['added_today'] = 0
                    settings['last_reset'] = today
                    attempted_members.clear()
                    save_json_file(AUTO_ADD_FILE, auto_add_settings)
                    logger.info(f"📅 New day! Reset daily counter")
                
                # Auto-join target group if needed
                if not auto_joined and settings.get('auto_join', True):
                    try:
                        logger.info(f"🔗 Attempting to join {target_group}...")
                        group = await client.get_entity(target_group)
                        try:
                            await client(functions.messages.ImportChatInviteRequest(group.username))
                        except:
                            pass
                        auto_joined = True
                        logger.info(f"✅ Connected to {target_group}")
                    except Exception as e:
                        logger.warning(f"Could not join {target_group}: {e}")
                
                # Get target group
                try:
                    group = await client.get_entity(target_group)
                    logger.info(f"🎯 Target group: {group.title if hasattr(group, 'title') else target_group}")
                except Exception as e:
                    logger.error(f"❌ Cannot find target group {target_group}: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get existing members
                logger.info("📋 Getting existing members...")
                existing_members = set()
                try:
                    async for user in client.iter_participants(group, limit=5000):
                        if user and user.id:
                            existing_members.add(user.id)
                    logger.info(f"   Group has {len(existing_members)} existing members")
                except Exception as e:
                    logger.error(f"Error getting existing members: {e}")
                
                # Get potential members from all sources
                logger.info("🔍 Collecting potential members from ALL sources...")
                potential_members, sources_stats = await get_all_potential_members(
                    client, settings, existing_members
                )
                
                total_found = sum(s.get('found', 0) for s in sources_stats.values() if isinstance(s, dict))
                total_new = sum(s.get('new', 0) for s in sources_stats.values() if isinstance(s, dict))
                
                logger.info(f"📊 SUMMARY: {total_found} total found, {total_new} new members available")
                
                if not potential_members:
                    logger.info("😴 No new members available. Waiting 10 minutes...")
                    await asyncio.sleep(600)
                    continue
                
                # Filter out attempted members
                fresh_members = potential_members - attempted_members
                logger.info(f"🎯 {len(fresh_members)} members to add")
                
                if not fresh_members:
                    logger.info("All potential members attempted. Clearing history...")
                    attempted_members.clear()
                    fresh_members = potential_members
                
                # Add members one by one
                added_this_cycle = 0
                
                for user_id in list(fresh_members):
                    try:
                        if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                            break
                        
                        attempted_members.add(user_id)
                        
                        if user_id in existing_members:
                            continue
                        
                        try:
                            user_entity = await client.get_input_entity(user_id)
                            
                            await client(functions.channels.InviteToChannelRequest(
                                group,
                                [user_entity]
                            ))
                            
                            settings['added_today'] = settings.get('added_today', 0) + 1
                            settings['total_added'] = settings.get('total_added', 0) + 1
                            settings['last_added'] = datetime.now().isoformat()
                            added_this_cycle += 1
                            existing_members.add(user_id)
                            
                            if added_this_cycle % 10 == 0:
                                save_json_file(AUTO_ADD_FILE, auto_add_settings)
                            
                            logger.info(f"✅ Added user {user_id} | Today: {settings['added_today']} | Total: {settings['total_added']}")
                            
                            consecutive_errors = 0
                            await asyncio.sleep(delay_seconds)
                            
                        except errors.FloodWaitError as e:
                            logger.warning(f"⏳ Flood wait {e.seconds}s")
                            await asyncio.sleep(e.seconds + 5)
                        except (errors.UserPrivacyRestrictedError, errors.UserNotMutualContactError):
                            logger.info(f"🔒 User {user_id} has restrictions")
                            continue
                        except errors.UserAlreadyParticipantError:
                            logger.info(f"👥 User {user_id} already in group")
                            existing_members.add(user_id)
                            continue
                        except Exception as e:
                            consecutive_errors += 1
                            logger.error(f"Error adding {user_id}: {e}")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                logger.warning(f"⚠️ Too many errors. Pausing 5 minutes...")
                                await asyncio.sleep(300)
                                consecutive_errors = 0
                            continue
                            
                    except Exception as e:
                        logger.error(f"Unexpected error with user {user_id}: {e}")
                        continue
                
                save_json_file(AUTO_ADD_FILE, auto_add_settings)
                
                logger.info(f"📈 Cycle complete: Added {added_this_cycle} members")
                logger.info(f"   Today: {settings['added_today']} | All-time: {settings['total_added']}")
                
                # Wait between cycles
                if added_this_cycle > 0:
                    wait_time = random.randint(60, 180)
                else:
                    wait_time = random.randint(300, 600)
                
                logger.info(f"⏰ Waiting {wait_time//60} minutes before next scan...")
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            await asyncio.sleep(random.randint(60, 300))
            
        except Exception as e:
            logger.error(f"Critical error in auto-add loop: {e}")
            await asyncio.sleep(300)

# ==================== KEEP ALIVE SYSTEM ====================

def keep_alive():
    """Keep Render from sleeping"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=10)
            logger.info(f"🔋 Keep-alive ping at {time.strftime('%H:%M:%S')}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(240)  # 4 minutes

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

@app.route('/auto-add')
def auto_add():
    return send_file('auto_add.html')

@app.route('/settings')
def settings():
    return send_file('settings.html')

@app.route('/fog')
def fog():
    return send_file('fog.html')

# ==================== API ROUTES ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'time': datetime.now().isoformat()
    })

@app.route('/api/ping')
def ping():
    return jsonify({'pong': True, 'time': time.time()})

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = []
    for acc in accounts:
        account_key = str(acc['id'])
        has_reply = account_key in reply_settings and reply_settings[account_key].get('enabled', False)
        has_auto_add = account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False)
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'auto_reply_enabled': has_reply,
            'auto_add_enabled': has_auto_add
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
                retry_delay=2,
                timeout=15
            )
            try:
                await client.connect()
                logger.info(f"Connected to Telegram for {phone}")
                
                result = await client.send_code_request(phone)
                logger.info(f"Code sent successfully to {phone}")
                
                session_id = str(int(time.time() * 1000))
                temp_sessions[session_id] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': session_id}
                
            except errors.FloodWaitError as e:
                logger.warning(f"Flood wait for {phone}: {e.seconds}s")
                return {'success': False, 'error': f'Please wait {e.seconds} seconds before trying again'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except errors.PhoneNumberBannedError:
                return {'success': False, 'error': 'This phone number is banned from Telegram'}
            except Exception as e:
                logger.error(f"Error sending code: {e}")
                return {'success': False, 'error': f'Cannot send code: {str(e)}'}
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
        return jsonify({'success': False, 'error': 'Missing code or session ID'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired. Please try again.'})
    
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
                    return {'success': False, 'need_password': True, 'error': '2FA password required'}
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
            save_json_file(ACCOUNTS_FILE, accounts)
            
            logger.info(f"✅ Account added: {me.first_name} ({me.phone})")
            return {'success': True, 'account': {'id': new_id, 'name': me.first_name, 'phone': me.phone}}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid verification code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired. Please request a new one.'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid 2FA password'}
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        # Clean up session
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
                remove_invalid_account(account_id)
                return {'success': False, 'error': 'Account session expired. Please re-login.'}
            
            dialogs = await client.get_dialogs(limit=50)
            
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
                        if hasattr(dialog.message.media, 'photo'):
                            chat['lastMessage'] = '📷 Photo'
                        elif hasattr(dialog.message.media, 'video'):
                            chat['lastMessage'] = '🎬 Video'
                        elif hasattr(dialog.message.media, 'voice'):
                            chat['lastMessage'] = '🎤 Voice message'
                        else:
                            chat['lastMessage'] = '📎 Media'
                    
                    if dialog.message.date:
                        chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                
                chats.append(chat)
            
            return {'success': True, 'chats': chats}
            
        except AuthKeyUnregisteredError:
            remove_invalid_account(account_id)
            return {'success': False, 'error': 'Session expired'}
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
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
    
    if not all([account_id, chat_id, message]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Session expired'}
            
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True, 'message': 'Sent successfully'}
            
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
    
    # Stop services
    stop_auto_reply_for_account(account_id)
    
    # Remove from settings
    account_key = str(account_id)
    if account_key in reply_settings:
        del reply_settings[account_key]
        save_json_file(REPLY_SETTINGS_FILE, reply_settings)
    
    if account_key in auto_add_settings:
        del auto_add_settings[account_key]
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
    
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_json_file(ACCOUNTS_FILE, accounts)
        return jsonify({'success': True, 'message': 'Account removed'})
    
    return jsonify({'success': False, 'error': 'Account not found'})

@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    settings = reply_settings.get(account_key, {'enabled': False})
    
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    if account_key not in reply_settings:
        reply_settings[account_key] = {}
    
    was_enabled = reply_settings[account_key].get('enabled', False)
    reply_settings[account_key]['enabled'] = enabled
    
    save_json_file(REPLY_SETTINGS_FILE, reply_settings)
    
    # Start or stop based on setting
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
    
    return jsonify({'success': True, 'message': f'Auto-reply {"enabled" if enabled else "disabled"}'})

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
        save_json_file(CONVERSATION_HISTORY_FILE, conversation_history)
    
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
                    'date_created': str(auth.date_created) if auth.date_created else None,
                    'date_active': str(auth.date_active) if auth.date_active else None,
                    'ip': auth.ip,
                    'country': auth.country,
                    'region': auth.region,
                    'current': auth.current
                }
                
                if auth.current:
                    current_hash = auth.hash
                
                sessions.append(session_info)
            
            return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            
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
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
            return {'success': True, 'message': 'Session terminated'}
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

# ==================== AUTO-ADD API ROUTES ====================

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    default_settings = {
        'enabled': False,
        'target_group': 'Abe_armygroup',
        'delay_seconds': 25,
        'source_groups': ['@telegram', '@durov', '@TechCrunch', '@bbcnews', '@cnn'],
        'use_contacts': True,
        'use_recent_chats': True,
        'use_scraping': True,
        'use_mutual_contacts': True,
        'scrape_limit_per_group': 200,
        'skip_bots': True,
        'skip_inaccessible': True,
        'auto_join': True,
        'total_added': 0,
        'added_today': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'last_added': None
    }
    
    if account_key in auto_add_settings:
        settings = auto_add_settings[account_key]
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
    else:
        settings = default_settings.copy()
        auto_add_settings[account_key] = settings
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
    
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data received'})
        
        account_id = data.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account_key = str(account_id)
        
        if account_key not in auto_add_settings:
            auto_add_settings[account_key] = {}
        
        was_enabled = auto_add_settings[account_key].get('enabled', False)
        
        # Update all settings
        auto_add_settings[account_key].update({
            'enabled': data.get('enabled', False),
            'target_group': data.get('target_group', 'Abe_armygroup'),
            'delay_seconds': data.get('delay_seconds', 25),
            'source_groups': data.get('source_groups', []),
            'use_contacts': data.get('use_contacts', True),
            'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True),
            'use_mutual_contacts': data.get('use_mutual_contacts', True),
            'scrape_limit_per_group': data.get('scrape_limit_per_group', 200),
            'skip_bots': data.get('skip_bots', True),
            'skip_inaccessible': data.get('skip_inaccessible', True),
            'auto_join': data.get('auto_join', True)
        })
        
        # Initialize counters
        if 'total_added' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['total_added'] = 0
        if 'added_today' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['added_today'] = 0
        
        # Reset daily counter if new day
        today = datetime.now().strftime('%Y-%m-%d')
        if auto_add_settings[account_key].get('last_reset') != today:
            auto_add_settings[account_key]['added_today'] = 0
            auto_add_settings[account_key]['last_reset'] = today
        
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
        
        logger.info(f"Auto-add settings saved for account {account_id}: enabled={auto_add_settings[account_key]['enabled']}")
        
        # Start or stop auto-add
        enabled = auto_add_settings[account_key]['enabled']
        if enabled and not was_enabled:
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(professional_auto_add_loop(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[f"auto_add_{account_key}"] = thread
                logger.info(f"🚀 Started auto-add for account {account_id}")
        
        return jsonify({'success': True, 'message': 'Auto-add settings updated'})
        
    except Exception as e:
        logger.error(f"Error updating auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    settings = auto_add_settings.get(account_key, {})
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
        'total_added': settings.get('total_added', 0),
        'enabled': settings.get('enabled', False),
        'last_reset': settings.get('last_reset', ''),
        'last_added': settings.get('last_added')
    })

# ==================== STARTUP ====================

def start_auto_add_threads():
    """Start auto-add for all enabled accounts after server starts"""
    time.sleep(5)
    logger.info("Starting auto-add threads...")
    for account in accounts:
        account_key = str(account['id'])
        if account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False):
            thread = threading.Thread(
                target=lambda acc=account: run_async(professional_auto_add_loop(acc)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_key}"] = thread
            logger.info(f"Started auto-add for account {account.get('name')}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM MULTI-ACCOUNT MANAGER v2.0')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Reply settings loaded: {len(reply_settings)}')
    print(f'✅ Auto-add settings loaded: {len(auto_add_settings)}')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    logger.info("✅ Keep-alive started")
    
    # Start auto-reply for enabled accounts
    threading.Thread(target=start_all_auto_replies, daemon=True).start()
    logger.info("✅ Auto-reply threads started")
    
    # Start auto-add for enabled accounts
    threading.Thread(target=start_auto_add_threads, daemon=True).start()
    logger.info("✅ Auto-add threads started")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
