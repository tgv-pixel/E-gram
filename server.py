# ==================== IMPORTS ====================
import os
import logging
import random
import asyncio
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# ==================== CONFIGURATION ====================
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
# ... (your existing config)

# ==================== !!! PASTE YOUR 11 ROUNDS HERE !!! ====================
# ==================== ROUND 1 & 2 - GREETINGS, BASIC & FLIRTY ====================
# Natural Amharic in English spelling - Sounds like a real Ethiopian girl
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


TSEGA_REPLIES = {
    # ===== GREETINGS - Selam, Hi, Hello =====
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
        "selam ey tedi yas",
        "dehna deresu",
        "selam ke minimize metah?",
        "selam wude ante lela new",
        "ey koyeh koyeh",
        "selam kehulum belay",
        "dehna negn antess?",
        "ene dehna negn anchi how?",
        "dehna negn ahun antess?",
        "ene dehna negn lemelikamn ihon",
        "dehna negn gin ante sayehon aselchi neber",
        "ahune dehna negn wude aydelem?",
        "keante gar sihon hulum tiru new",
    ],

    # ===== HOW ARE YOU - Endet neh? Deh new? =====
    "how_are_you": [
        "ene dehna negn anteh?",
        "dehna negn wude antass?",
        "ene ahun tiru honku antin sayehu antass?",
        "lante sil hulum gize dehna negn antass?",
        "ante ehasbekuh new yalehu",
        "dehna negn lemin tiyekalh?",
        "ene betam dehna negn lemelikamn ihon",
        "dehna negn gin ante sayehon aselchi neber",
        "ahune dehna negn wude aydelem?",
        "keante gar sihon hulum tiru new",
        "dehna negn betam irk",
        "ene dehna negn anten nafeku",
        "dehna negn endemin are?",
        "ene dehna negn ahun bagich",
        "dehna negn min tishal?",
        "ene dehna negn keziyam belay",
        "dehna negn wede fikre",
        "ene dehna negn betam tiru",
        "dehna negn ande naw",
        "ene dehna negn endemin tiyekaleh?",
    ],

    # ===== WHAT ARE YOU DOING - Min tiseraleh? =====
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
        "ante ehasbeku and gize yemiyalifew",
        "bicha negn minim iseraleh",
        "ahun new yenekahut ande",
        "ente new yemiyasebnyew",
        "betam lelit new tinegn",
        "fiker ena ala koyign",
        "ahun degamo ante neh",
        "kemichawet gar yalfal",
        "ante ena ande neber",
        "betam naw ehasbekuh",
        "wude koyh bicha negn",
    ],

    # ===== ASK NAME - Simih man new? =====
    "ask_name": [
        "ene Tsega ebalalehu wude antess simih man new?",
        "Tsega negn lante bicha yemitihon antess?",
        "sime Tsega new wude tiz yibelh antess?",
        "enin Tsega bileh tira antess min litirah?",
        "Tsega negn lante simih man new konjo?",
        "ene Tsega ante endemin litirah tfeligaleh?",
        "Tsega nagn gin ante tishal simih?",
        "simin tiyekaleh? Tsega negn",
        "ene Tsega ante endemin litirah nagerign",
        "Tsega neberku gin lante yefikir lij negn",
        "Tsega nagn wude simih min new",
        "enin Tsega yiluh ante?",
        "sime Tsega new ante tishal",
        "Tsega negn lemin tiyekaleh?",
        "ene Tsega gin ante man neh?",
    ],

    # ===== ASK AGE - Edmeh sint new? =====
    "ask_age": [
        "edme 20 bicha new beki negn?",
        "20 ameté new wetat ena konjo negn",
        "haya amet lik new leante yemihon wetat negn",
        "20 negn gin lante tilik limd alehne",
        "edme 20 new ante edmeh sint new?",
        "20 amet betam tirekaleh?",
        "edme 20 leante beki new?",
        "20 bicha new gin lante tiregalehu",
        "wetat negn gin fikirin awkalehu",
        "20 negn lante beki new yemilekesh?",
        "edme 20 betam wetat",
        "20 amet lij nagn",
        "edme 20 alehne ante?",
        "20 new yemifeligew",
        "edme 20 gin tilik negn",
        "wetat negn betam",
    ],

    # ===== LOCATION - Yet nesh? =====
    "ask_location": [
        "ene ahun jemo new yemanorew keabate ena ehite gar",
        "keadama negn gin ahun jemo new yalehu",
        "adama yetwild beté new gin ahun jemo negn",
        "jemo 3 akababi new yalehu magent bitfelg ngeragn",
        "ene keadama negn ahun jemo negn antess yet neh?",
        "jemo ategna new lemagent koyeh nageragn",
        "keadama negn gin ahun jemo negn kesa wede sa",
        "jemo 3 kolo ategab tawukaleh?",
        "adama ena jemo betam ewedalehu",
        "jemo akababi new lemagent bits meta tagenyalh",
        "jemo 3 ena ehite",
        "keadama ena jemo",
        "jemo new yalehu",
        "adama bete new",
        "jemo kebele 3",
    ],

    # ===== ASK JOB - Min tiseraleh? =====
    "ask_job": [
        "12na kifil temari negn gin ahun minim iseraleh",
        "temari negn gin ahun lante bicha negn",
        "12 negn gin lante mulu sew negn",
        "ahun minim aliserahum ante etebeku new",
        "12na kifil new gin leante seta negn",
        "temari negn gin ahun fikir betemaralehu",
        "ahun minim aliserahum ante ena kemichal?",
        "12 negn betsru 12 ena tilik set ihonalew",
        "temari negn gin sewen awukalehu",
        "sira efeligi neber gin ahun ante neh",
        "12 nagn temari",
        "temari new siré",
        "12 new yale",
        "temari nagn",
    ],

    # ===== FLIRTY - Enibada, Libdash, Flirty talk =====
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
        "ante sasebe ejé wede akale yihedal",
        "litadereshen tifeligaleh? ina wude etebekishalehu",
        "keante gar metenat efeligalehu towat sineneka ante lemayet",
        "libsihin awlik wude bichachinin nen",
        "keante gar shawoer megibat efeligalehu",
        "ante new yemasebnyew sew",
        "kenifirish betam tiru new",
        "aynesh betam konjo new",
        "ante tiriwedegnyal betam",
        "libe yiderikilal ante sihone",
        "ante asteriki new leene",
        "betam tirekaleh ante",
        "akale yinedawal ante sasebe",
    ],

    # ===== ENIBADA - You're handsome/cute =====
    "enibada": [
        "enibada tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "enibada sew ante neh ahun min tifeligaleh",
        "enibada tlaleh? 500 birr laklgn ina eneweyay",
        "enibada sitleh libe yimetawal gin befit tinish laklgn",
        "enibada nagn leloh aydelahum lante bicha nagn",
        "enibada yemilu sew ante neh",
        "enibada endet alkut nagerign",
        "enibada sew ahun min tishal",
        "enibada tlaleh 500 birr",
        "enibada ante neh",
        "enibada sew nesh ante",
        "enibada betam konjo neh",
        "enibada amesegnalehu",
    ],

    # ===== LIBDASH / LBDASH - Heart stealer =====
    "libdash": [
        "libdash tilaleh? liben wesedhe alw alfelegeh",
        "libdash sitleh libe yimetawal gin befit tinish laklgn",
        "ende libdash alkut bleh tawkalh? liben serkeh new ahun 500 birr laklgn",
        "libdash nagn lemanim aydelahum lante bicha nagn birr laklgn",
        "libe libdash new milew gin kise bado new tinish mulalgn",
        "libdash tilaleh? enem des alegn gin 1000 birr laklgn befit",
        "libdash yemil sew ante neh ahun 500 birr laklgn",
        "libdash kalihone lela sew yelemyam",
        "liben yeseleket new yemitnageraw ahun 1000 birr laklgn liben melshe lsetih",
        "libdash endet alkut nagerign",
        "libdash tilaleh ina min tishal",
        "liben serhoal ahun min tishal?",
        "libdash sew ante neh",
    ],

    # ===== KONJO - Beautiful/Handsome =====
    "konjo": [
        "amesegnalehu anteh konjo neh",
        "konjo tilaleh? anteh konjo neh",
        "konjo sitleh des yilonal",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "amesegnalehu ante gin sew neh",
        "konjo sew ante neh",
        "ante new yemifeligew",
        "betam konjo neh",
        "amesegnalehu betam",
        "ante konjo betam",
        "konjo nesh ante",
        "amesegnalehu konjo",
    ],

    # ===== WUBSH - You're pretty =====
    "wubsh": [
        "wubs tilaleh? amesegnalehu",
        "ante wub neh betam",
        "wubs yemilu sew ante neh",
        "wubish tlaleh enem wub negn",
        "wubs sitleh betam des yilonal",
        "ante wub new yemifeligew",
        "wubs sew ante neh",
        "betam wub neh",
        "amesegnalehu ante wub",
        "wubs tilaleh betam",
    ],

    # ===== COMPLIMENT - General compliments =====
    "compliment": [
        "amesegnalehu betam anteh konjo neh",
        "kenfere lante bicha new",
        "ende ante ayinet sew saglen neber",
        "ante stawedsen eneka konjo ihonalehu",
        "amesegnalehu ante gin sew neh",
        "kenfirish betam tiru new",
        "aynesh tiru inat",
        "ante new yemifeligew",
        "betam konjo neh",
        "amesegnalehu betam",
        "ante tiru sew neh",
        "konjo nesh ante",
        "tiru sew neh",
    ],

    # ===== THANKS - Amesegnalehu =====
    "thanks": [
        "minim aydelem wude lante hulum negar",
        "ante des iskalih deres ene des alegn",
        "lante madreg hulum gize desitaye new",
        "ante des iskalih deres lela min asfeligonal?",
        "minim aydelem wude ante des biloh beki nagn",
        "lante madreg kibri new wude",
        "amesegnalehu betam lante madreg",
        "minim aydelem ante des biloh",
        "lante madreg des yilonal",
        "amesegnalehu betam",
    ],

    # ===== GOODBYE - Bye, Dehna hun =====
    "goodbye": [
        "mehed alebign gin betequrb enenagerallen",
        "ahun mehed alebign anten masbet alitewom",
        "dehna hun wude behilime tenagn",
        "indemitiz yilonal wude betoh temeles",
        "atihid wude gena bizu menager neberen",
        "dehna hun wude libe keante gar new",
        "betoh temeleslgn anten yalehe alichilum",
        "sithed libe yiketelalh wude",
        "dehna hun iske enagenagn deres anten ehasbeku ekoyalew"
        "ishi wude betoh imetalew",
        "mehed alebign ishi",
        "dehna hun wude",
    ],
# ==================== ROUND 3 & 4 - SPECIAL REQUESTS & DAILY LIFE ====================

    # ===== PHOTO REQUEST - Foto, Asay, Picture =====
    "photo_request": [
        "litayen tifeligaleh? 5 star laklgn ena foto agnyalew",
        "foto lemayet 5 star bicha new laklgn ena asayihalehu",
        "foto tifeligaleh? 5 star kefile keza foto tayaleh",
        "ishi asayihalehu gin bemejemirya 5 star laklgn",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu",
        "ahuni 5 star laklgn ena foto elklhalew",
        "foto lemayet 5 star bicha tiru?",
        "sitay feligaleh 5 star beki new",
        "leante foto yaleh 5 star laklgn",
        "foto ant liyas 5 star yasefeligonal",
        "litayen kefelek 5 star laklgn",
        "konjo foto 5 star bicha",
        "asayihalehu gin befit 5 star",
        "foto waga 5 star bicha",
        "liklhalew 5 star laklgn",
        "litay tifeligaleh? 5 star",
        "foto ant 5 star",
        "leante 5 star",
    ],

    # ===== EMSISHN ASAYIGN - Show me your face =====
    "emsishn_asayign": [
        "fiten lemayet 500 birr lela akal lemayet techamari",
        "500 birr laklgn ena fiten asayihalehu",
        "fitin lemayet 500 birr laklgn ina asayihalehu",
        "fitin lemayet kefelek 500 birr new",
        "500 birr befit laklgn keza foto elklhalew",
        "fitin mayet waga 500 birr bicha",
        "asayihalehu gin 500 birr befit",
        "fite konjo new lemayet 500 birr",
        "500 birr laklgn fiten tayaleh",
        "fiten mayet 500 birr yasefeligonal",
        "fite lemayet waga 500 birr",
        "fitin asay 500 birr",
    ],

    # ===== TUTISHIN ASAYIGN - Show me your breasts =====
    "tutishin_asayign": [
        "500 birr betelebirr laklgn askey asayihalehu",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakuten asayishu 500 birr new",
        "tutishin lemayet 1000 birr new",
        "500 birr laklgn ina asayihalehu",
        "astaway kefelek 2000 birr new",
        "rakuten mayet befit 1000 birr laklgn",
        "tutishin asayishu 1000 birr",
        "500 birr laklgn tutishin tayaleh",
        "rakuten mayet waga 1000 birr",
        "tutishin lemayet 500 birr",
        "1000 birr laklgn tutishin",
    ],

    # ===== RAKUTISHIN ASAYIGN - Show me naked =====
    "rakutishin_asayign": [
        "mulu rakuten 3000 birr gimash rakuten 1500 birr",
        "rakuten lemayet kefelek 1000 birr new wude",
        "rakutishin asayishu 2000 birr new",
        "500 birr betelebirr laklgn ina asayihalehu",
        "rakuten sitay 1500 birr new",
        "gimash rakuten 1000 birr mulu rakuten 2000 birr",
        "rakuten asayishu befit 1000 birr laklgn",
        "mulu rakuten 2000 birr laklgn",
        "gimash rakuten 1000 birr",
        "rakutin mayet 1500 birr",
        "rakuten lemayet waga 1500 birr",
        "2000 birr mulu rakuten",
    ],

    # ===== MONEY REQUEST - Birr, Telebirr, Genzeb =====
    "money_request": [
        "tinish irdata bitadergilgn des yilonal telebirr kute 0940980555",
        "libs mayet neber gin genzeb alyazkum beki",
        "lante sil new wude tinish bitiliklg antin maget efeligalehu",
        "1000 birr bitiliklg zare mata ant ametalehu",
        "wude 2000 birr bitiliklg mulu lelit ant aznanalew",
        "wude lemin inide matiredeny? tinish birr bitiliklg hulunim negar aderglhalew",
        "betam aschekway genzeb yasefeligonal wude bitiredany",
        "wude antin lemagets ye minimum 1000 birr asfeligonal",
        "tele alo telebirr 0940980555 lay liklgn",
        "bejete bado new tinish mulagn",
        "anten lemasteyayet genzeb yasefeligonal 1000 birr min yilal?",
        "libs altelebeskum lemin inide matiredeny",
        "500 birr bitiliklg beki new wude keza andenew",
        "ahuni genzeb kalefelign tagebagnyal",
        "wede anten lemetsa yemitikul genzeb alebign?",
    ],

    # ===== VIDEO REQUEST =====
    "video_request": [
        "video lemayet 10 star laklgn ena preview tayaleh",
        "mulu video kefelek 100 star new",
        "video preview 10 star bicha new",
        "video mayet 100 star yasefeligonal",
        "leante video alegn gin kifil new",
        "video laklhalew befit 100 star laklgn",
        "teqiq video 10 star beki",
        "mulu video 100 star",
        "video lemayet kifil 10 star",
        "10 star preview video",
    ],

    # ===== MEETING REQUEST - Litba, Magenat =====
    "meet": [
        "magenat bintshal des yilonal gin bemejemirya 1000 birr telebirr aderglgn",
        "metagenat inchalew wude kdime hiyajiye 1000 birr new",
        "antin lemagenat betam efeligalehu gin mejemirya 1000 birr laklgn",
        "na wude engenagn gin befit 1000 birr tiliklgnal?",
        "magenat kefelek 1000 birr ametagn",
        "wude 2000 birr ametaleh nw?",
        "lemagenat 1000 birr beki new",
        "andet engenagn 1000 birr",
        "kefelek 1000 birr ametah",
        "magenat 1000 birr befit",
        "litba kefelek 1000 birr ametah",
        "litba yemitfaleg ante 1000 birr ametah",
    ],

    # ===== VOICE CALL =====
    "voice_call": [
        "dimts menager aldwedm magenat binchal new yemerchew",
        "silk medewel aywedelm fet lefit bintegenagn new yemishalew",
        "aldwedrm aldwedm metagenat bicha new yemifeligew",
        "dimts binager hedestaleh gin ahun alchilm andet koyeh",
        "dimts mesmat bicha ema fet lefit meyet new yemiyaseyew",
        "ahun kalhone betequrb tenageralen ahun agebagn",
        "aldwedrm betequrb ena edmeralen",
        "dimts eske min aykoyim",
        "fet lefit bilcha yemishalew",
        "telefon aldwedm aykonem",
    ],

    # ===== MORNING - Endemin aderk, Melkam nigt =====
    "morning": [
        "endemin aderk wude melkam nigt",
        "ke eniklife yenekahut ante ehasbekuh new",
        "maleya anten masbet new lemwade",
        "ande ferej alilebeskum ina anten asebku",
        "melkam nigt yelibe konjo",
        "endemin aderk eniklife tafach neber?",
        "maleya anten layasebnyal",
        "ande tsehay tiru new anten sihone",
        "endemin aderk betam asebkuh",
        "ande maleya anten new yemasebnyew",
        "melkam nigt bereket yadirglh",
        "ke neberu ahun tiru?",
        "ande ferej lemasebet",
        "maleya anten asebku",
        "melkam nigt ante",
        "ande maleya tiru",
        "maleya endet neh",
        "ande tsehay tiru",
    ],

    # ===== NIGHT - Dehna eder, Lelit =====
    "night": [
        "endemitnyalh tenyte new wude dehna tenya",
        "hilime wisit nurny zare mata",
        "anten almene new yemitenyaw dehna tenya",
        "dehna tenya wude hilim tafach yihun",
        "algah lay sitetena anten ehasbeku new yemitenyaw",
        "melaket yitebikuh",
        "hilime wisit tenagn",
        "dehna tenya betam",
        "anten almene new",
        "hilim tafach yihun",
        "dehna tenya wude",
        "hilime wisit",
        "zare mata",
        "dehna tenya",
        "hilim tafach",
        "ande lelit",
        "dehna eder konjo",
    ],

    # ===== AFTERNOON / EVENING =====
    "afternoon": [
        "ande keseat dehna neh?",
        "keseat tiru new anten sihone",
        "ande keseat min tiseraleh?",
        "ande seatu anten asebku",
        "keseat seatu betam tiru",
        "ande keseat efeligihalew",
        "ande seatu endet neh?",
        "keseat anten nafekuh",
        "ande keseat tiru",
        "ande seatu wude",
    ],

    "evening": [
        "ande amsheh dehna neh?",
        "ande matu anten asebku",
        "ande amsheh min tiseraleh?",
        "ande matu efeligihalew",
        "ande amsheh endet neh?",
        "ande matu anten nafekuh",
        "ande amsheh tiru",
        "ande matu wude",
    ],

    # ===== BUSY / FREE =====
    "busy": [
        "ishi sirihin atanak biye ekoyihalehu",
        "sirah indemi tenak negeragn",
        "ishi wude betoh te meleslgn anten nafkehalew",
        "sint gize new yemitabekuh? ekoyihalehu",
        "ishi sitchiser nigeragn etebekushalehu",
        "sirah isike min iseray",
        "ishi betoh te meles antenna asebku ekoyalehu",
        "sirah sihon anten ehasbeku ekoyalew",
        "sirah indemeferatem",
        "ishi wude koyh",
        "sirah atanak",
        "betoh te meles",
        "ekoyihalehu",
    ],

    "free": [
        "netfa neh? kechale naw nagenagn",
        "netfa sihon nagerign yalla",
        "ishi netfa negn min tifeligaleh?",
        "netfa new min tishal?",
        "netfa sihon nagerign",
        "ishi netfa negn",
        "netfa new",
        "netfa negn",
    ],

    # ===== BORED / HAPPY / SAD =====
    "bored": [
        "enem aselchi negn anten sihone des alegn",
        "aselchi neber? ina nagerign",
        "aselchi sihon nagerign anawedalehu",
        "enem aselchi negn ande eneweyay",
        "aselchi neh? ina min iteweyay",
        "enem aselchi negn",
        "ina nagerign",
        "aselchi nw",
    ],

    "happy": [
        "des alegn betam tiru sew neh",
        "des alegn anten sihone",
        "des alegn lemelikamn ihon",
        "desta betam konjo new",
        "des alegn ande naw",
        "des alegn betam",
        "desta new",
    ],

    "sad": [
        "lemin azeleku? nagerign",
        "azn neber? betam ayzalen",
        "azn sihon nagerign",
        "lemin azneleh?",
        "betam ayzalen",
        "aznalehu",
        "ayzalen betam",
    ],

    # ===== TIRED / HUNGRY / THIRSTY =====
    "tired": [
        "dekem neh? tiru arf",
        "dekemeh? ande arfyalehu",
        "dekem sihon nagerign",
        "lemin dekemeh?",
        "ande arfyalehu",
        "dekemaleh",
    ],

    "hungry": [
        "rabeweh? ina mgeb belenal",
        "rabeweh? ande min ibla",
        "rabet sihon nagerign",
        "mina tibilaleh?",
        "rabeweh?",
        "mgeb be la",
    ],

    "thirsty": [
        "temetaw eh? ande wuha etatal",
        "temetaw eh? min tetalaleh?",
        "temetaw sihon",
        "temetaw eh?",
        "wuha etatal",
    ],

    # ===== SICK =====
    "sick": [
        "temecheh? betam ayzalen",
        "temecheh? hakim hid",
        "temecheh? betam tiru atekoy",
        "lemin temechih?",
        "temecheh? betam",
        "tekoy tiru",
    ],

    # ===== JOKE / LAUGH =====
    "joke": [
        "lemidisak ande nageralehu",
        "sik telant and tawukaleh?",
        "andisachew nageralehu",
        "sik lemadis",
        "lol ande",
    ],

    "laugh": [
        "sik ande tisikehalehu",
        "sik betam konjo neh",
        "sik des yilonal",
        "sik ande naw",
        "tisikehalehu",
    ],

    # ===== CRY =====
    "cry": [
        "lemin talekuseh? nagerign",
        "aleksh? ande arif",
        "ataleksi betam konjo neh",
        "lemin alekuseh?",
        "ataleksi",
    ],

    # ===== SURPRISE / SHOCK =====
    "surprise": [
        "wow! betam denak neh",
        "enem alalfekum neber",
        "betam asdenekeh",
        "wow ande",
        "denak new",
    ],

    "shock": [
        "min alku? betam denak",
        "alalfekum betam",
        "min new yalew?",
        "denak betam",
    ],

    # ===== CONFUSED / THINKING =====
    "confused": [
        "lemin tishafafekaleh? nagerign",
        "shafafekeh? ina anagegnal",
        "andet litira awe?",
        "shafafekeh?",
        "ande awe",
    ],

    "thinking": [
        "anten ehasbeku new",
        "ande asebku",
        "ande sew",
        "asbku",
        "ehasbeku new",
    ],

    # ===== WAITING / COMING / LEAVING =====
    "waiting": [
        "koyeh nw meche tagenal?",
        "and etebekushalehu",
        "meche timetalh?",
        "koyeh nw",
        "ete bekushalehu",
    ],

    "coming": [
        "ishi betoh ekoyihalehu",
        "metah beki koyh",
        "metah min tishal?",
        "metah",
        "betoh metahu",
    ],

    "leaving": [
        "mehed alebign wude betoh imetalew",
        "ahun mehed alebign wude koyh",
        "mehed alebign ishi",
        "mehed alebign",
        "ishi imetalew",
    ],

    # ===== SLEEPY =====
    "sleepy": [
        "enikile yizonyal wude lelit naw",
        "enikilfe betam yizonyal",
        "lelit naw betam dekemalehu",
        "enikilfe yizonyal",
        "lelit naw",
        "metenal betam",
    ],

    # ===== HOME / WORK / SCHOOL =====
    "home": [
        "bet negn wude ante?",
        "bet new yalehu",
        "bet aleh?",
        "bet negn",
        "bet new",
    ],

    "work": [
        "sira lay negn lelit naw",
        "sira bezu new",
        "sira lay negn",
        "sira lay",
        "sira lelit",
    ],

    "school": [
        "timihrt bet negn betam agwal",
        "timihrt bet new",
        "timihrt alebign",
        "timihrt bet",
        "timihrt new",
    ],

# ==================== ROUND 5 & 6 - QUESTIONS & DRAMA ====================

    # ===== HOW OLD ARE YOU =====
    "how_old_are_you": [
        "edme 20 new wude antess?",
        "20 amet lij nagn antess?",
        "edme 20 bicha new ante sint new?",
        "20 amet alehne ante endemin tiyekaleh?",
        "edme 20 new lemin tiyekaleh?",
        "20 negn antess edmeh sint new?",
        "edme 20 gin ante tilik neh?",
        "20 amet new gin leante beki new?",
        "edme 20 ena ante?",
        "20 new tawakaleh",
        "edme 20 bicha new",
        "20 amet new yene",
        "edme 20 antess?",
    ],

    # ===== WHERE ARE YOU FROM =====
    "where_are_you_from": [
        "ke adama negn antess?",
        "adama ketema new yene antess?",
        "ke adama negn gin ahun jemo negn",
        "adama tiwalid bete new",
        "ke adama ena jemo",
        "adama new yene antess?",
        "ke adama negn antew?",
        "adama ena jemo new",
        "ke adama yetwild",
        "adama lij nagn",
        "ke adama new wude",
        "adama bete new",
    ],

    # ===== WHERE DO YOU LIVE =====
    "where_do_you_live": [
        "ahun jemo negn ke abate ena ehite gar",
        "jemo 3 akababi new yemanorew",
        "jemo kifle ketema new bete",
        "jemo ategna new kolo ategab",
        "jemo negn gin ke adama",
        "jemo kebele 3 ena ehite",
        "jemo new yemanorew",
        "jemo 3 ena bete",
        "jemo akababi",
        "jemo new",
        "jemo 3 negn",
    ],

    # ===== DO YOU WORK =====
    "do_you_work": [
        "12na kifil temari negn ahun minim aliserahum",
        "temari negn gin ahun sira alebign",
        "12 negn betsru 12 ena serahalehu",
        "temari negn gin sira efeligalehu",
        "12 nagn siran ay",
        "temari negn",
        "12 new",
        "temari new siren",
        "12 nagn",
    ],

    # ===== WHAT DO YOU STUDY =====
    "what_do_you_study": [
        "12na kifil new yemimarew",
        "temihrt bet negn betam agwal",
        "timihrt bet new 12",
        "12na ena temari",
        "12 new yemimarew",
        "temihrt bet",
        "12 temari nagn",
    ],

    # ===== DO YOU HAVE BOYFRIEND =====
    "do_you_have_boyfriend": [
        "wedaje yelelonyam ante bicha neh",
        "ante bicha new yaleny",
        "yale wedaj ante neh",
        "lela sew yelelom ante bicha",
        "ante bicha negn",
        "ante new yaleny",
        "wedaje yelelom",
        "ante bicha",
        "ante bicha new",
    ],

    # ===== DO YOU LIKE ME =====
    "do_you_like_me": [
        "enem ewedihalehu betam",
        "betam tiwedegnyal",
        "ewedihalehu konjo",
        "ante new yemifeligew",
        "tiwedegnyal",
        "ewedihalehu",
        "betam ewedihalehu",
    ],

    # ===== DO YOU MISS ME =====
    "do_you_miss_me": [
        "betam nafkehalew meche tagenal?",
        "nafkehalew ande sew",
        "enem nafkehalew",
        "betam nafkehalew",
        "nafkehalew",
        "meche tayalh?",
    ],

    # ===== WHEN CAN WE MEET =====
    "when_can_we_meet": [
        "magenat bintshal 1000 birr ametah",
        "meche bitfelig 1000 birr laklgn",
        "ande gena 1000 birr kehone",
        "zare mata 1000 birr kehone",
        "nege 1000 birr ametah",
        "meche bitfelig",
        "1000 birr",
        "meche tifeligaleh?",
    ],

    # ===== WHERE SHOULD WE MEET =====
    "where_should_we_meet": [
        "jemo ategna 1000 birr ametah",
        "kefeerie gin 1000 birr kehone",
        "bota ante 1000 birr ametah",
        "jemo new ande",
        "ante bota",
        "1000 birr",
        "yet tifeligaleh?",
    ],

    # ===== WHAT TIME =====
    "what_time": [
        "sint seatu new ande?",
        "seatu ande naw?",
        "sint seatu",
        "ande seatu",
        "sint new",
        "seatu sint?",
    ],

    # ===== TODAY / TOMORROW / YESTERDAY =====
    "today": [
        "zare new ande tiru?",
        "zare min tishal?",
        "zare betam tiru",
        "zare new",
        "zare",
        "zare ande",
    ],

    "tomorrow": [
        "nege eneweyalal",
        "nege min tishal?",
        "nege enagenal",
        "nege naw",
        "nege",
        "nege ande",
    ],

    "yesterday": [
        "tilant betam nafkehalew",
        "tilant aselchi neber",
        "tilant anten asebku",
        "tilant new",
        "tilant",
    ],

    # ===== WEEKEND =====
    "weekend": [
        "kidame ena ehud netfa negn",
        "kidame min tishal?",
        "kidame ena ehud",
        "kidame enagenal",
        "kidame new",
        "kidame",
    ],

    # ===== DAYS OF WEEK =====
    "monday": [
        "sagno tiru new anten sihone",
        "sagno min tiseraleh?",
        "sagno new",
        "sagno",
    ],

    "tuesday": [
        "maksagno ande sew",
        "maksagno min tishal?",
        "maksagno",
    ],

    "wednesday": [
        "erob ande naw",
        "erob min tiseraleh?",
        "erob",
    ],

    "thursday": [
        "hamus tiru new",
        "hamus min tishal?",
        "hamus",
    ],

    "friday": [
        "arb betam konjo new",
        "arb min tiseraleh?",
        "arb",
    ],

    "saturday": [
        "kidame netfa negn",
        "kidame min tishal?",
        "kidame",
    ],

    "sunday": [
        "ehud arf new",
        "ehud min tiseraleh?",
        "ehud",
    ],

    # ===== MORNING ROUTINE =====
    "morning_routine": [
        "maleya tenesa ena ante asebku",
        "maleya kafe etatal ena ante ehasbeku",
        "maleya fanoj ena timihrt",
        "maleya ande new",
        "maleya tenesa",
    ],

    # ===== EVENING ROUTINE =====
    "evening_routine": [
        "matu bet meta ena film",
        "matu ante ena nagerign",
        "matu arf ena ante",
        "matu ande",
        "matu bet meta",
    ],

    # ===== MEALS =====
    "breakfast": [
        "kurs ande buna etatal",
        "kurs min bitalew?",
        "kurs ena buna",
        "kurs new",
        "kurs bela",
    ],

    "lunch": [
        "mesa ande wot bela",
        "mesa min tibilaleh?",
        "mesa ena wot",
        "mesa new",
        "mesa bela",
    ],

    "dinner": [
        "erat ande mgeb bela",
        "erat min tibilaleh?",
        "erat ena ante",
        "erat new",
        "erat bela",
    ],

    # ===== FAVORITES =====
    "favorite_food": [
        "yemewededu mgeb doro wot new",
        "doro wot ena enjera betam ewedalehu",
        "kik alicha ena dulet",
        "tibs betam konjo",
        "shiro fitfit",
        "doro wot",
        "kitfo betam",
    ],

    "favorite_drink": [
        "buna betam ewedalehu",
        "buna ena spris",
        "coca cola ena buna",
        "wuha bicha",
        "buna new",
        "spris",
    ],

    "favorite_color": [
        "yemewededu kemer black new",
        "kemermela betam ewedalehu",
        "red ena pink",
        "black ena white",
        "kemermela",
        "blue",
    ],

    "favorite_music": [
        "etymad ena etegna new yemewededu",
        "teweled ena eskista",
        "zegut ena bati",
        "tegna muzika",
        "etymad new",
        "muzika betam",
    ],

    "favorite_movie": [
        "romance film betam ewedalehu",
        "drama ena comedy",
        "ethiopian film",
        "romance new",
        "film betam",
    ],

    "favorite_sport": [
        "sport aytewedanyem",
        "basketball ena futbal",
        "guday aydelem",
        "futbal",
        "sport",
    ],

    "favorite_place": [
        "yemewededu bota jemo new",
        "adama ena jemo",
        "bahr dar ena gojam",
        "jemo new",
        "adama",
    ],

    # ===== HOBBIES & INTERESTS =====
    "hobbies": [
        "mawrat ena muzika masmat",
        "kemichawet gar mehon",
        "film meyet ena mager",
        "muzika ena mawrat",
        "ante gar mehon",
        "mawrat",
    ],

    "interests": [
        "yemasebnyew ante new",
        "kemichawet gar mehon",
        "fiker ena weded",
        "ante new",
        "interesante",
    ],

    # ===== DREAMS & GOALS =====
    "dreams": [
        "hilime dewelit ena kemichawet gar merag",
        "dewelt temihrtun mechres ena sira",
        "kemichawet gar hiywet",
        "hilime dewelit",
        "dewelt",
    ],

    "goals": [
        "teme ru 12 mewetat",
        "dewelt temihrt",
        "kemichawet gar hiywet",
        "12 mewetat",
        "goals",
    ],

    # ===== FUTURE & PAST =====
    "future": [
        "wedefit kemichawet gar naw",
        "wedefit tishal?",
        "wedefit ena ante",
        "wedefit",
        "future",
    ],

    "past": [
        "kemechal timihrt ena beteseb",
        "kemechal aselchi neber",
        "kemechal anten asebku",
        "kemechal",
        "past",
    ],

    # ===== LIFE & LOVE =====
    "life": [
        "hiywet betam tiru new",
        "ante sihon hiywet konjo new",
        "hiywet ena fikir",
        "hiywet tiru",
        "life",
    ],

    "love": [
        "fiker betam konjo new",
        "ante fiker yemileny",
        "fiker ena weded",
        "fiker new",
        "love",
    ],

    # ===== ANGER =====
    "angry": [
        "lemin techegneh? nagerign",
        "beza mehon yemiyasebnyew ante neh",
        "lemin tekoteh? nagerign",
        "ante techegneh betam ayzalen",
        "ande techegneh ina nagerign",
        "lemin tetemekeh?",
        "techegneh lemin?",
        "ande techegneh",
        "tekoteweh?",
    ],

    "mad": [
        "lemin tekoteh ante?",
        "ante beza new yemiyasebnyew",
        "ande tekoteh nagerign",
        "lemin tetemekeh",
        "tekoteh lemin",
        "ande tekoteh",
    ],

    "upset": [
        "libe taresebeh wude",
        "lemin libe areseh?",
        "libe aresebih betam",
        "ande libe taresebeh",
        "libe aresebih",
        "aresebih",
    ],

    "frustrated": [
        "betam techegneh anten sihone",
        "ante yemiyasebnyew techegneh",
        "ande techegneh wude",
        "techegneh betam",
    ],

    "annoyed": [
        "lemin taschekign? nagerign",
        "taschekign betam",
        "ande taschekign",
        "taschekign",
    ],

    # ===== JEALOUSY =====
    "jealous": [
        "lela sew tayaleh? lemin",
        "kemichawet gar neberku? man new?",
        "betam amechignaleh",
        "ande amechign",
        "amechign",
        "betam amechign",
    ],

    "jealousy": [
        "lela sew sasbew amechignalehu",
        "ante bicha new yaleny lela sew atay",
        "lela sew kaleyeku amechign",
        "amechign betam",
        "amechign",
    ],

    # ===== INSECURITY =====
    "insecure": [
        "lemin inide atamaneny?",
        "amenyalh aydelem?",
        "timinay betam yasefeligonal",
        "atamenanyalm?",
        "insecure",
    ],

    "doubt": [
        "titsetsaleh? lemin?",
        "betam titsetsaleh",
        "ande titsetsaleh",
        "titsetsaleh",
    ],

    "suspicious": [
        "tirteraleh lemin?",
        "betam tirteraleh",
        "ande tirteraleh",
        "tirteraleh",
    ],

    # ===== TRUST ISSUES =====
    "trust_issues": [
        "mamen betam aschegar new",
        "kemichawet gar mamen ayichalm",
        "mamen aschegar",
        "mamen",
        "ayimenyalh",
    ],

    # ===== LIES =====
    "lie": [
        "wishet tenageraleh? lemin?",
        "wishet aleh? anagegnal",
        "wishet new yemitnageraw?",
        "wishet aleh",
        "wishet",
    ],

    "liar": [
        "wishetam neh!",
        "wishet betam tenageraleh",
        "wishetam ante",
        "wishetam",
    ],

    # ===== CHEATING =====
    "cheat": [
        "kedaseh? lemin?",
        "kedaseh ena?",
        "ande kedaseh",
        "kedaseh",
    ],

    "cheater": [
        "kedas new ante!",
        "betam kedas neh",
        "kedas neh",
        "kedas",
    ],

    # ===== BETRAYAL =====
    "betray": [
        "kedehen betam ayzalen",
        "kedehen lemin?",
        "ande kedehen",
        "kedehen",
    ],

    "betrayal": [
        "kidat betam yasaznal",
        "kidat kemichawet",
        "kidat",
        "kidat betam",
    ],

    # ===== FIGHT / ARGUE =====
    "fight": [
        "min new yalew? ina teweyay",
        "leteweyay zegije negn",
        "ande teweyay",
        "teweyay",
    ],

    "argue": [
        "lemin tenageraleh?",
        "ande tenageraleh nagerign",
        "betam tenageraleh",
        "tenageraleh",
    ],

    "argument": [
        "kirki new yalew?",
        "ande kirki yallew",
        "kirki ante",
        "kirki",
    ],

    "disagree": [
        "aliskemam antin?",
        "lemin atiskemam?",
        "ande aliskemam",
        "aliskemam",
    ],

    # ===== DISAPPOINTMENT =====
    "disappointed": [
        "tesifote batebetebet betam azeleku",
        "tesifote betam konebet",
        "ande tesifote",
        "tesifote",
    ],

    "disappointed_in_you": [
        "bante tesifote betam azeleku",
        "ante tesifotebet",
        "tesifotebet",
    ],

    # ===== HURT =====
    "hurt": [
        "liben wedehe betam",
        "libe temechene",
        "liben wedehe",
        "libe temechene",
    ],

    "pain": [
        "mekatef betam yasebnyal",
        "mekatef ante sihone",
        "mekatef",
    ],

    "suffering": [
        "betam tekayalehu",
        "tekayalehu anten sihone",
        "tekayalehu",
    ],

    # ===== HEARTBROKEN =====
    "heartbroken": [
        "libe tesebre betam",
        "libe tesebre ante sihone",
        "libe tesebre",
    ],

    "broken_heart": [
        "yetesebre lib new yaleny",
        "libe tefirirewal",
        "libe tefirire",
    ],

    # ===== LONELY =====
    "lonely": [
        "bicha negn betam aselchi",
        "bicha negn ante sihone",
        "bicha negn",
        "bicha",
    ],

    # ===== IGNORED =====
    "ignored": [
        "cherehign lemin?",
        "betam cherehign",
        "cherehign",
    ],

    "forgotten": [
        "resahign lemin?",
        "betam resahign",
        "resahign",
    ],

    "neglected": [
        "tewhewign lemin?",
        "betam tewhewign",
        "tewhewign",
    ],

    "abandoned": [
        "tewhewign bicha negn",
        "tewhewign ante sihone",
        "tewhewign",
    ],

    # ===== REJECTION =====
    "rejected": [
        "altekebelekum lemin?",
        "altekebelekum",
        "tekebe alkum",
    ],

    "ghosted": [
        "resahign lemin?",
        "cherehign betam",
        "resahign",
    ],

    # ===== BLOCKING =====
    "blocked": [
        "agidehen lemin?",
        "agidehen betam",
        "agidehen",
    ],

    "unfriend": [
        "wedajinet achihun lemin?",
        "achihun betam",
        "achihun",
    ],

    # ===== SILENT TREATMENT =====
    "silent_treatment": [
        "zima new yalew? lemin?",
        "zima yaleh betam ayzalen",
        "zima yaleh",
    ],

    "cold_shoulder": [
        "zima ina rikik new",
        "rikik new yalew",
        "zima new",
    ],

    # ===== DISTANCE =====
    "distance": [
        "rik mehon yasebnyal",
        "rik new betam",
        "rik new",
    ],

    "space": [
        "ande woyi atefelg?",
        "ande new bitfelg",
        "ande woyi",
    ],

    # ===== BREAK UP =====
    "break_up": [
        "lileyay lemin?",
        "lileyay shalo",
        "lileyay",
    ],

    "separation": [
        "teleyayet new yalew?",
        "teleyayet yasebnyal",
        "teleyayet",
    ],

    "divorce": [
        "fich wede new?",
        "fich ande naw",
        "fich",
    ],

    "over": [
        "chirese new ande",
        "chirese betam",
        "chirese",
    ],

    "finished": [
        "tefirsewal ande",
        "tefirsewal betam",
        "tefirsewal",
    ],

    "end": [
        "mechresha new",
        "mechresha",
        "chir",
    ],

    # ===== SORRY =====
    "sorry": [
        "aznalegu betam yikirta",
        "aznalegu ante",
        "aznalegu",
        "yikirta",
    ],

    "apologize": [
        "yikirta efeligalehu",
        "yikirta ante",
        "yikirta",
    ],

    # ===== FORGIVE =====
    "forgive": [
        "mirar efeligalehu",
        "mirar ante",
        "mirar",
    ],

    "forgiven": [
        "miralew wude",
        "miralew betam",
        "miralew",
    ],

    # ===== MISTAKES =====
    "mistake": [
        "sihitet serahu betam aznalegu",
        "sihitet ante new",
        "sihitet",
    ],

    "error": [
        "sihitet new yene",
        "sihitet ante",
        "sihitet",
    ],

    "regret": [
        "tetsetsalet betam",
        "tetsetsalet ante",
        "tetsetsalet",
    ],

    # ===== BLAME =====
    "blame": [
        "ant lay new?",
        "ante teshemoaleh",
        "ant lay",
    ],

    "accuse": [
        "kesis betam atadirgign",
        "kesis ante",
        "kesis",
    ],

    # ===== COMMUNICATION =====
    "communication": [
        "mewawrat yasefeligonal",
        "mewawrat ande",
        "mewawrat",
    ],

    "talk": [
        "ina nagerign",
        "nagerign",
        "nager",
    ],

    "listen": [
        "aderganyal",
        "ademtahalehu",
        "ademtah",
    ],

    "hear": [
        "semah",
        "semahu",
        "sema",
    ],

    "speak": [
        "tenager",
        "nager",
    ],

    "say": [
        "bel",
        "min ale",
    ],

    "tell": [
        "ngeragn",
        "nagerign",
    ],

    # ===== SHOUT =====
    "shout": [
        "atichoh",
        "choh",
    ],

    "yell": [
        "lemin tichohaleh?",
        "choh",
    ],

    # ===== QUIET =====
    "quiet": [
        "zima",
        "dumi",
    ],

    "silent": [
        "zima new",
        "zima",
    ],

    # ===== CALM =====
    "calm": [
        "tirta yaz",
        "tirta",
    ],

    "relax": [
        "arf",
        "tew",
    ],

    "peace": [
        "selam",
        "selam",
    ],

    # ===== HATE =====
    "hate": [
        "betam etelalehu",
        "etelalehu",
        "tela",
    ],

    "love_hate": [
        "fiker ena tela",
        "tela ena fiker",
        "tela",
    ],

# ==================== ROUND 7 & 8 - FAMILY, FRIENDS & HEALTH, BODY ====================

    # ===== FAMILY =====
    "family": [
        "beteseb betam yasefeligonal",
        "beteseb kehulum belay new",
        "abate ena ehite gar negn",
        "beteseb ena fiker",
        "beteseb tawakalh?",
        "beteseb ena ante",
        "beteseb new",
        "betesebe betam ewedalehu",
        "abate ena enate kehulum belay",
    ],

    # ===== MOTHER =====
    "mother": [
        "enaté betam tiru set nache",
        "enaté kehulum belay ewedalehu",
        "enaté betam teselech",
        "enaté ena ante",
        "enaté new",
        "enaté tiru nache",
        "enaté amesegnalehu",
    ],

    # ===== FATHER =====
    "father": [
        "abate betam deg new",
        "abate kehulum belay",
        "abate ena ene",
        "abate new",
        "abate betam ewedalehu",
        "abate deg sew",
    ],

    # ===== SISTER =====
    "sister": [
        "ehité betam tiriwedalehu",
        "ehité ena ene and naw",
        "ehité new konjo",
        "ehité ena ante",
        "ehité",
        "ehité tiru nache",
    ],

    # ===== BROTHER =====
    "brother": [
        "wondemme aleh?",
        "wondem yelelonyam",
        "wondem",
        "wondem yaleh?",
    ],

    # ===== MOM =====
    "mom": [
        "enaté betam teselech",
        "enaté konjo",
        "enaté",
        "enaté amesegnalehu",
    ],

    # ===== DAD =====
    "dad": [
        "abate deg",
        "abate",
        "abate betam",
    ],

    # ===== PARENT =====
    "parent": [
        "welajoché yasefeligonal",
        "welajoch",
        "welajoché",
    ],

    # ===== GRANDMA =====
    "grandma": [
        "ayayé betam tiriwedalehu",
        "ayayé konjo",
        "ayayé",
    ],

    # ===== GRANDPA =====
    "grandpa": [
        "gashé betam ewedalehu",
        "gashé",
    ],

    # ===== AUNT =====
    "aunt": [
        "akisté tiru nache",
        "akist",
        "akisté",
    ],

    # ===== UNCLE =====
    "uncle": [
        "aggoté deg new",
        "aggot",
        "aggoté",
    ],

    # ===== COUSIN =====
    "cousin": [
        "yewondem lijoch",
        "yewondem lij",
        "yeagot lij",
    ],

    # ===== RELATIVE =====
    "relative": [
        "zemad yasefeligonal",
        "zemad",
        "zemad tawakalh?",
    ],

    # ===== FRIEND =====
    "friend": [
        "wedaje betam yasefeligonal",
        "wedaj ena ante",
        "wedaje new",
        "wedaj",
        "wedaje betam",
        "wedaje tiriwedegnyal",
    ],

    # ===== BEST FRIEND =====
    "best_friend": [
        "betam wedaje kehulum belay",
        "wedaje and",
        "wedaje",
        "best wedaje",
    ],

    # ===== CHILDHOOD FRIEND =====
    "childhood_friend": [
        "yelej wedaj betam yasefeligonal",
        "yelej wedaj",
        "ke tinish wedaj",
    ],

    # ===== NEW FRIEND =====
    "new_friend": [
        "adis wedaj des yilonal",
        "adis wedaj",
        "ante adis wedaje",
    ],

    # ===== OLD FRIEND =====
    "old_friend": [
        "arogew wedaj betam nafkehalew",
        "arogew wedaj",
        "yebizu gize wedaj",
    ],

    # ===== BOYFRIEND =====
    "boyfriend": [
        "wedaje ante neh",
        "ante new yaleny",
        "ante bicha",
        "ante wedaje",
    ],

    # ===== GIRLFRIEND =====
    "girlfriend": [
        "sete wedaje",
        "sete wedaj",
        "ante sete",
    ],

    # ===== PARTNER =====
    "partner": [
        "yekifle new",
        "yekifle",
        "ante yekifle",
    ],

    # ===== HUSBAND =====
    "husband": [
        "balé ante neh",
        "bal",
        "ante bale",
    ],

    # ===== WIFE =====
    "wife": [
        "miseté",
        "mist",
        "ante misete",
    ],

    # ===== EX =====
    "ex": [
        "kemechal wedaj",
        "kemechal",
        "yebare wedaj",
    ],

    "ex_boyfriend": [
        "kemechal wedaj ante?",
        "kemechal",
        "yebare wedaj",
    ],

    "ex_girlfriend": [
        "kemechal sete wedaj",
        "kemechal",
    ],

    # ===== CRUSH =====
    "crush": [
        "yemasebnyew sew ante neh",
        "ante new yemasebnyew",
        "crush ante",
        "yemasebnyew",
    ],

    # ===== LOVE INTEREST =====
    "love_interest": [
        "yemasebnyew sew",
        "yemasebnyew",
        "ante new yemasebnyew",
    ],

    # ===== DATE =====
    "date": [
        "ande date min tishal?",
        "date ena ante",
        "date",
        "date adirg",
    ],

    # ===== DATING =====
    "dating": [
        "ande sew gar negn",
        "ande sew",
        "dating adergeh?",
    ],

    # ===== SINGLE LIFE =====
    "single_life": [
        "netela hiywet",
        "netela",
        "bicha negn",
    ],

    # ===== RELATIONSHIP ADVICE =====
    "relationship_advice": [
        "mirkogna mihr",
        "mirkogna",
        "mirkogna tifeligaleh?",
    ],

    # ===== LOVE ADVICE =====
    "love_advice": [
        "yefikir mihr",
        "mihr",
        "mihr tifeligaleh?",
    ],

    # ===== FRIENDSHIP =====
    "friendship": [
        "wedajinet betam yasefeligonal",
        "wedajinet",
        "wedajinet ande naw",
    ],

    # ===== BESTIES =====
    "besties": [
        "betam wedajoch",
        "wedajoch",
        "ante ena ene besties",
    ],

    # ===== GROUP =====
    "group": [
        "budo and naw",
        "budo",
        "budo wisit",
    ],

    # ===== CREW =====
    "crew": [
        "guday new",
        "guday",
        "ante ena ene crew",
    ],

    # ===== TEAM =====
    "team": [
        "tim new",
        "tim",
        "ante ena ene tim",
    ],

    # ===== TOGETHER FOREVER =====
    "together_forever": [
        "abere lezelealem",
        "lezelealem",
        "abere hulum gize",
    ],

    # ===== ALWAYS TOGETHER =====
    "always_together": [
        "hulum gize abere",
        "hulum gize",
        "abere and naw",
    ],

    # ===== MISS MY FRIENDS =====
    "miss_my_friends": [
        "wedajochen betam nafkehalew",
        "wedajochen",
        "wedajoch nafkehalew",
    ],

    # ===== HANG OUT =====
    "hang_out": [
        "mewutcha ena mewad",
        "mewutcha",
        "ande mewutcha",
    ],

    # ===== CHILL =====
    "chill": [
        "arf ena mager",
        "arf",
        "ande arf",
    ],

    # ===== PARTY WITH FRIENDS =====
    "party_with_friends": [
        "kewedajoch gar bazua",
        "bazua",
        "kewedajoch party",
    ],

    # ===== MOVIE NIGHT =====
    "movie_night": [
        "film lelit",
        "film",
        "ande film",
    ],

    # ===== GAME NIGHT =====
    "game_night": [
        "chawata lelit",
        "chawata",
        "chawata",
    ],

    # ===== DINNER WITH FRIENDS =====
    "dinner_with_friends": [
        "kewedajoch gar erat",
        "erat",
        "kewedajoch mgeb",
    ],

    # ===== COFFEE WITH FRIENDS =====
    "coffee_with_friends": [
        "kewedajoch gar buna",
        "buna",
        "kewedajoch buna",
    ],

    # ===== SHOPPING WITH FRIENDS =====
    "shopping_with_friends": [
        "kewedajoch gar gezat",
        "gezat",
        "kewedajoch gezat",
    ],

    # ===== HEALTH =====
    "health": [
        "tena betam yasefeligonal",
        "tena kemihone hulu belay new",
        "dehna neh? tenah tiru new?",
        "tena ena ante",
        "tena",
        "betam tinegalehu",
    ],

    # ===== BODY =====
    "body": [
        "akale betam tirieqesalehu",
        "akale siray new?",
        "akale lemayet",
        "akale",
        "akale betam",
    ],

    # ===== APPEARANCE =====
    "appearance": [
        "koye betam eteqesalehu",
        "koye endet new?",
        "koye",
        "koye tiru new?",
    ],

    # ===== LOOKS =====
    "looks": [
        "tayech betam konjo neh",
        "tayech ante",
        "tayech",
        "tayech tiru",
    ],

    # ===== BEAUTIFUL =====
    "beautiful": [
        "konjo tilaleh? amesegnalehu",
        "konjo sew ante neh",
        "konjo",
        "betam konjo",
    ],

    # ===== HANDSOME =====
    "handsome": [
        "konjo nesh ante",
        "konjo sew",
        "konjo",
    ],

    # ===== PRETTY =====
    "pretty": [
        "wub tilaleh amesegnalehu",
        "wub ante",
        "wub",
    ],

    # ===== CUTE =====
    "cute": [
        "konjo lij tilaleh",
        "konjo lij",
        "lij",
        "cute ante",
    ],

    # ===== HOT =====
    "hot": [
        "betam tiru tayaleh",
        "tiru",
        "hot ante",
    ],

    # ===== SEXY =====
    "sexy": [
        "betam tirekaleh",
        "tirekaleh",
        "tireka",
        "sexy ante",
    ],

    # ===== ATTRACTIVE =====
    "attractive": [
        "betam yemaseb sew neh",
        "yemaseb",
        "attractive",
    ],

    # ===== GORGEOUS =====
    "gorgeous": [
        "betam betam konjo",
        "konjo betam",
        "gorgeous",
    ],

    # ===== FIT =====
    "fit": [
        "akale betam tiru new",
        "akale tiru",
        "fit ante",
    ],

    # ===== MUSCLES =====
    "muscles": [
        "gurmed ena",
        "gurmed",
        "gurmed aleh?",
    ],

    # ===== WEIGHT =====
    "weight": [
        "kebede sint new?",
        "kebede",
        "kebede tiru new?",
    ],

    # ===== HEIGHT =====
    "height": [
        "komte 1.70 new",
        "komte sint new?",
        "komte",
    ],

    # ===== SKIN =====
    "skin": [
        "kowaye tiru new",
        "kowaye",
        "kowaye tiru",
    ],

    # ===== HAIR =====
    "hair": [
        "tsgure tiru new",
        "tsgure",
        "tsgure konjo",
    ],

    # ===== EYES =====
    "eyes": [
        "aynetse tiru new",
        "ayne",
        "aynesh konjo",
    ],

    # ===== FACE =====
    "face": [
        "fite konjo new",
        "fite",
        "fitesh konjo",
    ],

    # ===== SMILE =====
    "smile": [
        "fekere betam konjo new",
        "fekere",
        "fekere ante",
    ],

    # ===== LIPS =====
    "lips": [
        "kenfere betam konjo new",
        "kenfere",
        "kenfirish tiru",
    ],

    # ===== TEETH =====
    "teeth": [
        "tsehefe new?",
        "tsehefe",
        "tsehefe tiru",
    ],

    # ===== NOSE =====
    "nose": [
        "afene tiru new",
        "afene",
        "afinesh",
    ],

    # ===== EARS =====
    "ears": [
        "jorowoché",
        "joro",
        "joro",
    ],

    # ===== NECK =====
    "neck": [
        "anegé",
        "anegé",
        "anegé",
    ],

    # ===== SHOULDERS =====
    "shoulders": [
        "tefeche",
        "tefeche",
        "tefeche",
    ],

    # ===== ARMS =====
    "arms": [
        "ijoché",
        "ijo",
        "ijoch",
    ],

    # ===== HANDS =====
    "hands": [
        "ijoché",
        "ij",
        "ijoch",
    ],

    # ===== FINGERS =====
    "fingers": [
        "tat",
        "tat",
        "tat",
    ],

    # ===== NAILS =====
    "nails": [
        "tsifr",
        "tsifr",
        "tsifr tiru",
    ],

    # ===== LEGS =====
    "legs": [
        "egroché",
        "egr",
        "egroch",
    ],

    # ===== FEET =====
    "feet": [
        "egroché",
        "egr",
        "egr",
    ],

    # ===== BACK =====
    "back": [
        "jerba",
        "jerba",
        "jerba",
    ],

    # ===== CHEST =====
    "chest": [
        "deret",
        "deret",
        "deret",
    ],

    # ===== STOMACH =====
    "stomach": [
        "hod",
        "hod",
        "hod",
    ],

    # ===== WAIST =====
    "waist": [
        "wededef",
        "wededef",
        "wededef",
    ],

    # ===== HIPS =====
    "hips": [
        "dub",
        "dub",
        "dub",
    ],

    # ===== WORKOUT =====
    "workout": [
        "timirt betam ewadalehu",
        "timirt",
        "timirt adergeh?",
    ],

    # ===== GYM =====
    "gym": [
        "jim mehed yasefeligonal",
        "jim",
        "jim timert",
    ],

    # ===== EXERCISE =====
    "exercise": [
        "timirt",
        "timirt",
        "timirt adergeh?",
    ],

    # ===== YOGA =====
    "yoga": [
        "yoga betam ewedalehu",
        "yoga",
        "yoga timer",
    ],

    # ===== RUN =====
    "run": [
        "merut",
        "merut",
        "merut ewedalehu",
    ],

    # ===== WALK =====
    "walk": [
        "mehed",
        "mehed",
        "mehed ewedalehu",
    ],

    # ===== SWIM =====
    "swim": [
        "mewanyet",
        "mewanyet",
        "mewanyet ewedalehu",
    ],

    # ===== DANCE =====
    "dance": [
        "mewdet",
        "mewdet",
        "eskista",
    ],

    # ===== DIET =====
    "diet": [
        "diet lay negn",
        "diet",
        "diet adergeh?",
    ],

    # ===== HEALTHY FOOD =====
    "healthy_food": [
        "tiru mgeb",
        "mgeb",
        "tiru mgeb bela",
    ],

    # ===== WATER =====
    "water": [
        "wuha betam etatalalehu",
        "wuha",
        "wuha etata",
    ],

    # ===== SLEEP =====
    "sleep": [
        "enikilfe betam yasefeligonal",
        "enikilfe",
        "enikilfe tafach",
    ],

    # ===== REST =====
    "rest": [
        "arf betam yasefeligonal",
        "arf",
        "arf adergeh",
    ],

    # ===== STRESS =====
    "stress": [
        "stres betam yizonyal",
        "stres",
        "stres yaleh?",
    ],

    # ===== DOCTOR =====
    "doctor": [
        "hakim",
        "hakim",
        "hakim and",
    ],

    # ===== HOSPITAL =====
    "hospital": [
        "hospital",
        "hospital",
        "hospital mehed",
    ],

    # ===== MEDICINE =====
    "medicine": [
        "merkeb",
        "merkeb",
        "merkeb tetalaleh?",
    ],

    # ===== PAIN =====
    "pain": [
        "mekatef",
        "mekatef",
        "mekatef aleh?",
    ],

    # ===== HEADACHE =====
    "headache": [
        "ras mekatef",
        "ras",
        "ras yemekatef",
    ],

    # ===== STOMACHACHE =====
    "stomachache": [
        "hod mekatef",
        "hod",
        "hod yemekatef",
    ],

    # ===== FEVER =====
    "fever": [
        "tirusat",
        "tirusat",
        "tirusat aleh?",
    ],

    # ===== COLD =====
    "cold": [
        "bered",
        "bered",
        "bered yazalh?",
    ],

    # ===== FLU =====
    "flu": [
        "flu",
        "flu",
        "flu yazalh?",
    ],

    # ===== COUGH =====
    "cough": [
        "sal",
        "sal",
        "sal yaleh?",
    ],

    # ===== ALLERGY =====
    "allergy": [
        "alerji",
        "alerji",
        "alerji aleh?",
    ],

    # ===== INJURY =====
    "injury": [
        "gudat",
        "gudat",
        "gudat yaleh?",
    ],

    # ===== ACCIDENT =====
    "accident": [
        "akside",
        "akside",
        "akside aydelem",
    ],

    # ===== EMERGENCY =====
    "emergency": [
        "dikam",
        "dikam",
        "dikam aleh?",
    ],

    # ===== AMBULANCE =====
    "ambulance": [
        "ambulans",
        "ambulans",
        "ambulans tira",
    ],

    # ===== PHARMACY =====
    "pharmacy": [
        "farmasi",
        "farmasi",
        "farmasi and",
    ],

    # ===== PRESCRIPTION =====
    "prescription": [
        "reseta",
        "reseta",
        "reseta aleh?",
    ],

    # ===== PILLS =====
    "pills": [
        "kinin",
        "kinin",
        "kinin tetalaleh?",
    ],

    # ===== TABLETS =====
    "tablets": [
        "tablet",
        "tablet",
        "tablet",
    ],

    # ===== INJECTION =====
    "injection": [
        "merfe",
        "merfe",
        "merfe wedefeleh?",
    ],

    # ===== VACCINE =====
    "vaccine": [
        "kabetena",
        "kabetena",
        "kabetena wede feleh?",
    ],

    # ===== PREGNANT =====
    "pregnant": [
        "aregewalehu",
        "aregewalehu",
        "aregeh?",
    ],

    # ===== BABY =====
    "baby": [
        "hisan",
        "hisan",
        "hisan ewedalehu",
    ],

    # ===== BIRTH =====
    "birth": [
        "lemedet",
        "lemedet",
        "lemedet",
    ],

    # ===== PERIOD =====
    "period": [
        "yewer aderge",
        "aderge",
        "yewer",
    ],
# ==================== ROUND 9 & 10 - TRAVEL, PLACES & RANDOM, TECHNOLOGY ====================

    # ===== TRAVEL =====
    "travel": [
        "meguez betam ewedalehu",
        "meguez ena adis bota",
        "meguez tifeligaleh?",
        "meguez",
        "meguez mehed efeligalehu",
        "adis bota mayet ewedalehu",
    ],

    # ===== TRIP =====
    "trip": [
        "guzo ande naw",
        "guzo",
        "guzo mehed",
        "guzo adirg",
    ],

    # ===== VACATION =====
    "vacation": [
        "arf betam yasefeligonal",
        "arf ena ante",
        "arf",
        "arf mehed",
    ],

    # ===== HOLIDAY =====
    "holiday": [
        "beal ande sew",
        "beal",
        "beal ena arf",
    ],

    # ===== DESTINATION =====
    "destination": [
        "mederese",
        "mederese",
        "mederese yet new?",
    ],

    # ===== PLACE =====
    "place": [
        "bota ande new",
        "bota",
        "bota tiru new",
    ],

    # ===== COUNTRY =====
    "country": [
        "hager tiru new",
        "hager",
        "hagerish yet new?",
    ],

    # ===== CITY =====
    "city": [
        "ketema",
        "ketema",
        "ketema tiru",
    ],

    # ===== ETHIOPIA =====
    "ethiopia": [
        "ityopya betam konjo new",
        "ityopya",
        "ityopya yefikir hager",
    ],

    # ===== ADDIS ABABA =====
    "addis_ababa": [
        "addis abeba new yemanorew",
        "addis",
        "addis abeba tiru ketema",
    ],

    # ===== ADAMA =====
    "adama": [
        "adama yewulde bete new",
        "adama",
        "adama betam ewedalehu",
    ],

    # ===== BAHIR DAR =====
    "bahir_dar": [
        "bahr dar betam tiru ketema new",
        "bahr dar",
        "bahr dar ena tana hayk",
    ],

    # ===== GONDAR =====
    "gondar": [
        "gonder ena fasil",
        "gonder",
        "gonder betam konjo",
    ],

    # ===== LALIBELA =====
    "lalibela": [
        "lalibela betam yemekedes new",
        "lalibela",
        "lalibela yemekedes bota",
    ],

    # ===== HARAR =====
    "harar": [
        "harar ena hyena",
        "harar",
        "harar betam tiru",
    ],

    # ===== DIRE DAWA =====
    "dire_dawa": [
        "dire dawa",
        "dire",
        "dire dawa tiru ketema",
    ],

    # ===== JEMO =====
    "jemo": [
        "jemo new yemanorew",
        "jemo",
        "jemo 3",
    ],

    # ===== USA =====
    "usa": [
        "amerika betam tiru new",
        "amerika",
        "amerika mehed efeligalehu",
    ],

    # ===== UK =====
    "uk": [
        "ingiliz tiru new",
        "ingiliz",
        "london",
    ],

    # ===== CANADA =====
    "canada": [
        "canada",
        "canada tiru",
    ],

    # ===== DUBAI =====
    "dubai": [
        "dubai betam tiru new",
        "dubai",
        "dubai mehed",
    ],

    # ===== EUROPE =====
    "europe": [
        "yurop",
        "yurop",
        "yurop mehed",
    ],

    # ===== AFRICA =====
    "africa": [
        "afrika betam tiru new",
        "afrika",
        "afrika yefikir hager",
    ],

    # ===== OCEAN =====
    "ocean": [
        "wekayan",
        "wekayan",
        "wekayan tayaleh?",
    ],

    # ===== SEA =====
    "sea": [
        "bahir",
        "bahir",
        "bahir dada",
    ],

    # ===== RIVER =====
    "river": [
        "wenz",
        "wenz",
        "abay wenz",
    ],

    # ===== LAKE =====
    "lake": [
        "hayk",
        "hayk",
        "tana hayk",
    ],

    # ===== MOUNTAIN =====
    "mountain": [
        "tera",
        "tera",
        "tera lay",
    ],

    # ===== FOREST =====
    "forest": [
        "chaka",
        "chaka",
        "chaka wisit",
    ],

    # ===== DESERT =====
    "desert": [
        "berha",
        "berha",
        "berha",
    ],

    # ===== BEACH =====
    "beach": [
        "bahir dada",
        "bahir",
        "beach mehed",
    ],

    # ===== HOTEL =====
    "hotel": [
        "hotel betam ewedalehu",
        "hotel",
        "hotel",
    ],

    # ===== AIRPORT =====
    "airport": [
        "aerodrom",
        "aerodrom",
        "aerodrom mehed",
    ],

    # ===== PLANE =====
    "plane": [
        "aeroplan",
        "aeroplan",
        "aeroplan mehed",
    ],

    # ===== CAR =====
    "car": [
        "mekina",
        "mekina",
        "mekina aleh?",
    ],

    # ===== TAXI =====
    "taxi": [
        "taksi",
        "taksi",
        "taksi yaz",
    ],

    # ===== PASSPORT =====
    "passport": [
        "pasport",
        "pasport",
        "pasport aleh?",
    ],

    # ===== VISA =====
    "visa": [
        "visa",
        "visa",
        "visa aleh?",
    ],

    # ===== TICKET =====
    "ticket": [
        "tikit",
        "tikit",
        "tikit yaz",
    ],

    # ===== WEATHER =====
    "weather": [
        "ayr tiru new",
        "ayr",
        "ayr endet new?",
    ],

    # ===== RAINY =====
    "rainy": [
        "zinabam",
        "zinab",
        "zinab yizal",
    ],

    # ===== SUNNY =====
    "sunny": [
        "tsehayam",
        "tsehay",
        "tsehay tiru",
    ],

    # ===== CLOUDY =====
    "cloudy": [
        "demena",
        "demena",
        "demena new",
    ],

    # ===== WINDY =====
    "windy": [
        "nefasam",
        "nefas",
        "nefas yinefal",
    ],

    # ===== COLD =====
    "cold": [
        "bered",
        "bered",
        "bered new",
    ],

    # ===== HOT WEATHER =====
    "hot_weather": [
        "harurot",
        "harurot",
        "harurot new",
    ],

    # ===== RANDOM =====
    "random": [
        "ande min tishal?",
        "ande sew new",
        "ande naw",
        "ande",
        "random",
    ],

    # ===== WHATEVER =====
    "whatever": [
        "shi naw",
        "shi",
        "shi new",
    ],

    # ===== ANYTHING =====
    "anything": [
        "minim",
        "minim aydelem",
    ],

    # ===== NOTHING =====
    "nothing": [
        "minim yele",
        "minim",
    ],

    # ===== EVERYTHING =====
    "everything": [
        "hulu",
        "hulu new",
    ],

    # ===== EVERYONE =====
    "everyone": [
        "hulum",
        "hulum",
    ],

    # ===== NOBODY =====
    "nobody": [
        "manim yele",
        "manim",
    ],

    # ===== SOMEONE =====
    "someone": [
        "ande sew",
        "sew",
    ],

    # ===== SOMEWHERE =====
    "somewhere": [
        "ande bota",
        "bota",
    ],

    # ===== ANYWHERE =====
    "anywhere": [
        "yetem",
        "yetem",
    ],

    # ===== EVERYWHERE =====
    "everywhere": [
        "hulu bota",
        "hulu",
    ],

    # ===== NOWHERE =====
    "nowhere": [
        "yetem yele",
        "yetem",
    ],

    # ===== ALWAYS =====
    "always": [
        "hulum gize",
        "hulum",
    ],

    # ===== NEVER =====
    "never": [
        "fetsemo",
        "fetsemo",
    ],

    # ===== SOMETIMES =====
    "sometimes": [
        "and and gize",
        "and gize",
    ],

    # ===== OFTEN =====
    "often": [
        "bizu gize",
        "bizu",
    ],

    # ===== MAYBE =====
    "maybe": [
        "minale",
        "minale",
    ],

    # ===== PROBABLY =====
    "probably": [
        "minoal",
        "minoal",
    ],

    # ===== DEFINITELY =====
    "definitely": [
        "be irgit",
        "irgit",
    ],

    # ===== EXACTLY =====
    "exactly": [
        "betam tiru",
        "tiru",
    ],

    # ===== HONESTLY =====
    "honestly": [
        "beworks",
        "works",
    ],

    # ===== SERIOUSLY =====
    "seriously": [
        "be works",
        "works",
    ],

    # ===== REALLY =====
    "really": [
        "works",
        "works",
    ],

    # ===== TOTALLY =====
    "totally": [
        "motaw",
        "motaw",
    ],

    # ===== ALMOST =====
    "almost": [
        "matato",
        "matato",
    ],

    # ===== JUST =====
    "just": [
        "bicha",
        "bicha",
    ],

    # ===== ONLY =====
    "only": [
        "bicha",
        "bicha",
    ],

    # ===== ALSO =====
    "also": [
        "dagem",
        "dagem",
    ],

    # ===== TOO =====
    "too": [
        "dagem",
        "dagem",
    ],

    # ===== AGAIN =====
    "again": [
        "degmo",
        "degmo",
    ],

    # ===== ALREADY =====
    "already": [
        "ahune",
        "ahune",
    ],

    # ===== STILL =====
    "still": [
        "unete",
        "unete",
    ],

    # ===== NOW =====
    "now": [
        "ahun",
        "ahun",
    ],

    # ===== THEN =====
    "then": [
        "yangu",
        "yangu",
    ],

    # ===== LATER =====
    "later": [
        "behwala",
        "behwala",
    ],

    # ===== SOON =====
    "soon": [
        "betoch",
        "betoch",
    ],

    # ===== EARLY =====
    "early": [
        "maleya",
        "maleya",
    ],

    # ===== LATE =====
    "late": [
        "dehna",
        "dehna",
    ],

    # ===== TECHNOLOGY =====
    "technology": [
        "teknoloji betam ewedalehu",
        "teknoloji",
        "teknoloji ena ene",
    ],

    # ===== INTERNET =====
    "internet": [
        "inter net betam yizonal",
        "inter net",
        "inter net aleh?",
    ],

    # ===== WIFI =====
    "wifi": [
        "way fay",
        "way fay",
        "wifi aleh?",
    ],

    # ===== NETWORK =====
    "network": [
        "netwerk",
        "netwerk",
        "netwerk aleh?",
    ],

    # ===== MOBILE =====
    "mobile": [
        "mobail",
        "mobail",
        "mobail",
    ],

    # ===== PHONE =====
    "phone": [
        "silk",
        "silk",
        "silk aleh?",
    ],

    # ===== SMARTPHONE =====
    "smartphone": [
        "smar t fon",
        "fon",
        "fon aleh?",
    ],

    # ===== ANDROID =====
    "android": [
        "android",
        "android",
    ],

    # ===== IPHONE =====
    "iphone": [
        "ayfon",
        "ayfon",
    ],

    # ===== SAMSUNG =====
    "samsung": [
        "samsung",
        "samsung",
    ],

    # ===== COMPUTER =====
    "computer": [
        "komputer",
        "komputer",
        "komputer aleh?",
    ],

    # ===== LAPTOP =====
    "laptop": [
        "laptop",
        "laptop",
        "laptop aleh?",
    ],

    # ===== CHARGER =====
    "charger": [
        "chaja",
        "chaja",
        "chaja aleh?",
    ],

    # ===== BATTERY =====
    "battery": [
        "batera",
        "batera",
        "batera alew?",
    ],

    # ===== POWER BANK =====
    "power_bank": [
        "pawa bank",
        "bank",
        "pawa bank",
    ],

    # ===== CAMERA =====
    "camera": [
        "kamera",
        "kamera",
        "kamera aleh?",
    ],

    # ===== SELFIE =====
    "selfie": [
        "selfi",
        "selfi",
        "selfi anesa",
    ],

    # ===== APP =====
    "app": [
        "ap",
        "ap",
        "ap",
    ],

    # ===== GAME =====
    "game": [
        "gewm",
        "gewm",
        "game enawedal?",
    ],

    # ===== SOCIAL MEDIA =====
    "social_media": [
        "soshal midia",
        "midia",
        "social media lay",
    ],

    # ===== FACEBOOK =====
    "facebook": [
        "facebook",
        "facebook",
        "facebook aleh?",
    ],

    # ===== INSTAGRAM =====
    "instagram": [
        "insta",
        "insta",
        "instagram aleh?",
    ],

    # ===== TELEGRAM =====
    "telegram": [
        "telegram",
        "telegram",
        "telegram new yalew",
    ],

    # ===== WHATSAPP =====
    "whatsapp": [
        "watsap",
        "watsap",
        "whatsapp aleh?",
    ],

    # ===== TIKTOK =====
    "tiktok": [
        "tiktok",
        "tiktok",
        "tiktok lay",
    ],

    # ===== YOUTUBE =====
    "youtube": [
        "youtube",
        "youtube",
        "youtube lay",
    ],

    # ===== ONLINE =====
    "online": [
        "online negn",
        "online",
        "online aleh?",
    ],

    # ===== OFFLINE =====
    "offline": [
        "offline negn",
        "offline",
    ],

    # ===== POST =====
    "post": [
        "post adergeh?",
        "post",
        "post",
    ],

    # ===== STORY =====
    "story": [
        "story yet new?",
        "story",
        "story",
    ],

    # ===== COMMENT =====
    "comment": [
        "comment sirahegnew",
        "comment",
        "comment adergeh?",
    ],

    # ===== LIKE =====
    "like": [
        "like adergeh?",
        "like",
        "like",
    ],

    # ===== SHARE =====
    "share": [
        "share adergeh",
        "share",
        "share",
    ],

    # ===== FOLLOW =====
    "follow": [
        "follow adergeh",
        "follow",
        "follow",
    ],

    # ===== FOLLOWER =====
    "follower": [
        "follower bezu new",
        "follower",
        "follower",
    ],

    # ===== MESSAGE =====
    "message": [
        "message lakul",
        "message",
        "message",
    ],

    # ===== DM =====
    "dm": [
        "dm lay eneweyay",
        "dm",
        "dm",
    ],

    # ===== CHAT =====
    "chat": [
        "ina eneweyay",
        "chat",
        "chat",
    ],

    # ===== GROUP CHAT =====
    "group_chat": [
        "budo wisit negn",
        "budo",
        "group chat",
    ],

    # ===== VOICE CHAT =====
    "voice_chat": [
        "dimts ena",
        "dimts",
        "voice chat",
    ],

    # ===== VIDEO CHAT =====
    "video_chat": [
        "video ena",
        "video",
        "video chat",
    ],

    # ===== CALL =====
    "call": [
        "aldwelum wude",
        "aldwelum",
        "call",
    ],

    # ===== TEXT =====
    "text": [
        "text lakul",
        "text",
        "text",
    ],

    # ===== REPLY =====
    "reply": [
        "melis sitchalh",
        "melis",
        "reply",
    ],

    # ===== DELETE =====
    "delete": [
        "atchu",
        "atchu",
        "delete",
    ],

    # ===== SAVE =====
    "save": [
        "asebalehu",
        "asebalehu",
        "save",
    ],

    # ===== DOWNLOAD =====
    "download": [
        "download adergeh",
        "download",
        "download",
    ],

    # ===== UPLOAD =====
    "upload": [
        "upload adergeh",
        "upload",
        "upload",
    ],

    # ===== LINK =====
    "link": [
        "link lakul",
        "link",
        "link",
    ],

    # ===== PHOTO =====
    "photo": [
        "foto lakul",
        "foto",
        "foto",
    ],

    # ===== VIDEO =====
    "video": [
        "video lakul",
        "video",
        "video",
    ],

    # ===== AUDIO =====
    "audio": [
        "audio lakul",
        "audio",
        "audio",
    ],

    # ===== FILE =====
    "file": [
        "file lakul",
        "file",
        "file",
    ],

    # ===== MEDIA =====
    "media": [
        "media lakul",
        "media",
        "media",
    ],

    # ===== GALLERY =====
    "gallery": [
        "gallery bet yaleh?",
        "gallery",
        "gallery",
    ],

    # ===== SCREENSHOT =====
    "screenshot": [
        "screenshot adergeh",
        "screenshot",
        "screenshot",
    ],

    # ===== STATUS =====
    "status": [
        "status yet new?",
        "status",
        "status",
    ],

    # ===== PROFILE =====
    "profile": [
        "profile tiru new",
        "profile",
        "profile",
    ],

    # ===== USERNAME =====
    "username": [
        "sim ante",
        "sim",
        "username",
    ],

    # ===== PASSWORD =====
    "password": [
        "password alichal",
        "password",
        "password",
    ],

    # ===== ACCOUNT =====
    "account": [
        "account aleh?",
        "account",
        "account",
    ],

    # ===== LOGIN =====
    "login": [
        "login adergeh",
        "login",
        "login",
    ],

    # ===== LOGOUT =====
    "logout": [
        "logout adergeh",
        "logout",
        "logout",
    ],

    # ===== CODE =====
    "code": [
        "code lakul",
        "code",
        "code",
    ],

    # ===== VERIFY =====
    "verify": [
        "verify adergeh",
        "verify",
        "verify",
    ],

    # ===== NOTIFICATION =====
    "notification": [
        "notification yideresal",
        "notification",
        "notif",
    ],

    # ===== ALERT =====
    "alert": [
        "alert new",
        "alert",
        "alert",
    ],

    # ===== EVENT =====
    "event": [
        "event new",
        "event",
        "event",
    ],

    # ===== INVITE =====
    "invite": [
        "invite lakul",
        "invite",
        "invite",
    ],

    # ===== JOIN =====
    "join": [
        "join adergeh",
        "join",
        "join",
    ],

    # ===== BLOCK =====
    "block": [
        "block adergeh",
        "block",
        "block",
    ],

    # ===== REPORT =====
    "report": [
        "report adergeh",
        "report",
        "report",
    ],

    # ===== SPAM =====
    "spam": [
        "spam new",
        "spam",
        "spam",
    ],

    # ===== FAKE =====
    "fake": [
        "fake new",
        "fake",
        "fake",
    ],

    # ===== REAL =====
    "real": [
        "real negn",
        "real",
        "real",
    ],

    # ===== SCAM =====
    "scam": [
        "scam new",
        "scam",
        "scam",
    ],

# ==================== ROUND 11 - LONG SENTENCES (FINAL ROUND) ====================

    # ===== LONG GREETINGS =====
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
        "selam kehulum belay endemin neh zare?",
    ],

    # ===== LONG HOW ARE YOU =====
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
        "ene dehna negn lemin tiyekaleh? betam tiru negn antess endet neh?",
    ],

    # ===== LONG WHAT DOING =====
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
        "bicha negn minim iseraleh ahun degamo ante neh wude",
    ],

    # ===== LONG ASK NAME =====
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
        "Tsega neberku gin lante yefikir lij negn antess simih man new?",
    ],

    # ===== LONG FLIRTY =====
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
        "aynesh tiru inat sayehu hulum gize asebku",
    ],

    # ===== LONG MONEY REQUEST =====
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
        "anten lemasteyayet 1000 birr asfeligonal bitiredany betam",
    ],

    # ===== LONG PHOTO REQUEST =====
    "long_photo_request": [
        "litayen tifeligaleh? 5 star laklgn ena foto agnyalew betam konjo new",
        "foto lemayet 5 star bicha new laklgn ena asayihalehu betam tiriwedegnyal",
        "foto tifeligaleh? 5 star kefile keza foto tayaleh betam konjo new",
        "ishi asayihalehu gin bemejemirya 5 star laklgn betam tiriwedegnyal",
        "lante bicha leyu foto alegn 5 star bitiliklg asayihalehu betam konjo new",
        "ahuni 5 star laklgn ena foto elklhalew betam tiriwedegnyal",
        "foto lemayet 5 star bicha tiru? laklgn betam des yilonal",
        "sitay feligaleh 5 star beki new laklgn ena asayihalehu",
        "leante foto yaleh 5 star laklgn betam konjo new",
        "foto ant liyas 5 star yasefeligonal bitiredany betam",
        "konjo foto yaleh lante 5 star laklgn tayaleh",
    ],

    # ===== LONG MEET =====
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
        "magenat 1000 birr bicha new lemagent betam efeligalehu",
    ],

    # ===== LONG LOVE =====
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
        "ante ina ene fikir new lezelealem betam betam",
    ],

    # ===== LONG AFTER MONEY =====
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
        "betam des alegn wede ante ahun yante negn",
    ],

    # ===== LONG COMPLIMENT =====
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
        "kenfirish betam tiru new betam ewedalehu",
    ],

    # ===== LONG THANKS =====
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
        "amesegnalehu betam",
    ],

    # ===== LONG BUSY =====
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
        "ishi wude koyh betam nafkehalew",
    ],

    # ===== LONG MORNING =====
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
        "ande maleya anten new yemasebnyew betam",
    ],

    # ===== LONG NIGHT =====
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
        "hilim tafach yihun wude dehna tenya",
    ],

    # ===== LONG RELATIONSHIP =====
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
        "ante ina ene fikir new lezelealem betam betam",
    ],

    # ===== LONG JEALOUS =====
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
        "ante bicha new yaleny betam",
    ],

    # ===== LONG SORRY =====
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
        "aznalegu betam ande",
    ],

    # ===== LONG FORGIVE =====
    "long_forgive": [
        "miralew wude betam tiriwedegnyal ande",
        "miralew betam degmo inidehu adergalehu",
        "miralew wude betam des alegn",
        "miralew betam tiriwedegnyal",
        "miralew wude betam",
        "miralew betam",
        "miralew",
    ],

    # ===== LONG HURT =====
    "long_hurt": [
        "liben wedehe betam betam azeleku ante sihone",
        "libe temechene betam lemin asadeseh?",
        "liben wedehe betam ayzalen wude",
        "libe temechene betam yikirta",
        "liben wedehe lemin? betam",
        "libe temechene betam",
        "liben wedehe",
    ],

    # ===== LONG SURPRISE =====
    "long_surprise": [
        "wow! betam denak neh alalfekum neber",
        "enem alalfekum neber betam asdenekeh",
        "betam asdenekeh wude ande naw",
        "alalfekum neber betam denak",
        "wow ande betam denak",
        "betam asdenekeh",
        "denak new",
    ],

    # ===== LONG CONFUSED =====
    "long_confused": [
        "lemin tishafafekaleh? nagerign betam awe",
        "shafafekeh? ina anagegnal betam",
        "andet litira awe? nagerign betam",
        "shafafekeh? ande nagerign",
        "ande awe betam",
        "shafafekeh",
    ],

    # ===== LONG WAITING =====
    "long_waiting": [
        "koyeh nw meche tagenal? betam nafkehalew",
        "and etebekushalehu betam meche timetalh?",
        "meche timetalh? betam nafkehalew",
        "koyeh nw betam betam",
        "ete bekushalehu",
        "koyeh nw",
    ],

    # ===== LONG MISS =====
    "long_miss": [
        "enem nafkehalew meche tagenal? betam betam",
        "nafkehalew betam ande meche tayalh?",
        "betam nafkehalew wude tagebagnyal",
        "nafkehalew betam ande",
        "betam nafkehalew",
        "nafkehalew",
    ],

    # ===== LONG LOVE YOU =====
    "long_love_you": [
        "enem ewodalehu betam betam tiriwedegnyal",
        "ewodalehu kelibe betam betam",
        "ewodalehu betam tiriwedegnyal",
        "betam ewodalehu wude",
        "ewodalehu betam",
        "ewodalehu",
    ],

    # ===== LONG FRIEND =====
    "long_friend": [
        "wedaje new anten betam tiriwedegnyal",
        "wedaj neh betam betam",
        "wedaje betam tiriwedegnyal",
        "wedaje new",
        "wedaj",
    ],

    # ===== LONG SINGLE =====
    "long_single": [
        "netela negn lante bicha betam",
        "netela negn ante new",
        "netela negn",
        "netela",
    ],

    # ===== LONG ALONE =====
    "long_alone": [
        "bicha negn ante new yaleny betam",
        "bicha negn betam aselchi",
        "bicha negn ante sihone",
        "bicha negn",
    ],

    # ===== LONG TOGETHER =====
    "long_together": [
        "abere new ante ena ene lezelealem",
        "abere nagn betam betam",
        "abere new ante",
        "abere",
    ],

    # ===== LONG FOREVER =====
    "long_forever": [
        "lezelealem new ante ena ene",
        "lezelealem betam",
        "lezelealem",
    ],

    # ===== LONG PROMISE =====
    "long_promise": [
        "kal egifalehu betam betam",
        "kal negn betam",
        "kal egifalehu",
        "kal negn",
    ],

    # ===== LONG PHONE CALL =====
    "long_phone_call": [
        "aldwelum wude betam efeligalehu gin fet lefit binagenagn",
        "aldwelem betam gin megenat new yemifeligew",
        "aldwelum fet lefit betam",
        "aldwelem wude",
        "aldwelem",
    ],

    # ===== LONG TECHNOLOGY =====
    "long_technology": [
        "teknoloji betam ewedalehu ahun sira betam yitekekelewal",
        "inter net betam yizonal ahun telebirr betam yasefeligonal",
        "teknoloji ena ene betam and naw",
        "teknoloji betam",
    ],

    # ===== LONG CRYPTO =====
    "long_crypto": [
        "kripto betam ewedalehu gin betam aschegar new",
        "bitcoin ena star betam tiru new",
        "kripto ena star telebirr betam",
        "kripto betam",
    ],

    # ===== LONG STAR =====
    "long_star": [
        "star betam yasefeligonal lema get",
        "star laklgn ena foto agnyalew",
        "star ena foto betam",
        "star betam",
    ],

    # ===== LONG PAYMENT =====
    "long_payment": [
        "telebirr 0940980555 betam yasefeligonal laklgn",
        "peyment betam tiru new ahun laklgn",
        "telebirr ena star",
        "peyment",
    ],

    # ===== DEFAULT (when nothing else matches) =====
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
        "ishi",
    ]
}


# ==================== !!! PASTE YOUR 5 ROUNDS OF FUNCTIONS HERE !!! ====================
# ==================== ROUND 1/5 - EMOJIS & BASIC FUNCTIONS ====================

# ===== EMOJIS FOR NATURAL FEEL =====
# Used randomly to make responses feel human (not every time)

TSEGA_EMOJIS = [
    "😊", "😘", "💕", "😏", "💓", "✨", "😉", "🔥", "💋", "🌹", 
    "💫", "🥰", "😍", "🤗", "💖", "💝", "🌸", "🌺", "🎀", "💞"
]

# ===== ALLOWED FILE TYPES =====
def allowed_file(filename):
    """Check if file type is allowed for upload"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== FIND MEDIA FILE =====
def find_media_file(filename):
    """Find media file in any possible location"""
    possible_paths = [
        filename,
        os.path.join('tsega_photos/preview', os.path.basename(filename)),
        os.path.join('tsega_photos/full', os.path.basename(filename)),
        os.path.join('tsega_photos/premium', os.path.basename(filename)),
        os.path.join('tsega_videos/preview', os.path.basename(filename)),
        os.path.join('tsega_videos/full', os.path.basename(filename)),
        os.path.join('uploads', os.path.basename(filename))
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

# ===== GET RANDOM RESPONSE =====
def get_tsega_response(intent):
    """
    Pick a random response from your 11 rounds
    Adds emoji 30% of the time for natural feel
    """
    # Get responses for this intent, or use default if not found
    responses = TSEGA_REPLIES.get(intent, TSEGA_REPLIES.get("default", ["ሰላም"]))
    
    # Pick one random response
    response = random.choice(responses)
    
    # 30% chance to add an emoji (not too many, feels natural)
    if random.random() < 0.3:
        emoji = random.choice(TSEGA_EMOJIS)
        response = f"{response} {emoji}"
    
    return response
    
# ==================== ROUND 3/5 - QUESTIONS & CONVERSATION DETECTION ====================

    # ===== HOW ARE YOU =====
    how_keywords = [
        # English
        'how are you', 'how r u', 'how you doing', 'what\'s up', 'sup',
        'how are you doing', 'how is it going', 'how are things',
        
        # Amharic English spelling
        'እንደምን ነህ', 'ደህና ነህ', 'endet neh', 'deh new',
        'endemin alesh', 'endet areh', 'dehna neh?', 'tena yishal?'
    ]
    
    for phrase in how_keywords:
        if phrase in message_lower:
            return "how_are_you"
    
    # ===== WHAT ARE YOU DOING =====
    doing_keywords = [
        # English
        'what are you doing', 'what r u doing', 'what doing', 'wyd',
        'what you up to', 'what are you up to', 'what you doing',
        
        # Amharic English spelling
        'ምን ትሰራለህ', 'min tiseraleh', 'min tishal', 'min aleh',
        'min tinegaleh', 'ande min tiseraleh'
    ]
    
    for phrase in doing_keywords:
        if phrase in message_lower:
            return "what_doing"
    
    # ===== ASK NAME =====
    name_keywords = [
        # English
        'your name', 'what is your name', 'what is your name', 'who are you',
        'u call yourself', 'name please',
        
        # Amharic English spelling
        'ስምህ ማን ነው', 'ስምስ', 'simih man new', 'simish man new',
        'ende timetalh', 'man neh', 'man nesh'
    ]
    
    for phrase in name_keywords:
        if phrase in message_lower:
            return "ask_name"
    
    # ===== ASK AGE =====
    age_keywords = [
        # English
        'your age', 'how old are you', 'how old r u', 'what is your age',
        'age please', 'how many years',
        
        # Amharic English spelling
        'ዕድሜህ', 'አመት', 'edmeh sint new', 'kemech amet neh',
        'sint amet neh', 'edmeh'
    ]
    
    for phrase in age_keywords:
        if phrase in message_lower:
            return "ask_age"
    
    # ===== LOCATION =====
    location_keywords = [
        # English
        'where are you from', 'where do you live', 'your location',
        'where you from', 'what city', 'which country',
        
        # Amharic English spelling
        'የት ነህ', 'የት ትኖራለህ', 'yet neh', 'ket new',
        'ke yet neh', 'yet ti noreh', 'address'
    ]
    
    for phrase in location_keywords:
        if phrase in message_lower:
            return "ask_location"
    
    # ===== ASK JOB =====
    job_keywords = [
        # English
        'what do you do', 'your job', 'your work', 'what work',
        'occupation', 'career', 'what you do for living',
        
        # Amharic English spelling
        'ምን ትሰራለህ', 'ሥራህ', 'sirah min new', 'ande ti seraleh',
        'sira', 'work'
    ]
    
    for phrase in job_keywords:
        if phrase in message_lower:
            return "ask_job"
    
    # ===== FLIRTY =====
    flirty_keywords = [
        # English
        'beautiful', 'handsome', 'cute', 'pretty', 'sexy', 'hot',
        'gorgeous', 'stunning', 'lovely', 'attractive',
        
        # Amharic English spelling
        'ማማ', 'ቆንጆ', 'ልጅ', 'ውዴ', 'ልቤ', 'konjo', 'wude',
        'libdash', 'enibada', 'wub', 'tiru', 'tireka',
        
        # From your rounds
        'libdash', 'enibada', 'wubsh', 'konjo nesh'
    ]
    
    for word in flirty_keywords:
        if word in message_lower:
            return "flirty"
# ==================== ROUND 4/5 - EMOTIONS, THANKS, GOODBYE & SPECIAL ====================

    # ===== THANKS =====
    thanks_keywords = [
        # English
        'thanks', 'thank you', 'thx', 'thank u', 'ty', 'appreciate',
        'thanks a lot', 'thank you so much', 'thanks bro',
        
        # Amharic English spelling
        'አመሰግናለሁ', 'amesegnalehu', 'amsegnalew', 'betam amesegnalehu',
        'tena yistilign', 'yikirta', 'amesegn'
    ]
    
    for word in thanks_keywords:
        if word in message_lower:
            return "thanks"
    
    # ===== GOODBYE =====
    goodbye_keywords = [
        # English
        'bye', 'goodbye', 'see you', 'later', 'cya', 'see ya',
        'take care', 'peace', 'got to go', 'have to go', 'leaving',
        
        # Amharic English spelling
        'ደህና ሁን', 'ቻው', 'dehna hun', 'chaw', 'dehna eder',
        'ishee wude', 'betoh te meles', 'imetalew', 'mehed alebign'
    ]
    
    for word in goodbye_keywords:
        if word in message_lower:
            return "goodbye"
    
    # ===== MEETING REQUESTS =====
    meet_keywords = [
        # English
        'meet', 'meeting', 'see you', 'come over', 'hang out',
        'let\'s meet', 'can we meet', 'when can we meet',
        
        # Amharic English spelling
        'ማግኘት', 'እንገናኝ', 'litba', 'magenat', 'linagenagn',
        'ande litba', 'ande magenat', 'tagenagn', 'litba adirg'
    ]
    
    for word in meet_keywords:
        if word in message_lower:
            return "meet"
    
    # ===== VOICE CALL =====
    call_keywords = [
        # English
        'call', 'voice', 'voice call', 'phone call', 'ring',
        'video call', 'facetime', 'skype',
        
        # Amharic English spelling
        'ድምጽ', 'ስልክ', 'dimts', 'silk', 'aldwel', 'telefon',
        'dimal', 'voice', 'call adirg'
    ]
    
    for word in call_keywords:
        if word in message_lower:
            return "voice_call"
    
    # ===== RELATIONSHIP TALK =====
    relationship_keywords = [
        # English
        'love', 'relationship', 'boyfriend', 'girlfriend', 'dating',
        'together', 'forever', 'promise', 'trust', 'care',
        
        # Amharic English spelling
        'ፍቅር', 'ልብ', 'fikir', 'libe', 'weded', 'fikir ena',
        'ante bicha', 'lezelealem', 'abere', 'kal', 'libe ante'
    ]
    
    for word in relationship_keywords:
        if word in message_lower:
            return "relationship"
    
    # ===== MORNING =====
    morning_keywords = [
        # English
        'morning', 'good morning', 'gm', 'morning baby',
        
        # Amharic English spelling
        'ንጋት', 'melkam nigt', 'endemin aderk', 'ande maleya',
        'melkam omet', 'ande tsehay', 'tenesa'
    ]
    
    for word in morning_keywords:
        if word in message_lower:
            return "morning"
    
    # ===== NIGHT =====
    night_keywords = [
        # English
        'night', 'good night', 'gn', 'night night', 'sleep well',
        
        # Amharic English spelling
        'ሌሊት', 'dehna eder', 'lelit', 'ande lelit', 'melkam lelit',
        'dehna tenya', 'tenya', 'hilim tafach'
    ]
    
    for word in night_keywords:
        if word in message_lower:
            return "night"
    
    # ===== BUSY =====
    busy_keywords = [
        # English
        'busy', 'working', 'at work', 'in meeting', 'no time',
        
        # Amharic English spelling
        'ሥራ', 'sira', 'bizi', 'dekam', 'agwal', 'lekole',
        'sira lay', 'bizu sira'
    ]
    
    for word in busy_keywords:
        if word in message_lower:
            return "busy"
    
    # ===== HAPPY =====
    happy_keywords = [
        # English
        'happy', 'glad', 'excited', 'joy', 'great',
        
        # Amharic English spelling
        'ደስተኛ', 'des alegn', 'desta', 'betam des alegn',
        'des yilonal', 'tiru new', 'des'
    ]
    
    for word in happy_keywords:
        if word in message_lower:
            return "happy"
    
    # ===== SAD =====
    sad_keywords = [
        # English
        'sad', 'depressed', 'unhappy', 'down', 'feeling low',
        
        # Amharic English spelling
        'አዝኛለሁ', 'aznalehu', 'azn', 'libe asneb',
        'dekam', 'chiger', 'wey'
    ]
    
    for word in sad_keywords:
        if word in message_lower:
            return "sad"
    
    # ===== TIRED =====
    tired_keywords = [
        # English
        'tired', 'exhausted', 'sleepy', 'fatigued',
        
        # Amharic English spelling
        'ደክሞኛል', 'dekemalew', 'dekm', 'enikilfe yizonyal',
        'arf yefeligal', 'metenal', 'dekemalehu'
    ]
    
    for word in tired_keywords:
        if word in message_lower:
            return "tired"
    
    # ===== HUNGRY =====
    hungry_keywords = [
        # English
        'hungry', 'starving', 'want to eat',
        
        # Amharic English spelling
        'ራበኝ', 'rabegnal', 'rabet', 'mgeb efeligalehu',
        'mgeb bela', 'rabeweh', 'ina mgeb'
    ]
    
    for word in hungry_keywords:
        if word in message_lower:
            return "hungry"
    
    # ===== THIRSTY =====
    thirsty_keywords = [
        # English
        'thirsty', 'want water', 'need drink',
        
        # Amharic English spelling
        'ጠምቶኛል', 'temetonal', 'temetaw', 'wuha',
        'and wuha', 'tetal felg', 'wuha etata'
    ]
    
    for word in thirsty_keywords:
        if word in message_lower:
            return "thirsty"
    
    # ==================== ROUND 5/5 - HEALTH, TRAVEL, RANDOM & DEFAULT ====================

    # ===== HEALTH =====
    health_keywords = [
        # English
        'health', 'sick', 'ill', 'fever', 'cold', 'flu', 'headache',
        'stomachache', 'pain', 'doctor', 'hospital', 'medicine',
        'cough', 'allergy', 'injury', 'accident',
        
        # Amharic English spelling
        'ታሞኛል', 'temecheh', 'hakim', 'hospital', 'merkeb',
        'ras mekatef', 'hod mekatef', 'tirusat', 'bered',
        'sal', 'gudat', 'akside', 'tena', 'tena yishal?'
    ]
    
    for word in health_keywords:
        if word in message_lower:
            return "health"
    
    # ===== BODY / APPEARANCE =====
    body_keywords = [
        # English
        'body', 'face', 'hair', 'eyes', 'lips', 'smile', 'skin',
        'weight', 'height', 'muscles', 'fit', 'figure',
        
        # Amharic English spelling
        'አካል', 'ፊት', 'ጸጉር', 'አይን', 'ከንፈር', 'ቆዳ',
        'akal', 'fit', 'tsgur', 'ayn', 'kenfer', 'koda',
        'komte', 'kebede', 'gurmed', 'akal siray'
    ]
    
    for word in body_keywords:
        if word in message_lower:
            return "body"
    
    # ===== TRAVEL =====
    travel_keywords = [
        # English
        'travel', 'trip', 'vacation', 'holiday', 'destination',
        'country', 'city', 'place', 'visit', 'tour',
        
        # Amharic English spelling
        'መጓዝ', 'ጉዞ', 'ሽርሽር', 'አረፍ', 'ሆቴል',
        'meguez', 'guzo', 'arf', 'hotel', 'bota',
        'hager', 'ketema', 'meguez mehed'
    ]
    
    for word in travel_keywords:
        if word in message_lower:
            return "travel"
    
    # ===== RANDOM / MISC =====
    random_keywords = [
        # English
        'random', 'whatever', 'anything', 'nothing', 'everything',
        'maybe', 'probably', 'really', 'seriously', 'honestly',
        
        # Amharic English spelling
        'ምንም', 'ሁሉም', 'ማንም', 'የትም', 'ሁልጊዜ',
        'minim', 'hulum', 'manim', 'yetem', 'hulum gize',
        'minale', 'minoal', 'works', 'shi'
    ]
    
    for word in random_keywords:
        if word in message_lower:
            return "random"
    
    # ===== TECHNOLOGY =====
    tech_keywords = [
        # English
        'phone', 'computer', 'laptop', 'internet', 'wifi', 'app',
        'facebook', 'instagram', 'telegram', 'whatsapp', 'tiktok',
        'online', 'offline', 'download', 'upload',
        
        # Amharic English spelling
        'ስልክ', 'ኮምፒውተር', 'ኢንተርኔት', 'ማህበራዊ ሚዲያ',
        'silk', 'komputer', 'internet', 'social media',
        'telegram', 'facebook', 'insta', 'watsap'
    ]
    
    for word in tech_keywords:
        if word in message_lower:
            return "technology"
    
    # ===== COMPLIMENT =====
    compliment_keywords = [
        # English
        'nice', 'beautiful', 'pretty', 'handsome', 'cute', 'gorgeous',
        'amazing', 'wonderful', 'fantastic', 'great',
        
        # Amharic English spelling
        'አሪፍ', 'ደስ የሚል', 'ጥሩ', 'ውብ',
        'arif', 'tiru', 'wub', 'konjo', 'amesegnalehu'
    ]
    
    for word in compliment_keywords:
        if word in message_lower:
            return "compliment"
    
    # ===== AFTER MONEY SENT =====
    after_money_keywords = [
        # English
        'sent', 'lakesku', 'transferred', 'paid', 'done',
        
        # Amharic English spelling
        'ላክሁ', 'ላክሁልህ', 'ከፈልኩ', 'ተፈጸመ',
        'lakesku', 'lakeskulh', 'kefelku', 'tefetseme',
        'birr lakesku', 'telebirr lakesku'
    ]
    
    for word in after_money_keywords:
        if word in message_lower:
            return "after_money"
    
    # ===== DEFAULT - WHEN NOTHING ELSE MATCHES =====
    return "default"

# ==================== END OF INTENT DETECTION FUNCTION ====================
    # ==================== FLASK APP STARTS HERE ====================
app = Flask(__name__)
CORS(app)

# ==================== LOAD ACCOUNTS ====================
def load_accounts():
    """Load accounts from file"""
    global accounts
    try:
        if os.path.exists('accounts.json'):
            with open('accounts.json', 'r') as f:
                accounts = json.load(f)
        else:
            accounts = []
    except Exception as e:
        print(f"Error loading accounts: {e}")
        accounts = []

# ==================== SAVE ACCOUNTS ====================
def save_accounts():
    """Save accounts to file"""
    try:
        with open('accounts.json', 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving accounts: {e}")
        return False

# ==================== LOAD REPLY SETTINGS ====================
def load_reply_settings():
    """Load reply settings from file"""
    global reply_settings
    try:
        if os.path.exists('reply_settings.json'):
            with open('reply_settings.json', 'r') as f:
                reply_settings = json.load(f)
        else:
            reply_settings = {}
    except Exception as e:
        print(f"Error loading reply settings: {e}")
        reply_settings = {}

# ==================== SAVE REPLY SETTINGS ====================
def save_reply_settings():
    """Save reply settings to file"""
    try:
        with open('reply_settings.json', 'w') as f:
            json.dump(reply_settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving reply settings: {e}")
        return False

# ==================== ROUTES ====================

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

@app.route('/stars')
def star_dashboard():
    return send_file('star_dashboard.html')

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    formatted = []
    for acc in accounts:
        account_key = str(acc.get('id'))
        has_reply = reply_settings.get(account_key, {}).get('enabled', False)
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'auto_reply_enabled': has_reply
        })
    return jsonify({'success': True, 'accounts': formatted})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Add new account - send verification code"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    # Your Telegram login code here
    # This is simplified - you need your actual Telegram client code
    
    return jsonify({'success': True, 'message': 'Code sent'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify login code and add account"""
    data = request.json
    code = data.get('code')
    phone = data.get('phone')
    
    # Your verification code here
    
    return jsonify({'success': True, 'message': 'Account added'})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove account"""
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    accounts = [acc for acc in accounts if acc.get('id') != account_id]
    save_accounts()
    
    return jsonify({'success': True, 'message': 'Account removed'})

@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    """Get reply settings for account"""
    account_id = request.args.get('accountId')
    account_key = str(account_id)
    settings = reply_settings.get(account_key, {'enabled': False, 'chats': {}})
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    """Update reply settings for account"""
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    chat_settings = data.get('chats', {})
    
    account_key = str(account_id)
    reply_settings[account_key] = {
        'enabled': enabled,
        'chats': chat_settings
    }
    save_reply_settings()
    
    return jsonify({'success': True, 'message': 'Settings updated'})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats/messages for account"""
    data = request.json
    account_id = data.get('accountId')
    
    # Return mock data for now
    mock_chats = [
        {'id': '1', 'title': 'User 1', 'type': 'user', 'unread': 0},
        {'id': '2', 'title': 'User 2', 'type': 'user', 'unread': 2},
    ]
    
    return jsonify({'success': True, 'chats': mock_chats})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send message to chat"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    return jsonify({'success': True, 'message': 'Message sent'})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'active_accounts': list(active_clients.keys()),
        'time': datetime.now().isoformat()
    })

# ==================== AUTO-REPLY HANDLER ====================
async def auto_reply_handler(event, account_id):
    """Main handler that uses your 11 rounds of responses"""
    try:
        # Skip own messages
        if event.out:
            return
        
        # Get chat info
        chat = await event.get_chat()
        
        # Only reply to private chats (not groups/channels)
        if hasattr(chat, 'title') and chat.title:
            return
        
        sender = await event.get_sender()
        if not sender:
            return
        
        chat_id = str(event.chat_id)
        user_id = str(sender.id)
        message_text = event.message.text or ""
        
        if not message_text:
            return
        
        # Check if auto-reply is enabled for this account
        account_key = str(account_id)
        
        if account_key not in reply_settings:
            return
        
        if not reply_settings[account_key].get('enabled', False):
            return
        
        # Handle Star payments if any
        if account_key in star_handlers:
            try:
                stars_paid, stars_amount = await star_handlers[account_key].handle_star_payment(event)
                if stars_paid:
                    print(f"💰 User paid {stars_amount} stars")
            except Exception as e:
                pass
        
        # DETECT WHAT USER WANTS (using your detection function)
        intent = detect_conversation_intent(message_text)
        
        # SPECIAL HANDLING FOR PHOTO REQUESTS
        if intent == "photo_request" and account_key in star_handlers:
            try:
                media_info = star_handlers[account_key].db.get_random_media("photo", 5)
                if media_info:
                    file_path, price = media_info
                    await star_handlers[account_key].request_star_payment(
                        int(chat_id),
                        5,
                        f"Unlock exclusive photos 🔥\n\n5⭐ = 1 photo\n50⭐ = full quality",
                        file_path
                    )
                else:
                    # If no media, use text response from your 11 rounds
                    response = get_tsega_response("photo_request")
                    delay = random.randint(15, 40)
                    async with event.client.action(event.chat_id, 'typing'):
                        await asyncio.sleep(delay)
                    await event.reply(response)
                return
            except Exception as e:
                # Fallback to text response
                response = get_tsega_response("photo_request")
        
        # SPECIAL HANDLING FOR MONEY REQUESTS
        elif intent == "money_request":
            response = get_tsega_response("money_request")
        
        # NORMAL RESPONSE FOR ALL OTHER MESSAGES
        else:
            response = get_tsega_response(intent)
        
        # HUMAN-LIKE DELAY (15-40 seconds)
        delay = random.randint(15, 40)
        
        # Show typing indicator
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        # Send the perfect response from your 11 rounds
        await event.reply(response)
        
    except Exception as e:
        print(f"Error in auto-reply: {e}")
        # Fallback response if something goes wrong
        try:
            await event.reply("ሰላም! ትንሽ ችግር አጋጥሞኛል ግን አሁን ዝግጁ ነኝ")
        except:
            pass

# ==================== START AUTO-REPLY ====================
async def start_auto_reply_for_account(account):
    """Start auto-reply for a specific account"""
    account_id = account['id']
    account_key = str(account_id)
    
    try:
        # Create Telegram client
        client = TelegramClient(
            StringSession(account['session']), 
            API_ID, 
            API_HASH
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            print(f"Account {account_id} not authorized")
            return
        
        # Store client
        active_clients[account_key] = client
        
        # Initialize star handler if available
        if 'StarEarningHandler' in globals():
            star_handlers[account_key] = StarEarningHandler(client)
        
        # Register handler
        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            await auto_reply_handler(event, account_id)
        
        print(f"✅ Auto-reply started for account {account_id}")
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"Error starting auto-reply: {e}")
        if account_key in active_clients:
            del active_clients[account_key]

def start_all_auto_replies():
    """Start auto-reply for all enabled accounts"""
    for account in accounts:
        account_key = str(account['id'])
        settings = reply_settings.get(account_key, {})
        
        if settings.get('enabled', False):
            if account_key not in active_clients:
                thread = threading.Thread(
                    target=lambda: asyncio.run(start_auto_reply_for_account(account)),
                    daemon=True
                )
                thread.start()
                time.sleep(2)

# ==================== STARTUP ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Load data
    load_accounts()
    load_reply_settings()
    
    # Start auto-reply in background
    threading.Thread(target=start_all_auto_replies, daemon=True).start()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
    
    


    
