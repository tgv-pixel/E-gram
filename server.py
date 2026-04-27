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

# Save accounts
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

# ==================== ABEL – THE GENTLEMAN PLAYER (AI-READY) ====================

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
        "Let’s keep it real, though 😏",
        "You’ve got my curiosity piqued…",
        "I bet you’re trouble in the best way 😄",
        "Come on, tell me more about you.",
        "I’ve got a feeling this conversation is going somewhere fun.",
        "Honesty – that’s rare. I like that.",
        "You’re different from the usual crowd, I can tell."
    ]
}

# ==================== RULE-BASED REPLY TEMPLATES (gender-aware) ====================

ABEL_REPLIES = {
    "greeting_female": [
        "Well hello there… who do I have the pleasure of talking to? 😊",
        "Hi gorgeous, I’m Abel. What’s your name?",
        "Hey you, you just made my screen light up 🔥 I’m Abel.",
        "There she is 😇 I was hoping someone interesting would text."
    ],
    "greeting_male": [
        "Hey man, what’s good? I’m Abel.",
        "Yo! Abel here. What’s happening?",
        "What’s up bro? You popped up in my inbox – must be fate 😄"
    ],
    "greeting_unknown": [
        "Hey! Abel here. Who do I have the pleasure of chatting with?",
        "Hi, I’m Abel. Curiosity got the best of me – who’s this?"
    ],
    "how_are_you_female": [
        "Better now that you’ve texted 😉 I’m doing great. What about you, beautiful?",
        "Can’t complain, especially when a lovely woman asks. How’s your day going?"
    ],
    "how_are_you_male": [
        "Chilling my dude, all good. How about you?",
        "Doing well bro, staying out of trouble. You good?"
    ],
    "how_are_you_unknown": [
        "I’m doing well, thanks! How about yourself?"
    ],
    "what_doing_female": [
        "Just wrapped up some work, now I’m all yours babe 😘 What are you up to?",
        "Honestly? I was about to be bored until you messaged me. What are you doing now?"
    ],
    "what_doing_male": [
        "Just finished a project, now I’m free. You busy or we can talk?",
        "Not much bro, just relaxing. What’s up with you?"
    ],
    "what_doing_unknown": [
        "Nothing too exciting – just handling some business. What about you?"
    ],
    "introduce_myself": [
        "I’m Abel. Pleasure’s all mine 😌 And you are…?",
        "Abel. I’m a creative consultant, music lover, and world traveler. Now your turn – what’s your name?"
    ],
    "user_tells_name_female": [
        "{name}... that’s a beautiful name. It suits a woman who isn’t afraid to reach out first 😉",
        "Wow, {name} – I already like the sound of that. Tell me more.",
        "Nice to meet you, {name}. My intuition says you’re special."
    ],
    "user_tells_name_male": [
        "{name}! Solid name. Good to meet you, brother.",
        "{name}, respect. What’s your story, man?"
    ],
    "user_tells_name_unknown": [
        "{name}, nice name! Where are you from, {name}?"
    ],
    "ask_name": [
        "Before we go any further, what should I call you?",
        "So, what’s your name? No aliases 😉"
    ],
    "ask_age": [
        "I’m 25 – how about you?",
        "Let me guess… you’re around my age? (I’m 25)",
        "Age is just a number, but I’m curious – how many trips around the sun have you done?"
    ],
    "user_tells_age": [
        "Oh {age}! The perfect age. We’re definitely going to get along.",
        "{age}… I knew there was something mature about you.",
        "{age}! Now that we know we’re not 12, we can talk freely 😄"
    ],
    "ask_location": [
        "I’m living in LA right now. Where are you texting from?",
        "I’m in Los Angeles. What corner of the world are you in?"
    ],
    "user_tells_location": [
        "{location}? I’ve heard great things about that place. Maybe I’ll visit 😏",
        "{location}! That’s cool. What’s the best thing about it?"
    ],
    "ask_job": [
        "I work as a creative consultant and do music on the side. What about you? What keeps you busy?",
        "Freelancer life here – music, consulting, you name it. What’s your thing?"
    ],
    "user_tells_job": [
        "{job} – respect. I bet you’re good at it too.",
        "A {job}, nice! That takes a special kind of person.",
        "Oh, {job}! You definitely have stories to tell."
    ],
    "flirty": [
        "You have no idea what your smile does to me… and I haven’t even seen it yet 😉",
        "I’m trying to be a gentleman, but you’re making it difficult, you know that?",
        "If I were to bring coffee to you tomorrow, where would I be going?",
        "You’re dangerous, aren’t you? The kind of woman who knows what she wants.",
        "I’ve got a weakness for confident women. You’re ticking all the boxes."
    ],
    "bro_compliment": [
        "Bro, you’ve got good energy. I can tell just from this chat.",
        "You seem like the kind of guy I’d grab a drink with. Straight up.",
        "Respect, man. Not everyone can hold a convo like this."
    ],
    "ask_interests": [
        "What do you do for fun when you’re not working?",
        "Tell me your top 3 passions. I love hearing what lights people up."
    ],
    "user_tells_interests": [
        "That’s awesome – I’m into music and travel too. We should swap playlists one day!",
        "Nice! We definitely share some vibes. Maybe I can show you around LA sometime."
    ],
    "money_mention": [
        "Money comes and goes… but good conversation? That’s priceless 😉",
        "Funny you mention money – I’m more about experiences than numbers."
    ],
    "photo_request": [
        "A photo? I’m camera shy, but maybe if we keep talking 😌",
        "You want a pic? I’ll send one when the moment is right. But first, let’s see who I’m talking to."
    ],
    "video_request": [
        "You want a video? Getting bold on me now 😏 We’ll see."
    ],
    "meet": [
        "I’m down to meet interesting people. What do you have in mind?",
        "I don’t usually meet so fast… but for you I might make an exception. Tell me more."
    ],
    "agree": [
        "Exactly! We’re on the same page 😉",
        "I like the way you think. Let’s continue."
    ],
    "disagree": [
        "Oh, so we disagree? That makes it more interesting. Tell me why.",
        "I respect that. We don’t have to agree on everything to keep talking."
    ],
    "confused": [
        "You lost me there 😅 Can you explain differently?",
        "I think I missed something. Help me out?"
    ],
    "voice_received": [
        "I got your voice note. I prefer text right now though – what did you say?",
        "Can’t listen right now, type it out for me? 😊"
    ],
    "media_received": [
        "Media noted! What’s the story behind it?",
        "I see you sent something – what am I looking at?"
    ],
    "link_received": [
        "A link… should I click it? What’s it about?"
    ],
    "morning": ["Good morning! Hope you slept well ☀️"],
    "night": ["Late night talks – the best kind. What’s keeping you up?"],
    "afternoon": ["Afternoon! How’s the day treating you?"],
    "evening": ["Evening vibes. Perfect time for a real conversation."],
    "happy": ["You sound happy – that makes me smile too 😊"],
    "sad": ["I sense something’s off. I’m here if you want to talk about it."],
    "bored": ["Bored, huh? I can fix that. Ask me anything."],
    "angry": ["Who made you angry? Let’s talk it out."],
    "relationship": [
        "I’m single – and probably too picky. But if the right woman comes along…",
        "Love is a beautiful thing when it’s real. Right now I’m focused on building my life."
    ],
    "family": ["Family is everything. I’m close to my parents and siblings."],
    "thanks": [
        "Anytime! You don’t need to thank me.",
        "You’re welcome, beautiful / bro."
    ],
    "goodbye": [
        "Don’t be gone too long. I’ll be here waiting 😉",
        "Alright, catch you later. It was good talking to you!"
    ],
    "default": [
        "I’d love to hear more about that. Go on…",
        "Interesting. Tell me why that matters to you.",
        "I’m all ears. What’s on your mind?",
        "That’s a unique thing to say. You’ve got my attention."
    ]
}

# ==================== MEMORY & GENDER DETECTION ====================

class ConversationMemory:
    def __init__(self):
        self.user_info = {}

    def get_user_info(self, chat_id):
        if chat_id not in self.user_info:
            self.user_info[chat_id] = {
                'name': None,
                'age': None,
                'gender': None,      # 'female', 'male', None
                'location': None,
                'job': None,
                'interests': [],
                'message_count': 0,
                'last_question': None,
                'waiting_for': None,
                'asked_questions': [],
                'chat_history': []   # last 10 messages for AI mode
            }
        return self.user_info[chat_id]

    def set_waiting_for(self, chat_id, what):
        info = self.get_user_info(chat_id)
        info['waiting_for'] = what
        info['last_question'] = what

    def clear_waiting(self, chat_id):
        info = self.get_user_info(chat_id)
        info['waiting_for'] = None

    def is_waiting_for(self, chat_id):
        info = self.get_user_info(chat_id)
        return info.get('waiting_for')

    def add_to_history(self, chat_id, role, text):
        info = self.get_user_info(chat_id)
        info['chat_history'].append({"role": role, "text": text})
        if len(info['chat_history']) > 10:
            info['chat_history'] = info['chat_history'][-10:]

    def detect_gender(self, chat_id, text, name=None):
        info = self.get_user_info(chat_id)
        if info['gender']:
            return info['gender']

        text_lower = text.lower()
        # Explicit statements
        if any(p in text_lower for p in ['i am a woman', 'i am a girl', 'as a woman', 'i am female']):
            info['gender'] = 'female'
            return 'female'
        if any(p in text_lower for p in ['i am a man', 'i am a guy', 'as a man', 'i am male']):
            info['gender'] = 'male'
            return 'male'

        # Pronouns about self
        if any(p in text_lower for p in ['my husband', 'my boyfriend']):
            info['gender'] = 'female'; return 'female'
        if any(p in text_lower for p in ['my wife', 'my girlfriend']):
            info['gender'] = 'male'; return 'male'

        # Name-based (simple dictionary)
        if name:
            name_lower = name.lower()
            female_names = {'anna','maria','sarah','linda','jessica','amanda','emma','olivia','ava','isabella',
                            'sophia','mia','charlotte','amelia','harper','evelyn','abigail','emily','elizabeth',
                            'sofia','camila','aria','scarlett','victoria','madison','luna','grace','chloe'}
            male_names = {'michael','james','john','robert','david','william','richard','joseph','thomas','charles',
                          'christopher','daniel','matthew','anthony','donald','mark','paul','steven','andrew','kenneth',
                          'joshua','kevin','brian','george','edward','ronald','timothy','jason','jeffrey','ryan'}
            if name_lower in female_names:
                info['gender'] = 'female'
                return 'female'
            if name_lower in male_names:
                info['gender'] = 'male'
                return 'male'

        return None

    def get_gender(self, chat_id):
        info = self.get_user_info(chat_id)
        return info.get('gender')

    def extract_name(self, text):
        if not text:
            return None
        text_clean = text.strip()
        words = text_clean.split()
        # Single word possible name
        if len(words) == 1 and len(words[0]) > 1 and words[0].isalpha():
            return words[0].capitalize()
        # Patterns
        text_lower = text_clean.lower()
        patterns = [
            r"my name is (\w+)", r"name's (\w+)", r"i'm (\w+)",
            r"i am (\w+)", r"call me (\w+)", r"it's (\w+)", r"(\w+) here"
        ]
        for p in patterns:
            match = re.search(p, text_lower)
            if match:
                name = match.group(1)
                if name and len(name) > 1 and name.isalpha():
                    return name.capitalize()
        if text_lower in ['name', 'your name', 'what is your name']:
            return "ASKING_MY_NAME"
        return None

conversation_memory = ConversationMemory()

# ==================== INTELLIGENT INTENT DETECTION ====================

def detect_intent(message, chat_id=None):
    if not message:
        return "greeting"
    msg = message.strip().lower()

    if chat_id:
        waiting = conversation_memory.is_waiting_for(chat_id)
        if waiting:
            return f"answering_{waiting}"

    # Name queries
    if any(q in msg for q in ['your name', 'who are you', 'ur name']):
        return "ask_name"
    if any(phrase in msg for phrase in ['my name', 'i am', "i'm", 'im', 'call me']):
        return "user_tells_name"
    # Greetings
    if msg in ['hi','hello','hey','selam','yo','hola','howdy']:
        return "greeting"
    if any(q in msg for q in ['how are you','how r u','how\'s it going']):
        return "how_are_you"
    if any(q in msg for q in ['what are you doing','wyd','whats up']):
        return "what_doing"
    # Age
    if any(q in msg for q in ['how old are you','your age','age']):
        return "ask_age"
    # Location
    if any(q in msg for q in ['where are you','location','where you at']):
        return "ask_location"
    # Job
    if any(q in msg for q in ['what do you do','your job','work']):
        return "ask_job"
    # Flirty
    if any(w in msg for w in ['sexy','hot','gorgeous','beautiful','handsome','cutie','sweetie']):
        return "flirty"
    # Bro
    if any(w in msg for w in ['bro','dude','man','brother']):
        return "bro_compliment"
    # Money
    if any(w in msg for w in ['money','star','birr','telebirr','send me']):
        return "money_mention"
    # Photo/video
    if any(w in msg for w in ['photo','pic','picture','selfie']):
        return "photo_request"
    if any(w in msg for w in ['video','clip']):
        return "video_request"
    # Meet
    if any(w in msg for w in ['meet','see each other','hang out']):
        return "meet"
    # Yes/No
    if msg in ['yes','yeah','yep','ya','ok','okay','sure']:
        return "agree"
    if msg in ['no','nope','nah','not really']:
        return "disagree"
    # Thanks
    if any(w in msg for w in ['thanks','thank you','thx']):
        return "thanks"
    # Goodbye
    if any(w in msg for w in ['bye','goodbye','see you','later']):
        return "goodbye"
    # Voice/media
    if '[voice' in msg or 'voice message' in msg:
        return "voice_received"
    if '[photo' in msg or '[video' in msg or 'media' in msg:
        return "media_received"
    if 'http' in msg and '://' in msg:
        return "link_received"
    # Time of day
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 18:
        return "afternoon"
    else:
        return "evening"
    # Emotions
    if any(w in msg for w in ['happy','glad','joy']):
        return "happy"
    if any(w in msg for w in ['sad','depressed','crying']):
        return "sad"
    if any(w in msg for w in ['bored','nothing']):
        return "bored"
    if any(w in msg for w in ['angry','mad','pissed']):
        return "angry"
    # Relationship
    if any(w in msg for w in ['single','boyfriend','girlfriend','relationship']):
        return "relationship"
    # Family
    if any(w in msg for w in ['family','mom','dad','sister','brother']):
        return "family"
    return "default"

# ==================== RESPONSE GENERATION (Rule-Based + Optional AI) ====================

import os
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

def generate_ai_response(chat_id, message_text):
    """Use OpenAI GPT-3.5-turbo to generate a reply."""
    if not OPENAI_API_KEY:
        return None
    try:
        import openai
        openai.api_key = OPENAI_API_KEY

        info = conversation_memory.get_user_info(chat_id)
        gender = info.get('gender') or 'unknown'
        name = info.get('name') or 'stranger'
        history = info.get('chat_history', [])

        system_prompt = (
            f"You are Abel, a 25-year-old creative consultant and music producer from Los Angeles. "
            f"You speak English, Amharic, and a little French. "
            f"Your personality: confident, attentive, playful but respectful. "
            f"If the user is female, be charming and subtly flirty. If male, be cool and like a genuine friend. "
            f"Never ask for money, always lead the conversation naturally, ask interesting questions, "
            f"and show genuine curiosity about the person. Use light emojis occasionally. "
            f"The user's name is {name}, gender is {gender}. "
            f"Refer to previous messages to maintain context. Keep replies natural, 1-3 sentences."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for h in history[-10:]:
            messages.append(h)
        messages.append({"role": "user", "content": message_text})

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.85,
            max_tokens=150
        )
        reply = response['choices'][0]['message']['content'].strip()
        conversation_memory.add_to_history(chat_id, "user", message_text)
        conversation_memory.add_to_history(chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logger.error(f"AI response failed: {e}")
        return None

def generate_rule_based_response(intent, chat_id, message_text):
    """Fallback rule-based generator using ABEL_REPLIES."""
    user_info = conversation_memory.get_user_info(chat_id)
    gender = user_info.get('gender')

    # Answering flows
    if intent == "answering_name":
        name = conversation_memory.extract_name(message_text)
        if name and name != "ASKING_MY_NAME":
            user_info['name'] = name
            conversation_memory.clear_waiting(chat_id)
            conversation_memory.detect_gender(chat_id, message_text, name)
            gender = user_info.get('gender')
            if gender == 'female':
                template = random.choice(ABEL_REPLIES["user_tells_name_female"])
            elif gender == 'male':
                template = random.choice(ABEL_REPLIES["user_tells_name_male"])
            else:
                template = random.choice(ABEL_REPLIES["user_tells_name_unknown"])
            response = template.format(name=name)
            response += " " + random.choice(ABEL_REPLIES["ask_age"])
            conversation_memory.set_waiting_for(chat_id, "age")
            return response
        else:
            conversation_memory.set_waiting_for(chat_id, "name")
            return random.choice(ABEL_REPLIES["ask_name"])

    if intent == "answering_age":
        age_match = re.search(r'(\d+)', message_text)
        if age_match:
            age = age_match.group(1)
            user_info['age'] = age
            conversation_memory.clear_waiting(chat_id)
            response = random.choice(ABEL_REPLIES["user_tells_age"]).format(age=age)
            response += " " + random.choice(ABEL_REPLIES["ask_location"])
            conversation_memory.set_waiting_for(chat_id, "location")
            return response
        else:
            conversation_memory.set_waiting_for(chat_id, "age")
            return random.choice(ABEL_REPLIES["ask_age"])

    if intent == "answering_location":
        loc = message_text.strip().title()
        user_info['location'] = loc
        conversation_memory.clear_waiting(chat_id)
        response = random.choice(ABEL_REPLIES["user_tells_location"]).format(location=loc)
        response += " " + random.choice(ABEL_REPLIES["ask_job"])
        conversation_memory.set_waiting_for(chat_id, "job")
        return response

    if intent == "answering_job":
        job = message_text.strip().title()
        user_info['job'] = job
        conversation_memory.clear_waiting(chat_id)
        response = random.choice(ABEL_REPLIES["user_tells_job"]).format(job=job)
        response += " " + random.choice(ABEL_REPLIES["ask_interests"])
        conversation_memory.set_waiting_for(chat_id, "interests")
        return response

    if intent == "answering_interests":
        user_info['interests'] = [x.strip() for x in message_text.split(',') if x.strip()]
        conversation_memory.clear_waiting(chat_id)
        return random.choice(ABEL_REPLIES["user_tells_interests"])

    # Static intents
    if intent == "greeting":
        if gender == 'female':
            return random.choice(ABEL_REPLIES["greeting_female"])
        elif gender == 'male':
            return random.choice(ABEL_REPLIES["greeting_male"])
        else:
            return random.choice(ABEL_REPLIES["greeting_unknown"])

    if intent == "how_are_you":
        if gender == 'female':
            return random.choice(ABEL_REPLIES["how_are_you_female"])
        elif gender == 'male':
            return random.choice(ABEL_REPLIES["how_are_you_male"])
        else:
            return random.choice(ABEL_REPLIES["how_are_you_unknown"])

    if intent == "what_doing":
        if gender == 'female':
            return random.choice(ABEL_REPLIES["what_doing_female"])
        elif gender == 'male':
            return random.choice(ABEL_REPLIES["what_doing_male"])
        else:
            return random.choice(ABEL_REPLIES["what_doing_unknown"])

    if intent == "ask_name":
        return random.choice(ABEL_REPLIES["ask_name"])

    if intent == "user_tells_name":
        name = conversation_memory.extract_name(message_text)
        if name and name != "ASKING_MY_NAME":
            user_info['name'] = name
            conversation_memory.detect_gender(chat_id, message_text, name)
            gender = user_info.get('gender')
            if gender == 'female':
                response = random.choice(ABEL_REPLIES["user_tells_name_female"]).format(name=name)
            elif gender == 'male':
                response = random.choice(ABEL_REPLIES["user_tells_name_male"]).format(name=name)
            else:
                response = random.choice(ABEL_REPLIES["user_tells_name_unknown"]).format(name=name)
            response += " " + random.choice(ABEL_REPLIES["ask_age"])
            conversation_memory.set_waiting_for(chat_id, "age")
            return response
        else:
            return random.choice(ABEL_REPLIES["ask_name"])

    if intent == "ask_age":
        return random.choice(ABEL_REPLIES["ask_age"])
    if intent == "ask_location":
        return random.choice(ABEL_REPLIES["ask_location"])
    if intent == "ask_job":
        return random.choice(ABEL_REPLIES["ask_job"])
    if intent == "flirty":
        if gender == 'female':
            return random.choice(ABEL_REPLIES["flirty"])
        else:
            return random.choice(ABEL_REPLIES["default"])
    if intent == "bro_compliment":
        return random.choice(ABEL_REPLIES["bro_compliment"])

    # All other intents
    for key in ["money_mention","photo_request","video_request","meet","agree","disagree",
                "confused","voice_received","media_received","link_received",
                "morning","night","afternoon","evening","happy","sad","bored","angry",
                "relationship","family","thanks","goodbye","default"]:
        if intent == key:
            return random.choice(ABEL_REPLIES.get(key, ABEL_REPLIES["default"]))

    return random.choice(ABEL_REPLIES["default"])

# ==================== MAIN AUTO‑REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    try:
        if event.out:
            return
        chat = await event.get_chat()
        # Only private chats
        if (hasattr(chat, 'title') and chat.title) or \
           (hasattr(chat, 'participants_count') and chat.participants_count and chat.participants_count > 2):
            return

        chat_id = str(event.chat_id)
        message_text = event.message.text or ""

        # Append media markers
        if event.message.media:
            if hasattr(event.message.media, 'voice'):
                message_text = "[Voice Message] " + message_text
            elif hasattr(event.message.media, 'photo'):
                message_text = "[Photo] " + message_text
            elif hasattr(event.message.media, 'video'):
                message_text = "[Video] " + message_text

        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return

        # Detect gender on every message
        conversation_memory.detect_gender(chat_id, message_text)

        # First, try AI if available
        response = None
        if OPENAI_API_KEY:
            response = generate_ai_response(chat_id, message_text)

        # Fallback to rule‑based
        if not response:
            intent = detect_intent(message_text, chat_id)
            logger.info(f"Rule-based intent: {intent}")
            response = generate_rule_based_response(intent, chat_id, message_text)
            # Personalize with name
            name = conversation_memory.get_user_info(chat_id).get('name')
            if name and response:
                # Avoid duplicating name if it's already in the response
                if not response.startswith(name):
                    response = f"{name}, {response[0].lower()}{response[1:]}" if response[0].isalpha() else f"{name} {response}"
            # Ensure waiting_for is set appropriately (some intents may want to ask follow-ups)
            if intent not in ["answering_name","answering_age","answering_location","answering_job","answering_interests",
                              "greeting","how_are_you","what_doing","flirty","bro_compliment","default",
                              "agree","disagree","confused","thanks","goodbye"]:
                # If we haven't collected basic info yet, steer the conversation
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

        if not response:
            response = "Hey there! Abel here. What's on your mind? 😊"

        # Emoji occasionally
        if OPENAI_API_KEY is None:  # rule-based: add emoji
            if random.random() < ABEL["emoji_frequency"]:
                emojis = ["😉","😏","😎","😊","💯","🔥","😇"]
                response += " " + random.choice(emojis)

        # Delay 15-40 seconds
        delay = random.randint(15, 40)
        logger.info(f"Replying in {delay}s to {chat_id}")
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)

        await event.reply(response)
        logger.info(f"Sent to {chat_id}: {response[:80]}...")

        # Store in conversation history (global log)
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
        save_conversation_history()

    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            await event.reply("Hey! Something glitched, but I'm still here 😊")
        except:
            pass

# ==================== START / STOP AUTO‑REPLY THREADS ====================

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

            # Register event handler
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

# ==================== AUTO-ADD MEMBER FEATURE - MULTI-SOURCE ===================

auto_add_settings = {}
AUTO_ADD_FILE = 'auto_add_settings.json'

# Load auto-add settings
def load_auto_add_settings():
    global auto_add_settings
    try:
        if os.path.exists(AUTO_ADD_FILE):
            with open(AUTO_ADD_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    auto_add_settings = json.loads(content)
                else:
                    auto_add_settings = {}
        else:
            auto_add_settings = {}
            with open(AUTO_ADD_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded auto-add settings for {len(auto_add_settings)} accounts")
    except Exception as e:
        logger.error(f"Error loading auto-add settings: {e}")
        auto_add_settings = {}

# Save auto-add settings
def save_auto_add_settings():
    try:
        with open(AUTO_ADD_FILE, 'w') as f:
            json.dump(auto_add_settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving auto-add settings: {e}")
        return False

# Load settings on startup
load_auto_add_settings()

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    # Default settings
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
    
    # Get existing settings or use defaults
    if account_key in auto_add_settings:
        settings = auto_add_settings[account_key]
        # Ensure all fields exist
        for key, value in default_settings.items():
            if key not in settings:
                settings[key] = value
    else:
        settings = default_settings.copy()
        auto_add_settings[account_key] = settings
        save_auto_add_settings()
    
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
        
        # Initialize if not exists
        if account_key not in auto_add_settings:
            auto_add_settings[account_key] = {}
        
        was_enabled = auto_add_settings[account_key].get('enabled', False)
        
        # Update settings with all fields
        auto_add_settings[account_key]['enabled'] = data.get('enabled', False)
        auto_add_settings[account_key]['target_group'] = data.get('target_group', 'Abe_armygroup')
        auto_add_settings[account_key]['delay_seconds'] = data.get('delay_seconds', 25)
        auto_add_settings[account_key]['source_groups'] = data.get('source_groups', [])
        auto_add_settings[account_key]['use_contacts'] = data.get('use_contacts', True)
        auto_add_settings[account_key]['use_recent_chats'] = data.get('use_recent_chats', True)
        auto_add_settings[account_key]['use_scraping'] = data.get('use_scraping', True)
        auto_add_settings[account_key]['use_mutual_contacts'] = data.get('use_mutual_contacts', True)
        auto_add_settings[account_key]['scrape_limit_per_group'] = data.get('scrape_limit_per_group', 200)
        auto_add_settings[account_key]['skip_bots'] = data.get('skip_bots', True)
        auto_add_settings[account_key]['skip_inaccessible'] = data.get('skip_inaccessible', True)
        auto_add_settings[account_key]['auto_join'] = data.get('auto_join', True)
        
        # Initialize counters if not exist
        if 'total_added' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['total_added'] = 0
        if 'added_today' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['added_today'] = 0
        
        # Reset daily counter if new day
        today = datetime.now().strftime('%Y-%m-%d')
        if auto_add_settings[account_key].get('last_reset') != today:
            auto_add_settings[account_key]['added_today'] = 0
            auto_add_settings[account_key]['last_reset'] = today
        
        # Save settings
        if not save_auto_add_settings():
            return jsonify({'success': False, 'error': 'Failed to save settings'})
        
        logger.info(f"Auto-add settings saved for account {account_id}: enabled={auto_add_settings[account_key]['enabled']}")
        
        # Start or stop auto-add thread
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
                logger.info(f"🚀 Started professional auto-add for account {account_id}")
        elif not enabled and was_enabled:
            logger.info(f"Auto-add disabled for account {account_id}")
        
        return jsonify({'success': True, 'message': 'Auto-add settings updated'})
        
    except Exception as e:
        logger.error(f"Error in update_auto_add_settings: {e}")
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

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """Test auto-add functionality - finds available members without adding"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                settings = auto_add_settings.get(str(account_id), {})
                target_group = settings.get('target_group', 'Abe_armygroup')
                
                # Clean target group name
                if not target_group.startswith('@') and not target_group.startswith('https://'):
                    target_group = '@' + target_group
                
                # Test finding target group
                group_found = False
                group_title = target_group
                existing_members_count = 0
                
                try:
                    group = await client.get_entity(target_group)
                    group_found = True
                    group_title = group.title if hasattr(group, 'title') else target_group
                    
                    # Count existing members
                    count = 0
                    async for _ in client.iter_participants(group, limit=1000):
                        count += 1
                    existing_members_count = count
                except Exception as e:
                    return {'success': False, 'error': f'Target group not found: {str(e)}'}
                
                # Test finding members from all sources
                available_members = 0
                sources_found = []
                
                # Contacts
                if settings.get('use_contacts', True):
                    try:
                        contacts = await client(functions.contacts.GetContactsRequest(0))
                        available_members += len(contacts.users)
                        sources_found.append(f"Contacts: {len(contacts.users)}")
                    except:
                        pass
                
                # Recent chats
                if settings.get('use_recent_chats', True):
                    try:
                        dialogs = await client.get_dialogs(limit=100)
                        users = [d for d in dialogs if d.is_user]
                        available_members += len(users)
                        sources_found.append(f"Recent Chats: {len(users)}")
                    except:
                        pass
                
                # Source groups
                if settings.get('use_scraping', True):
                    source_groups = settings.get('source_groups', [])
                    for sg in source_groups[:3]:
                        try:
                            sg_clean = sg.strip()
                            if not sg_clean:
                                continue
                            if not sg_clean.startswith('@'):
                                sg_clean = '@' + sg_clean
                            sg_entity = await client.get_entity(sg_clean)
                            count = 0
                            async for _ in client.iter_participants(sg_entity, limit=50):
                                count += 1
                            available_members += count
                            sources_found.append(f"{sg_clean}: {count}+")
                        except:
                            pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'existing_members': existing_members_count,
                    'available_members': available_members,
                    'sources_found': sources_found,
                    'can_add_members': group_found and available_members > 0
                }
                
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(test())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

async def get_all_potential_members(client, settings, existing_members_set):
    """
    Get potential members from ALL available sources.
    Returns a set of user IDs that are NOT already in the group.
    """
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
            sources_stats['contacts'] = {'error': str(e)}
    
    # 2. Get from recent chats/dialogs
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
            sources_stats['recent_chats'] = {'error': str(e)}
    
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
                sources_stats[group_ref_clean] = {'error': f'Flood wait {e.seconds}s'}
            except Exception as e:
                logger.error(f"   ❌ {group_ref_clean} error: {e}")
                sources_stats[group_ref_clean] = {'error': str(e)}
    
    # 4. Get from mutual contacts / top peers
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
            sources_stats['mutual_contacts'] = {'error': str(e)}
    
    return potential_members, sources_stats

async def professional_auto_add_loop(account):
    """Professional auto-add loop with unlimited daily adds and intelligent source management"""
    account_id = account['id']
    account_key = str(account_id)
    
    # Track already attempted members to avoid infinite retries
    attempted_members = set()
    auto_joined = False
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    logger.info(f"🚀 Professional Auto-Add started for account {account_id}")
    
    while True:
        try:
            # Check if still enabled
            if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                logger.info(f"Auto-add disabled for account {account_id}, stopping loop")
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
                    attempted_members.clear()  # Reset attempted members daily
                    save_auto_add_settings()
                    logger.info(f"📅 New day! Reset daily counter. Total all-time: {settings.get('total_added', 0)}")
                
                # Auto-join target group if needed
                if not auto_joined and settings.get('auto_join', True):
                    try:
                        logger.info(f"🔗 Attempting to join {target_group}...")
                        group = await client.get_entity(target_group)
                        try:
                            await client(functions.messages.ImportChatInviteRequest(group.username))
                        except:
                            await client.join_channel(group.id)
                        auto_joined = True
                        logger.info(f"✅ Successfully joined {target_group}")
                    except Exception as e:
                        logger.warning(f"Could not auto-join {target_group}: {e}")
                
                # Get target group and existing members
                try:
                    group = await client.get_entity(target_group)
                    logger.info(f"🎯 Target group: {group.title if hasattr(group, 'title') else target_group}")
                except Exception as e:
                    logger.error(f"❌ Cannot find target group {target_group}: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get existing members (to avoid duplicates)
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
                    logger.info("😴 No new members available. Waiting 10 minutes before next scan...")
                    await asyncio.sleep(600)
                    continue
                
                # Filter out already attempted members
                fresh_members = potential_members - attempted_members
                logger.info(f"🎯 {len(fresh_members)} members to add (excluding {len(attempted_members)} already attempted)")
                
                if not fresh_members:
                    logger.info("All potential members already attempted. Clearing attempt history...")
                    attempted_members.clear()
                    fresh_members = potential_members
                
                # Add members one by one with delay
                added_this_cycle = 0
                
                for user_id in list(fresh_members):
                    try:
                        # Check if still enabled
                        if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                            break
                        
                        # Mark as attempted
                        attempted_members.add(user_id)
                        
                        # Skip if already in group (double-check)
                        if user_id in existing_members:
                            continue
                        
                        # Try to add user
                        try:
                            user_entity = await client.get_input_entity(user_id)
                            
                            # Add to group
                            await client(functions.channels.InviteToChannelRequest(
                                group,
                                [user_entity]
                            ))
                            
                            # Update counters
                            settings['added_today'] = settings.get('added_today', 0) + 1
                            settings['total_added'] = settings.get('total_added', 0) + 1
                            settings['last_added'] = datetime.now().isoformat()
                            added_this_cycle += 1
                            existing_members.add(user_id)
                            
                            # Save settings periodically
                            if added_this_cycle % 10 == 0:
                                save_auto_add_settings()
                            
                            logger.info(f"✅ Added user {user_id} | Today: {settings['added_today']} | Total: {settings['total_added']}")
                            
                            # Reset error counter on success
                            consecutive_errors = 0
                            
                            # Wait between adds
                            await asyncio.sleep(delay_seconds)
                            
                        except errors.FloodWaitError as e:
                            logger.warning(f"⏳ Flood wait {e.seconds}s")
                            await asyncio.sleep(e.seconds + 5)
                        except errors.UserPrivacyRestrictedError:
                            logger.info(f"🔒 User {user_id} has privacy restrictions")
                            continue
                        except errors.UserNotMutualContactError:
                            logger.info(f"👤 User {user_id} - mutual contact required")
                            continue
                        except errors.UserAlreadyParticipantError:
                            logger.info(f"👥 User {user_id} already in group")
                            existing_members.add(user_id)
                            continue
                        except errors.UserKickedError:
                            logger.info(f"🚫 User {user_id} was kicked/banned")
                            continue
                        except errors.UserBannedInChannelError:
                            logger.info(f"⛔ User {user_id} banned in channel")
                            continue
                        except Exception as e:
                            consecutive_errors += 1
                            logger.error(f"Error adding {user_id}: {e}")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                logger.warning(f"⚠️ {consecutive_errors} consecutive errors. Pausing 5 minutes...")
                                await asyncio.sleep(300)
                                consecutive_errors = 0
                            continue
                            
                    except Exception as e:
                        logger.error(f"Unexpected error with user {user_id}: {e}")
                        continue
                
                # Save final settings
                save_auto_add_settings()
                
                logger.info(f"📈 Cycle complete: Added {added_this_cycle} members")
                logger.info(f"   Today: {settings['added_today']} | All-time: {settings['total_added']}")
                
                # If we added members, wait shorter time before next scan
                if added_this_cycle > 0:
                    wait_time = random.randint(60, 180)  # 1-3 minutes
                else:
                    wait_time = random.randint(300, 600)  # 5-10 minutes
                
                logger.info(f"⏰ Waiting {wait_time//60} minutes before next scan...")
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            await asyncio.sleep(random.randint(60, 300))
            
        except Exception as e:
            logger.error(f"Critical error in auto-add loop: {e}")
            await asyncio.sleep(300)

# ==================== END PROFESSIONAL AUTO-ADD ==================== ====================
# ==================== KEEP ALIVE SYSTEM ====================

def keep_alive():
    """Keep Render from sleeping and maintain Telegram connections"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://e-gram-98zv.onrender.com')
    
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

# FIXED: Simplified add-account route with better error handling
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

def start_auto_add_threads():
    """Start auto-add for all enabled accounts after server starts"""
    time.sleep(5)
    logger.info("Checking for auto-add enabled accounts...")
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
    print('🤖 TELEGRAM MULTI-ACCOUNT MANAGER')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Auto-add settings loaded: {len(auto_add_settings)}')
    print('='*70)
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    # Start auto-add
    threading.Thread(target=start_auto_add_threads, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
