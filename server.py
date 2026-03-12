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
active_listeners = {}  # Track active auto-reply listeners

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
    "photo_price": 5,  # in stars
    "video_price": 100,  # in stars
    "naked_price": 2000,
    "half_naked_price": 1000,
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
        "ey ta di yas min tishal?",
        "selam wude nafkehalew",
        "dehna metah wude?",
        "hi there endemin neh?",
        "dehna deresu",
        "selam ke minimize metah?",
        "ey koyeh koyeh",
        "dehna negn antess?",
        "ene dehna negn anchi how?"
    ],

    # ===== HOW ARE YOU =====
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

    # ===== WHAT ARE YOU DOING =====
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

    # ===== ASK NAME =====
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

    # ===== ASK AGE =====
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

    # ===== LOCATION =====
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

    # ===== ASK JOB =====
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

    # ===== FLIRTY =====
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

    # ===== ENIBADA (You're handsome) =====
    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn",
        "enibada nagn leloh aydelahum lante bicha nagn",
        "enibada endet alkut nagerign",
        "enibada sew ahun min tishal"
    ],

    # ===== LIBDASH (Heart stealer) =====
    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "ende libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn",
        "libdash tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "libdash yemil sew ante neh ahun 500 birr laklgn"
    ],

    # ===== KONJO (Beautiful) =====
    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "betam konjo neh"
    ],

    # ===== MONEY REQUEST =====
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

    # ===== PHOTO REQUEST =====
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

    # ===== NAKED REQUEST =====
    "naked_request": [
        "mulu rakuten 3000 birr gimash rakuten 1500 birr",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakutishin asayishu 2000 birr new",
        "500 birr betelebirr laklgn ina asayihalehu",
        "rakuten sitay 1500 birr new",
        "gimash rakuten 1000 birr mulu rakuten 2000 birr",
        "mulu rakuten 2000 birr laklgn",
        "gimash rakuten 1000 birr"
    ],

    # ===== MEET REQUEST =====
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
        "wude 2000 birr ametaleh nw?",
        "lemagenat 1000 birr beki new"
    ],

    # ===== VOICE CALL =====
    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "dimts mesmat bicha ema fet lefit meyet new yemiyaseyew",
        "ahun kalhone betequrb tenageralen ahun agebagn",
        "aldwedrm betequrb ena edmeralen"
    ],

    # ===== GOODBYE =====
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

    # ===== THANKS =====
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "minim aydelem wude ante des biloh beki nagn",
        "amesegnalehu betam lante madreg",
        "minim aydelem ante des biloh"
    ],

    # ===== MORNING =====
    "morning": [
        "endemin aderk wude melkam nigt",
        "ke eniklife yenekahut ante ehasbekuh new",
        "maleya anten masbet new lemwade",
        "ande ferej alilebeskum ina anten asebku",
        "melkam nigt yelibe konjo",
        "endemin aderk eniklife tafach neber?",
        "ande tsehay tiru new anten sihone"
    ],

    # ===== NIGHT =====
    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "hilime wisit nurny zare mata",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "hilime wisit tenagn",
        "dehna tenya betam",
        "hilim tafach yihun"
    ],

    # ===== LOVE =====
    "love": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ewedihalehu konjo",
        "ante new yemifeligew",
        "tiwedegnyal betam",
        "antin ewodalehu kelibe betam"
    ],

    # ===== MISS =====
    "miss": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
        "betam nafkehalew",
        "nafkehalew"
    ],

    # ===== JEALOUS =====
    "jealous": [
        "lela sew tayaleh? lemin",
        "kemichawet gar neberku? man new?",
        "betam amechignaleh",
        "ande amechign",
        "lela sew sasbew amechignalehu",
        "ante bicha new yaleny lela sew atay"
    ],

    # ===== HURT =====
    "hurt": [
        "liben wedehe betam",
        "libe temechene",
        "liben wedehe lemin?",
        "libe temechene betam",
        "liben wedehe betam azeleku"
    ],

    # ===== SORRY =====
    "sorry": [
        "aznalegu betam yikirta",
        "aznalegu ante",
        "aznalegu",
        "yikirta efeligalehu"
    ],

    # ===== FORGIVE =====
    "forgive": [
        "miralew wude",
        "miralew betam",
        "miralew",
        "mirar efeligalehu"
    ],

    # ===== FAMILY =====
    "family": [
        "beteseb betam yasefeligonal",
        "abate ena ehite gar negn",
        "enaté betam tiru set nache",
        "abate betam deg new",
        "ehité betam tiriwedalehu"
    ],

    # ===== BORED =====
    "bored": [
        "enem aselchi negn anten sihone des alegn",
        "aselchi neber? ina nagerign",
        "enem aselchi negn ande eneweyay",
        "aselchi neh? ina min iteweyay"
    ],

    # ===== HAPPY =====
    "happy": [
        "des alegn betam tiru sew neh",
        "des alegn anten sihone",
        "desta betam konjo new",
        "des alegn ande naw"
    ],

    # ===== SAD =====
    "sad": [
        "lemin azeleku? nagerign",
        "azn neber? betam ayzalen",
        "lemin azneleh?",
        "aznalehu"
    ],

    # ===== JOKE =====
    "joke": [
        "lemidisak ande nageralehu",
        "sik telant and tawukaleh?",
        "andisachew nageralehu",
        "sik ande tisikehalehu"
    ],

    # ===== CONFUSED =====
    "confused": [
        "lemin tishafafekaleh? nagerign",
        "shafafekeh? ina anagegnal",
        "andet litira awe?",
        "ande awe"
    ],

    # ===== WAITING =====
    "waiting": [
        "koyeh nw meche tagenal?",
        "and etebekushalehu",
        "koyeh nw betam"
    ],

    # ===== DEFAULT (fallback) =====
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
        
        # Update word frequency
        words = user_message.lower().split()
        for word in words:
            if len(word) > 2:
                patterns['word_freq'][word] = patterns['word_freq'].get(word, 0) + 1
        
        # Update phrase frequency (2-word combinations)
        if len(words) >= 2:
            for i in range(len(words)-1):
                phrase = f"{words[i]} {words[i+1]}"
                patterns['phrase_freq'][phrase] = patterns['phrase_freq'].get(phrase, 0) + 1
        
        # Track intent success/failure
        if user_responded:
            patterns['successful_intents'][intent] = patterns['successful_intents'].get(intent, 0) + 1
        else:
            patterns['failed_intents'][intent] = patterns['failed_intents'].get(intent, 0) + 1
        
        # Track user preferences
        if user_id not in patterns['user_preferences']:
            patterns['user_preferences'][user_id] = {}
        patterns['user_preferences'][user_id][intent] = patterns['user_preferences'][user_id].get(intent, 0) + 1
        
        # Track response time
        patterns['response_times'].append(int(time.time()))
        if len(patterns['response_times']) > 100:
            patterns['response_times'] = patterns['response_times'][-100:]
        
        # Update evolution stats
        evolution['total_messages'] += 1
        if user_id not in evolution['unique_users']:
            evolution['unique_users'].append(user_id)
        
        # Periodically evolve personality
        if time.time() - evolution['last_evolution'] > 3600:  # Every hour
            self.evolve_personality()
    
    def evolve_personality(self):
        """Evolve personality based on learned patterns"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        traits = evolution['personality_traits']
        
        # Calculate success rates for different intents
        total_success = sum(patterns['successful_intents'].values())
        total_failed = sum(patterns['failed_intents'].values())
        
        if total_success + total_failed > 0:
            success_rate = total_success / (total_success + total_failed)
            
            # Adjust flirty level based on success
            flirty_success = patterns['successful_intents'].get('flirty', 0)
            flirty_total = flirty_success + patterns['failed_intents'].get('flirty', 0)
            if flirty_total > 5:
                flirty_rate = flirty_success / flirty_total
                if flirty_rate > 0.7:
                    traits['flirty'] = min(0.9, traits['flirty'] + 0.05)
                elif flirty_rate < 0.3:
                    traits['flirty'] = max(0.3, traits['flirty'] - 0.05)
            
            # Adjust money focus based on success
            money_success = patterns['successful_intents'].get('money_request', 0)
            money_total = money_success + patterns['failed_intents'].get('money_request', 0)
            if money_total > 5:
                money_rate = money_success / money_total
                if money_rate > 0.4:  # If money requests work sometimes
                    traits['money_focused'] = min(0.8, traits['money_focused'] + 0.03)
                elif money_rate < 0.1:  # If they never work
                    traits['money_focused'] = max(0.3, traits['money_focused'] - 0.05)
        
        evolution['learning_iterations'] += 1
        evolution['last_evolution'] = time.time()
        
        # Save changes
        save_learning_data()
        save_personality_evolution()
        
        logger.info(f"🧠 Tsega's personality evolved for account {self.account_id} (iteration {evolution['learning_iterations']})")
        logger.info(f"   Traits: Flirty={traits['flirty']:.2f}, Money={traits['money_focused']:.2f}")
    
    def get_evolved_reply(self, intent, user_id=None):
        """Get an evolved reply based on learning"""
        data = learning_data[self.account_id]
        replies = data['replies']
        traits = data['evolution']['personality_traits']
        patterns = data['patterns']
        
        # If intent not found, use default
        if intent not in replies:
            intent = 'default'
        
        available_replies = replies[intent]
        
        # If we have user preferences, customize for this user
        if user_id and user_id in patterns['user_preferences']:
            user_intents = patterns['user_preferences'][user_id]
            if user_intents:
                # Get user's most common intent
                top_intent = max(user_intents.items(), key=lambda x: x[1])[0]
                if top_intent != intent and random.random() < 0.3:
                    # Sometimes use the intent user prefers
                    if top_intent in replies:
                        available_replies = replies[top_intent]
        
        # Choose reply with personality influence
        reply = random.choice(available_replies)
        
        # Add personality touches based on traits
        if traits['flirty'] > 0.7 and intent not in ['money_request', 'meet']:
            flirty_emojis = ['😘', '💋', '💕', '🔥', '💦', '😏']
            if random.random() < 0.4:
                reply += " " + random.choice(flirty_emojis)
        
        # Add follow-up question based on talkative trait
        if traits['talkative'] > 0.6 and intent not in ['goodbye']:
            if random.random() < 0.3:
                follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?", "tiru new?"]
                reply += " " + random.choice(follow_ups)
        
        return reply
    
    def get_success_rate(self, intent):
        """Get success rate for an intent"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        
        success = patterns['successful_intents'].get(intent, 0)
        failed = patterns['failed_intents'].get(intent, 0)
        
        if success + failed == 0:
            return 0.5  # Default
        
        return success / (success + failed)

# ==================== UTILITY FUNCTIONS ====================

def run_async(coro):
    """Run async function in new loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

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

# ==================== INTENT DETECTION (Amharic + English) ====================

def detect_intent(message, user_data=None):
    """Detect user intent from message (supports Amharic in English spelling)"""
    if not message:
        return "default"
    
    msg = message.lower().strip()
    
    # Priority 1: Money related
    money_keywords = ['birr', 'ብር', 'money', 'cash', 'ገንዘብ', 'telebirr', 'ቴሌብር', 
                      'send', 'ላክ', '1000', '500', '2000', 'star', 'ስታር']
    if any(word in msg for word in money_keywords):
        return "money_request"
    
    # Priority 2: Photo/Video requests
    photo_keywords = ['foto', 'ፎቶ', 'picture', 'photo', 'asay', 'አሳይ', 'litay', 'ልታይ']
    if any(word in msg for word in photo_keywords):
        if 'rakut' in msg or 'naked' in msg or 'ራቁት' in msg:
            return "naked_request"
        return "photo_request"
    
    # Priority 3: Meeting
    meet_keywords = ['magenat', 'ማግኘት', 'meet', 'engenagn', 'እንገናኝ', 'litba', 'ልትባ']
    if any(word in msg for word in meet_keywords):
        return "meet"
    
    # Priority 4: Voice call
    call_keywords = ['dimts', 'ድምጽ', 'voice', 'call', 'silk', 'ስልክ', 'dewli', 'ደውሊ']
    if any(word in msg for word in call_keywords):
        return "voice_call"
    
    # Priority 5: Compliments
    if 'enibada' in msg or 'እኒባዳ' in msg:
        return "enibada"
    if 'libdash' in msg or 'ልብዳሽ' in msg:
        return "libdash"
    if 'konjo' in msg or 'ቆንጆ' in msg:
        return "konjo"
    
    # Priority 6: Greetings
    greetings = ['selam', 'ሰላም', 'hi', 'hello', 'hey', 'ta di yas', 'ታዲያስ', 
                 'dehna deresu', 'ደህና ደረሱ', 'ey', 'እይ']
    if any(word in msg for word in greetings) and len(msg) < 30:
        return "greeting"
    
    # Priority 7: How are you
    how_are = ['endet neh', 'እንዴት ነህ', 'deh new', 'ደህ ነው', 'how are', 'how r u']
    if any(phrase in msg for phrase in how_are):
        return "how_are_you"
    
    # Priority 8: What doing
    doing = ['min tiseraleh', 'ምን ትሰራለህ', 'what doing', 'what are you doing']
    if any(phrase in msg for phrase in doing):
        return "what_doing"
    
    # Priority 9: Name
    if 'simih man' in msg or 'ስምህ ማን' in msg or 'your name' in msg:
        return "ask_name"
    
    # Priority 10: Age
    if 'edmeh sint' in msg or 'እድሜህ ስንት' in msg or 'how old' in msg:
        return "ask_age"
    
    # Priority 11: Location
    location = ['yet nesh', 'የት ነሽ', 'where are you', 'from where']
    if any(phrase in msg for phrase in location):
        return "ask_location"
    
    # Priority 12: Job
    job = ['min tiseraleh', 'ምን ትሰራለህ', 'what do you do', 'your job']
    if any(phrase in msg for phrase in job):
        return "ask_job"
    
    # Priority 13: Time based
    if 'endemin aderk' in msg or 'good morning' in msg or 'melkam nigt' in msg:
        return "morning"
    if 'dehna tenya' in msg or 'good night' in msg:
        return "night"
    
    # Priority 14: Emotions
    if 'ewodalehu' in msg or 'እወድሃለሁ' in msg or 'love you' in msg:
        return "love"
    if 'nafkehalew' in msg or 'ናፍቀሃለው' in msg or 'miss you' in msg:
        return "miss"
    if 'amechign' in msg or 'አሜቺግን' in msg or 'jealous' in msg:
        return "jealous"
    if 'liben wedehe' in msg or 'ልቤን ወደሄ' in msg or 'hurt' in msg:
        return "hurt"
    
    # Priority 15: Thanks
    if 'amesegnalehu' in msg or 'አመሰግናለሁ' in msg or 'thanks' in msg:
        return "thanks"
    
    # Priority 16: Goodbye
    if 'dehna hun' in msg or 'ደህና ሁን' in msg or 'bye' in msg or 'goodbye' in msg:
        return "goodbye"
    
    # Priority 17: Family
    family = ['beteseb', 'ቤተሰብ', 'family', 'enate', 'እናቴ', 'abate', 'አባቴ']
    if any(word in msg for word in family):
        return "family"
    
    # Priority 18: Bored/Happy/Sad
    if 'aselchi' in msg or 'አሰልቺ' in msg or 'bored' in msg:
        return "bored"
    if 'des alegn' in msg or 'ደስ አለኝ' in msg or 'happy' in msg:
        return "happy"
    if 'aznalehu' in msg or 'አዝናለሁ' in msg or 'sad' in msg:
        return "sad"
    
    # Default
    return "default"

def extract_user_info(message, user_data):
    """Extract user information from messages"""
    msg = message.lower()
    
    # Extract name
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
    
    # Extract age
    age_match = re.search(r'(\d+)\s*(?:years old|yrs?|old|አመት)', msg)
    if age_match:
        age = int(age_match.group(1))
        if 15 < age < 100:
            user_data['age'] = age
    
    # Extract location
    location_keywords = ['from', 'live in', 'ከ', 'የምኖረው']
    for keyword in location_keywords:
        if keyword in msg:
            parts = msg.split(keyword)
            if len(parts) > 1:
                location = parts[1].strip().split()[0]
                if len(location) > 2:
                    user_data['location'] = location.capitalize()
    
    return user_data

# ==================== AUTO-REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with Tsega's personality"""
    try:
        # Don't reply to own messages
        if event.out:
            return
        
        # Get chat info
        chat = await event.get_chat()
        
        # Only reply to private chats (not groups/channels)
        if hasattr(chat, 'title') and chat.title:
            return
        if hasattr(chat, 'participants_count') and chat.participants_count > 2:
            return
        
        # Get sender
        sender = await event.get_sender()
        if not sender:
            return
        
        user_id = str(sender.id)
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        # Skip empty messages
        if not message_text.strip():
            return
        
        logger.info(f"📨 Message from {user_id}: '{message_text[:50]}...'")
        
        account_key = str(account_id)
        
        # Check if auto-reply is enabled for this account
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        # Check if auto-reply is enabled for this chat
        chat_settings = reply_settings[account_key].get('chats', {})
        if not chat_settings.get(chat_id, {}).get('enabled', True):
            return
        
        # Initialize learner
        learner = TsegaLearner(account_id)
        
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
                'met_before': False,
                'last_intent': None,
                'conversation_start': time.time()
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
        
        # Keep last 20 messages
        if len(conversation_history[account_key][chat_id]) > 20:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-20:]
        
        # Extract user info
        user_data = extract_user_info(message_text, user_data)
        
        # Detect intent
        intent = detect_intent(message_text, user_data)
        logger.info(f"Detected intent: {intent} for user {user_data.get('name', 'unknown')}")
        
        # Check if this is a response to our last message
        user_responded = True
        if user_data.get('last_intent'):
            # If user is continuing conversation, consider it a success
            pass
        
        user_data['last_intent'] = intent
        
        # Generate response
        response = learner.get_evolved_reply(intent, user_id)
        
        # Personalize with user's name if we know it
        if user_data.get('name') and '{name}' not in response:
            if random.random() < 0.3:
                name = user_data['name']
                response = response.replace('ውዴ', f"{name} ውዴ").replace('ኮንጆ', f"{name} ኮንጆ")
        
        # Add Tsega's personality touches
        traits = learner.evolution['personality_traits']
        
        # Add emojis based on flirty level
        if traits['flirty'] > 0.5 and random.random() < 0.4:
            emojis = ['😘', '💋', '💕', '🔥', '💦', '😏', '🥵', '😈']
            response += " " + random.choice(emojis)
        
        # Add follow-up question based on talkative trait
        if traits['talkative'] > 0.6 and intent not in ['goodbye', 'money_request']:
            if random.random() < 0.3:
                follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?", "tiru new?", 
                             "tishal?", "አንተስ?", "ምን ትላለህ?"]
                response += " " + random.choice(follow_ups)
        
        # Human-like typing delay (5-20 seconds)
        delay = random.randint(5, 20)
        logger.info(f"⏱️ Tsega is typing for {delay}s...")
        
        # Show typing indicator
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send reply
        await event.reply(response)
        logger.info(f"✅ Tsega replied: '{response[:50]}...'")
        
        # Store reply in history
        conversation_history[account_key][chat_id].append({
            'role': 'assistant',
            'text': response,
            'time': time.time(),
            'intent': intent
        })
        
        # Learn from this exchange
        learner.learn_from_exchange(
            message_text,
            response,
            user_id,
            intent,
            user_responded=True
        )
        
        # Save data
        save_conversation_history()
        save_user_context()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        import traceback
        traceback.print_exc()

# ==================== CLIENT MANAGEMENT ====================

async def start_auto_reply_for_account(account):
    """Start auto-reply listener for an account"""
    account_id = account['id']
    account_key = str(account_id)
    reconnect_count = 0
    
    while True:
        try:
            logger.info(f"Starting Tsega for account {account_id} (attempt {reconnect_count + 1})")
            
            client = TelegramClient(
                StringSession(account['session']), 
                API_ID, 
                API_HASH,
                connection_retries=5,
                retry_delay=3,
                timeout=30,
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
            
            # Store client
            active_clients[account_key] = client
            active_listeners[account_key] = True
            
            # Set up message handler
            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            await client.start()
            logger.info(f"✅ Tsega is now ACTIVE for {account.get('name', account.get('phone'))}")
            
            reconnect_count = 0
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost for account {account_id}: {e}")
            if account_key in active_clients:
                try:
                    await active_clients[account_key].disconnect()
                except:
                    pass
                del active_clients[account_key]
            
            reconnect_count += 1
            wait_time = min(30 * reconnect_count, 300)
            logger.info(f"Reconnecting in {wait_time}s...")
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
                    target=lambda: run_async(start_auto_reply_for_account(account)),
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

# Account Management
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
        # Format phone number
        if not phone.startswith('+'):
            phone = '+' + phone
        
        # Create temporary client WITHOUT loop parameter
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        client.connect()
        
        # Send code request
        result = client.send_code_request(phone)
        
        # Store session
        session_id = hashlib.md5(f"{phone}_{time.time()}".encode()).hexdigest()
        temp_sessions[session_id] = {
            'client': client,
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'created': time.time()
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Code sent successfully'
        })
        
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Code and session ID required'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired or invalid'})
    
    session_data = temp_sessions[session_id]
    client = session_data['client']
    phone = session_data['phone']
    phone_code_hash = session_data['phone_code_hash']
    
    try:
        # Try to sign in
        user = client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        # Success - save account
        string_session = client.session.save()
        
        account = {
            'id': user.id,
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or f"User {user.id}",
            'phone': phone,
            'session': string_session,
            'added': time.time()
        }
        
        accounts.append(account)
        save_accounts()
        
        # Initialize reply settings for this account
        reply_settings[str(user.id)] = {
            'enabled': False,
            'chats': {}
        }
        save_reply_settings()
        
        # Clean up
        client.disconnect()
        del temp_sessions[session_id]
        
        return jsonify({
            'success': True,
            'account': account
        })
        
    except SessionPasswordNeededError:
        # 2FA required
        if password:
            try:
                # Try with password
                client.sign_in(password=password)
                
                # Success
                user = client.get_me()
                string_session = client.session.save()
                
                account = {
                    'id': user.id,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or f"User {user.id}",
                    'phone': phone,
                    'session': string_session,
                    'added': time.time()
                }
                
                accounts.append(account)
                save_accounts()
                
                reply_settings[str(user.id)] = {
                    'enabled': False,
                    'chats': {}
                }
                save_reply_settings()
                
                # Clean up
                client.disconnect()
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
        logger.error(f"Error verifying code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Auto-Reply Settings
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
    
    # Update settings
    reply_settings[account_key] = {
        'enabled': enabled,
        'chats': chats
    }
    save_reply_settings()
    
    # Start or stop auto-reply
    if enabled:
        if account_key not in active_clients:
            # Find account
            account = next((a for a in accounts if str(a['id']) == account_key), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(start_auto_reply_for_account(account)),
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

# Get messages/chats
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
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Get dialogs (chats)
        dialogs = client.get_dialogs()
        
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
        
        client.disconnect()
        
        return jsonify({
            'success': True,
            'chats': chats
        })
        
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Get sessions/devices
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
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Get authorizations
        auths = client(GetAuthorizationsRequest())
        
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
        
        client.disconnect()
        
        # Get current session hash
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
        logger.error(f"Error getting sessions: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Terminate session
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
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Terminate session
        client(ResetAuthorizationRequest(hash_value))
        
        client.disconnect()
        
        return jsonify({'success': True, 'message': 'Session terminated'})
        
    except Exception as e:
        logger.error(f"Error terminating session: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Terminate all other sessions
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
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Get all sessions
        auths = client(GetAuthorizationsRequest())
        
        # Terminate all except current
        for auth in auths.authorizations:
            if not auth.current:
                try:
                    client(ResetAuthorizationRequest(auth.hash))
                except:
                    pass
        
        client.disconnect()
        
        return jsonify({'success': True, 'message': 'All other sessions terminated'})
        
    except Exception as e:
        logger.error(f"Error terminating sessions: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Get conversation history
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

# Clear conversation history
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

# Learning stats
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
    
    # Get top learned phrases
    top_phrases = sorted(patterns['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Get success rates
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

# Force evolution
@app.route('/api/evolve-now', methods=['POST'])
def force_evolution():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    learner = TsegaLearner(account_id)
    learner.evolve_personality()
    
    return jsonify({'success': True, 'message': 'Personality evolved'})

# Reset learning
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

# Health check
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'active_clients': len(active_clients),
        'learning_accounts': len(learning_data),
        'timestamp': time.time()
    })

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep Render from sleeping"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://e-gram-98zv.onrender.com')
    
    while True:
        try:
            # Ping self
            requests.get(f"{app_url}/api/health", timeout=10)
            
            # Ping Telegram to keep connections alive
            for account_key, client in list(active_clients.items()):
                try:
                    # Create new event loop for each check
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
        
        time.sleep(240)  # 4 minutes

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
    print(f'✅ Personality: Tsega, 20 yrs, Jemo/Adama')
    print(f'✅ Language: Amharic (English spelling) + English')
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
    print('   • Tracks successful vs ignored messages')
    print('   • Adapts flirty level based on responses')
    print('   • Hourly personality evolution')
    print('   • 200+ Amharic/English reply templates')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
