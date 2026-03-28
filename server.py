#!/usr/bin/env python3
"""
Telegram Multi-Account Manager with Auto-Add System
"""

import os
import json
import sqlite3
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
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatAdminRequiredError

# ==================== CONFIGURATION ====================

API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Default target group
DEFAULT_TARGET_GROUP = "Abe_armygroup"

# Auto-add default settings
DEFAULT_AUTO_ADD_SETTINGS = {
    "enabled": True,  # Auto-add is ALWAYS enabled for new accounts
    "target_group": DEFAULT_TARGET_GROUP,
    "daily_limit": 100,  # Min 100, max 500 per day
    "delay_seconds": 30,  # Between 10-50 seconds
    "added_today": 0,
    "last_reset": datetime.now().strftime("%Y-%m-%d"),
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

# ==================== DATABASE SETUP ====================

def init_database():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect('telegram_accounts.db')
    c = conn.cursor()
    
    # Accounts table
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  phone TEXT,
                  session_string TEXT,
                  created_at TIMESTAMP,
                  last_active TIMESTAMP,
                  auto_add_enabled INTEGER DEFAULT 1)''')
    
    # Auto-add settings table
    c.execute('''CREATE TABLE IF NOT EXISTS auto_add_settings
                 (account_id INTEGER PRIMARY KEY,
                  enabled INTEGER DEFAULT 1,
                  target_group TEXT,
                  daily_limit INTEGER DEFAULT 100,
                  delay_seconds INTEGER DEFAULT 30,
                  added_today INTEGER DEFAULT 0,
                  last_reset TEXT,
                  source_groups TEXT,
                  use_contacts INTEGER DEFAULT 1,
                  use_recent_chats INTEGER DEFAULT 1,
                  use_scraping INTEGER DEFAULT 1,
                  scrape_limit INTEGER DEFAULT 150,
                  skip_bots INTEGER DEFAULT 1,
                  skip_inaccessible INTEGER DEFAULT 1,
                  auto_join INTEGER DEFAULT 1,
                  FOREIGN KEY (account_id) REFERENCES accounts(id))''')
    
    # Added members tracking
    c.execute('''CREATE TABLE IF NOT EXISTS added_members
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  account_id INTEGER,
                  user_id INTEGER,
                  username TEXT,
                  added_at TIMESTAMP,
                  source TEXT,
                  FOREIGN KEY (account_id) REFERENCES accounts(id))''')
    
    # Member sources cache (to avoid re-adding same users)
    c.execute('''CREATE TABLE IF NOT EXISTS member_cache
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  account_id INTEGER,
                  user_id INTEGER,
                  source_group TEXT,
                  cached_at TIMESTAMP,
                  UNIQUE(account_id, user_id))''')
    
    # Auto-add activity log
    c.execute('''CREATE TABLE IF NOT EXISTS auto_add_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  account_id INTEGER,
                  user_id INTEGER,
                  username TEXT,
                  action TEXT,
                  status TEXT,
                  message TEXT,
                  timestamp TIMESTAMP,
                  FOREIGN KEY (account_id) REFERENCES accounts(id))''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def get_db():
    """Get database connection"""
    conn = sqlite3.connect('telegram_accounts.db')
    conn.row_factory = sqlite3.Row
    return conn

# ==================== AUTO-ADD HELPERS ====================

def get_auto_add_settings(account_id):
    """Get auto-add settings for an account"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM auto_add_settings WHERE account_id = ?", (account_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        settings = dict(row)
        # Parse source_groups JSON
        if settings.get('source_groups'):
            try:
                settings['source_groups'] = json.loads(settings['source_groups'])
            except:
                settings['source_groups'] = DEFAULT_AUTO_ADD_SETTINGS['source_groups']
        else:
            settings['source_groups'] = DEFAULT_AUTO_ADD_SETTINGS['source_groups']
        return settings
    else:
        return DEFAULT_AUTO_ADD_SETTINGS.copy()

def save_auto_add_settings(account_id, settings):
    """Save auto-add settings for an account"""
    conn = get_db()
    c = conn.cursor()
    
    # Check if exists
    c.execute("SELECT account_id FROM auto_add_settings WHERE account_id = ?", (account_id,))
    exists = c.fetchone()
    
    source_groups_json = json.dumps(settings.get('source_groups', []))
    
    if exists:
        c.execute('''UPDATE auto_add_settings SET
                     enabled = ?, target_group = ?, daily_limit = ?, delay_seconds = ?,
                     added_today = ?, last_reset = ?, source_groups = ?,
                     use_contacts = ?, use_recent_chats = ?, use_scraping = ?,
                     scrape_limit = ?, skip_bots = ?, skip_inaccessible = ?, auto_join = ?
                     WHERE account_id = ?''',
                  (1 if settings.get('enabled') else 0,
                   settings.get('target_group', DEFAULT_TARGET_GROUP),
                   settings.get('daily_limit', 100),
                   settings.get('delay_seconds', 30),
                   settings.get('added_today', 0),
                   settings.get('last_reset', datetime.now().strftime("%Y-%m-%d")),
                   source_groups_json,
                   1 if settings.get('use_contacts') else 0,
                   1 if settings.get('use_recent_chats') else 0,
                   1 if settings.get('use_scraping') else 0,
                   settings.get('scrape_limit', 150),
                   1 if settings.get('skip_bots') else 0,
                   1 if settings.get('skip_inaccessible') else 0,
                   1 if settings.get('auto_join') else 0,
                   account_id))
    else:
        c.execute('''INSERT INTO auto_add_settings
                     (account_id, enabled, target_group, daily_limit, delay_seconds,
                      added_today, last_reset, source_groups, use_contacts,
                      use_recent_chats, use_scraping, scrape_limit, skip_bots,
                      skip_inaccessible, auto_join)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (account_id,
                   1 if settings.get('enabled') else 0,
                   settings.get('target_group', DEFAULT_TARGET_GROUP),
                   settings.get('daily_limit', 100),
                   settings.get('delay_seconds', 30),
                   settings.get('added_today', 0),
                   settings.get('last_reset', datetime.now().strftime("%Y-%m-%d")),
                   source_groups_json,
                   1 if settings.get('use_contacts') else 0,
                   1 if settings.get('use_recent_chats') else 0,
                   1 if settings.get('use_scraping') else 0,
                   settings.get('scrape_limit', 150),
                   1 if settings.get('skip_bots') else 0,
                   1 if settings.get('skip_inaccessible') else 0,
                   1 if settings.get('auto_join') else 0))
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Saved auto-add settings for account {account_id}")

def log_auto_add_activity(account_id, user_id, username, action, status, message):
    """Log auto-add activity"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO auto_add_log
                 (account_id, user_id, username, action, status, message, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (account_id, user_id, username, action, status, message, datetime.now()))
    conn.commit()
    conn.close()

def add_to_member_cache(account_id, user_id, source_group):
    """Add user to member cache to avoid re-adding"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT OR IGNORE INTO member_cache
                     (account_id, user_id, source_group, cached_at)
                     VALUES (?, ?, ?, ?)''',
                  (account_id, user_id, source_group, datetime.now()))
        conn.commit()
    except:
        pass
    conn.close()

def is_member_cached(account_id, user_id):
    """Check if user is already cached"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM member_cache WHERE account_id = ? AND user_id = ?", (account_id, user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def record_added_member(account_id, user_id, username, source):
    """Record that a member was added"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO added_members
                 (account_id, user_id, username, added_at, source)
                 VALUES (?, ?, ?, ?, ?)''',
              (account_id, user_id, username, datetime.now(), source))
    conn.commit()
    conn.close()
    
    # Also update added_today count
    update_added_today_count(account_id)

def update_added_today_count(account_id):
    """Update the added_today count for an account"""
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Count today's additions
    c.execute('''SELECT COUNT(*) FROM added_members
                 WHERE account_id = ? AND DATE(added_at) = ?''',
              (account_id, today))
    count = c.fetchone()[0]
    
    # Update settings
    c.execute('''UPDATE auto_add_settings SET added_today = ? WHERE account_id = ?''',
              (count, account_id))
    conn.commit()
    conn.close()
    
    return count

def reset_daily_counts():
    """Reset daily counts for all accounts (run daily)"""
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute('''UPDATE auto_add_settings SET added_today = 0, last_reset = ?
                 WHERE last_reset != ?''',
              (today, today))
    conn.commit()
    conn.close()
    logger.info("✅ Reset daily counts for all accounts")

def get_remaining_capacity(account_id, settings=None):
    """Get remaining members that can be added today"""
    if not settings:
        settings = get_auto_add_settings(account_id)
    
    daily_limit = settings.get('daily_limit', 100)
    added_today = settings.get('added_today', 0)
    
    return max(0, daily_limit - added_today)

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
            if dialog.is_user and not dialog.entity.bot:
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
            if dialog.is_user and not dialog.entity.bot:
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
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, name, phone, session_string FROM accounts WHERE id = ?", (account_id,))
        account = c.fetchone()
        conn.close()
        
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
    
    if account_id not in auto_add_tasks or not auto_add_tasks[account_id].is_alive():
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        auto_add_tasks[account_id] = thread
        logger.info(f"Started auto-add loop for account {account_id}")

def check_and_auto_join_target_group(account_id, client, target_group):
    """Check if account is in target group, join if not"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Check if already in group
        entity = loop.run_until_complete(client.get_entity(target_group))
        
        # Try to join if not already a member
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
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, phone, created_at FROM accounts ORDER BY created_at DESC")
    accounts = [dict(row) for row in c.fetchall()]
    conn.close()
    
    # Add auto-add status for each account
    for acc in accounts:
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
            
            # Save account to database
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO accounts (name, phone, session_string, created_at, last_active)
                         VALUES (?, ?, ?, ?, ?)''',
                      (me.first_name or me.username, phone, client.session.save(),
                       datetime.now(), datetime.now()))
            account_id = c.lastrowid
            conn.commit()
            conn.close()
            
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
        
        settings = get_auto_add_settings(account_id)
        return jsonify({'success': True, 'settings': settings})
    
    else:  # POST
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        settings = {
            'enabled': data.get('enabled', True),
            'target_group': data.get('target_group', DEFAULT_TARGET_GROUP),
            'daily_limit': min(500, max(100, data.get('daily_limit', 100))),
            'delay_seconds': min(50, max(10, data.get('delay_seconds', 30))),
            'source_groups': data.get('source_groups', DEFAULT_AUTO_ADD_SETTINGS['source_groups']),
            'use_contacts': data.get('use_contacts', True),
            'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True),
            'scrape_limit': data.get('scrape_limit', 150),
            'skip_bots': data.get('skip_bots', True),
            'skip_inaccessible': data.get('skip_inaccessible', True),
            'auto_join': data.get('auto_join', True)
        }
        
        save_auto_add_settings(account_id, settings)
        
        # Start auto-add loop if enabled
        if settings['enabled']:
            start_auto_add_loop(account_id)
        
        return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/api/auto-add-stats', methods=['GET'])
def auto_add_stats():
    """Get auto-add stats for an account"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = get_auto_add_settings(account_id)
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
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
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT session_string FROM accounts WHERE id = ?", (account_id,))
    account = c.fetchone()
    conn.close()
    
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
def remove_account():
    """Remove an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Stop auto-add loop if running
    if account_id in auto_add_tasks:
        # Thread will die on its own
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
    
    # Delete from database
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    c.execute("DELETE FROM auto_add_settings WHERE account_id = ?", (account_id,))
    c.execute("DELETE FROM added_members WHERE account_id = ?", (account_id,))
    c.execute("DELETE FROM member_cache WHERE account_id = ?", (account_id,))
    c.execute("DELETE FROM auto_add_log WHERE account_id = ?", (account_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Account removed'})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'time': datetime.now().isoformat()}), 200

# ==================== STARTUP ====================

# Store temporary login sessions
temp_sessions = {}

# Daily reset thread
def daily_reset_loop():
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
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM accounts")
    accounts = c.fetchall()
    conn.close()
    
    for account in accounts:
        account_id = account[0]
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
    
    # Initialize database
    init_database()
    
    # Start daily reset thread
    start_daily_reset()
    
    # Start auto-add for existing accounts
    start_auto_add_for_existing_accounts()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
