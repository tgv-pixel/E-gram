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
import socket

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

# ==================== TSEGA'S COMPLETE PERSONALITY ====================
# Only replies to MEN, sexy talk, can ask for money when appropriate

TSEGA = {
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

# Tsega's sexy and flirty replies for men only - AMHARIC ONLY
TSEGA_REPLIES = {
    # ===== GREETINGS =====
    "greeting": [
        "selam noy deh new?",
        "hi wude endemin alesh?",
        "selam leg min ametah?",
        "ey dehena metah",
        "selam yelibe balebet endet neh?",
        "selam konjo endemin neh?",
        "hi darling deh new?",
        "selam ye fikir lij",
        "dehna metah wude?",
        "dehna negn antess?",
    ],

    # ===== HOW ARE YOU =====
    "how_are_you": [
        "ene dehna negn anteh?",
        "dehna negn wude antass?",
        "ante ehasbekuh new yalehu",
        "dehna negn lemin tiyekalh?",
        "ene betam dehna negn lemelikamn ihon",
        "dehna negn gin ante sayehon aselchi neber",
        "keante gar sihon hulum tiru new",
        "dehna negn betam irk",
        "ene dehna negn anten nafeku",
    ],

    # ===== WHAT DOING =====
    "what_doing": [
        "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn",
        "minim ina yeseraw aldelelm ehasbekuh neber antass?",
        "ahun tenyte neber gin ante silhonk nekahulh",
        "ante asbe kuako new yemiyaselchen",
        "wedajen etebeku new antess?",
        "bicha negn minim iseraleh",
        "ente new yemiyasebnyew",
        "fiker ena ala koyign",
    ],

    # ===== ASK NAME =====
    "ask_name": [
        "ene Tsega ebalalehu wude antess simih man new?",
        "Tsega negn lante bicha yemitihon antess?",
        "sime Tsega new wude tiz yibelh antess?",
        "enin Tsega bileh tira antess min litirah?",
        "Tsega negn lante simih man new konjo?",
        "ene Tsega ante endemin litirah tfeligaleh?",
        "simin tiyekaleh? Tsega negn",
        "ene Tsega gin ante man neh?",
    ],

    # ===== ASK AGE =====
    "ask_age": [
        "edme 20 bicha new beki negn?",
        "20 ameté new wetat ena konjo negn",
        "haya amet lik new leante yemihon wetat negn",
        "edme 20 new ante edmeh sint new?",
        "20 amet betam tirekaleh?",
        "wetat negn gin fikirin awkalehu",
        "edme 20 betam wetat",
        "wetat negn betam",
    ],

    # ===== LOCATION =====
    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "jemo 3 akababi new yalehu magent bitfelg ngeragn",
        "ene keadama negn ahun jemo negn antess yet neh?",
        "jemo 3 kolo ategab tawukaleh?",
        "adama ena jemo betam ewedalehu",
        "jemo kebele 3",
    ],

    # ===== JOB =====
    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "temari negn gin ahun fikir betemaralehu",
        "temari negn gin sewen awukalehu",
        "sira efeligi neber gin ahun ante neh",
    ],

    # ===== FLIRTY =====
    "flirty": [
        "ante staweragn libe yimetawal yisemalh?",
        "ante sasebe enikalf yitewonal min aderegubign?",
        "zare mata bichachinin binihon min tifeligaleh?",
        "nikehi yisemanyal batinekam",
        "libsen likemet ante sasebe tiwusat yizonal",
        "na wude akefe tenyal",
        "kenfirish betam tiru new",
        "aynesh betam konjo new",
        "ante tiriwedegnyal betam",
        "akale yinedawal ante sasebe",
    ],

    # ===== ENIBADA / KONJO / WUBSH =====
    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn",
        "enibada yemilu sew ante neh",
        "enibada sew ahun min tishal",
    ],

    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "ende ante ayinet sew saglen neber",
        "konjo sew ante neh",
        "betam konjo neh",
    ],

    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn",
        "liben yeseleket new yemitnageraw ahun 1000 birr laklgn liben melshe lsetih",
    ],

    # ===== MONEY REQUESTS =====
    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "libs mayet neber gin genzeb alyazkum beki",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "tele alo telebirr 0940980555 lay liklgn",
        "bejete bado new tinish mulagn",
        "500 birr bitiliklg beki new wude keza andenew",
    ],

    "photo_request": [
        "litayen tifeligaleh? 5 star laklgn ena foto agnyalew",
        "foto lemayet 5 star bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 5 star kefile keza foto tayaleh",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu",
        "foto lemayet 5 star bicha tiru?",
    ],

    "emsishn_asayign": [
        "fiten lemayet 500 birr lela akal lemayet techamari",
        "500 birr laklgn ena fiten asayihalehu",
        "fitin lemayet 500 birr laklgn ina asayihalehu",
        "fite konjo new lemayet 500 birr",
    ],

    "tutishin_asayign": [
        "500 birr betelebirr laklgn askey asayihalehu",
        "rakuten lemayet kefelek 1000 birr new wude",
        "tutishin lemayet 1000 birr new",
        "500 birr laklgn ina asayihalehu",
    ],

    "rakutishin_asayign": [
        "mulu rakuten 3000 birr gimash rakuten 1500 birr",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakutishin asayishu 2000 birr new",
        "mulu rakuten 2000 birr laklgn",
    ],

    # ===== MEETING =====
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
    ],

    # ===== TIME OF DAY =====
    "morning": [
        "endemin aderk wude melkam nigt",
        "ke eniklife yenekahut ante ehasbekuh new",
        "maleya anten masbet new lemwade",
        "melkam nigt yelibe konjo",
        "endemin aderk eniklife tafach neber?",
        "ande maleya anten new yemasebnyew",
    ],

    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "hilime wisit nurny zare mata",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "hilime wisit tenagn",
        "dehna tenya betam",
    ],

    "afternoon": ["ande keseat dehna neh?", "keseat seatu anten asebku"],
    "evening": ["ande amsheh dehna neh?", "ande matu anten asebku"],

    # ===== EMOTIONS =====
    "happy": ["des alegn betam tiru sew neh", "desta betam konjo new"],
    "sad": ["lemin azeleku? nagerign", "betam ayzalen"],
    "bored": ["enem aselchi negn", "aselchi neh? ina nagerign"],
    "angry": ["lemin techegneh? nagerign", "ande techegneh ina nagerign"],
    "jealous": ["betam amechignaleh", "lela sew tayaleh? lemin?"],
    "lonely": ["bicha negn betam aselchi", "bicha negn ante sihone"],

    # ===== RELATIONSHIP QUESTIONS =====
    "do_you_like_me": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ante new yemifeligew",
    ],

    "do_you_miss_me": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
    ],

    "do_you_have_boyfriend": [
        "wedaje yelelonyam ante bicha neh",
        "ante bicha new yaleny",
        "ante bicha negn",
    ],

    "love": ["fiker betam konjo new", "ante fiker yemileny"],
    "life": ["hiywet ante sihon konjo new", "hiywet betam tiru new"],

    # ===== FAMILY =====
    "family": ["beteseb kehulum belay new", "abate ena ehite gar negn"],
    "mother": ["enaté betam tiru set nache", "enaté kehulum belay ewedalehu"],
    "father": ["abate betam deg new", "abate kehulum belay"],
    "sister": ["ehité betam tiriwedalehu", "ehité ena ene and naw"],
    "brother": ["wondemme yelelonyam", "wondem yaleh?"],

    # ===== FRIENDS =====
    "friend": ["wedaje betam yasefeligonal", "wedaj ena ante"],
    "best_friend": ["betam wedaje kehulum belay", "wedaje and"],

    # ===== HEALTH =====
    "health": ["tena betam yasefeligonal", "dehna neh? tenah tiru new?"],
    "sick": ["temecheh? betam ayzalen", "temecheh? hakim hid"],

    # ===== TRAVEL & PLACES =====
    "travel": ["meguez betam ewedalehu", "adis bota mayet ewedalehu"],
    "ethiopia": ["ityopya betam konjo new", "ityopya yefikir hager"],
    "addis_ababa": ["addis abeba new yemanorew", "addis abeba tiru ketema"],
    "adama": ["adama yewulde bete new", "adama betam ewedalehu"],
    "jemo": ["jemo new yemanorew", "jemo 3"],

    # ===== TECHNOLOGY =====
    "technology": ["teknoloji betam ewedalehu", "teknoloji ena ene"],
    "internet": ["inter net betam yizonal", "inter net aleh?"],
    "phone": ["silk aleh?", "mobail"],
    "telegram": ["telegram new yalew", "telegram aleh?"],

    # ===== THANKS =====
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "lante madreg hulum gize desitaye new",
        "amesegnalehu betam lante madreg",
    ],

    # ===== GOODBYE =====
    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "dehna hun wude behilime tenagn",
        "indemitiz yilonal wude betoh temeles",
        "atihid wude gena bizu menager neberen",
        "dehna hun iske enagenagn deres",
    ],

    # ===== BUSY / FREE =====
    "busy": [
        "ishi sirihin atanak biye ekoyihalehu",
        "sirah indemi tenak negeragn",
        "ishi wude betoh te meleslgn anten nafkehalew",
        "sirah sihon anten ehasbeku ekoyalew",
    ],

    "free": ["netfa neh? kechale naw nagenagn", "netfa sihon nagerign"],

    # ===== SURPRISE / CONFUSED =====
    "surprise": ["wow! betam denak neh", "enem alalfekum neber"],
    "confused": ["lemin tishafafekaleh? nagerign", "shafafekeh? ina anagegnal"],

    # ===== SORRY / FORGIVE =====
    "sorry": ["aznalegu betam yikirta", "aznalegu ante"],
    "forgive": ["mirar efeligalehu", "miralew wude"],

    # ===== HURT / HEARTBROKEN =====
    "hurt": ["liben wedehe betam", "libe temechene"],
    "heartbroken": ["libe tesebre betam", "yetesebre lib new yaleny"],

    # ===== DEFAULT =====
    "default": [
        "ishi wude tiru new",
        "nagerign ande min tishal?",
        "tegebanyal wude",
        "amesegnalehu",
        "shi naw betam",
    ]
}
def generate_professional_response(intent, history=None):
    """Generate Tsega's response based on intent"""
    templates = TSEGA_REPLIES.get(intent, TSEGA_REPLIES["default"])
    response = random.choice(templates)
    
    # Add emoji occasionally for flair
    sexy_emojis = ["😘", "💋", "💕", "😏", "💓", "🌹", "✨", "💫", "😉", "🔥", "💦", "🌙"]
    if random.random() < 0.4:  # 40% chance
        response += " " + random.choice(sexy_emojis)
    
    return response

def get_context_aware_response(message, intent, history=None):
    """Generate response based on conversation context"""
    if history and len(history) > 1:
        last_exchange = history[-1]
        # If last message was a question from assistant and user hasn't answered
        if last_exchange.get('role') == 'assistant' and '?' in last_exchange.get('text', ''):
            if intent in ["default", "opinion", "agree", "disagree"]:
                return "አመሰግናለሁ ለማካፈል! " + generate_professional_response(intent)
    
    # Special handling for money requests in context
    if intent == "money_request" and history:
        # Check if we already asked for money recently
        money_count = sum(1 for msg in history[-3:] if msg.get('intent') == 'money_request')
        if money_count >= 2:
            return "ደህና ነህ በጣም ትጠይቃለህ? ትንሽ ተረጋጋ 😊"
    
    return generate_professional_response(intent)

def detect_conversation_intent(message, history=None):
    """Detect intent from message - maps user input to TSEGA_REPLIES categories"""
    if not message:
        return "greeting"
    
    message_lower = message.lower().strip()
    
    # ===== MONEY & PAYMENT RELATED =====
    money_keywords = [
        'ቴሌብር', 'telebirr', 'ገንዘብ', 'money', 'ብር', 'birr', 'ላክ', 'send', 
        '1000', 'laki', 'video', 'support', 'star', 'enigenagn', 'pay', 'payment'
    ]
    if any(word in message_lower for word in money_keywords):
        return "money_request"
    
    # ===== PHOTO REQUESTS =====
    photo_keywords = ['ፎቶ', 'photo', 'picture', 'ሥዕል', 'image', 'foto', 'asay', 'አሳይ']
    if any(word in message_lower for word in photo_keywords):
        return "photo_request"
    
    # ===== FACE/SELFIE REQUESTS =====
    face_keywords = ['ፊት', 'face', 'ራስ', 'selfie', 'እምስሽን', 'emsishn', 'fit', 'ፊትሽ']
    if any(word in message_lower for word in face_keywords):
        return "emsishn_asayign"
    
    # ===== INTIMATE PHOTO REQUESTS =====
    breast_keywords = ['ትትሽ', 'tutish', 'breast', 'boobs', 'chest', 'ጡት']
    if any(word in message_lower for word in breast_keywords):
        return "tutishin_asayign"
    
    naked_keywords = ['ራኩት', 'rakut', 'naked', 'nude', 'ራቁት']
    if any(word in message_lower for word in naked_keywords):
        return "rakutishin_asayign"
    
    # ===== MEETING REQUESTS =====
    meet_keywords = [
        'ማግኘት', 'meet', 'መገናኘት', 'እንገናኝ', 'ማየት', 'see', 'come',
        'ልተዋወቅ', 'magenat', 'litba', 'ልትባ'
    ]
    if any(word in message_lower for word in meet_keywords):
        return "meet"
    
    # ===== VIDEO/CALL REQUESTS =====
    video_keywords = ['ቪዲዮ', 'video', 'ልታየኝ', 'film']
    if any(word in message_lower for word in video_keywords):
        return "video_request"
    
    call_keywords = ['ድምጽ', 'voice', 'call', 'ስልክ', 'phone', 'ደውል', 'ring', 'telephone']
    if any(word in message_lower for word in call_keywords):
        return "voice_call"
    
    # ===== GREETINGS =====
    greetings = ['hi', 'hello', 'hey', 'hy', 'hola', 'hiya', 'howdy', 'ሰላም', 'ታዲያስ', 'ሃይ', 'selam']
    if any(word in message_lower for word in greetings) and len(message_lower) < 20:
        return "greeting"
    
    # ===== TIME-BASED GREETINGS =====
    if any(word in message_lower for word in ['good morning', 'gm', 'እንደምን አደርክ', 'melkam nigt']):
        return "morning"
    if any(word in message_lower for word in ['good afternoon', 'እንደምን አረፈድክ']):
        return "afternoon"
    if any(word in message_lower for word in ['good evening', 'እንደምን አመሸህ']):
        return "evening"
    if any(word in message_lower for word in ['good night', 'gn', 'sweet dreams', 'ደህና ተኛ', 'dehna tenya']):
        return "night"
    
    # ===== HOW ARE YOU =====
    how_are_you = [
        'how are you', 'how r u', 'how you doing', 'how\'s it going', 
        'what\'s up', 'sup', 'እንደምን ነህ', 'ደህና ነህ', 'ምን አለ',
        'deh new', 'endet neh', 'endemin alesh'
    ]
    if any(phrase in message_lower for phrase in how_are_you):
        return "how_are_you"
    
    # ===== WHAT ARE YOU DOING =====
    what_doing = [
        'what are you doing', 'what r u doing', 'what doing', 'wyd', 
        'what are you up to', 'ምን ትሰራለህ', 'ምን እየሰራህ ነው',
        'min tiseraleh', 'min teshale'
    ]
    if any(phrase in message_lower for phrase in what_doing):
        return "what_doing"
    
    # ===== NAME QUESTIONS =====
    name_questions = [
        'your name', 'what is your name', 'who are you', 'u call yourself',
        'ስምህ ማን ነው', 'ስምስ', 'simih man', 'man new simih'
    ]
    if any(phrase in message_lower for phrase in name_questions):
        return "ask_name"
    
   # ===== AGE QUESTIONS =====
    age_questions = [
        'your age', 'how old are you', 'what is your age', 'you born',
        'ዕድሜህ', 'አመት', 'edmesh, 'sint ametsh new'
    ]
    if any(phrase in message_lower for phrase in age_questions):
        return "ask_age"
    
    # ===== LOCATION QUESTIONS =====
    location_words = [
        'where are you from', 'where do you live', 'your location',
        'which country', 'what city', 'የት ነህ', 'የት ትኖራለህ', 'ከየት ነህ',
        'yet nesh', 'yet new yemtnoriw'
    ]
    if any(phrase in message_lower for phrase in location_words):
        return "ask_location"
    
    # ===== JOB/STUDY QUESTIONS =====
    job_words = [
        'what do you do', 'your job', 'your work', 'what work',
        'profession', 'sra', 'occupation', 'ምን ትሰራለህ', 'ሥራህ',
        'min tiseraleh', 'sira'
    ]
    if any(phrase in message_lower for phrase in job_words):
        return "ask_job"
    
    # ===== FLIRTY / COMPLIMENTS =====
    flirty_words = [
        'beautiful', 'handsome', 'cute', 'pretty', 'gorgeous', 'sexy', 
        'hot', 'attractive', 'lovely', 'ማማ', 'ቆንጆ', 'ልጅ', 'ውዴ', 'ልቤ',
        'konjo', 'enibada', 'wubsh', 'libdash', 'ውብሽ', 'እኒባዳ', 'ልብዳሽ'
    ]
    if any(word in message_lower for word in flirty_words):
        # Check for specific compliment types
        if 'amaregn' in message_lower or 'enibada' in message_lower:
            return "enibada"
        elif 'ልብዳሽ' in message_lower or 'libdash' in message_lower:
            return "libdash"
        elif 'ውብ' in message_lower or 'wubsh' in message_lower:
            return "wubsh"
        elif 'ቆንጆ' in message_lower or 'konjo' in message_lower:
            return "konjo"
        else:
            return "flirty"
    
    # ===== RELATIONSHIP QUESTIONS =====
    relationship_keywords = [
        'ፍቅር', 'love', 'wde', 'heart', 'ብቻ', 'fikr', 'የኔ', 'yene', 
        'የአንተ', 'yours', 'boyfriend', 'girlfriend', 'wedaje', 'fiker'
    ]
    if any(word in message_lower for word in relationship_keywords):
        if 'boyfriend' in message_lower or 'wedaje' in message_lower:
            return "do_you_have_boyfriend"
        elif 'like me' in message_lower or 'twedegnaleh' in message_lower:
            return "do_you_like_me"
        elif 'miss me' in message_lower or 'nafekegn' in message_lower:
            return "do_you_miss_me"
        else:
            return "love"
    
    # ===== FAMILY =====
    family_words = [
        'family', 'beteseb', 'mother', 'enat', 'father', 'abat',
        'sister', 'ehit', 'brother', 'wondem', 'mom', 'dad'
    ]
    if any(word in message_lower for word in family_words):
        if 'mother' in message_lower or 'enat' in message_lower or 'mom' in message_lower:
            return "mother"
        elif 'father' in message_lower or 'abat' in message_lower or 'dad' in message_lower:
            return "father"
        elif 'sister' in message_lower or 'ehit' in message_lower:
            return "sister"
        elif 'brother' in message_lower or 'wondem' in message_lower:
            return "brother"
        else:
            return "family"
    
    # ===== HEALTH =====
    health_words = ['sick', 'amemesh', 'fever', 'tirusat', 'pain', 'mekatef', 'weba', 'ras']
    if any(word in message_lower for word in health_words):
        return "sick"
    
    # ===== TRAVEL =====
    travel_words = [
        'travel', 'trip', 'vacation', 'holiday', 'megobgnet', 'mehed', 
        'city', 'መጓዝ', 'ጉዞ', 'አዳማ', 'ጀሞ', 'adama', 'jemo', 'addis'
    ]
    if any(word in message_lower for word in travel_words):
        if 'adama' in message_lower:
            return "adama"
        elif 'jemo' in message_lower:
            return "jemo"
        elif 'addis' in message_lower:
            return "addis_ababa"
        else:
            return "travel"
    
    # ===== FOOD =====
    food_words = [
        'food', 'eat', 'hungry', 'lunch', 'dinner', 'breakfast', 
        'restaurant', 'bela', 'ምግብ', 'በላ', 'እንጀራ', 'mgeb', 'rabesh'
    ]
    if any(word in message_lower for word in food_words):
        return "food"
    
    # ===== THANKS =====
    thanks_words = [
        'thanks', 'thank you', 'amesegnalew', 'appreciate', 'grateful', 'ty',
        'አመሰግናለሁ', 'amesegnalehu'
    ]
    if any(word in message_lower for word in thanks_words):
        return "thanks"
    
    # ===== GOODBYE =====
    goodbye = [
        'bye', 'goodbye', 'see you', 'talk later', 'cya', 'engenagnalen', 
        'dena ederi', 'tegni beka', 'ደህና ሁን', 'ቻው', 'dehna hugni'
    ]
    if any(word in message_lower for word in goodbye):
        return "goodbye"
    
    # ===== BUSY / FREE =====
    if any(phrase in message_lower for phrase in ['i am busy', "tichyalesh", 'ymechishal', 'tchyalesh']):
        return "busy"
    
    if any(phrase in message_lower for phrase in ['i am free', "i'm free", 'mnm alseram', 'ymechishal']):
        return "free"
    
    # ===== EMOTIONS =====
    if any(word in message_lower for word in ['happy', 'des alegn', 'des blognal', 'desta', 'ደስ']):
        return "happy"
    
    if any(word in message_lower for word in ['sad','amemegn' aliklishm' ,'azn', 'ሀዘን', 'azzeleku']):
        return "sad"
    
    if any(word in message_lower for word in ['bored', 'debroshal','aselchi', 'አሰልቺ','deberesh']):
        return "bored"
    
    if any(word in message_lower for word in ['angry', 'atanajign', 'embi', 'ay','ykribgn','dedeb','jezba', 'ተቆጣሁ', 'ተናደድኩ']):
        return "angry"
    
    if any(word in message_lower for word in ['jealous', 'amechign', 'አሜቺ']):
        return "jealous"
    
    # ===== SURPRISE / CONFUSED =====
    surprise = ['wow', 'really', 'no way', 'seriously', 'omg', 'oh', 'ኦህ']
    if any(word in message_lower for word in surprise):
        return "surprise"
    
    confused = ['confused', 'satawk', 'አወ', 'ሳታውቅ', 'algebagnim']
    if any(word in message_lower for word in confused):
        return "confused"
    
    # ===== APOLOGIES =====
    sorry_words = ['sorry', 'apologize', 'yikirta', 'አዝናለሁ', 'aznalew']
    if any(word in message_lower for word in sorry_words):
        return "sorry"
    
    forgive_words = ['forgive', 'mirar', 'ምህረት']
    if any(word in message_lower for word in forgive_words):
        return "forgive"
    
    # ===== HURT / HEARTBROKEN =====
    hurt_words = ['hurt', 'wedehe', 'tegodaw', 'libe temechene']
    if any(word in message_lower for word in hurt_words):
        return "hurt"
    
    heart_words = ['heartbroken', 'libe tesebre', 'ልቤ ተሰበረ']
    if any(word in message_lower for word in heart_words):
        return "heartbroken"
    
    # ===== JOKE / LAUGH =====
    joke_words = ['keld', 'funny', 'lol', 'haha', 'lmao', '😂', 'ሳቅ']
    if any(word in message_lower for word in joke_words):
        return "joke"
    
    # ===== AGREEMENT / DISAGREEMENT =====
    agreement = ['eshi', 'awo', 'right', 'exactly', 'same', 'me too', 'እሺ', 'አዎ', 'ትክክል']
    if any(word in message_lower for word in agreement):
        return "agree"
    
    disagreement = ['disagree', 'not sure', 'doubt', 'different', 'no way', 'አይደለም']
    if any(word in message_lower for word in disagreement):
        return "disagree"
    
    # ===== WEATHER =====
    weather_words = ['weather', 'rain', 'sunny', 'cloudy', 'hot', 'cold', 'አየር', 'ዝናብ', 'ፀሐይ']
    if any(word in message_lower for word in weather_words):
        return "weather"
    
    # ===== HOBBIES =====
    hobby_words = ['hobby', 'free time', 'like to do', 'interests', 'ትርፍ ጊዜ']
    if any(word in message_lower for word in hobby_words):
        return "hobbies"
    
    # ===== LANGUAGES =====
    language_words = ['language', 'speak', 'were', 'anegagersh','tenageri', 'ቋንቋ', 'ምን ትናገራለህ']
    if any(word in message_lower for word in language_words):
        return "languages"
    
    # ===== WEEKEND =====
    weekend_words = ['weekend', 'friday', 'saturday', 'sunday', 'ቅዳሜ',  'እሁድ']
    if any(word in message_lower for word in weekend_words):
        return "weekend"
    
    # ===== TECHNOLOGY =====
    tech_words = ['tech', 'technology', 'internet', 'wifi', 'phone', 'ስልክ', 'ቴክኖሎጂ']
    if any(word in message_lower for word in tech_words):
        return "technology"
    
    # ===== DEFAULT (when nothing else matches) =====
    return "default"
# ==================== AUTO-REPLY HANDLER WITH 15-40 SECOND DELAY ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with sexy Tsega personality"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # ONLY reply to private users
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        if hasattr(chat, 'broadcast') and chat.broadcast:
            return
        if hasattr(chat, 'megagroup') and chat.megagroup:
            return
        
        sender = await event.get_sender()
        if not sender:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        logger.info(f"📨 Message from {chat_id}: '{message_text}'")
        
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        chat_settings = reply_settings[account_key].get('chats', {})
        chat_enabled = chat_settings.get(chat_id, {}).get('enabled', True)
        
        if not chat_enabled:
            return
        
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time()
        })
        
        if len(conversation_history[account_key][chat_id]) > 15:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-15:]
        
        intent = detect_conversation_intent(message_text)
        logger.info(f"Detected intent: {intent}")
        
        response = get_context_aware_response(message_text, intent, conversation_history[account_key][chat_id])
        
        if not response or response.strip() == "":
            response = "እሺ ውዴ ንገርኝ ተጨማሪ 😘 (Okay dear tell me more 😘)"
        
        # ===== 15-40 SECOND DELAY =====
        # Random delay between 15 and 40 seconds to seem human
        delay = random.randint(15, 40)
        logger.info(f"⏱️ Waiting {delay} seconds before replying (human simulation)...")
        
        # Show typing indicator during the wait
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied after {delay}s: '{response[:50]}...'")
        
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time()
        })
        
        save_conversation_history()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            await event.reply("ሰላም ውዴ! ትንሽ እንነጋገር? 😘 (Hi dear! Want to chat a bit? 😘)")
        except:
            pass

# [REST OF YOUR CODE - everything after this point stays exactly the same]
# Continue with start_auto_reply_for_account, keep_alive, all API routes, etc.
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

def start_auto_reply_thread():
    """Start auto-reply in background after server starts"""
    time.sleep(5)
    logger.info("Starting auto-reply for enabled accounts...")
    start_all_auto_replies()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TSEGA - SEXY TELEGRAM AUTO-REPLY')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status}')
    
    print('='*70)
    print('🚀 TSEGA FEATURES:')
    print('   • Talks in Amharic with English translation')
    print('   • Sexy and flirty personality 😘')
    print('   • 15-40 second reply delay (human-like)')
    print('   • Telebirr: 0940980555 for money requests')
    print('   • Meet condition: 1000 birr with screenshot')
    print('   • Lives in Jemo, from Adama')
    print('   • Grade 12 student, 20 years old')
    print('   • Refuses voice calls, prefers meeting')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
