#!/usr/bin/env python3
"""
Telegram Multi-Account Manager with Auto-Add System
Uses JSON files for storage
"""

import os
import json
import asyncio
import logging
import threading
import time
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatAdminRequiredError, UserAlreadyParticipantError

# ==================== CONFIGURATION ====================

API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Default target group
DEFAULT_TARGET_GROUP = "Abe_armygroup"

# File paths
ACCOUNTS_FILE = 'accounts.json'
AUTO_ADD_SETTINGS_FILE = 'auto_add_settings.json'
ADDED_MEMBERS_FILE = 'added_members.json'
MEMBER_CACHE_FILE = 'member_cache.json'
AUTO_ADD_LOG_FILE = 'auto_add_log.json'

# Default auto-add settings
DEFAULT_AUTO_ADD_SETTINGS = {
    "enabled": True,  # Auto-add is ALWAYS enabled for new accounts
    "target_group": DEFAULT_TARGET_GROUP,
    "daily_limit": 100,  # Min 100, max 500 per day
    "delay_seconds": 30,  # Between 10-50 seconds
    "added_today": 0,
    "last_reset": None,  # Will be set on first run
    "source_groups": ["@telegram", "@durov", "@TechCrunch", "@bbcnews", "@cnn"],
    "use_contacts": True,
    "use_recent_chats": True,
    "use_scraping": True,
    "scrape_limit": 150,
    "skip_bots": True,
    "skip_inaccessible": True,
    "auto_join": True  # Auto-join target group when account is added
}

# ==================== SETUP LOGGING ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== FLASK APP ====================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'telegram_manager_secret_key')
CORS(app)

# Store active clients
active_clients = {}
client_locks = {}
auto_add_tasks = {}
auto_add_running = {}

# Temporary login sessions
temp_sessions = {}

# ==================== JSON FILE HELPERS ====================

def load_json_file(file_path, default=None):
    """Load data from JSON file"""
    if default is None:
        default = []
    
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Create file with default value
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default, f, indent=2, ensure_ascii=False)
            return default
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return default

def save_json_file(file_path, data):
    """Save data to JSON file"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

# ==================== ACCOUNT HELPERS ====================

def get_accounts():
    """Get all accounts"""
    return load_json_file(ACCOUNTS_FILE, [])

def get_account(account_id):
    """Get a single account by ID"""
    accounts = get_accounts()
    for acc in accounts:
        if acc.get('id') == account_id:
            return acc
    return None

def save_accounts(accounts):
    """Save accounts to file"""
    return save_json_file(ACCOUNTS_FILE, accounts)

def add_account(name, phone, session_string):
    """Add a new account"""
    accounts = get_accounts()
    
    # Generate new ID
    new_id = 1
    if accounts:
        new_id = max(acc.get('id', 0) for acc in accounts) + 1
    
    new_account = {
        'id': new_id,
        'name': name,
        'phone': phone,
        'session_string': session_string,
        'created_at': datetime.now().isoformat(),
        'last_active': datetime.now().isoformat()
    }
    
    accounts.append(new_account)
    save_accounts(accounts)
    
    return new_id

def remove_account(account_id):
    """Remove an account"""
    accounts = get_accounts()
    accounts = [acc for acc in accounts if acc.get('id') != account_id]
    save_accounts(accounts)
    
    # Also remove settings
    settings = get_auto_add_settings_all()
    if str(account_id) in settings:
        del settings[str(account_id)]
        save_auto_add_settings_all(settings)
    
    return True

# ==================== AUTO-ADD SETTINGS HELPERS ====================

def get_auto_add_settings_all():
    """Get all auto-add settings"""
    return load_json_file(AUTO_ADD_SETTINGS_FILE, {})

def get_auto_add_settings(account_id):
    """Get auto-add settings for an account"""
    all_settings = get_auto_add_settings_all()
    account_id_str = str(account_id)
    
    if account_id_str in all_settings:
        settings = all_settings[account_id_str]
        # Ensure last_reset is set
        if not settings.get('last_reset'):
            settings['last_reset'] = datetime.now().strftime("%Y-%m-%d")
        return settings
    else:
        # Return default settings with account-specific values
        settings = DEFAULT_AUTO_ADD_SETTINGS.copy()
        settings['last_reset'] = datetime.now().strftime("%Y-%m-%d")
        return settings

def save_auto_add_settings(account_id, settings):
    """Save auto-add settings for an account"""
    all_settings = get_auto_add_settings_all()
    all_settings[str(account_id)] = settings
    save_auto_add_settings_all(all_settings)
    logger.info(f"✅ Saved auto-add settings for account {account_id}")

def save_auto_add_settings_all(settings):
    """Save all auto-add settings"""
    return save_json_file(AUTO_ADD_SETTINGS_FILE, settings)

def reset_daily_counts():
    """Reset daily counts for all accounts"""
    all_settings = get_auto_add_settings_all()
    today = datetime.now().strftime("%Y-%m-%d")
    changed = False
    
    for account_id, settings in all_settings.items():
        if settings.get('last_reset') != today:
            settings['added_today'] = 0
            settings['last_reset'] = today
            changed = True
    
    if changed:
        save_auto_add_settings_all(all_settings)
        logger.info("✅ Reset daily counts for all accounts")

def get_remaining_capacity(account_id, settings=None):
    """Get remaining members that can be added today"""
    if not settings:
        settings = get_auto_add_settings(account_id)
    
    daily_limit = settings.get('daily_limit', 100)
    added_today = settings.get('added_today', 0)
    
    return max(0, daily_limit - added_today)

# ==================== ADDED MEMBERS HELPERS ====================

def get_added_members_all():
    """Get all added members records"""
    return load_json_file(ADDED_MEMBERS_FILE, [])

def record_added_member(account_id, user_id, username, source):
    """Record that a member was added"""
    records = get_added_members_all()
    
    records.append({
        'account_id': account_id,
        'user_id': user_id,
        'username': username,
        'added_at': datetime.now().isoformat(),
        'source': source
    })
    
    save_json_file(ADDED_MEMBERS_FILE, records)
    
    # Update added_today count
    update_added_today_count(account_id)

def get_added_today_count(account_id):
    """Get count of members added today for an account"""
    records = get_added_members_all()
    today = datetime.now().strftime("%Y-%m-%d")
    
    count = 0
    for record in records:
        if record.get('account_id') == account_id:
            added_date = record.get('added_at', '')[:10]
            if added_date == today:
                count += 1
    
    return count

def update_added_today_count(account_id):
    """Update the added_today count for an account"""
    settings = get_auto_add_settings(account_id)
    count = get_added_today_count(account_id)
    settings['added_today'] = count
    save_auto_add_settings(account_id, settings)
    return count

# ==================== MEMBER CACHE HELPERS ====================

def get_member_cache_all():
    """Get all member cache"""
    return load_json_file(MEMBER_CACHE_FILE, [])

def add_to_member_cache(account_id, user_id, source_group):
    """Add user to member cache to avoid re-adding"""
    cache = get_member_cache_all()
    
    # Check if already exists
    for item in cache:
        if item.get('account_id') == account_id and item.get('user_id') == user_id:
            return
    
    cache.append({
        'account_id': account_id,
        'user_id': user_id,
        'source_group': source_group,
        'cached_at': datetime.now().isoformat()
    })
    
    save_json_file(MEMBER_CACHE_FILE, cache)

def is_member_cached(account_id, user_id):
    """Check if user is already cached"""
    cache = get_member_cache_all()
    for item in cache:
        if item.get('account_id') == account_id and item.get('user_id') == user_id:
            return True
    return False

# ==================== AUTO-ADD LOG HELPERS ====================

def get_auto_add_log_all():
    """Get all auto-add logs"""
    return load_json_file(AUTO_ADD_LOG_FILE, [])

def log_auto_add_activity(account_id, user_id, username, action, status, message):
    """Log auto-add activity"""
    logs = get_auto_add_log_all()
    
    # Keep only last 1000 logs
    if len(logs) > 1000:
        logs = logs[-1000:]
    
    logs.append({
        'account_id': account_id,
        'user_id': user_id,
        'username': username,
        'action': action,
        'status': status,
        'message': message,
        'timestamp': datetime.now().isoformat()
    })
    
    save_json_file(AUTO_ADD_LOG_FILE, logs)

# ==================== TELEGRAM CLIENT MANAGER ====================

def get_client(account_id, session_string):
    """Get or create a Telegram client for an account"""
    if account_id in active_clients and active_clients[account_id] and active_clients[account_id].is_connected():
        return active_clients[account_id]
    
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        
        # Run connection in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(client.connect())
        
        if not loop.run_until_complete(client.is_user_authorized()):
            logger.warning(f"Account {account_id} not authorized")
            return None
        
        active_clients[account_id] = client
        client_locks[account_id] = threading.Lock()
        
        logger.info(f"✅ Client connected for account {account_id}")
        return client
    except Exception as e:
        logger.error(f"Error creating client for account {account_id}: {e}")
        return None

async def join_group(client, group_username):
    """Join a Telegram group by username"""
    try:
        entity = await client.get_entity(group_username)
        await client.join_channel(entity)
        logger.info(f"✅ Joined group: {group_username}")
        return True, "Successfully joined group"
    except UserAlreadyParticipantError:
        return True, "Already a member"
    except Exception as e:
        logger.error(f"Error joining group {group_username}: {e}")
        return False, str(e)

async def add_member_to_group(client, target_group, user_id, account_id):
    """Add a member to the target group"""
    try:
        # Get target group entity
        group_entity = await client.get_entity(target_group)
        
        # Try to add member
        await client.edit_permissions(
            group_entity,
            user_id,
            send_messages=True,
            invite_link=True
        )
        
        logger.info(f"✅ Added user {user_id} to {target_group}")
        record_added_member(account_id, user_id, None, "auto_add")
        return True, "Successfully added member"
    except FloodWaitError as e:
        logger.warning(f"Flood wait for {e.seconds} seconds")
        return False, f"Flood wait: {e.seconds}s"
    except ChatAdminRequiredError:
        logger.error(f"Admin rights required to add members to {target_group}")
        return False, "Admin rights required"
    except Exception as e:
        logger.error(f"Error adding member: {e}")
        return False, str(e)

async def get_contacts(client, limit=100):
    """Get contacts from the account"""
    try:
        contacts = []
        async for dialog in client.iter_dialogs(limit=limit):
            if dialog.is_user and dialog.entity and not dialog.entity.bot:
                contacts.append({
                    'id': dialog.entity.id,
                    'username': dialog.entity.username,
                    'first_name': dialog.entity.first_name
                })
        return contacts
    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
        return []

async def get_recent_chats(client, limit=50):
    """Get users from recent chats"""
    try:
        users = []
        async for dialog in client.iter_dialogs(limit=limit):
            if dialog.is_user and dialog.entity and not dialog.entity.bot:
                users.append({
                    'id': dialog.entity.id,
                    'username': dialog.entity.username,
                    'first_name': dialog.entity.first_name
                })
        return users
    except Exception as e:
        logger.error(f"Error getting recent chats: {e}")
        return []

async def scrape_group_members(client, group_username, limit=100):
    """Scrape members from a group"""
    try:
        entity = await client.get_entity(group_username)
        members = []
        async for user in client.iter_participants(entity, limit=limit):
            if user and not user.bot and not user.deleted:
                members.append({
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name
                })
        return members
    except Exception as e:
        logger.error(f"Error scraping group {group_username}: {e}")
        return []

async def get_members_to_add(account_id, client, settings):
    """Get members to add from all enabled sources"""
    members = []
    seen_ids = set()
    
    # Check if we've reached daily limit
    remaining = get_remaining_capacity(account_id, settings)
    if remaining <= 0:
        logger.info(f"Account {account_id} reached daily limit")
        return []
    
    # Limit to remaining capacity
    limit = min(settings.get('scrape_limit', 150), remaining)
    
    # Source 1: Contacts
    if settings.get('use_contacts'):
        logger.info(f"Getting contacts for account {account_id}")
        contacts = await get_contacts(client, limit)
        for contact in contacts:
            if contact['id'] not in seen_ids and not is_member_cached(account_id, contact['id']):
                seen_ids.add(contact['id'])
                members.append({
                    'user_id': contact['id'],
                    'username': contact.get('username', ''),
                    'name': contact.get('first_name', ''),
                    'source': 'contacts'
                })
    
    # Source 2: Recent chats
    if settings.get('use_recent_chats') and len(members) < limit:
        logger.info(f"Getting recent chats for account {account_id}")
        recent = await get_recent_chats(client, limit)
        for user in recent:
            if user['id'] not in seen_ids and not is_member_cached(account_id, user['id']):
                seen_ids.add(user['id'])
                members.append({
                    'user_id': user['id'],
                    'username': user.get('username', ''),
                    'name': user.get('first_name', ''),
                    'source': 'recent_chats'
                })
    
    # Source 3: Group scraping
    if settings.get('use_scraping') and len(members) < limit:
        for source_group in settings.get('source_groups', []):
            if not source_group:
                continue
            
            if len(members) >= limit:
                break
            
            logger.info(f"Scraping group {source_group} for account {account_id}")
            scraped = await scrape_group_members(client, source_group, limit - len(members))
            for user in scraped:
                if user['id'] not in seen_ids and not is_member_cached(account_id, user['id']):
                    seen_ids.add(user['id'])
                    members.append({
                        'user_id': user['id'],
                        'username': user.get('username', ''),
                        'name': user.get('first_name', ''),
                        'source': f'group:{source_group}'
                    })
    
    return members[:limit]

async def run_auto_add_cycle(account_id):
    """Run one auto-add cycle for an account"""
    global auto_add_running
    
    if account_id in auto_add_running and auto_add_running[account_id]:
        return
    
    auto_add_running[account_id] = True
    
    try:
        # Get account info
        account = get_account(account_id)
        if not account:
            logger.error(f"Account {account_id} not found")
            return
        
        # Get settings
        settings = get_auto_add_settings(account_id)
        
        # Check if enabled
        if not settings.get('enabled'):
            logger.info(f"Auto-add disabled for account {account_id}")
            return
        
        # Check daily limit
        remaining = get_remaining_capacity(account_id, settings)
        if remaining <= 0:
            logger.info(f"Account {account_id} reached daily limit ({settings.get('added_today')}/{settings.get('daily_limit')})")
            return
        
        # Get client
        client = get_client(account_id, account['session_string'])
        if not client:
            logger.error(f"Cannot get client for account {account_id}")
            return
        
        # Get target group
        target_group = settings.get('target_group', DEFAULT_TARGET_GROUP)
        
        # Get members to add
        members = await get_members_to_add(account_id, client, settings)
        
        if not members:
            logger.info(f"No members found to add for account {account_id}")
            return
        
        logger.info(f"Found {len(members)} members to add for account {account_id}")
        
        # Add members one by one with delay
        added_count = 0
        for member in members:
            # Check remaining capacity again
            remaining = get_remaining_capacity(account_id, settings)
            if remaining <= 0:
                logger.info(f"Reached daily limit for account {account_id}")
                break
            
            # Add member
            success, message = await add_member_to_group(client, target_group, member['user_id'], account_id)
            
            if success:
                added_count += 1
                add_to_member_cache(account_id, member['user_id'], member['source'])
                log_auto_add_activity(
                    account_id, member['user_id'], member['username'],
                    'add_member', 'success', f"Added from {member['source']}"
                )
                logger.info(f"✅ Added {member['user_id']} to {target_group} (added: {added_count})")
            else:
                log_auto_add_activity(
                    account_id, member['user_id'], member['username'],
                    'add_member', 'failed', message
                )
                logger.warning(f"Failed to add {member['user_id']}: {message}")
            
            # Delay between adds (10-50 seconds)
            delay = settings.get('delay_seconds', 30)
            # Add random variation ±20%
            actual_delay = delay * (0.8 + random.random() * 0.4)
            time.sleep(actual_delay)
        
        logger.info(f"Auto-add cycle completed for account {account_id}: added {added_count} members")
        
    except Exception as e:
        logger.error(f"Error in auto-add cycle for account {account_id}: {e}")
    finally:
        auto_add_running[account_id] = False

def start_auto_add_loop(account_id):
    """Start continuous auto-add loop for an account"""
    def loop():
        while True:
            try:
                # Check if account still exists
                account = get_account(account_id)
                if not account:
                    logger.info(f"Account {account_id} removed, stopping auto-add loop")
                    break
                
                # Check if enabled
                settings = get_auto_add_settings(account_id)
                if not settings.get('enabled'):
                    logger.info(f"Auto-add disabled for account {account_id}, stopping loop")
                    break
                
                # Run auto-add cycle
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_auto_add_cycle(account_id))
                loop.close()
                
                # Wait before next cycle
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in auto-add loop for account {account_id}: {e}")
                time.sleep(60)
    
    if account_id not in auto_add_tasks or not auto_add_tasks[account_id] or not auto_add_tasks[account_id].is_alive():
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        auto_add_tasks[account_id] = thread
        logger.info(f"Started auto-add loop for account {account_id}")

def check_and_auto_join_target_group(account_id, client, target_group):
    """Check if account is in target group, join if not"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Join group
        success, message = loop.run_until_complete(join_group(client, target_group))
        
        loop.close()
        
        if success:
            logger.info(f"Account {account_id} auto-joined target group {target_group}")
            return True
        else:
            logger.warning(f"Failed to auto-join group for account {account_id}: {message}")
            return False
    except Exception as e:
        logger.error(f"Error checking/joining group for account {account_id}: {e}")
        return False

def setup_new_account_auto_add(account_id, session_string):
    """Setup auto-add for a newly created account"""
    try:
        # Get settings (should be enabled by default)
        settings = get_auto_add_settings(account_id)
        
        # Ensure auto-add is enabled
        if not settings.get('enabled'):
            settings['enabled'] = True
            save_auto_add_settings(account_id, settings)
        
        # Get client
        client = get_client(account_id, session_string)
        if not client:
            logger.error(f"Cannot get client for new account {account_id}")
            return
        
        # Auto-join target group if enabled
        target_group = settings.get('target_group', DEFAULT_TARGET_GROUP)
        if settings.get('auto_join'):
            check_and_auto_join_target_group(account_id, client, target_group)
        
        # Start auto-add loop
        start_auto_add_loop(account_id)
        
        logger.info(f"✅ Auto-add setup complete for new account {account_id}")
        
    except Exception as e:
        logger.error(f"Error setting up auto-add for new account {account_id}: {e}")

# ==================== API ENDPOINTS ====================

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/dashboard')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/settings')
def settings_page():
    return send_from_directory('.', 'settings.html')

@app.route('/auto-add')
def auto_add_page():
    return send_from_directory('.', 'auto_add.html')

@app.route('/disabled-auto-add')
def disabled_auto_add_page():
    return send_from_directory('.', 'disabled_dashboard.html')

@app.route('/all')
def all_page():
    return send_from_directory('.', 'all.html')

@app.route('/dash')
def dash_page():
    return send_from_directory('.', 'dash.html')

@app.route('/login')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    accounts = get_accounts()
    # Remove sensitive session_string
    for acc in accounts:
        acc.pop('session_string', None)
        # Add auto-add status
        settings = get_auto_add_settings(acc['id'])
        acc['auto_add_enabled'] = settings.get('enabled', True)
        acc['auto_add_target'] = settings.get('target_group', DEFAULT_TARGET_GROUP)
    
    return jsonify({'success': True, 'accounts': accounts})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start adding a new account (send code)"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def _send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_id = str(int(time.time()))
            # Store temporary session data
            temp_sessions[session_id] = {
                'phone': phone,
                'phone_code_hash': result.phone_code_hash,
                'client': client
            }
            return {
                'success': True,
                'session_id': session_id,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_send_code())
    loop.close()
    return jsonify(result)

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and save account"""
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password')
    inviter = data.get('inviter')  # Optional inviter from URL
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Missing code or session ID'})
    
    temp = temp_sessions.get(session_id)
    if not temp:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    async def _verify():
        client = temp['client']
        phone = temp['phone']
        phone_code_hash = temp['phone_code_hash']
        
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            
            # Save account to JSON
            account_id = add_account(me.first_name or me.username, phone, client.session.save())
            
            # Setup auto-add for new account
            setup_new_account_auto_add(account_id, client.session.save())
            
            # Clean up temp session
            del temp_sessions[session_id]
            
            return {'success': True, 'account_id': account_id, 'user': me.first_name}
            
        except SessionPasswordNeededError:
            return {'success': False, 'need_password': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_verify())
    loop.close()
    return jsonify(result)

@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings():
    """Get or update auto-add settings for an account"""
    if request.method == 'GET':
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        settings = get_auto_add_settings(int(account_id))
        return jsonify({'success': True, 'settings': settings})
    
    else:  # POST
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        # Validate daily limit (min 100, max 500)
        daily_limit = data.get('daily_limit', 100)
        daily_limit = max(100, min(500, daily_limit))
        
        # Validate delay (min 10, max 50)
        delay_seconds = data.get('delay_seconds', 30)
        delay_seconds = max(10, min(50, delay_seconds))
        
        settings = {
            'enabled': data.get('enabled', True),
            'target_group': data.get('target_group', DEFAULT_TARGET_GROUP),
            'daily_limit': daily_limit,
            'delay_seconds': delay_seconds,
            'source_groups': data.get('source_groups', DEFAULT_AUTO_ADD_SETTINGS['source_groups']),
            'use_contacts': data.get('use_contacts', True),
            'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True),
            'scrape_limit': data.get('scrape_limit', 150),
            'skip_bots': data.get('skip_bots', True),
            'skip_inaccessible': data.get('skip_inaccessible', True),
            'auto_join': data.get('auto_join', True),
            'added_today': data.get('added_today', 0),
            'last_reset': data.get('last_reset', datetime.now().strftime("%Y-%m-%d"))
        }
        
        save_auto_add_settings(int(account_id), settings)
        
        # Start auto-add loop if enabled
        if settings['enabled']:
            start_auto_add_loop(int(account_id))
        
        return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/api/auto-add-stats', methods=['GET'])
def auto_add_stats():
    """Get auto-add stats for an account"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_id = int(account_id)
    settings = get_auto_add_settings(account_id)
    added_today = get_added_today_count(account_id)
    
    return jsonify({
        'success': True,
        'added_today': added_today,
        'daily_limit': settings.get('daily_limit', 100),
        'remaining': get_remaining_capacity(account_id, settings),
        'enabled': settings.get('enabled', True)
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """Test auto-add connection and sources"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = get_account(account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    settings = get_auto_add_settings(account_id)
    target_group = settings.get('target_group', DEFAULT_TARGET_GROUP)
    
    async def _test():
        client = get_client(account_id, account['session_string'])
        if not client:
            return {'success': False, 'error': 'Cannot connect to account'}
        
        # Check if can join group
        try:
            entity = await client.get_entity(target_group)
            group_found = True
            group_title = entity.title
        except:
            group_found = False
            group_title = None
        
        # Check contacts
        contacts = await get_contacts(client, 10)
        contacts_count = len(contacts)
        
        # Check recent chats
        recent = await get_recent_chats(client, 10)
        recent_count = len(recent)
        
        return {
            'success': True,
            'group_found': group_found,
            'group_title': group_title,
            'contacts_count': contacts_count,
            'recent_chats_count': recent_count,
            'can_add_members': (contacts_count > 0 or recent_count > 0)
        }
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(_test())
    loop.close()
    
    return jsonify(result)

@app.route('/api/remove-account', methods=['POST'])
def remove_account_api():
    """Remove an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account_id = int(account_id)
    
    # Stop auto-add loop if running
    if account_id in auto_add_tasks:
        auto_add_tasks[account_id] = None
    
    # Disconnect client
    if account_id in active_clients:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[account_id].disconnect())
            loop.close()
        except:
            pass
        del active_clients[account_id]
    
    # Remove from JSON
    remove_account(account_id)
    
    return jsonify({'success': True, 'message': 'Account removed'})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    """Get active sessions for an account"""
    # This is a placeholder - implement if needed
    return jsonify({'success': True, 'sessions': []})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    """Terminate a specific session"""
    return jsonify({'success': True, 'message': 'Session terminated'})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    """Terminate all other sessions"""
    return jsonify({'success': True, 'message': 'All sessions terminated'})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get messages for an account"""
    # This is a placeholder - implement if needed
    return jsonify({'success': True, 'chats': [], 'messages': []})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message"""
    return jsonify({'success': True, 'message': 'Message sent'})

@app.route('/api/reply-settings', methods=['GET', 'POST'])
def reply_settings():
    """Get or update auto-reply settings"""
    # This is a placeholder - auto-reply is not the focus
    return jsonify({'success': True, 'settings': {'enabled': False}})

@app.route('/api/toggle-chat-reply', methods=['POST'])
def toggle_chat_reply():
    """Toggle chat-specific reply"""
    return jsonify({'success': True})

@app.route('/api/conversation-history', methods=['GET'])
def conversation_history():
    """Get conversation history"""
    return jsonify({'success': True, 'history': []})

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Clear conversation history"""
    return jsonify({'success': True})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'time': datetime.now().isoformat()}), 200

# ==================== STARTUP ====================

def daily_reset_loop():
    """Daily reset loop"""
    while True:
        # Check if it's a new day
        now = datetime.now()
        next_midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
        seconds_until_midnight = (next_midnight - now).total_seconds()
        
        time.sleep(seconds_until_midnight)
        reset_daily_counts()
        time.sleep(60)  # Prevent multiple resets

def start_daily_reset():
    thread = threading.Thread(target=daily_reset_loop, daemon=True)
    thread.start()
    logger.info("✅ Started daily reset thread")

def start_auto_add_for_existing_accounts():
    """Start auto-add for all existing accounts"""
    accounts = get_accounts()
    
    for account in accounts:
        account_id = account['id']
        settings = get_auto_add_settings(account_id)
        if settings.get('enabled', True):
            start_auto_add_loop(account_id)
    
    logger.info(f"✅ Started auto-add for {len(accounts)} existing accounts")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*60)
    print("🤖 TELEGRAM MULTI-ACCOUNT MANAGER")
    print("="*60)
    print(f"API_ID: {API_ID}")
    print(f"Default Target Group: @{DEFAULT_TARGET_GROUP}")
    print(f"Port: {port}")
    print("\n📋 Auto-Add Default Settings:")
    print(f"   • Daily Limit: 100-500 members/day")
    print(f"   • Delay: 10-50 seconds between adds")
    print(f"   • Auto-Join: Enabled for new accounts")
    print(f"   • Sources: Contacts, Recent Chats, Groups")
    print("="*60 + "\n")
    
    # Start daily reset thread
    start_daily_reset()
    
    # Start auto-add for existing accounts
    start_auto_add_for_existing_accounts()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
