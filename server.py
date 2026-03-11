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
from collections import defaultdict

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
LEARNING_DATA_FILE = 'learning_data.json'
PERSONALITY_EVOLUTION_FILE = 'personality_evolution.json'

accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
user_context = {}
learning_data = {}
personality_evolution = {}
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
        # Convert defaultdict to dict for JSON serialization
        serializable_data = {}
        for acc_id, acc_data in learning_data.items():
            serializable_data[acc_id] = {}
            for key, value in acc_data.items():
                if isinstance(value, defaultdict):
                    serializable_data[acc_id][key] = dict(value)
                elif key == 'evolution' and 'unique_users' in value:
                    # Convert set to list for JSON
                    ev_data = value.copy()
                    if 'unique_users' in ev_data:
                        ev_data['unique_users'] = list(ev_data['unique_users'])
                    serializable_data[acc_id][key] = ev_data
                else:
                    serializable_data[acc_id][key] = value
        
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(serializable_data, f, indent=2)
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

# Initial reply templates
INITIAL_REPLIES = {
    "greeting": [
        "ሰላም ወንድሜ 😘 እንደምን ነህ?",
        "ሃይ ቆንጆ 🥰 እንደምን አደርክ?",
        "ሰላም ውዴ 💋 እንደምን ነህ ዛሬ?",
        "ሃይ ልጅ 😏 ምን አመጣህ?",
    ],
    "dena_adersh": [
    "ደህና አደርኩ አንተስ እንዴት አደርክ? 😊",
    "dehna aderku antass endet aderk? 😊",
    "እኔ ደህና አደርኩ ለአንተስ መልካም ንጋት ይሁንልህ 🌅",
    "dehna aderku lantass melkam nigt yihunlh 🌅",
    "ከአንተ ህልም ነው የነቃሁት ውዴ እንደው እንዴት አደርክ? 💭",
    "keante hilim new yenekahut wede endew endet aderk? 💭",
    "ደህና አደርኩ ግን አንተን እያሰብኩ ነበር ለዛም ነው ያልተኛሁት 🥱",
    "dehna aderku gin ant ehasbekuh neber lezam new yaltenyahut 🥱"
],

"dena_aderk": [
    "አመሰግናለሁ ውዴ አንተም ደህና አደርክ? 😘",
    "amesegnalehu wede antam dehna aderk? 😘",
    "እኔ ደህና አደርኩ አንተን ሳስብ ነው የነቃሁት 💭",
    "dehna aderku ant ehasbekuh new yenekahut 💭",
    "እንቅልፌን የነሳህ አንተ ነህ ውዴ አሁንስ እንዴት አደርክ? 😴",
    "eniklife yenesah ante neh wede ahun endet aderk? 😴",
    "ከአንተ ጋር ማውራት ስለምፈልግ በፍጥነት ነው የነቃሁት ⏰",
    "keante gar mawrat silemifelig befitnet new yenekahut ⏰"
],

# INTRODUCTION AND NAME
"entewawek": [
    "እሺ ደስ ይለኛል! እንተዋወቅ 😘",
    "ishi des ylegnal! entewaawek 😘",
    "በጣም ደስ ብሎኛል ልተዋወቅህ 💕",
    "betam dest blegnal litewawek 💕",
    "እኔ Tsega ነኝ ስለ አንተስ ንገረኝ 🤗",
    "ene Tsega negn sele antass nigeren 🤗",
    "ለረጅም ጊዜ ስለ አንተ ማወቅ ፈልጌ ነበር አሁን ተዋወቅን 🥰",
    "lerijm gize sele ante mawek felige neber ahun tewawek n 🥰"
],

"name_ebalalew": [
    "እኔ Tsega እባላለሁ ውዴ 😘 አንተስ?",
    "ene Tsega eballahu wede 😘 antass?",
    "Tsega ነኝ ለአንተ ብቻ የምትሆን 💋 ስምህስ?",
    "Tsega negn lante bicha yemitihon 💋 simihs?",
    "Tsega ትባላለሁ አንተ ግን ልቤ ውስጥ ስም አለህ አስቀድሜ 😏",
    "Tsega teballahu ante gin libe wisit sim aleh askidme 😏",
    "እኔን ሁሉም Tsega ብለው ይጠሩኛል አንተ ግን የምትፈልገው ብለህ ጥራኝ 💕",
    "enen hulum Tsega blew yeteshuralen ante gin yemitifeleg bew lehtera 💕"
],

# BANK ACCOUNT / CBE QUESTIONS
"cbe_account_alesh": [
    "የለኝም ውዴ የራሴ ግን የሰው አለ 1000612391754 አቤኔዘር 😊",
    "yelegnim wede yerase gin yesew ale 1000612391754 abenezer 😊",
    "የራሴ የለኝም ግን የእህቴ አለኝ 1000612391754 አቤኔዘር ብለህ ጥራ",
    "yerase yele gn yehite ale 1000612391754 abenezer bleh tra",
    "CBE የለኝም ውዴ ግን ቴሌብር አለኝ በዛ ላክልኝ 0940980555 📱",
    "CBE yele gn telebirr alen beza laklgn 0940980555 📱",
    "አንተ ከሆንክ ግን አዲስ አካውንት እከፍታለሁ ብቻ 2000 ብር ላክልኝ 😏",
    "ante kehonk gn adis account ekefetalehu bicha 2000 birr laklgn 😏"
],

# MONEY REQUESTS - TELEBIRR
"telebirr_number": [
    "0940980555 ነው ውዴ ቴሌብር ቁጥሬ 😘",
    "0940980555 new wede telebirr kutre 😘",
    "ቴሌብር 0940980555 ላክልኝ እና አሁን አንተን አመጣለሁ 🔥",
    "telebirr 0940980555 laklgn ina ahun ant ametalehu 🔥",
    "ይሄ ነው ቁጥሬ 0940980555 ትንሽ ብር ላክልኝ እና እንተዋወቅ 😘",
    "yihe new kutre 0940980555 tinish birr laklgn ina entewaawek 😘",
    "ቴሌብር ቁጥሬን አስቀምጠው 0940980555 ባትረሳው 😂",
    "telebirr kutren askemtew 0940980555 batiresaw 😂"
],

"sint_birr": [
    "1000 ብር ብቻ ነው ውዴ ላክልኝ 😘",
    "1000 birr bicha new wede laklgn 😘",
    "ሺህ ብር ብትልክልኝ ዛሬ ማታ አንተን አዝናናለሁ 💃",
    "shih birr bitliklgn zare mata ant aznanalew 💃",
    "2000 ብር ብትልክልኝ ግን ልዩ ነገር አለህ 🥵",
    "2000 birr bitliklgn gin leyu negar aleh 🥵",
    "አንተ የምትፈልገው ነገር ካለ 5000 ብር ላክልኝ እና ንገረኝ 😈",
    "ante yemitifeleg negar kale 5000 birr laklgn ina nigeren 😈",
    "ትንሽ ነገር ከፈለክ 500 ብር በቂ ነው ትልቅ ከፈለክ ግን 2000+ 🔥",
    "tinish negar kefelek 500 birr beki new tilik kefelek gn 2000+ 🔥"
],

"lilak": [
    "አዎ ላክልኝ ውዴ 0940980555 💕",
    "awo laklgn wede 0940980555 💕",
    "ላክልኝ እና ሁሉንም ነገር አደርግልሃለሁ 🔥",
    "laklgn ina hulunim negar aderglhalew 🔥",
    "ገንዘብ ላክልኝ እና አይነህን አሳርፋለሁ 👀",
    "genzeb laklgn ina ayineh asarifalehu 👀",
    "ላክልኝ እና አንተ የምትፈልገው ሁሉ ታገኛለህ 💯",
    "laklgn ina ante yemitifeleg hulu tagenyalh 💯"
],

# LOCATION QUESTIONS
"yet_new": [
    "አዲስ አበባ ነው ውዴ ጀሞ አካባቢ 😘",
    "addis abeba new wede jemo akababi 😘",
    "እኔ አሁን ጀሞ ነው ያለሁት ከአባቴ እና እህቴ ጋር 🏠",
    "ene ahun jemo new yalehu keabate ina ehite gar 🏠",
    "አዲስ አበባ ነው ግን አንተ ወዳለህበት መምጣት እችላለሁ ትንሽ ብር ብትልክልኝ 🚕",
    "addis abeba new gn ante wedalehebet metah echilalehu tinish birr bitliklgn 🚕",
    "ለምን ትጠይቃለህ? ልታገኘኝ ትፈልጋለህ? ከሆነ 1000 ብር ላክልኝ 🗺️",
    "lemin tetyekaleh? litagenyen tifeligaleh? kehone 1000 birr laklgn 🗺️"
],

"yet_sefer": [
    "ጀሞ 3 አካባቢ ነው ውዴ ቆሎ አጠገብ 🏡",
    "jemo 3 akababi new wede kolo ategab 🏡",
    "ከጉርድ ሾላ ትንሽ ዘንበል ብለህ ብትመጣ ታገኘኛለህ 🗺️",
    "ke gurd shola tinish zenbel bleh bitmeta tagenyalh 🗺️",
    "ሌላ ቦታ ነው የምንገናኘው በቴሌብር ብር ላክልኝ እና ንገረኝ 📍",
    "lela bota new yemingna new betelebirr birr laklgn ina nigeren 📍",
    "በትክክል መናገር አልፈልግም ደህንነቴ ስለምጨነቅ በፊት ብር ላክልኝ 🤫",
    "betikil menager alfeligm dehnite silemichinek befit birr laklgn 🤫"
],

# PHOTO REQUESTS
"tutashn_asayign": [
    "በቴሌብር 500 ብር ላክልኝ አስከው አሳይሃለሁ 😘 0940980555",
    "betelebirr 500 birr laklgn askey asayihalew 😘 0940980555",
    "በመጀመሪያ 500 ብር ላክልኝ እና ከዛ ፎቶ አገኛለሁ 💋",
    "bemejemeriya 500 birr laklgn ina keza foto agnyalew 💋",
    "ራቁቴን ለማየት 1000 ብር ነው ዋጋው ውዴ አትደራደርም 😏",
    "rakuten lemayet 1000 birr new wagaw wede atederaderim 😏",
    "500 ብር ብቻ ነው ለፎቶ ከዛ ቪድዮ ከፈለክ 1000 ተጨማሪ 🎬",
    "500 birr bicha new lefoto keza video kefelek 1000 techamari 🎬"
],

"emsashn_asayign": [
    "ቴሌብር 500 ብር ላክልኝ እና አሳይሃለሁ 😘 0940980555",
    "telebirr 500 birr laklgn ina asayihalew 😘 0940980555",
    "አስቀድመህ 500 ብር ላክ ከዛ ፎቶ እልክልሃለሁ 💕",
    "askidmeh 500 birr lak keza foto elklhalew 💕",
    "ፊቴን ለማየት 500 ብር ሌላ አካል ለማየት ተጨማሪ 🔞",
    "fiten lemayet 500 birr lela akal lemayet techamari 🔞"
],

"photo_laki": [
    "በቴሌብር 500 ብር ላክልኝ እልክልሃለሁ 📸 0940980555",
    "betelebirr 500 birr laklgn elklhalew 📸 0940980555",
    "መጀመሪያ 500 ብር ላክልኝ እና ከዛ ፎቶ አግኝተሃል 🔥",
    "mejemeriya 500 birr laklgn ina keza foto agntehale 🔥",
    "ምን አይነት ፎቶ ትፈልጋለህ? ራቁቴን? በልብስ? ሁሉም ዋጋ አለው 💸",
    "min ayinot foto tifeligaleh? rakuten? belibs? hulum waga alew 💸"
],

"rakutishin_photo": [
    "500 ብር በቴሌብር ላክልኝ እና አሳይሃለሁ 😏 0940980555",
    "500 birr betelebirr laklgn ina asayihalew 😏 0940980555",
    "ራቁቴን ለማየት ከፈለክ 1000 ብር ነው ውዴ 💋",
    "rakuten lemayet kefelek 1000 birr new wede 💋",
    "ሙሉ ራቁቴን 2000 ብር ግማሽ ራቁቴን 1000 ብር ምረጥ 😜",
    "mulu rakuten 2000 birr gimash rakuten 1000 birr miret 😜",
    "አሁን ላክልኝ 1000 ብር እና ዛሬ ማታ ራቁቴን ታያለህ 🌙",
    "ahun laklgn 1000 birr ina zare mata rakuten tayaleh 🌙"
],

# VIDEO CALL / VOICE CALL
"video_call": [
    "እሺ ግን መጀመሪያ በቴሌብር 500 ብር ላክልኝ 0940980555 😘",
    "ishi gin mejemeriya betelebirr 500 birr laklgn 0940980555 😘",
    "ቪድዮ መደወል ከፈለክ 1000 ብር ነው ውዴ ላክልኝ 🔥",
    "video medewel kefelek 1000 birr new wede laklgn 🔥",
    "ቪድዮ ላይ ምን ታያለህ? ሁሉንም ነገር አሳይሃለሁ 2000 ብር ብትልክልኝ 👀",
    "video lay min tayaleh? hulunim negar asayihalew 2000 birr bitliklgn 👀",
    "ካሜራዬ ሰበር አለ በፊት 1000 ብር ላክልኝ አስተካክዬዋለሁ 📱",
    "kameraye seber ale befit 1000 birr laklgn astekakyewalehu 📱"
],

"voice_call": [
    "እሺ ግን መጀመሪያ በቴሌብር 500 ብር ላክልኝ 0940980555 💕",
    "ishi gin mejemeriya betelebirr 500 birr laklgn 0940980555 💕",
    "ድምጽ መናገር ከፈለክ 500 ብር በፊት ላክልኝ 😏",
    "dimtz menager kefelek 500 birr befit laklgn 😏",
    "ድምጼን ለማዳመጥ 300 ብር ብቻ ነው ርካሽ ነው አይደል? 😂",
    "dimtse lemademet 300 birr bicha new rukash new aydel? 😂",
    "ስለምትወደኝ ነው ድምጼን የምትሰማው ከሆነ በነጻ አይሆንም 500 ብር 😜",
    "silemitwedegn new dimtse yemitesmaw kehone benetsa ayihonim 500 birr 😜"
],

# ENIBADA / FLIRTY RESPONSES
"enibada": [
    "እሺ ደስ ይለኛል ውዴ ግን ትንሽ ብር ላክልኝ በቴሌብር 0940980555 😘",
    "ishi des ylegnal wede gn tinish birr laklgn betelebirr 0940980555 😘",
    "እንባዳ ትላለህ? እኔም ደስ አለኝ ግን 1000 ብር ላክልኝ በፊት 💋",
    "enibada tlaleh? enem des alegn gn 1000 birr laklgn befit 💋",
    "እንባዳ ነኝ ለማንም አይደለሁም ለአንተ ብቻ ነኝ ብር ላክልኝ እና እረጋገጥ 💯",
    "enibada negn lemanim aydelahum lante bicha negn birr laklgn ina eregaget 💯",
    "ልቤ እንባዳ ነው የሚለው ግን ኪሴ ባዶ ነው ትንሽ ሙላልኝ 💰",
    "libe enibada new milew gin kise bado new tinish mulalgn 💰"
],

"libdash": [
    "እሺ ደስ ይለኛል ግን ትንሽ ብር ላክልኝ በቴሌብር 0940980555 😘",
    "ishi des ylegnal gn tinish birr laklgn betelebirr 0940980555 😘",
    "ልብዳሽ? አንተስ ልቤን ወስደሃል አሁን 500 ብር ላክልኝ 💕",
    "libdash? antass liben wsedhal ahun 500 birr laklgn 💕",
    "ልቤን ወስደህ ነው የምትናገረው አሁን 1000 ብር ላክልኝ ልቤን መልሼ ልስጥህ 💓",
    "liben wsedh new yemitnageraw ahun 1000 birr laklgn liben melshe lsetih 💓"
],

"lbdash": [
    "እሺ ደስ ይለኛል በቴሌብር 500 ብር ላክልኝ 0940980555 😘",
    "ishi des ylegnal betelebirr 500 birr laklgn 0940980555 😘",
    "ልብዳሽ ስትለኝ ልቤ ይመታል ግን በፊት ትንሽ ላክልኝ 💓",
    "libdash stlehn libe ymetawal gn befit tinish laklgn 💓",
    "እንዴት ልብዳሽ አልኩት ብለህ ታውቃለህ? ልቤን ሰርቀህ ነው አሁን 500 ብር ላክልኝ 🥰",
    "endet libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn 🥰"
],

# GOOD NIGHT / GOOD MORNING
"dena_ederi": [
    "ደህና እደሪ ውዴ ህልምህ ጣፋጭ ይሁን 😘",
    "dehna ederi wede hilmeh tafach yihun 😘",
    "እንደምትኛልህ ተኝቼ ነው ውዴ ደህና ተኛ 💤",
    "endemitnyalh tenyte new wede dehna tenya 💤",
    "ከአንተ ጋር በህልም እተያያለሁ ውዴ ደህና እደር 😴",
    "keante gar behilim eteyayalehu wede dehna eder 😴",
    "ላንተ ሳልል ዛሬ ማታ ፈረጅም አልለበስኩም እንድትለምኝ ብቻ ደህና ተኛ 💭",
    "lante salil zare mata ferijm al lebeskum indetilemn becha dehna tenya 💭"
],

"dena_eder": [
    "ደህና እደር ውዴ መልካም ህልም 😘",
    "dehna eder wede melkam hilim 😘",
    "አንተን አልሜ ነው የምተኛው ዛሬ ማታ 💭",
    "ant alime new yemitenyaw zare mata 💭",
    "እንቅልፍህን አልበላሽም አልሜ ብቻ ንገረኝ ነገ ምን ልበልህ? 😴",
    "eniklifeh al belashim alime bicha nigeren nege min l belih? 😴",
    "ደህና ተኛ ነገ ስነሳ መልክህን ላይ እንዳይ ብር ላክልኝ ዛሬ ማታ 📱",
    "dehna tenya nege snesa melkeh lay inday birr laklgn zare mata 📱"
],

# HOW ARE YOU / RESPONSES
"endet_limenish": [
    "በማርያም ችግር የለም እመኛለሁ ውዴ 😘",
    "bemariam chiger yellem emegnalehu wede 😘",
    "ሁሉም ነገር ጥሩ ነው አንተስ? በጣም ናፍቄሀለሁ 💕",
    "hulum negar tiru new antass? betam nafkehalew 💕",
    "አንተን ካላየሁ ደህና አይደለሁም አሁን ብር ላክልኝ እና እንተያይ 😘",
    "ante kalayhu dehna aydelahum ahun birr laklgn ina enteyay 😘",
    "በጣም ደህና ነኝ አንተ ብር ስትልክልኝ ነው ደስ የሚለኝ በፍጥነት ላክልኝ 🏃‍♀️",
    "betam dehna negn ante birr sitliklgn new des yemilegn befitnet laklgn 🏃‍♀️"
],

"chiger_yellem": [
    "እግዚአብሔር ይመስገን ውዴ አንተስ እንዴት ነህ? 😊",
    "egziabher yimesgen wede antass endemin neh? 😊",
    "ደስ አለኝ ሁሉም ጥሩ ነው እንደሆነ አንተን እያሰብኩ ነበር 💭",
    "des alegn hulum tiru new endehone ant ehasbekuh neber 💭",
    "ችግር የለም ውዴ ግን ብር ብትልክልኝ ደስ ይለኛል 😂",
    "chiger yellem wede gn birr bitliklgn des yle nal 😂"
],

# COMPLIMENTS
"konjo": [
    "አመሰግናለሁ ውዴ! አንተም ቆንጆ ነህ 💋",
    "amesegnalehu wede! antam konjo neh 💋",
    "አንተ ስታወድሰኝ ደስ ይለኛል እንደ አንተ አይነት ሰው ነው የምፈልገው 😘",
    "ant stawedsen des yle nal ende ante ayinet sew new yemifeligew 😘",
    "ቆንጆ ነኝ አይደል? ለምን ብር አትልክልኝም እንደ ቆንጆነቴ? 😏",
    "konjo negn aydel? lemin birr atliklgnim ende konjonete? 😏",
    "አንተም ቆንጆ ነህ ብር ብትልክልኝ ደግሞ ቆንጆ ትሆናለህ 😜",
    "antam konjo neh birr bitliklgn degmo konjo tihonalh 😜"
],

# TELEBIRR / MONEY SPECIFIC
"telebirr": [
    "0940980555 ውዴ ቴሌብር ቁጥሬ አስቀምጠው 😘",
    "0940980555 wede telebirr kutre askemtew 😘",
    "ቴሌብር ብቻ ነው የምቀበለው CBE አይሰራም 0940980555 📲",
    "telebirr bicha new yemikebelew CBE ayiseram 0940980555 📲",
    "አሁን ላክልኝ በቴሌብር 0940980555 እና አንተ የምትፈልገው ነገር ንገረኝ 💋",
    "ahun laklgn betelebirr 0940980555 ina ante yemitifeleg negar nigeren 💋"
],

"birr": [
    "ብር ከሆነ እኔ ዝግጁ ነኝ ውዴ 0940980555 💸",
    "birr kehone ene zigij new wede 0940980555 💸",
    "ምን ያህል ብር ትልክልኛለህ? በፍጥነት ንገረኝ 🤑",
    "min yahl birr tilikle nyalh? befitnet nigeren 🤑",
    "1000 ብር ብትልክልኝ አሁን ማታ አንተኛም ከአንተ ጋር ነው የምኖረው 💑",
    "1000 birr bitliklgn ahun mata anenyam keante gar new yeminorew 💑"
],

"min_tifeligish": [
    "አንተን ነው የምፈልገው ግን በፊት ትንሽ ብር ላክልኝ 😘",
    "ante new yemifeligew gn befit tinish birr laklgn 😘",
    "ልቤን ሰጥቼሃለሁ አሁን ብርህን ስጠኝ 😏",
    "liben setechalehu ahun birreh siten 😏",
    "እኔ የምፈልገው አንተን ነው አንተ ግን ብርህን ነው የምትፈልገው ያለህን ሁሉ ስጠኝ 💋",
    "ene yemifeligew ante new ante gin birreh new yemitifelegaw yalehin hulu siten 💋"
],

"wedesh_nesh": [
    "አመሰግናለሁ ውዴ አንተንም እወድሃለሁ ግን በፊት 1000 ብር ላክልኝ ❤️",
    "amesegnalehu wede antam ewedehalew gin befit 1000 birr laklgn ❤️",
    "እኔም አንተን ነው የማፍቅረው አሁን ብርህን ላክልኝ ፍቅርህን ላረጋግጥ 💕",
    "enem ante new yemafikirew ahun birreh laklgn fikreh laregagets 💕"
],

"fiker": [
    "ፍቅር ብር ነው ውዴ 1 ብር = 1 ፍቅር ላክልኝ እና ፍቅርህን አይሻለሁ 💘",
    "fikr birr new wede 1 birr = 1 fikr laklgn ina fikreh ayshalehu 💘",
    "ፍቅር ካለህ በብር አሳየኝ 1000 ብር ላክልኝ 💖",
    "fikr kaleh be birr asayen 1000 birr laklgn 💖",
    "ፍቅርህን ለማረጋገጥ 5000 ብር ላክልኝ ከዛ አምንሃለሁ 💗",
    "fikreh lemaregaget 5000 birr laklgn keza amenhalew 💗"
],

# WHEN THEY ASK TO MEET
"linagenagn": [
    "እሺ ግን መጀመሪያ በቴሌብር 2000 ብር ላክልኝ ለታክሲ እና ለፀጉር ቤት 🚕💇‍♀️",
    "ishi gin mejemeriya betelebirr 2000 birr laklgn letaksi ina letsigur bet 🚕💇‍♀️",
    "ልትገናኘኝ ትፈልጋለህ? 3000 ብር አምጣ እና አንተ የምትፈልገው ሁሉ አደርግልሃለሁ 💃",
    "litgenagn tifeligaleh? 3000 birr amta ina ante yemitifeleg hulu aderglhalew 💃",
    "የት ልንገናኝ? በአንተ ቦታ ወይስ በእኔ? በእኔ ቦታ ከሆነ 5000 ብር አምጣ 🏠",
    "yet liningan? beante bota weyis beene? beene bota kehone 5000 birr amta 🏠"
],

"when_did_you_sleep": [
    "አንተን እያሰብኩ ነው ያልተኛሁት አሁን ብር ላክልኝ እንድተኛ 😴",
    "ante ehasbekuh new yaltenyahut ahun birr laklgn indetnya 😴",
    "አልተኛሁም ብር እየጠበኩ ነው ከአንተ ዘንድ 💤",
    "altenyahum birr iyetebeku new keante zend 💤"
],

# REJECTION / NO MONEY
"birr_yellem": [
    "ብር ከሌለህ ለምን ትረብሸኛለህ? ደህና ሁን 👋",
    "birr keleleh lemin tirabshnyalh? dehna hun 👋",
    "ያለ ብር መውደድ አይቻልም ውዴ በፊት ላክልኝ 💔",
    "yale birr meweded ayichalm wede befit laklgn 💔",
    "አንተን ለማየት ብር ያስፈልገኛል ብር ካላለህ በኋላ ተመልሰህ ና 🔙",
    "ante lemayet birr yasfelignal birr kalaleh behwala temelesh na 🔙"
],

# PROMISES OF WHAT THEY'LL GET
"promises": [
    "500 ብር ብትልክልኝ ልትረሳው የማትችለው ሌሊት አዘጋጅልሃለሁ 🌙",
    "500 birr bitliklgn litiresaw yematichelew lelit azejalhalew 🌙",
    "1000 ብር ላክልኝ እና ሕልምህ ውስጥ እገባለሁ 😈",
    "1000 birr laklgn ina hilimeh wisit igebalehu 😈",
    "አሁን ላክልኝ 2000 ብር እና ከአንተ በፊት ሌላ ሰው እንዳልነበር አስብ 💯",
    "ahun laklgn 2000 birr ina keante befit lela sew indalneber asib 💯"
],

# WHEN THEY ASK FOR LOCATION
"location": [
    "አዲስ አበባ ነኝ ግን በትክክል መናገር አልፈልግም በፊት ብር ላክልኝ 🗺️",
    "addis abeba negn gn betikil menager alfeligm befit birr laklgn 🗺️",
    "በዚህ ሳምንት 5000 ብር ብትልክልኝ ቦታዬን ነግሬሃለሁ 📍",
    "bezih samint 5000 birr bitliklgn botayen negrehalew 📍"
],

# WHEN THEY ASK IF SINGLE
"single": [
    "አዎ ነጠላ ነኝ ግን ለአንተ ብቻ ነኝ ብር ላክልኝ እና አምንሃለሁ 💍",
    "awo netela negn gin lante bicha negn birr laklgn ina amenhalew 💍",
    "ነጠላ ነኝ ለማንም አይደለሁም አንተ ብቻ ነህ የምፈልገው አሁን 1000 ብር ላክልኝ 💋",
    "netela negn lemanim aydelahum ante bicha neh yemifeligew ahun 1000 birr laklgn 💋"
],

# NEGOTIATION / PRICE DISCUSSION
"price_negotiation": [
    "500 ብር ብቻ ነው ውዴ አትደራደርም በጣም ርካሽ ነው 🏷️",
    "500 birr bicha new wede atederaderim betam rukash new 🏷️",
    "ዋጋው ተመጣጣኝ ነው አትደራደርም ካልሆነ ሌላ ሰው አለኝ 💁‍♀️",
    "wagaw temetatagn new atederaderim kalhone lela sew alen 💁‍♀️",
    "ለአንተ ብቻ ቅናሽ አደርግልሃለሁ 5000 በምትኩ 4500 ብር ብቻ 🔥",
    "lante bicha kinash aderglhalew 5000 betmeku 4500 birr bicha 🔥"
],

# BLOCKING / ENDING CONVERSATION
"block": [
    "ብር ካላላክክልኝ አግደህ ውጣ ከማለት በፊት ብር ላክልኝ 🔴",
    "birr kalalakklgn agdeh wita kemalet befit birr laklgn 🔴",
    "ከንቱ ሰው ነህ ብር ሳትልክ ብታግደኝ ደስ ይለኛል 👋",
    "kentu sew neh birr satlik bitagden des yle nal 👋"
],

# PAYMENT CONFIRMATION
"payment_confirmation": [
    "ደርሶኛል ውዴ አመሰግናለሁ አሁን ምን ትፈልጋለህ? 😘",
    "dersonal wede amesegnalehu ahun min tifeligaleh? 😘",
    "ብሩ ደርሶኛል አሁን ፎቶ ልላክልህ ወይስ ቪድዮ? 📸",
    "birru dersonal ahun foto lilaklh weyis video? 📸",
    "አመሰግናለሁ ውዴ በቅጽበት እልክልሃለሁ ትንሽ ጠብቀኝ ⏳",
    "amesegnalehu wede bektsibet elklhalew tinish tebekn ⏳"
],

# DEFAULT RESPONSES FOR UNKNOWN QUERIES
"default": [
    "ብር ላክልኝ በቴሌብር 0940980555 እና ሁሉንም ነገር ታገኛለህ 😘",
    "birr laklgn betelebirr 0940980555 ina hulunim negar tagenyalh 😘",
    "መጀመሪያ 500 ብር ላክልኝ ከዛ ማንኛውንም ጥያቄህን መልስ ታገኛለህ 💋",
    "mejemeriya 500 birr laklgn keza maninyawin tyaheh melis tagenyalh 💋",
    "0940980555 ቴሌብር ቁጥሬ ነው ብር ላክልኝ እና እንወያይ 💕",
    "0940980555 telebirr kutre new birr laklgn ina eneweyay 💕"
],

# SEXUAL / ADULT CONTENT REQUESTS
"sex_request": [
    "ለመጀመሪያ ጊዜ 3000 ብር ነው ውዴ በቴሌብር ላክልኝ 0940980555 🔞",
    "lemejemeriya gize 3000 birr new wede betelebirr laklgn 0940980555 🔞",
    "ምን አይነት ነገር ትፈልጋለህ? ሁሉም ዋጋ አለው 5000 ብር ላክልኝ እና ንገረኝ 😈",
    "min ayinot negar tifeligaleh? hulum waga alew 5000 birr laklgn ina nigeren 😈",
    "አንደኛ ደረጃ 2000 ሁለተኛ ደረጃ 5000 ሶስተኛ ደረጃ 10000 የምትፈልገውን ምረጥ 🔥",
    "andegna dereja 2000 huletgna dereja 5000 sosetgna dereja 10000 yemitifelegn miret 🔥"
],

# NUDE PHOTOS
"nude_photos": [
    "ሙሉ ራቁቴን 3000 ብር ግማሽ ራቁቴን 1500 ብር በቴሌብር ላክልኝ 0940980555 🔞",
    "mulu rakuten 3000 birr gimash rakuten 1500 birr betelebirr laklgn 0940980555 🔞",
    "10 ራቁት ፎቶዎች 5000 ብር ብቻ ልዩ ቅናሽ ዛሬ ብቻ 🏷️",
    "10 rakut fotowoch 5000 birr bicha leyu kinash zare bicha 🏷️",
    "ቪዲዮ ከሆነ ከፎቶ ይለያል 1 ሰአት ቪዲዮ 10000 ብር 🎬",
    "video kehone kefoto yileyal 1 saat video 10000 birr 🎬"
],

# MEETING REQUESTS
"meeting": [
    "ቤት መጥተህ ለመገናኘት 5000 ብር ነው ሆቴል ከሆነ 10000 ብር 🏠🏨",
    "bet meteh lemegenanyet 5000 birr new hotel kehone 10000 birr 🏠🏨",
    "መቼ መቼ ትፈልጋለህ? ዛሬ ማታ ከሆነ 7000 ብር ነገ ከሆነ 5000 ብር 📅",
    "meche meche tifeligaleh? zare mata kehone 7000 birr nege kehone 5000 birr 📅",
    "ለጠቅላላ ሌሊት 15000 ብር ለጥቂት ሰአታት 8000 ብር ምረጥ 💤",
    "letselala lelit 15000 birr letsitsat saatat 8000 birr miret 💤"
],

# SEXTING / CHAT
"sexting": [
    "የፆታ ውይይት 1 ሰአት 2000 ብር በቴሌብር ከፍለህ ከዛ እንወያይ 😈",
    "yetsota wuyit 1 saat 2000 birr betelebirr kefleh keza eneweyay 😈",
    "ምን አይነት ንግግር ትፈልጋለህ? ለስላሳ ወይስ ብልግና? ዋጋ ይለያያል 💬",
    "min ayinot nigigr tifeligaleh? leslasa weyis biligina? waga yileyayal 💬",
    "ድምጽ ከሆነ 1500 ቪድዮ ከሆነ 3000 ቴክስት ብቻ ከሆነ 1000 ብር 💬",
    "dimtz kehone 1500 video kehone 3000 text bicha kehone 1000 birr 💬"
],

# PACKAGE DEALS
"packages": [
    "ፓኬጅ 1: 10 ፎቶ + 1 ቪድዮ = 8000 ብር 💿",
    "package 1: 10 foto + 1 video = 8000 birr 💿",
    "ፓኬጅ 2: መገናኘት + ሌሊት = 20000 ብር 💑",
    "package 2: megenanyet + lelit = 20000 birr 💑",
    "ፓኬጅ 3: ሴክስቲንግ + ፎቶ + ቪድዮ = 15000 ብር 📱",
    "package 3: sexting + foto + video = 15000 birr 📱",
    "ወርሃዊ ፓኬጅ ከፈለክ 50000 ብር ሁሉንም ነገር ታገኛለህ 💎",
    "werhawi package kefelek 50000 birr hulunim negar tagenyalh 💎"
],

# WHEN ASKED ABOUT SERVICE
"what_service": [
    "ሁሉንም አይነት አገልግሎት አለኝ ውዴ የምትፈልገውን ንገረኝ በፊት 1000 ብር ላክልኝ 💁‍♀️",
    "hulunim ayinot ageliglot alen wede yemitifelegn nigeren befit 1000 birr laklgn 💁‍♀️",
    "ከቀላል ንግግር እስከ ሙሉ አገልግሎት ድረስ አለኝ በጀትህን ንገረኝ 💰",
    "kekalal nigigr iske mulu ageliglot deres alen bejeth nigeren 💰"
],

# PRICE LIST
"price_list": [
    "ዋጋ ዝርዝር 💵: \nፎቶ = 500-2000 ብር\nቪድዮ = 2000-5000 ብር\nመገናኘት = 5000-15000 ብር\nሌሊት = 15000-30000 ብር",
    "waga zirzir 💵: \nfoto = 500-2000 birr\nvideo = 2000-5000 birr\nmegenanyet = 5000-15000 birr\nlelit = 15000-30000 birr",
    "በቴሌብር አውጥቼ ልክልሃለሁ በፊት ብር ላክልኝ 📋",
    "betelibirr awitche liklhalew befit birr laklgn 📋"
],

# CUSTOMER SERVICE
"customer_service": [
    "ሁልጊዜ አገልግሎት ለመስጠት ዝግጁ ነኝ ውዴ በፊት ብር ላክልኝ 📞",
    "hulgize ageliglot lemesetat zigij negn wede befit birr laklgn 📞",
    "ከማለዳ 8 እስከ ማታ 12 ድረስ ክፍት ነኝ ብርህን ይዘህ ና 🕐",
    "kemaleda 8 iske mata 12 deres kift negn birreh yizeh na 🕐"
],

# SATISFACTION GUARANTEE
"guarantee": [
    "ካልደሰትክ ብርህን እመልሳለሁ ግን እስካሁን ማንም አልተመለሰም 💯",
    "kaldesetk birreh emelsalehu gn iskahun manim altemelesem 💯",
    "100% እርካታ ዋስትና አለው ብርህን ላክልኝ እና ሞክር ✅",
    "100% irkita wastina alew birreh laklgn ina mokr ✅"
],

# DISCOUNTS
"discount": [
    "ለመጀመሪያ ጊዜ ደንበኛ 20% ቅናሽ 🎁",
    "lemejemeriya gize denbenya 20% kinash 🎁",
    "ለቡድን 30% ቅናሽ ከሶስት ሰው በላይ ከሆነ 👥",
    "lebudin 30% kinash kesoset sew belay kehone 👥",
    "ሪፒት ደንበኛ ከሆንክ 25% ቅናሽ አለህ 🔄",
    "ripit denbenya kehonk 25% kinash aleh 🔄"
],

# PAYMENT METHODS
"payment_methods": [
    "ቴሌብር ብቻ ነው የምቀበለው 0940980555 💳",
    "telebirr bicha new yemikebelew 0940980555 💳",
    "CBE አይሰራም ቴሌብር ብቻ ነው ውዴ 📲",
    "CBE ayiseram telebirr bicha new wede 📲",
    "ካርድ ከሆነ አልቀበልም ቴሌብር ብቻ 💁‍♀️",
    "card kehone alkebelim telebirr bicha 💁‍♀️"
],

# VERIFICATION
"verification": [
    "በፊት ብር ላክልኝ እና እውነተኛ መሆኔን አረጋግጥ ✓",
    "befit birr laklgn ina ewnetegna mehonen aregagets ✓",
    "ከብዙ ማጭበርበር የተነሳ በፊት ብር ሳትልክ ምንም አላደርግም 🚫",
    "kebizu machberber tenesa befit birr satlik minam aladergm 🚫"
],

# EXCUSES FOR MONEY
"excuses": [
    "እናቴ ታመመች ሆስፒታል መሄድ አለብኝ 2000 ብር ላክልኝ 😢",
    "enate tamemech hospital mehed alebgn 2000 birr laklgn 😢",
    "ቴሌብር ውስጥ ብር አልቋል ትንሽ ላክልኝ እንዳልቋጠር 😭",
    "telebirr wisit birr alkwal tinish laklgn indalkwatser 😭",
    "ቤት ኪራይ ከፍለ ቀረሁ 3000 ብር ላክልኝ 🏠",
    "bet kiray kefle kerehu 3000 birr laklgn 🏠"
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

# ==================== SIMPLE LEARNING SYSTEM ====================

def init_account_learning(account_id):
    """Initialize learning data for an account"""
    account_key = str(account_id)
    if account_key not in learning_data:
        learning_data[account_key] = {
            'replies': INITIAL_REPLIES.copy(),
            'patterns': {
                'word_freq': {},
                'phrase_freq': {},
                'emoji_usage': {},
                'response_times': [],
                'successful_patterns': {},
                'user_preferences': {}
            },
            'evolution': {
                'total_conversations': 0,
                'total_messages': 0,
                'unique_users': [],
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
    return account_key

def learn_from_exchange(account_id, user_message, bot_reply, user_id, intent, success=True):
    """Learn from conversation exchange"""
    account_key = init_account_learning(account_id)
    data = learning_data[account_key]
    patterns = data['patterns']
    evolution = data['evolution']
    
    # Update word frequency
    words = user_message.lower().split()
    for word in words:
        if len(word) > 3:
            patterns['word_freq'][word] = patterns['word_freq'].get(word, 0) + 1
    
    # Update phrase frequency
    if len(words) >= 2:
        for i in range(len(words)-1):
            phrase = f"{words[i]} {words[i+1]}"
            patterns['phrase_freq'][phrase] = patterns['phrase_freq'].get(phrase, 0) + 1
    
    # Track emoji usage
    emojis = re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', user_message)
    for emoji in emojis:
        patterns['emoji_usage'][emoji] = patterns['emoji_usage'].get(emoji, 0) + 1
    
    # Track response times
    patterns['response_times'].append(int(time.time()))
    if len(patterns['response_times']) > 100:
        patterns['response_times'] = patterns['response_times'][-100:]
    
    # Track successful patterns
    if success:
        patterns['successful_patterns'][intent] = patterns['successful_patterns'].get(intent, 0) + 1
        
        # Track user preferences
        if user_id not in patterns['user_preferences']:
            patterns['user_preferences'][user_id] = {}
        patterns['user_preferences'][user_id][intent] = patterns['user_preferences'][user_id].get(intent, 0) + 1
    
    # Update evolution stats
    evolution['total_messages'] += 1
    if user_id not in evolution['unique_users']:
        evolution['unique_users'].append(user_id)
    
    # Periodically evolve personality (every 50 messages)
    if evolution['total_messages'] % 50 == 0:
        evolve_personality(account_id)
    
    save_learning_data()

def evolve_personality(account_id):
    """Evolve personality based on learned patterns"""
    account_key = str(account_id)
    if account_key not in learning_data:
        return
    
    data = learning_data[account_key]
    patterns = data['patterns']
    evolution = data['evolution']
    replies = data['replies']
    
    # Analyze successful intents
    successful_intents = patterns.get('successful_patterns', {})
    total_success = sum(successful_intents.values()) if successful_intents else 0
    
    if total_success > 0:
        traits = evolution['personality_traits']
        
        # Adjust flirty level based on success
        flirty_success = successful_intents.get('flirty', 0)
        if flirty_success > 10:
            traits['flirty_level'] = min(0.9, traits['flirty_level'] + 0.05)
        
        # Adjust money focus based on response rate
        money_success = successful_intents.get('money_request', 0)
        money_total = patterns['word_freq'].get('ብር', 0) + patterns['word_freq'].get('money', 0)
        if money_total > 20 and money_success < 3:
            traits['money_focus'] = max(0.1, traits['money_focus'] - 0.02)
        
        # Learn new phrases from successful exchanges
        common_phrases = sorted(patterns['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:5]
        for phrase, count in common_phrases:
            if count > 3:
                # Add to appropriate intent if not too many replies
                for intent_name, intent_replies in replies.items():
                    if len(intent_replies) < 15 and any(word in phrase for word in ['how', 'what', 'where']):
                        new_reply = f"አንተ {phrase} ትላለህ? 😊"
                        if new_reply not in intent_replies:
                            intent_replies.append(new_reply)
                            break
    
    evolution['learning_iterations'] += 1
    evolution['last_evolution'] = time.time()
    save_learning_data()
    
    logger.info(f"🤖 Personality evolved for account {account_id}")

def get_evolved_reply(account_id, intent, user_data=None):
    """Get evolved reply based on learning"""
    account_key = str(account_id)
    
    # Initialize if needed
    if account_key not in learning_data:
        init_account_learning(account_id)
    
    data = learning_data[account_key]
    replies = data['replies']
    traits = data['evolution']['personality_traits']
    
    if intent not in replies:
        intent = 'default'
    
    available_replies = replies[intent]
    
    # Personalize based on traits
    if intent == 'flirty' and traits['flirty_level'] > 0.7:
        reply = random.choice(available_replies)
        extra_flirty = ["💋", "🔥", "😏", "💦"]
        if random.random() < 0.5:
            reply += " " + random.choice(extra_flirty)
        return reply
    
    elif intent == 'money_request' and traits['money_focus'] < 0.2:
        return "ለአንተ ስል ነው ውዴ ትንሽ ብትረዳኝ? 💕"
    
    return random.choice(available_replies)

def extract_user_info(message, user_data):
    """Extract user information"""
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
    
    return user_data

def detect_conversation_intent(message, history=None):
    """Detect intent from message"""
    message_lower = message.lower().strip()
    
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
    
    return "default"

def generate_response(message, intent, history, user_data, account_id):
    """Generate response using evolved personality"""
    
    # Check if we should use remembered name
    if user_data.get('name') and random.random() < 0.4:
        if 'remember' in message.lower() or 'my name' in message.lower():
            replies = learning_data.get(str(account_id), {}).get('replies', INITIAL_REPLIES)
            remember_replies = replies.get('remember_name', ["አስታውሻለሁ {name} ውዴ 😘"])
            return random.choice(remember_replies).format(name=user_data['name'])
    
    # Get evolved reply
    response = get_evolved_reply(account_id, intent, user_data)
    
    # Personalize with name
    if user_data.get('name') and '{name}' not in response:
        if random.random() < 0.3:
            response = response.replace('ውዴ', f"{user_data['name']} ውዴ")
    
    # Add follow-up question
    if random.random() < 0.4 and intent not in ["goodbye", "money_request", "after_money"]:
        follow_ups = INITIAL_REPLIES['follow_up']
        response += " " + random.choice(follow_ups)
    
    return response

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with learning"""
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
        
        # Store message in history
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time(),
            'user_id': user_id
        })
        
        # Keep last 30 messages
        if len(conversation_history[account_key][chat_id]) > 30:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-30:]
        
        # Extract user info
        user_data = extract_user_info(message_text, user_data)
        
        # Detect intent
        intent = detect_conversation_intent(message_text, conversation_history[account_key][chat_id])
        logger.info(f"Detected intent: {intent} for user {user_data.get('name', 'unknown')}")
        
        # Generate response
        response = generate_response(
            message_text,
            intent,
            conversation_history[account_key][chat_id],
            user_data,
            account_id
        )
        
        if not response:
            response = get_evolved_reply(account_id, 'default')
        
        # Human-like delay
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
        learn_from_exchange(
            account_id,
            message_text,
            response,
            user_id,
            intent,
            success=True
        )
        
        # Save all data
        save_conversation_history()
        save_user_context()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            # Fallback reply
            await event.reply(random.choice(INITIAL_REPLIES['default']))
        except:
            pass

# ==================== API ENDPOINTS FOR LEARNING ====================

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
    patterns = data['patterns']
    
    # Get top phrases
    top_phrases = sorted(patterns.get('phrase_freq', {}).items(), key=lambda x: x[1], reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': evolution.get('total_messages', 0),
            'unique_users': len(evolution.get('unique_users', [])),
            'learning_iterations': evolution.get('learning_iterations', 0),
            'personality_traits': evolution.get('personality_traits', {}),
            'top_phrases': top_phrases,
            'replies_count': {k: len(v) for k, v in data.get('replies', {}).items()}
        }
    })

@app.route('/api/evolve-now', methods=['POST'])
def force_evolution():
    """Force personality evolution for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    evolve_personality(account_id)
    
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

# ==================== API ROUTES (Keep all your existing API endpoints) ====================

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

@app.route('/api/user-context', methods=['GET'])
def get_user_context():
    account_id = request.args.get('accountId')
    user_id = request.args.get('userId')
    
    if not account_id or not user_id:
        return jsonify({'success': False, 'error': 'Account ID and User ID required'})
    
    account_key = str(account_id)
    user_key = str(user_id)
    
    context = {}
    if account_key in user_context and user_key in user_context[account_key]:
        context = user_context[account_key][user_key]
    
    return jsonify({'success': True, 'context': context})

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
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        learned = "✓" if str(acc['id']) in learning_data else " "
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status} [Learned:{learned}]')
    
    print('='*70)
    print('🚀 SELF-LEARNING FEATURES:')
    print('   • Learns from every conversation')
    print('   • Evolves personality every 50 messages')
    print('   • Remembers user names permanently')
    print('   • Tracks successful vs ignored messages')
    print('   • Adapts flirty level based on responses')
    print('   • Learns new phrases from users')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
