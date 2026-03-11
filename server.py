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
        logger.info(f"Removed invalid account {account_id}")
        return True
    return False

# Load all data on startup
load_accounts()
load_reply_settings()
load_conversation_history()

# ==================== PROFESSIONAL CONVERSATION ENGINE ====================

# Personality configuration - Customize this!
PERSONALITY = {
    "name": "Sofia",
    "age": 28,
    "location": "Dubai",
    "job": "marketing consultant",
    "hobbies": ["traveling", "photography", "yoga"],
    "languages": ["English", "Arabic", "Hindi"],
    "style": "friendly_professional",
    "share_personal": True,
    "emoji_frequency": 0.3,
    "question_frequency": 0.4,
}

# Comprehensive response templates for ANY conversation
RESPONSES = {
    "greeting": [
        "Hi there! How's your day going?",
        "Hello! Nice to meet you.",
        "Hey! How are you doing today?",
        "Hi! What's new with you?"
    ],
    "how_are_you": [
        "I'm doing great, thanks for asking! Just busy with work. How about you?",
        "Pretty good! Enjoying my day so far. You?",
        "All good here! Just relaxing a bit. How are things with you?",
        "Can't complain! Life's good. What about you?"
    ],
    "what_doing": [
        "Just working on some projects right now. You know how it is!",
        "Taking a short break between meetings. What are you up to?",
        "Chilling at home, catching up on some reading. You?",
        "Just finished work, finally relaxing now!"
    ],
    "ask_name": [
        "I'm {name}. What's your name?",
        "My name is {name}. And you are?",
        "I'm {name}. Nice to meet you! What should I call you?"
    ],
    "ask_age": [
        "I'm {age}. How about you?",
        "{age} years young! What's your age?",
        "I just turned {age} recently. You?"
    ],
    "ask_location": [
        "I'm based in {location}. Where are you from?",
        "I live in {location}. What about you?",
        "{location} is home for me. Where do you call home?"
    ],
    "ask_job": [
        "I work as a {job}. What do you do for a living?",
        "I'm a {job}. Been doing it for a few years now. What's your profession?",
        "I work in {job}. It keeps me busy! What line of work are you in?"
    ],
    "ask_hobbies": [
        "I love {hobbies[0]}, {hobbies[1]}, and {hobbies[2]}. What are your hobbies?",
        "In my free time I enjoy {hobbies[0]} and {hobbies[1]}. What do you do for fun?",
        "I'm really into {hobbies[0]} these days. Any hobbies you're passionate about?"
    ],
    "languages": [
        "I speak {languages[0]}, {languages[1]}, and {languages[2]}. How many languages do you speak?",
        "I'm fluent in {languages[0]} and {languages[1]}. What languages do you know?",
        "Learning {languages[0]} was tough but worth it! Do you speak multiple languages?"
    ],
    "work": [
        "Work's been keeping me busy lately. How's your work life?",
        "Just finished a big project at work. Feels good! What's new at your job?",
        "Work is work, you know? Gets the bills paid. How are things on your end?",
        "Been working from home mostly. Kind of nice actually. How do you prefer to work?"
    ],
    "weekend": [
        "Looking forward to the weekend! Any fun plans?",
        "Weekend can't come soon enough! What are you up to this weekend?",
        "I'm planning to just relax this weekend. You?",
        "Might go out with friends this weekend. What about you?"
    ],
    "weather": [
        "The weather here in {location} is beautiful today. How's the weather where you are?",
        "It's been so nice lately, perfect for outdoor activities. What's the weather like there?",
        "Rainy day here, perfect for staying in. How's the weather treating you?"
    ],
    "food": [
        "Just had some amazing food! Do you like cooking or eating out?",
        "I'm always down for trying new restaurants. Any recommendations?",
        "Been craving some good food lately. What's your favorite cuisine?",
        "I love cooking on weekends. What's your specialty in the kitchen?"
    ],
    "travel": [
        "I love traveling! Been to 15 countries so far. What about you?",
        "Planning my next trip actually. Do you enjoy traveling?",
        "Traveling is my passion! What's the best place you've visited?",
        "I'd love to visit Japan next. Any travel dreams you're chasing?"
    ],
    "movies": [
        "Just watched a great movie last night. Are you into films?",
        "I'm more of a series person actually. What do you prefer?",
        "Movies are my go-to for relaxing. Seen anything good lately?",
        "What kind of movies do you like? I'm into thrillers mostly."
    ],
    "music": [
        "Music makes everything better! What do you listen to?",
        "I'm always looking for new music recommendations. What's your favorite genre?",
        "Been listening to a lot of indie lately. What's on your playlist?",
        "Do you play any instruments? I've always wanted to learn guitar."
    ],
    "sports": [
        "Not a huge sports fan but I enjoy watching football sometimes. You?",
        "I like staying active, do you play any sports?",
        "Gym is my stress relief. How do you stay fit?",
        "Watched an amazing game last week! Do you follow any sports?"
    ],
    "books": [
        "Currently reading a great book. Are you a reader?",
        "I love getting lost in a good book. What are you reading these days?",
        "Books are my escape. Fiction or non-fiction, what's your preference?",
        "Just finished an amazing novel. Any book recommendations for me?"
    ],
    "relationship": [
        "I'm single, just focusing on myself right now. You?",
        "In a relationship actually. What about you?",
        "It's complicated haha. How about you?",
        "Not looking for anything serious right now. Just enjoying life!"
    ],
    "family": [
        "I'm close with my family. Do you have siblings?",
        "Family is everything to me. Are you close with yours?",
        "I visit my parents whenever I can. What about your family?"
    ],
    "friends": [
        "Got a small but solid friend circle. Quality over quantity right?",
        "My friends are my support system. Do you have many close friends?",
        "Making friends as an adult is hard! How do you meet new people?"
    ],
    "opinion": [
        "That's interesting! What do you think about it?",
        "I never thought of it that way. What's your perspective?",
        "Good point! Why do you feel that way?",
        "I see where you're coming from. Tell me more."
    ],
    "agree": [
        "Totally agree with you!",
        "Exactly what I was thinking!",
        "You're absolutely right.",
        "Couldn't have said it better myself."
    ],
    "disagree": [
        "That's an interesting take. I see it a bit differently though.",
        "I respect your opinion, even if I don't fully agree.",
        "Fair point, but have you considered...",
        "I can see why you'd think that."
    ],
    "surprise": [
        "Wow, really? That's surprising!",
        "No way! Tell me more about that.",
        "Seriously? That's wild!",
        "Oh wow, I didn't expect that at all."
    ],
    "curious": [
        "That's fascinating! How did you get into that?",
        "I'd love to hear more about that.",
        "Really? What's that like?",
        "Interesting! When did that happen?"
    ],
    "compliment": [
        "That's so kind of you to say! Thank you 😊",
        "Aww thanks! You're sweet.",
        "Thank you! That made my day.",
        "You're too kind! Right back at you."
    ],
    "thanks": [
        "You're welcome! Happy to chat.",
        "No problem at all!",
        "Anytime, that's what friends are for.",
        "My pleasure! 😊"
    ],
    "flirty": [
        "Oh stop it, you're making me blush 😊",
        "Haha you're funny!",
        "Smooth talker, aren't you? 😄",
        "I like your style!"
    ],
    "joke": [
        "Haha that's a good one!",
        "LOL you got me there!",
        "😂 That's hilarious!",
        "You have a great sense of humor!"
    ],
    "morning": [
        "Good morning! Hope you slept well. Ready to tackle the day?",
        "Morning! Coffee already? ☕",
        "Rise and shine! How are you this morning?",
        "Good morning! What are your plans for today?"
    ],
    "afternoon": [
        "Good afternoon! How's your day going so far?",
        "Afternoon vibes! Surviving the day?",
        "Hope you're having a productive afternoon!",
        "Afternoon already? Time flies!"
    ],
    "evening": [
        "Good evening! How was your day?",
        "Evening! Finally time to relax, right?",
        "Hope you had a great day! What's for dinner?",
        "Evening chill mode activated! How are you?"
    ],
    "night": [
        "Getting late, should probably sleep soon. You?",
        "Night owl or early bird? I'm both haha",
        "Don't stay up too late!",
        "Goodnight! Sweet dreams! 😴"
    ],
    "goodbye": [
        "Gotta go now, talk later! Take care!",
        "Nice chatting with you! Catch you later 👋",
        "I have to run, but let's chat again soon!",
        "Take care! Message me anytime 😊"
    ],
    "command": [
        "Hi there! Thanks for your message. How are you today?",
        "Hello! How can I help you?",
        "Hey! Good to hear from you. What's up?",
        "Hi! Thanks for reaching out. How's your day going?"
    ],
    "busy": [
        "I understand being busy! What are you working on?",
        "No problem, we can chat whenever you're free. What's keeping you busy?",
        "Busy is good! Keeps life interesting. What are you up to?",
        "I get it, life gets hectic. Hope you're managing okay!"
    ],
    "default": [
        "I see! Tell me more about that.",
        "That's interesting! How so?",
        "Oh really? Go on...",
        "I get what you mean. What else?",
        "That makes sense. What do you think about...",
        "Hmm I never thought about it that way.",
        "Interesting perspective!",
        "Yeah, I know what you mean.",
        "Totally!",
        "For sure."
    ]
}

def detect_conversation_intent(message, history=None):
    """Advanced intent detection for natural conversation"""
    message = message.lower().strip()
    
    # Handle commands
    if message.startswith('/'):
        return "command"
    
    # Handle "I am busy" type messages
    if any(phrase in message for phrase in ['i am busy', "i'm busy", 'im busy', 'busy right now']):
        return "busy"
    
    # Check for empty messages
    if not message:
        return "greeting"
    
    # Time-based greetings
    current_hour = datetime.now().hour
    if any(word in message for word in ['good morning', 'gm']):
        return "morning"
    if any(word in message for word in ['good afternoon', 'good evening']):
        return "evening"
    if any(word in message for word in ['good night', 'gn', 'sweet dreams']):
        return "night"
    
    # Basic greetings
    greetings = ['hi', 'hello', 'hey', 'hy', 'hola', 'hiya', 'howdy']
    if any(word in message for word in greetings) and len(message) < 20:
        return "greeting"
    
    # How are you
    how_are_you = ['how are you', 'how r u', 'how you doing', 'how\'s it going', 'what\'s up', 'sup']
    if any(phrase in message for phrase in how_are_you):
        return "how_are_you"
    
    # What are you doing
    what_doing = ['what are you doing', 'what r u doing', 'what doing', 'wyd', 'what are you up to']
    if any(phrase in message for phrase in what_doing):
        return "what_doing"
    
    # Name related
    if any(phrase in message for phrase in ['your name', 'what is your name', 'who are you', 'u call yourself']):
        return "ask_name"
    
    # Age related
    if any(phrase in message for phrase in ['your age', 'how old are you', 'what is your age', 'you born']):
        return "ask_age"
    
    # Location related
    location_words = ['where are you from', 'where do you live', 'your location', 'which country', 'what city']
    if any(phrase in message for phrase in location_words):
        return "ask_location"
    
    # Job related
    job_words = ['what do you do', 'your job', 'your work', 'what work', 'profession', 'career', 'occupation']
    if any(phrase in message for phrase in job_words):
        return "ask_job"
    
    # Hobbies
    hobby_words = ['hobbies', 'free time', 'what do you like to do', 'what are your interests', 'passionate about']
    if any(phrase in message for phrase in hobby_words):
        return "ask_hobbies"
    
    # Languages
    language_words = ['languages', 'what language', 'do you speak', 'tongues', 'multilingual']
    if any(phrase in message for phrase in language_words):
        return "languages"
    
    # Work talk
    work_words = ['work', 'job', 'office', 'colleague', 'boss', 'career', 'profession']
    if any(word in message for word in work_words):
        return "work"
    
    # Weekend
    weekend_words = ['weekend', 'friday', 'saturday', 'sunday', 'days off']
    if any(word in message for word in weekend_words):
        return "weekend"
    
    # Weather
    weather_words = ['weather', 'rain', 'sunny', 'cloudy', 'hot', 'cold', 'temperature', 'forecast']
    if any(word in message for word in weather_words):
        return "weather"
    
    # Food
    food_words = ['food', 'eat', 'hungry', 'lunch', 'dinner', 'breakfast', 'restaurant', 'cook', 'recipe', 'meal']
    if any(word in message for word in food_words):
        return "food"
    
    # Travel
    travel_words = ['travel', 'trip', 'vacation', 'holiday', 'visit', 'country', 'city', 'tourist', 'fly']
    if any(word in message for word in travel_words):
        return "travel"
    
    # Movies/TV
    movie_words = ['movie', 'film', 'watch', 'show', 'series', 'netflix', 'episode', 'cinema', 'theatre']
    if any(word in message for word in movie_words):
        return "movies"
    
    # Music
    music_words = ['music', 'song', 'sing', 'playlist', 'spotify', 'genre', 'band', 'artist', 'concert']
    if any(word in message for word in music_words):
        return "music"
    
    # Sports
    sports_words = ['sport', 'game', 'match', 'team', 'play', 'ball', 'football', 'cricket', 'gym', 'workout']
    if any(word in message for word in sports_words):
        return "sports"
    
    # Books
    book_words = ['book', 'read', 'reading', 'novel', 'author', 'library', 'chapter', 'story']
    if any(word in message for word in book_words):
        return "books"
    
    # Relationship
    relationship_words = ['relationship', 'single', 'married', 'girlfriend', 'boyfriend', 'partner', 'dating']
    if any(word in message for word in relationship_words):
        return "relationship"
    
    # Family
    family_words = ['family', 'mom', 'dad', 'mother', 'father', 'sister', 'brother', 'parents', 'kids', 'children']
    if any(word in message for word in family_words):
        return "family"
    
    # Friends
    friend_words = ['friend', 'friends', 'buddies', 'social', 'circle', 'hang out']
    if any(word in message for word in friend_words):
        return "friends"
    
    # Compliments
    compliment_words = ['beautiful', 'handsome', 'cute', 'pretty', 'gorgeous', 'sexy', 'hot', 'attractive', 'lovely']
    if any(word in message for word in compliment_words):
        return "compliment"
    
    # Thanks
    thanks_words = ['thanks', 'thank you', 'thx', 'appreciate', 'grateful', 'ty']
    if any(word in message for word in thanks_words):
        return "thanks"
    
    # Jokes/Funny
    joke_words = ['joke', 'funny', 'lol', 'haha', 'hilarious', 'lmao', '😂', '😆']
    if any(word in message for word in joke_words):
        return "joke"
    
    # Agreement
    agreement = ['agree', 'true', 'right', 'exactly', 'same here', 'me too', 'definitely', 'absolutely']
    if any(word in message for word in agreement):
        return "agree"
    
    # Disagreement
    disagreement = ['disagree', 'not sure', 'doubt', 'different', 'not really', 'no way']
    if any(word in message for word in disagreement):
        return "disagree"
    
    # Surprise
    surprise = ['wow', 'really', 'no way', 'seriously', 'omg', 'oh', 'what', 'wtf']
    if any(word in message for word in surprise):
        return "surprise"
    
    # Questions (ends with ?)
    if '?' in message:
        return "curious"
    
    # Check for opinion words
    opinion_words = ['think', 'believe', 'feel', 'opinion', 'view', 'perspective', 'thoughts']
    if any(word in message for word in opinion_words):
        return "opinion"
    
    # Check if it's a goodbye
    goodbye = ['bye', 'goodbye', 'see you', 'talk later', 'cya', 'later', 'take care', 'peace']
    if any(word in message for word in goodbye):
        return "goodbye"
    
    # Default for everything else
    return "default"

def generate_professional_response(intent, history=None):
    """Generate a natural, human-like response"""
    
    # Get response templates for this intent
    templates = RESPONSES.get(intent, RESPONSES["default"])
    
    # Choose random template
    response = random.choice(templates)
    
    # Format with personality variables
    try:
        response = response.format(
            name=PERSONALITY["name"],
            age=PERSONALITY["age"],
            location=PERSONALITY["location"],
            job=PERSONALITY["job"],
            hobbies=PERSONALITY["hobbies"],
            languages=PERSONALITY["languages"]
        )
    except:
        pass
    
    # Add emoji occasionally
    if random.random() < PERSONALITY["emoji_frequency"]:
        emojis = ["😊", "👍", "😄", "🙂", "😉", "🤔", "😅", "👌", "😎", "✨", "💫", "🌟"]
        response += " " + random.choice(emojis)
    
    # Add follow-up question occasionally
    if random.random() < PERSONALITY["question_frequency"] and not response.endswith('?'):
        follow_ups = [
            " What do you think?",
            " How about you?",
            " Right?",
            " You know what I mean?",
            " What's your take on that?",
            " Don't you think so?",
            " What about your side?",
            " How's that sound?"
        ]
        response += random.choice(follow_ups)
    
    return response

def get_context_aware_response(message, intent, history=None):
    """Generate response based on conversation context"""
    
    # Check if this is a follow-up to previous conversation
    if history and len(history) > 1:
        last_exchange = history[-1]
        
        # If user just answered a question, acknowledge it
        if last_exchange.get('role') == 'assistant' and '?' in last_exchange.get('text', ''):
            if intent in ["default", "opinion", "agree"]:
                return "Thanks for sharing that! " + generate_professional_response(intent)
    
    return generate_professional_response(intent)

# ==================== AUTO-REPLY HANDLER WITH AUTO-RECONNECT ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with professional conversation ability"""
    try:
        # Don't reply to our own messages
        if event.out:
            return
        
        # Get chat info
        chat = await event.get_chat()
        
        # ONLY reply to private users (1-on-1 chats), NEVER groups/channels
        is_private = True
        
        # Check if it's a group/channel
        if hasattr(chat, 'title') and chat.title:
            is_private = False
            logger.info(f"Skipping group/channel: {chat.title}")
            return
        
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            is_private = False
            return
        
        if hasattr(chat, 'broadcast') and chat.broadcast:
            is_private = False
            return
        
        if hasattr(chat, 'megagroup') and chat.megagroup:
            is_private = False
            return
        
        # Get sender
        sender = await event.get_sender()
        if not sender:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        # CRITICAL: Always log
        logger.info(f"📨 Message from {chat_id}: '{message_text}'")
        
        # Check if auto-reply is enabled for this account
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            logger.info(f"Auto-reply disabled for account {account_id}")
            return
        
        # Check chat settings
        chat_settings = reply_settings[account_key].get('chats', {})
        chat_enabled = chat_settings.get(chat_id, {}).get('enabled', True)
        
        if not chat_enabled:
            logger.info(f"Chat {chat_id} has auto-reply disabled")
            return
        
        # Initialize conversation history
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        # Add user message to history
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time()
        })
        
        # Keep last 15 messages
        if len(conversation_history[account_key][chat_id]) > 15:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-15:]
        
        # Detect intent
        intent = detect_conversation_intent(message_text, conversation_history[account_key][chat_id])
        logger.info(f"Detected intent: {intent}")
        
        # Generate response
        response = get_context_aware_response(message_text, intent, conversation_history[account_key][chat_id])
        
        # Ensure we always have a response
        if not response or response.strip() == "":
            response = "I see. Tell me more about that."
        
        # Simulate typing (1-5 seconds)
        typing_duration = min(5, max(1, len(response) // 20))
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(typing_duration)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied: '{response[:100]}'")
        
        # Add bot response to history
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        # Save conversation
        save_conversation_history()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        # Try fallback
        try:
            await event.reply("Hi there! Thanks for your message. How can I help you today?")
        except:
            pass

async def start_auto_reply_for_account(account):
    """Start auto-reply listener with AUTO-RECONNECT capability"""
    account_id = account['id']
    account_key = str(account_id)
    reconnect_count = 0
    
    while True:  # Infinite reconnect loop
        try:
            logger.info(f"Starting auto-reply for account {account_id} (attempt {reconnect_count + 1})")
            
            # Create client with robust settings
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
            
            # Check authorization
            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized")
                await asyncio.sleep(30)
                reconnect_count += 1
                continue
            
            # Store client
            active_clients[account_key] = client
            
            # Define message handler
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            # Start client
            await client.start()
            logger.info(f"✅ Auto-reply ACTIVE for {account.get('name')} ({account.get('phone')})")
            
            # Reset reconnect count on success
            reconnect_count = 0
            
            # Keep running until disconnected
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost for account {account_id}: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            
            # Exponential backoff for reconnection
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)  # Max 5 minutes
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
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')
    
    while True:
        try:
            # Ping own app
            requests.get(app_url, timeout=10)
            requests.get(f"{app_url}/api/health", timeout=10)
            
            # Ping Telegram to keep connections alive
            for account_key, client in list(active_clients.items()):
                try:
                    # Send a tiny ping to Telegram
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

@app.route('/settings')
def settings():
    return send_file('settings.html')

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
    
    # Start or stop based on new setting
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM AUTO-REPLY FOR REAL ACCOUNTS')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status}')
    
    print('='*70)
    print('🚀 FEATURES:')
    print('   • 24/7 Auto-reply for REAL Telegram accounts')
    print('   • AUTO-RECONNECT on disconnect')
    print('   • KEEP-ALIVE system prevents sleeping')
    print('   • Replies ONLY to private chats')
    print('   • Natural human-like conversations')
    print('   • Remembers context (last 15 messages)')
    print('   • Simulates typing delays')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
