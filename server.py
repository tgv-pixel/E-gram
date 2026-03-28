from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FloodWaitError
import json
import os
import asyncio
import logging
import time
import threading
import requests
import base64
from datetime import datetime
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# JSON file paths
ACCOUNTS_FILE = 'accounts.json'
AUTO_ADD_FILE = 'auto_add_settings.json'
CHAT_PHOTOS_FILE = 'chat_photos.json'

# Global storage
accounts = []
temp_sessions = {}
auto_add_threads = {}
auto_add_settings = {}
chat_photos = {}

# ==================== JSON FILE FUNCTIONS ====================

def load_json_file(file_path, default_data):
    """Load data from JSON file"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default_data
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return default_data

def save_json_file(file_path, data):
    """Save data to JSON file"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

# ==================== LOAD ALL DATA ====================

def load_all_data():
    """Load all data from JSON files"""
    global accounts, auto_add_settings, chat_photos
    
    # Load accounts
    accounts_data = load_json_file(ACCOUNTS_FILE, [])
    accounts = []
    for acc in accounts_data:
        accounts.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'User'),
            'username': acc.get('username', ''),
            'session': acc.get('session', ''),
            'photo': acc.get('photo', None)
        })
    
    # Load auto-add settings
    auto_add_settings = load_json_file(AUTO_ADD_FILE, {})
    
    # Load chat photos
    chat_photos = load_json_file(CHAT_PHOTOS_FILE, {})
    
    logger.info(f"✅ Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")
    logger.info(f"✅ Loaded {len(auto_add_settings)} auto-add settings")
    logger.info(f"✅ Loaded {len(chat_photos)} chat photos")

def save_accounts():
    """Save accounts to JSON file"""
    accounts_data = []
    for acc in accounts:
        accounts_data.append({
            'id': acc['id'],
            'phone': acc['phone'],
            'name': acc['name'],
            'username': acc['username'],
            'session': acc['session'],
            'photo': acc.get('photo')
        })
    return save_json_file(ACCOUNTS_FILE, accounts_data)

def save_auto_add_settings_file():
    """Save auto-add settings to JSON file"""
    return save_json_file(AUTO_ADD_FILE, auto_add_settings)

def save_chat_photos_file():
    """Save chat photos to JSON file"""
    return save_json_file(CHAT_PHOTOS_FILE, chat_photos)

# ==================== AUTO-ADD FUNCTIONS ====================

def get_auto_settings(account_id):
    """Get auto-add settings for an account"""
    account_key = str(account_id)
    if account_key in auto_add_settings:
        return auto_add_settings[account_key]
    return {
        'enabled': False,
        'target_group': 'Abe_armygroup',
        'daily_limit': 30,
        'delay_seconds': 45,
        'added_today': 0,
        'last_reset': None,
        'auto_join': True
    }

def save_auto_settings(account_id, settings):
    """Save auto-add settings"""
    account_key = str(account_id)
    auto_add_settings[account_key] = settings
    save_auto_add_settings_file()

async def auto_join_target_group(client, target_group):
    """Auto-join target group for the account"""
    try:
        # Clean group name
        group_name = target_group
        if group_name.startswith('https://t.me/'):
            group_name = group_name.replace('https://t.me/', '@')
        elif not group_name.startswith('@'):
            group_name = '@' + group_name
        
        logger.info(f"Attempting to auto-join group: {group_name}")
        
        # Get the group entity
        group = await client.get_entity(group_name)
        logger.info(f"Found group: {group.title if hasattr(group, 'title') else group_name}")
        
        # Try to join
        try:
            await client(functions.channels.JoinChannelRequest(group))
            logger.info(f"✅ Successfully auto-joined group: {group_name}")
            return True
        except Exception as e:
            logger.warning(f"Could not join group {group_name}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error auto-joining group: {e}")
        return False

async def auto_add_worker(account_id):
    """Background worker for auto-add"""
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return
    
    # Initial auto-join check
    settings = get_auto_settings(account_id)
    if settings.get('auto_join', True):
        client = None
        try:
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                await auto_join_target_group(client, settings.get('target_group', 'Abe_armygroup'))
        except Exception as e:
            logger.error(f"Auto-join error on startup: {e}")
        finally:
            if client:
                await client.disconnect()
    
    while True:
        try:
            settings = get_auto_settings(account_id)
            if not settings.get('enabled'):
                break
            
            today = datetime.now().strftime('%Y-%m-%d')
            if settings.get('last_reset') != today:
                settings['added_today'] = 0
                settings['last_reset'] = today
                save_auto_settings(account_id, settings)
            
            if settings['added_today'] >= settings['daily_limit']:
                logger.info(f"Daily limit reached: {settings['added_today']}/{settings['daily_limit']}")
                await asyncio.sleep(3600)
                continue
            
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                # Auto-join if enabled
                if settings.get('auto_join', True):
                    await auto_join_target_group(client, settings.get('target_group', 'Abe_armygroup'))
                
                # Get target group
                target_group = settings.get('target_group', 'Abe_armygroup')
                group_name = target_group
                if not group_name.startswith('@') and not group_name.startswith('https://'):
                    group_name = '@' + group_name
                
                try:
                    group = await client.get_entity(group_name)
                    logger.info(f"Target group: {group.title if hasattr(group, 'title') else group_name}")
                except Exception as e:
                    logger.error(f"Target group not found: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get existing members
                existing = set()
                try:
                    async for user in client.iter_participants(group, limit=1000):
                        if user and user.id:
                            existing.add(user.id)
                    logger.info(f"Group has {len(existing)} existing members")
                except Exception as e:
                    logger.error(f"Error getting existing members: {e}")
                
                # Get contacts
                contacts = await client(functions.contacts.GetContactsRequest(0))
                new_members = []
                for user in contacts.users:
                    if user.id not in existing and not user.bot:
                        new_members.append(user)
                
                logger.info(f"Found {len(new_members)} new members to add")
                
                # Add members
                added = 0
                for user in new_members[:settings['daily_limit'] - settings['added_today']]:
                    try:
                        await client(functions.channels.InviteToChannelRequest(
                            group, [await client.get_input_entity(user.id)]
                        ))
                        settings['added_today'] += 1
                        added += 1
                        save_auto_settings(account_id, settings)
                        logger.info(f"✅ Added {user.first_name} to {target_group} ({settings['added_today']}/{settings['daily_limit']})")
                        await asyncio.sleep(settings['delay_seconds'])
                    except FloodWaitError as e:
                        logger.warning(f"Flood wait: {e.seconds}s")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        logger.error(f"Failed to add {user.id}: {e}")
                
                logger.info(f"Added {added} members this cycle")
                
            except Exception as e:
                logger.error(f"Auto-add loop error: {e}")
            finally:
                await client.disconnect()
            
            # Wait before next cycle
            wait_time = random.randint(1800, 3600)
            logger.info(f"Waiting {wait_time} seconds before next cycle...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Critical auto-add error: {e}")
            await asyncio.sleep(300)

def start_auto_add(account_id):
    """Start auto-add worker thread"""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auto_add_worker(account_id))
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    auto_add_threads[account_id] = thread
    logger.info(f"Started auto-add thread for account {account_id}")

# ==================== ACCOUNT FUNCTIONS ====================

def add_account(phone, name, username, session_string, photo=None):
    """Add new account"""
    new_id = 1
    if accounts:
        new_id = max([a['id'] for a in accounts]) + 1
    
    new_account = {
        'id': new_id,
        'phone': phone,
        'name': name,
        'username': username,
        'session': session_string,
        'photo': photo
    }
    accounts.append(new_account)
    save_accounts()
    return new_id

def remove_account_db(account_id):
    """Remove account"""
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    if str(account_id) in auto_add_settings:
        del auto_add_settings[str(account_id)]
    save_accounts()
    save_auto_add_settings_file()

def get_account_photo(account_id):
    """Get account photo"""
    for acc in accounts:
        if acc['id'] == account_id:
            return acc.get('photo')
    return None

def update_account_photo(account_id, photo):
    """Update account photo"""
    for acc in accounts:
        if acc['id'] == account_id:
            acc['photo'] = photo
            save_accounts()
            break

def get_chat_photo_db(account_id, chat_id):
    """Get cached chat photo"""
    key = f"{account_id}_{chat_id}"
    return chat_photos.get(key)

def save_chat_photo_db(account_id, chat_id, photo):
    """Save chat photo to cache"""
    key = f"{account_id}_{chat_id}"
    chat_photos[key] = photo
    save_chat_photos_file()

# Initialize data
load_all_data()

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

@app.route('/auto-add')
def auto_add(): 
    return send_file('auto_add.html')

@app.route('/settings')
def settings(): 
    return send_file('settings.html')

# ==================== HELPER FUNCTION ====================

def run_async(coro, timeout=45):
    """Run async function with timeout"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Operation timed out'}
        finally:
            loop.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({
        'success': True, 
        'accounts': [{'id': a['id'], 'phone': a['phone'], 'name': a['name'], 'username': a['username']} for a in accounts]
    })

@app.route('/api/account-info', methods=['POST'])
def get_account_info():
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_info():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                me = await client.get_me()
                photo = None
                try:
                    photo_data = await client.download_profile_photo(me, file=bytes)
                    if photo_data:
                        photo = base64.b64encode(photo_data).decode('utf-8')
                        update_account_photo(account['id'], photo)
                except:
                    pass
                return {
                    'success': True, 
                    'name': me.first_name or '', 
                    'username': me.username or '', 
                    'phone': me.phone or '', 
                    'photo': photo or account.get('photo')
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get_info()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account_route():
    try:
        phone = request.json.get('phone')
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                session_id = str(int(time.time()))
                temp_sessions[session_id] = {
                    'phone': phone, 
                    'hash': result.phone_code_hash, 
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': session_id}
            except FloodWaitError as e:
                return {'success': False, 'error': f'Wait {e.seconds} seconds'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send_code()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code, session_id, password = data.get('code'), data.get('session_id'), data.get('password', '')
        
        if session_id not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired'})
        
        session = temp_sessions[session_id]
        
        async def verify():
            client = TelegramClient(StringSession(session['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    await client.sign_in(session['phone'], code, phone_code_hash=session['hash'])
                except errors.SessionPasswordNeededError:
                    if not password:
                        return {'need_password': True}
                    await client.sign_in(password=password)
                
                me = await client.get_me()
                photo = None
                try:
                    photo_data = await client.download_profile_photo(me, file=bytes)
                    if photo_data:
                        photo = base64.b64encode(photo_data).decode('utf-8')
                except:
                    pass
                
                new_id = add_account(me.phone, me.first_name or 'User', me.username or '', client.session.save(), photo)
                
                # Auto-join target group after adding account
                settings = get_auto_settings(new_id)
                if settings.get('auto_join', True):
                    try:
                        await auto_join_target_group(client, settings.get('target_group', 'Abe_armygroup'))
                    except Exception as e:
                        logger.error(f"Auto-join after verification failed: {e}")
                
                return {'success': True}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        del temp_sessions[session_id]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account_route():
    try:
        account_id = request.json.get('accountId')
        remove_account_db(account_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    try:
        account_id, first_name = request.json.get('accountId'), request.json.get('firstName')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def update():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.UpdateProfileRequest(first_name=first_name))
                account['name'] = first_name
                save_accounts()
                return {'success': True}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(update()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-username', methods=['POST'])
def update_username():
    try:
        account_id = request.json.get('accountId')
        username = request.json.get('username', '').strip()
        if username.startswith('@'):
            username = username[1:]
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def update():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.UpdateUsernameRequest(username))
                account['username'] = username
                save_accounts()
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(update()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get all chats/dialogs for an account"""
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                dialogs = await client.get_dialogs(limit=200)
                chats = []
                for dialog in dialogs:
                    if not dialog:
                        continue
                    
                    # Determine chat type
                    chat_type = 'user'
                    if dialog.is_group:
                        chat_type = 'group'
                    elif dialog.is_channel:
                        chat_type = 'channel'
                    
                    # Get last message
                    last_message = ''
                    if dialog.message:
                        if dialog.message.text:
                            last_message = dialog.message.text[:100]
                        elif dialog.message.media:
                            last_message = '📎 Media'
                    
                    chat = {
                        'id': str(dialog.id),
                        'title': dialog.name or 'Unknown',
                        'type': chat_type,
                        'unread': dialog.unread_count or 0,
                        'lastMessage': last_message,
                        'lastMessageDate': int(dialog.message.date.timestamp()) if dialog.message and dialog.message.date else 0
                    }
                    chats.append(chat)
                
                # Sort by last message date
                chats.sort(key=lambda x: x['lastMessageDate'], reverse=True)
                
                return {'success': True, 'chats': chats}
            except AuthKeyUnregisteredError:
                return {'success': False, 'error': 'auth_key_unregistered'}
            except Exception as e:
                logger.error(f"Error in get-messages: {e}")
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch(), timeout=45))
    except Exception as e:
        logger.error(f"Error in get_messages route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-messages', methods=['POST'])
def get_chat_messages():
    """Get messages from a specific chat"""
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        chat_id = data.get('chatId')
        limit = data.get('limit', 100)
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                # Get entity
                try:
                    entity = await client.get_entity(int(chat_id))
                except:
                    try:
                        entity = await client.get_entity(chat_id)
                    except:
                        return {'success': False, 'error': 'Chat not found'}
                
                # Chat info
                chat_info = {
                    'id': str(entity.id),
                    'title': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 
                            'group' if hasattr(entity, 'megagroup') else 'user',
                    'username': getattr(entity, 'username', None)
                }
                
                # Get last seen for users
                if chat_info['type'] == 'user' and hasattr(entity, 'status'):
                    if hasattr(entity.status, 'was_online'):
                        chat_info['last_seen'] = int(entity.status.was_online.timestamp())
                    elif hasattr(entity.status, 'expires'):
                        chat_info['online'] = True
                
                # Get messages
                messages = []
                async for msg in client.iter_messages(entity, limit=limit):
                    message = {
                        'id': msg.id,
                        'text': msg.text or '',
                        'date': int(msg.date.timestamp()) if msg.date else 0,
                        'out': msg.out,
                        'has_media': msg.media is not None,
                        'media_type': None,
                        'media_data': None
                    }
                    
                    # Handle media
                    if msg.media:
                        if hasattr(msg.media, 'photo'):
                            message['media_type'] = 'photo'
                            try:
                                # Get thumbnail
                                thumb = await client.download_file(msg.media, bytes)
                                if thumb:
                                    # Resize for thumbnail
                                    message['media_data'] = base64.b64encode(thumb[:5000]).decode('utf-8')
                            except:
                                pass
                        elif hasattr(msg.media, 'document'):
                            message['media_type'] = 'document'
                        elif hasattr(msg.media, 'video'):
                            message['media_type'] = 'video'
                        elif hasattr(msg.media, 'audio'):
                            message['media_type'] = 'audio'
                    
                    messages.append(message)
                
                # Reverse to show oldest first
                messages.reverse()
                
                return {'success': True, 'messages': messages, 'chat_info': chat_info}
            except Exception as e:
                logger.error(f"Error in get-chat-messages: {e}")
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch(), timeout=60))
    except Exception as e:
        logger.error(f"Error in get_chat_messages route: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-photo', methods=['POST'])
def get_chat_photo():
    """Get profile photo of a chat/user"""
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        
        # Check cache first
        cached = get_chat_photo_db(account_id, chat_id)
        if cached:
            return jsonify({'success': True, 'photo': cached})
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                entity = await client.get_entity(int(chat_id))
                photo = await client.download_profile_photo(entity, file=bytes)
                if photo:
                    photo_base64 = base64.b64encode(photo).decode('utf-8')
                    save_chat_photo_db(account_id, chat_id, photo_base64)
                    return {'success': True, 'photo': photo_base64}
                return {'success': True, 'photo': None}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a text message"""
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                entity = await client.get_entity(int(data.get('chatId')))
                await client.send_message(entity, data.get('message'))
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-media', methods=['POST'])
def send_media():
    """Send media file (photo, video, document)"""
    try:
        account_id = request.form.get('accountId')
        chat_id = request.form.get('chatId')
        caption = request.form.get('caption', '')
        file = request.files.get('file')
        
        if not file:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        account = next((a for a in accounts if a['id'] == int(account_id)), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                entity = await client.get_entity(int(chat_id))
                file_data = file.read()
                
                # Send based on file type
                if file.content_type.startswith('image/'):
                    await client.send_file(entity, file_data, caption=caption)
                elif file.content_type.startswith('video/'):
                    await client.send_file(entity, file_data, caption=caption)
                else:
                    await client.send_file(entity, file_data, caption=caption)
                
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send(), timeout=60))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set-2fa', methods=['POST'])
def set_2fa():
    """Set up two-step verification"""
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def set_2fa_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                pwd = await client(functions.account.GetPasswordRequest())
                new_settings = types.account.PasswordInputSettings(
                    new_algo=pwd.new_algo,
                    new_password_hash=pwd.new_algo.hash(data.get('newPassword').encode('utf-8')),
                    hint=data.get('hint', '')
                )
                if data.get('email'):
                    new_settings.email = data.get('email')
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=data.get('currentPassword', '') if data.get('currentPassword') else pwd.current_password,
                    new_settings=new_settings
                ))
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(set_2fa_async()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    """Get active sessions for account"""
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                result = await client(functions.account.GetAuthorizationsRequest())
                sessions = []
                for auth in result.authorizations:
                    sessions.append({
                        'device_model': auth.device_model,
                        'platform': auth.platform,
                        'ip': auth.ip,
                        'country': auth.country,
                        'date_active': auth.date_active,
                        'current': auth.current
                    })
                return {'success': True, 'sessions': sessions}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    """Terminate all other sessions"""
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Account not authorized'}
                
                result = await client(functions.account.GetAuthorizationsRequest())
                current = None
                for auth in result.authorizations:
                    if auth.current:
                        current = auth.hash
                        break
                count = 0
                for auth in result.authorizations:
                    if auth.hash != current:
                        try:
                            await client(functions.account.ResetAuthorizationRequest(auth.hash))
                            count += 1
                        except:
                            pass
                return {'success': True, 'count': count}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add():
    """Get auto-add settings"""
    try:
        settings = get_auto_settings(int(request.args.get('accountId')))
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add():
    """Update auto-add settings"""
    try:
        data = request.json
        settings = {
            'enabled': data.get('enabled', False),
            'target_group': data.get('target_group', 'Abe_armygroup'),
            'daily_limit': data.get('daily_limit', 30),
            'delay_seconds': data.get('delay_seconds', 45),
            'added_today': 0,
            'last_reset': datetime.now().strftime('%Y-%m-%d'),
            'auto_join': data.get('auto_join', True)
        }
        account_id = int(data.get('accountId'))
        save_auto_settings(account_id, settings)
        
        if settings['enabled']:
            start_auto_add(account_id)
        
        # Also trigger auto-join immediately if enabled
        if settings['auto_join']:
            account = next((a for a in accounts if a['id'] == account_id), None)
            if account:
                async def join_async():
                    client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
                    await client.connect()
                    try:
                        if await client.is_user_authorized():
                            await auto_join_target_group(client, settings['target_group'])
                    finally:
                        await client.disconnect()
                
                threading.Thread(target=lambda: run_async(join_async()), daemon=True).start()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_stats():
    """Get auto-add statistics"""
    try:
        settings = get_auto_settings(int(request.args.get('accountId')))
        return jsonify({
            'success': True,
            'added_today': settings.get('added_today', 0),
            'daily_limit': settings.get('daily_limit', 30),
            'enabled': settings.get('enabled', False)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_add': len(auto_add_threads),
        'time': datetime.now().isoformat()
    })

@app.route('/ping')
def ping():
    return 'pong'

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled error: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500

# ==================== STARTUP ====================

def start_all_auto_add():
    """Start auto-add for all enabled accounts"""
    for account_id_str, settings in auto_add_settings.items():
        if settings.get('enabled'):
            start_auto_add(int(account_id_str))

if __name__ == '__main__':
    import random
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM ACCOUNT MANAGER')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print(f'✅ Auto-add enabled: {len([s for s in auto_add_settings.values() if s.get(\"enabled\")])}')
    print(f'✅ Storage: {ACCOUNTS_FILE}')
    print('='*70)
    print('\n🚀 FEATURES:')
    print('   • Multi-account management')
    print('   • Auto-add members to groups')
    print('   • Auto-join target groups')
    print('   • Send and receive messages')
    print('   • Media upload (photos, videos)')
    print('   • Profile pictures')
    print('   • Two-step verification (2FA)')
    print('   • Session management')
    print('   • Persistent JSON storage')
    print('='*70 + '\n')
    
    # Start auto-add for enabled accounts
    start_all_auto_add()
    
    # Run Flask
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
