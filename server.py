from flask import Flask, send_file, jsonify, request, render_template_string
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
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ==================== CONFIGURATION ====================

API_ID = int(os.environ.get('API_ID', '33465589'))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

ACCOUNTS_FILE = 'accounts.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'
CONVERSATION_HISTORY_FILE = 'conversation_history.json'
AUTO_ADD_FILE = 'auto_add_settings.json'

# ==================== GLOBAL VARIABLES ====================

accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
auto_add_settings = {}
active_clients = {}
client_tasks = {}

# ==================== FILE HELPERS ====================

def load_json_file(filename, default_value=None):
    if default_value is None:
        default_value = {}
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        return default_value
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default_value

def save_json_file(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")
        return False

def load_all_data():
    global accounts, reply_settings, conversation_history, auto_add_settings
    accounts = load_json_file(ACCOUNTS_FILE, [])
    reply_settings = load_json_file(REPLY_SETTINGS_FILE, {})
    conversation_history = load_json_file(CONVERSATION_HISTORY_FILE, {})
    auto_add_settings = load_json_file(AUTO_ADD_FILE, {})

def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_json_file(ACCOUNTS_FILE, accounts)
        return True
    return False

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Async error: {e}")
        raise
    finally:
        try:
            loop.close()
        except:
            pass

load_all_data()

# ==================== AUTO REPLY SYSTEM ====================

ABEL = {
    "name": "Abel",
    "age": 25,
    "location": "Los Angeles, USA",
    "job": "Creative Consultant & Music Producer",
}

class ConversationMemory:
    def __init__(self):
        self.user_info = {}

    def get_user_info(self, chat_id):
        chat_id = str(chat_id)
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
        self.get_user_info(chat_id)['waiting_for'] = what

    def clear_waiting(self, chat_id):
        self.get_user_info(chat_id)['waiting_for'] = None

    def add_to_history(self, chat_id, role, text):
        info = self.get_user_info(chat_id)
        info['chat_history'].append({"role": role, "text": text})
        if len(info['chat_history']) > 10:
            info['chat_history'] = info['chat_history'][-10:]

    def has_greeted(self, chat_id):
        return self.get_user_info(chat_id).get('greeting_sent', False)

    def set_greeting_sent(self, chat_id):
        self.get_user_info(chat_id)['greeting_sent'] = True

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

    def detect_gender(self, chat_id, text=None, name=None):
        info = self.get_user_info(chat_id)
        if info.get('gender'):
            return info['gender']
        if text:
            text_lower = text.lower()
            if any(p in text_lower for p in ['i am a woman', 'i am a girl', 'as a woman', 'i am female']):
                info['gender'] = 'female'
                return 'female'
            if any(p in text_lower for p in ['i am a man', 'i am a guy', 'as a man', 'i am male']):
                info['gender'] = 'male'
                return 'male'
        if name:
            female_names = {'anna','maria','sarah','linda','jessica','amanda','emma','olivia','sophia'}
            male_names = {'michael','james','john','robert','david','william','thomas','daniel'}
            if name.lower() in female_names:
                info['gender'] = 'female'
                return 'female'
            if name.lower() in male_names:
                info['gender'] = 'male'
                return 'male'
        return None

    def extract_name(self, text):
        if not text:
            return None
        words = text.strip().split()
        if len(words) == 1 and words[0].isalpha():
            return words[0].capitalize()
        patterns = [r"my name is (\w+)", r"i'm (\w+)", r"i am (\w+)", r"call me (\w+)"]
        for p in patterns:
            match = re.search(p, text.lower())
            if match:
                return match.group(1).capitalize()
        return None

conversation_memory = ConversationMemory()

ABEL_REPLIES = {
    "confirm_identity": [
        "Yeah, that's me – Abel. And you are?",
        "Yes, I'm Abel. What's your name?"
    ],
    "greeting_female": ["Well hello there… who do I have the pleasure of talking to? 😊"],
    "greeting_male": ["Hey man, what's good? I'm Abel."],
    "greeting_unknown": ["Hey! Abel here. Who do I have the pleasure of chatting with?"],
    "ask_name": ["So what's your name?", "What should I call you?"],
    "ask_age": ["I'm 25 – what about you?"],
    "ask_location": ["I'm in Los Angeles. Where are you?"],
    "ask_job": ["I'm a creative consultant. What do you do?"],
    "how_are_you": ["I'm good, thanks! What about you?", "Feeling great! And you?"],
    "flirty": ["You're making me smile… 😏", "I like the way you talk."],
    "bro_compliment": ["Bro, you've got good energy.", "Respect, man."],
    "default": ["Tell me more about you.", "I'm all ears. What's on your mind?"]
}

def detect_intent(message, chat_id):
    if not message:
        return "greeting"
    msg = message.strip().lower()
    info = conversation_memory.get_user_info(chat_id)
    
    waiting_for = info.get('waiting_for')
    if waiting_for:
        return f"answering_{waiting_for}"
    
    if any(q in msg for q in ['are you abel', 'is that abel']):
        return "confirm_identity"
    
    greeting_words = ['hi', 'hello', 'hey', 'selam', 'yo', 'hola']
    if msg in greeting_words or any(msg.startswith(g) for g in greeting_words):
        return "greeting" if not info['greeting_sent'] else "already_greeted_again"
    
    if any(q in msg for q in ['how are you', 'how r u']):
        return "how_are_you"
    if any(w in msg for w in ['sexy', 'hot', 'gorgeous', 'beautiful', 'cutie']):
        return "flirty"
    if any(w in msg for w in ['bro', 'dude', 'man']):
        return "bro_compliment"
    if any(phrase in msg for phrase in ['my name', 'i am', "i'm"]):
        return "user_tells_name"
    
    return "default"

def generate_response(intent, chat_id, message_text):
    info = conversation_memory.get_user_info(chat_id)
    gender = info.get('gender')
    
    if intent == "greeting":
        conversation_memory.set_greeting_sent(chat_id)
        conversation_memory.advance_stage(chat_id)
        if gender == 'female':
            return random.choice(ABEL_REPLIES["greeting_female"])
        elif gender == 'male':
            return random.choice(ABEL_REPLIES["greeting_male"])
        return random.choice(ABEL_REPLIES["greeting_unknown"])
    
    if intent == "confirm_identity":
        conversation_memory.set_greeting_sent(chat_id)
        return random.choice(ABEL_REPLIES["confirm_identity"])
    
    if intent == "answering_name":
        name = conversation_memory.extract_name(message_text)
        if name:
            info['name'] = name
            conversation_memory.detect_gender(chat_id, message_text, name)
            conversation_memory.clear_waiting(chat_id)
            conversation_memory.advance_stage(chat_id)
            return f"{name}, nice to meet you! How old are you?"
        return random.choice(ABEL_REPLIES["ask_name"])
    
    if intent == "answering_age":
        age_match = re.search(r'(\d+)', message_text)
        if age_match:
            info['age'] = age_match.group(1)
            conversation_memory.clear_waiting(chat_id)
            conversation_memory.advance_stage(chat_id)
            return f"Oh {info['age']}! Where are you from?"
        return random.choice(ABEL_REPLIES["ask_age"])
    
    if intent == "answering_location":
        info['location'] = message_text.strip().title()
        conversation_memory.clear_waiting(chat_id)
        conversation_memory.advance_stage(chat_id)
        return f"{info['location']} – nice! What do you do?"
    
    if intent == "answering_job":
        info['job'] = message_text.strip().title()
        conversation_memory.clear_waiting(chat_id)
        conversation_memory.advance_stage(chat_id)
        return f"Interesting! What do you enjoy doing in your free time?"
    
    mapping = {
        "how_are_you": "how_are_you",
        "flirty": "flirty",
        "bro_compliment": "bro_compliment",
        "default": "default"
    }
    
    return random.choice(ABEL_REPLIES.get(mapping.get(intent, "default"), ABEL_REPLIES["default"]))

async def auto_reply_handler(event, account_id):
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        if hasattr(chat, 'title') and chat.title:
            return
        
        chat_id = str(event.chat_id)
        message_text = event.message.text or ""
        
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        conversation_memory.detect_gender(chat_id, message_text)
        
        intent = detect_intent(message_text, chat_id)
        response = generate_response(intent, chat_id, message_text)
        
        if not response:
            response = "Hey there! Abel here. What's on your mind? 😊"
        
        info = conversation_memory.get_user_info(chat_id)
        if not info['name']:
            conversation_memory.set_waiting_for(chat_id, "name")
        elif not info['age']:
            conversation_memory.set_waiting_for(chat_id, "age")
        elif not info['location']:
            conversation_memory.set_waiting_for(chat_id, "location")
        elif not info['job']:
            conversation_memory.set_waiting_for(chat_id, "job")
        
        delay = random.randint(15, 40)
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        await event.reply(response)
        logger.info(f"Sent reply: {response[:50]}...")
        
    except Exception as e:
        logger.error(f"Auto-reply error: {e}")

async def start_auto_reply_for_account(account):
    account_id = account['id']
    account_key = str(account_id)
    
    while True:
        try:
            client = TelegramClient(
                StringSession(account['session']),
                API_ID, API_HASH,
                connection_retries=10,
                retry_delay=5,
                timeout=60
            )
            await client.connect()
            
            if not await client.is_user_authorized():
                remove_invalid_account(account_id)
                break
            
            active_clients[account_key] = client
            
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            logger.info(f"✅ Auto-reply active for {account.get('name')}")
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Connection lost: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            await asyncio.sleep(30)

def stop_auto_reply_for_account(account_id):
    account_key = str(account_id)
    if account_key in active_clients:
        try:
            run_async(active_clients[account_key].disconnect())
            del active_clients[account_key]
        except:
            pass

def start_all_auto_replies():
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

# ==================== AUTO-ADD SYSTEM ====================

async def get_all_potential_members(client, settings, existing_members_set):
    potential_members = set()
    
    # From contacts
    if settings.get('use_contacts', True):
        try:
            contacts = await client(functions.contacts.GetContactsRequest(0))
            for user in contacts.users:
                if user and user.id and not (settings.get('skip_bots', True) and user.bot):
                    potential_members.add(user.id)
        except:
            pass
    
    # From recent chats
    if settings.get('use_recent_chats', True):
        try:
            dialogs = await client.get_dialogs(limit=500)
            for dialog in dialogs:
                if dialog.is_user and dialog.entity and dialog.entity.id:
                    user = dialog.entity
                    if not (settings.get('skip_bots', True) and user.bot):
                        potential_members.add(user.id)
        except:
            pass
    
    # From source groups
    if settings.get('use_scraping', True):
        source_groups = settings.get('source_groups', [])
        scrape_limit = settings.get('scrape_limit_per_group', 200)
        
        for group_ref in source_groups:
            if not group_ref or not group_ref.strip():
                continue
            try:
                clean_ref = group_ref.strip()
                if not clean_ref.startswith('@'):
                    clean_ref = '@' + clean_ref
                source_group = await client.get_entity(clean_ref)
                count = 0
                async for user in client.iter_participants(source_group, limit=scrape_limit):
                    if user and user.id and not (settings.get('skip_bots', True) and user.bot):
                        potential_members.add(user.id)
                        count += 1
                        if count >= scrape_limit:
                            break
            except:
                pass
    
    # From mutual contacts
    if settings.get('use_mutual_contacts', True):
        try:
            mutual = await client(functions.contacts.GetTopPeersRequest(
                correspondents=True, bots_pm=False,
                groups=False, channels=False, limit=100
            ))
            if mutual.categories:
                for category in mutual.categories:
                    for peer in category.peers:
                        if hasattr(peer, 'user_id'):
                            potential_members.add(peer.user_id)
        except:
            pass
    
    # Remove existing members
    return potential_members - existing_members_set

async def professional_auto_add_loop(account):
    account_id = account['id']
    account_key = str(account_id)
    attempted_members = set()
    
    logger.info(f"🚀 Auto-Add started for account {account_id}")
    
    while True:
        try:
            if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                break
            
            settings = auto_add_settings[account_key]
            target_group = settings.get('target_group', 'Abe_armygroup')
            delay_seconds = settings.get('delay_seconds', 25)
            
            if not target_group.startswith('@'):
                target_group = '@' + target_group
            
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    await asyncio.sleep(60)
                    continue
                
                # Get target group
                group = await client.get_entity(target_group)
                
                # Get existing members
                existing_members = set()
                try:
                    async for user in client.iter_participants(group, limit=5000):
                        if user and user.id:
                            existing_members.add(user.id)
                except:
                    pass
                
                logger.info(f"Group has {len(existing_members)} members")
                
                # Get potential members
                potential_members = await get_all_potential_members(client, settings, existing_members)
                fresh_members = potential_members - attempted_members
                
                logger.info(f"Found {len(fresh_members)} new members to add")
                
                if not fresh_members:
                    attempted_members.clear()
                    await asyncio.sleep(300)
                    continue
                
                added_this_cycle = 0
                for user_id in list(fresh_members):
                    if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                        break
                    
                    attempted_members.add(user_id)
                    
                    try:
                        user_entity = await client.get_input_entity(user_id)
                        await client(functions.channels.InviteToChannelRequest(group, [user_entity]))
                        
                        settings['added_today'] = settings.get('added_today', 0) + 1
                        settings['total_added'] = settings.get('total_added', 0) + 1
                        settings['last_added'] = datetime.now().isoformat()
                        added_this_cycle += 1
                        
                        save_json_file(AUTO_ADD_FILE, auto_add_settings)
                        logger.info(f"✅ Added user {user_id} | Total: {settings['total_added']}")
                        
                        await asyncio.sleep(delay_seconds)
                        
                    except errors.FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 5)
                    except:
                        continue
                
                logger.info(f"Cycle complete: Added {added_this_cycle} members")
                
                if added_this_cycle > 0:
                    await asyncio.sleep(random.randint(60, 180))
                else:
                    await asyncio.sleep(random.randint(300, 600))
                
            finally:
                await client.disconnect()
            
        except Exception as e:
            logger.error(f"Auto-add error: {e}")
            await asyncio.sleep(300)

# ==================== KEEP ALIVE ====================

def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=10)
        except:
            pass
        time.sleep(240)

# ==================== ROUTES - PAGES ====================

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
def auto_add_page():
    return send_file('auto_add.html')

@app.route('/settings')
def settings_page():
    return send_file('settings.html')

@app.route('/fog')
def fog():
    return send_file('fog.html')

# ==================== API ROUTES ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'time': datetime.now().isoformat()
    })

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = []
    for acc in accounts:
        account_key = str(acc['id'])
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'auto_reply_enabled': account_key in reply_settings and reply_settings[account_key].get('enabled', False),
            'auto_add_enabled': account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False)
        })
    return jsonify({'success': True, 'accounts': formatted})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data received'})
        
        phone = data.get('phone')
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'})
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            try:
                await client.connect()
                result = await client.send_code_request(phone)
                session_id = str(int(time.time() * 1000))
                temp_sessions[session_id] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': session_id}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send_code()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id or session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'})
    
    session_data = temp_sessions[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session_data['session']), API_ID, API_HASH)
        await client.connect()
        try:
            try:
                await client.sign_in(session_data['phone'], code, phone_code_hash=session_data['hash'])
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            me = await client.get_me()
            new_id = max([a['id'] for a in accounts], default=0) + 1
            
            accounts.append({
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'session': client.session.save()
            })
            save_json_file(ACCOUNTS_FILE, accounts)
            return {'success': True}
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
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                remove_invalid_account(account_id)
                return {'success': False, 'error': 'Session expired'}
            
            dialogs = await client.get_dialogs(limit=50)
            chats = []
            for dialog in dialogs:
                chats.append({
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': 'group' if dialog.is_group else 'channel' if dialog.is_channel else 'user',
                    'unread': dialog.unread_count or 0
                })
            return {'success': True, 'chats': chats}
        finally:
            await client.disconnect()
    
    return jsonify(run_async(fetch()))

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id, message]):
        return jsonify({'success': False, 'error': 'Missing fields'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            entity = await client.get_entity(int(chat_id))
            await client.send_message(entity, message)
            return {'success': True}
        finally:
            await client.disconnect()
    
    return jsonify(run_async(send()))

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    stop_auto_reply_for_account(account_id)
    
    global accounts
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    save_json_file(ACCOUNTS_FILE, accounts)
    
    return jsonify({'success': True})

@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    account_id = request.args.get('accountId')
    account_key = str(account_id)
    settings = reply_settings.get(account_key, {'enabled': False})
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/reply-settings', methods=['POST'])
def update_reply_settings():
    data = request.json
    account_id = data.get('accountId')
    enabled = data.get('enabled', False)
    
    account_key = str(account_id)
    was_enabled = reply_settings.get(account_key, {}).get('enabled', False)
    
    if account_key not in reply_settings:
        reply_settings[account_key] = {}
    reply_settings[account_key]['enabled'] = enabled
    save_json_file(REPLY_SETTINGS_FILE, reply_settings)
    
    if enabled and not was_enabled:
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if account:
            thread = threading.Thread(
                target=lambda: run_async(start_auto_reply_for_account(account)),
                daemon=True
            )
            thread.start()
            client_tasks[account_key] = thread
    elif not enabled:
        stop_auto_reply_for_account(account_id)
    
    return jsonify({'success': True})

# ==================== AUTO-ADD API ROUTES ====================

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    
    default_settings = {
        'enabled': False,
        'target_group': 'Abe_armygroup',
        'delay_seconds': 25,
        'source_groups': ['@telegram', '@durov'],
        'use_contacts': True,
        'use_recent_chats': True,
        'use_scraping': True,
        'use_mutual_contacts': True,
        'scrape_limit_per_group': 200,
        'skip_bots': True,
        'skip_inaccessible': True,
        'auto_join': True,
        'total_added': 0,
        'added_today': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'last_added': None
    }
    
    if account_key not in auto_add_settings:
        auto_add_settings[account_key] = default_settings
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
    
    settings = auto_add_settings[account_key]
    for key, value in default_settings.items():
        if key not in settings:
            settings[key] = value
    
    # Reset daily counter if needed
    today = datetime.now().strftime('%Y-%m-%d')
    if settings.get('last_reset') != today:
        settings['added_today'] = 0
        settings['last_reset'] = today
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
    
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
        
        auto_add_settings[account_key].update({
            'enabled': data.get('enabled', False),
            'target_group': data.get('target_group', 'Abe_armygroup'),
            'delay_seconds': data.get('delay_seconds', 25),
            'source_groups': data.get('source_groups', []),
            'use_contacts': data.get('use_contacts', True),
            'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True),
            'use_mutual_contacts': data.get('use_mutual_contacts', True),
            'scrape_limit_per_group': data.get('scrape_limit_per_group', 200),
            'skip_bots': data.get('skip_bots', True),
            'skip_inaccessible': data.get('skip_inaccessible', True),
            'auto_join': data.get('auto_join', True)
        })
        
        if 'total_added' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['total_added'] = 0
        if 'added_today' not in auto_add_settings[account_key]:
            auto_add_settings[account_key]['added_today'] = 0
        
        save_json_file(AUTO_ADD_FILE, auto_add_settings)
        
        # Start/stop auto-add
        enabled = auto_add_settings[account_key]['enabled']
        if enabled and not was_enabled:
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if account:
                thread = threading.Thread(
                    target=lambda: run_async(professional_auto_add_loop(account)),
                    daemon=True
                )
                thread.start()
                client_tasks[f"auto_add_{account_key}"] = thread
                logger.info(f"🚀 Started auto-add for account {account_id}")
        
        return jsonify({'success': True, 'message': 'Settings updated'})
        
    except Exception as e:
        logger.error(f"Error updating auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_key = str(account_id)
    settings = auto_add_settings.get(account_key, {})
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
        'total_added': settings.get('total_added', 0),
        'enabled': settings.get('enabled', False),
        'last_added': settings.get('last_added')
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """IMPORTANT: This route MUST return valid JSON"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data received'})
        
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
                    return {'success': False, 'error': 'Account not authorized. Please re-login.'}
                
                settings = auto_add_settings.get(str(account_id), {})
                target_group = settings.get('target_group', 'Abe_armygroup')
                
                if not target_group.startswith('@'):
                    target_group = '@' + target_group
                
                # Test target group
                try:
                    group = await client.get_entity(target_group)
                    group_title = group.title if hasattr(group, 'title') else target_group
                    
                    # Count existing members
                    member_count = 0
                    async for _ in client.iter_participants(group, limit=1000):
                        member_count += 1
                except Exception as e:
                    return {'success': False, 'error': f'Cannot access target group: {str(e)}'}
                
                # Count available members
                available = 0
                sources = []
                
                if settings.get('use_contacts', True):
                    try:
                        contacts = await client(functions.contacts.GetContactsRequest(0))
                        available += len(contacts.users)
                        sources.append(f"Contacts: {len(contacts.users)}")
                    except:
                        pass
                
                if settings.get('use_recent_chats', True):
                    try:
                        dialogs = await client.get_dialogs(limit=100)
                        users = [d for d in dialogs if d.is_user]
                        available += len(users)
                        sources.append(f"Recent Chats: {len(users)}")
                    except:
                        pass
                
                return {
                    'success': True,
                    'group_found': True,
                    'group_title': group_title,
                    'existing_members': member_count,
                    'available_members': available,
                    'sources_found': sources,
                    'can_add_members': available > 0
                }
                
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(test())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Test auto-add error: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reconnect', methods=['GET'])
def reconnect_all():
    for account_key in list(active_clients.keys()):
        stop_auto_reply_for_account(int(account_key))
    time.sleep(2)
    start_all_auto_replies()
    return jsonify({'success': True, 'active': len(active_clients)})

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*60)
    print('🤖 TELEGRAM MULTI-ACCOUNT MANAGER')
    print('='*60)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print(f'✅ Auto-reply settings: {len(reply_settings)}')
    print(f'✅ Auto-add settings: {len(auto_add_settings)}')
    print('='*60 + '\n')
    
    # Start keep-alive
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-reply
    threading.Thread(target=start_all_auto_replies, daemon=True).start()
    
    # Start auto-add for enabled accounts
    for account in accounts:
        account_key = str(account['id'])
        if account_key in auto_add_settings and auto_add_settings[account_key].get('enabled', False):
            thread = threading.Thread(
                target=lambda acc=account: run_async(professional_auto_add_loop(acc)),
                daemon=True
            )
            thread.start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
