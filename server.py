from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError, FloodWaitError
import json
import os
import asyncio
import logging
import time
import threading
import requests
import sqlite3
import base64
import random
import shutil
from datetime import datetime, timedelta
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Database setup
DB_PATH = 'telegram_bot.db'
BACKUP_DIR = 'backups'

@contextmanager
def get_db():
    """Get database connection with context manager"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize all database tables"""
    with get_db() as conn:
        # Accounts table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                name TEXT,
                username TEXT,
                session TEXT,
                photo BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP,
                is_valid BOOLEAN DEFAULT 1
            )
        ''')
        
        # Conversation history table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                chat_id TEXT,
                chat_title TEXT,
                chat_photo BLOB,
                role TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Auto-add settings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auto_add_settings (
                account_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                target_group TEXT,
                daily_limit INTEGER DEFAULT 30,
                delay_seconds INTEGER DEFAULT 45,
                added_today INTEGER DEFAULT 0,
                last_reset TEXT,
                source_groups TEXT,
                use_contacts BOOLEAN DEFAULT 1,
                use_recent_chats BOOLEAN DEFAULT 1,
                use_scraping BOOLEAN DEFAULT 1,
                scrape_limit INTEGER DEFAULT 100,
                skip_bots BOOLEAN DEFAULT 1,
                skip_inaccessible BOOLEAN DEFAULT 1,
                auto_join BOOLEAN DEFAULT 1,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Auto-add log table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auto_add_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                action TEXT,
                user_id TEXT,
                username TEXT,
                status TEXT,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Chat photos cache
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                chat_id TEXT,
                photo BLOB,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id),
                UNIQUE(account_id, chat_id)
            )
        ''')
        
        logger.info("✅ Database initialized")

# Global storage
accounts = []
temp_sessions = {}
auto_add_tasks = {}
chat_photo_cache = {}

# Helper to run async functions with timeout
def run_async(coro, timeout=30):
    """Run async function with timeout"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        except asyncio.TimeoutError:
            logger.error("Operation timed out")
            return {'success': False, 'error': 'Operation timed out'}
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async error: {e}")
        return {'success': False, 'error': str(e)}

# Database functions
def load_accounts_from_db():
    """Load accounts from database"""
    global accounts
    accounts = []
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM accounts WHERE is_valid = 1 ORDER BY id').fetchall()
            for row in rows:
                accounts.append({
                    'id': row['id'],
                    'phone': row['phone'],
                    'name': row['name'],
                    'username': row['username'],
                    'session': row['session'],
                    'photo': row['photo'],
                    'last_active': row['last_active']
                })
        logger.info(f"✅ Loaded {len(accounts)} permanent accounts")
        
        # Validate each account session
        for acc in accounts:
            validate_account_session(acc)
            
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        init_db()

def validate_account_session(account):
    """Validate and refresh account session if needed"""
    async def validate():
        try:
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                # Update last active
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET last_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                                (datetime.now().isoformat(), account['id']))
                logger.info(f"✅ Account {account['name']} is valid")
                return True
            else:
                logger.warning(f"⚠️ Account {account['name']} session invalid")
                return False
        except Exception as e:
            logger.error(f"Error validating account {account['name']}: {e}")
            return False
        finally:
            await client.disconnect()
    
    try:
        result = run_async(validate(), timeout=10)
        if not result:
            mark_account_invalid(account['id'])
    except:
        pass

def mark_account_invalid(account_id):
    """Mark account as invalid in database"""
    with get_db() as conn:
        conn.execute('UPDATE accounts SET is_valid = 0 WHERE id = ?', (account_id,))

def add_account_to_db(phone, name, username, session_string, photo=None):
    """Add account to database"""
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO accounts (phone, name, username, session, photo, last_active) VALUES (?, ?, ?, ?, ?, ?)',
            (phone, name, username, session_string, photo, datetime.now().isoformat())
        )
        return cursor.lastrowid

def update_account_photo(account_id, photo):
    """Update account profile photo"""
    with get_db() as conn:
        conn.execute('UPDATE accounts SET photo = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (photo, account_id))

def get_account_photo(account_id):
    """Get account profile photo from database"""
    with get_db() as conn:
        row = conn.execute('SELECT photo FROM accounts WHERE id = ?', (account_id,)).fetchone()
        return row['photo'] if row else None

def remove_account_from_db(account_id):
    """Remove account from database"""
    with get_db() as conn:
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        conn.execute('DELETE FROM conversation_history WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM auto_add_settings WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM auto_add_log WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM chat_photos WHERE account_id = ?', (account_id,))

def save_chat_photo(account_id, chat_id, photo):
    """Save chat photo to database"""
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO chat_photos (account_id, chat_id, photo, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (account_id, chat_id, photo, datetime.now().isoformat()))

def get_cached_chat_photo(account_id, chat_id):
    """Get cached chat photo"""
    with get_db() as conn:
        row = conn.execute('SELECT photo FROM chat_photos WHERE account_id = ? AND chat_id = ?',
                          (account_id, chat_id)).fetchone()
        return row['photo'] if row else None

def backup_database():
    """Create automatic backup of database"""
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'telegram_bot_{timestamp}.db')
        
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"✅ Database backed up to: {backup_path}")
        
        # Keep only last 10 backups
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('telegram_bot_')])
        for old_backup in backups[:-10]:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
            
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False

def restore_database(backup_file):
    """Restore database from backup"""
    try:
        if os.path.exists(DB_PATH):
            # Backup current before restore
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pre_restore = os.path.join(BACKUP_DIR, f'pre_restore_{timestamp}.db')
            shutil.copy2(DB_PATH, pre_restore)
            logger.info(f"Pre-restore backup saved: {pre_restore}")
        
        shutil.copy2(backup_file, DB_PATH)
        logger.info(f"✅ Database restored from: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False

def get_auto_add_settings(account_id):
    """Get auto-add settings for an account"""
    with get_db() as conn:
        row = conn.execute('SELECT * FROM auto_add_settings WHERE account_id = ?', (account_id,)).fetchone()
        if row:
            return {
                'enabled': bool(row['enabled']),
                'target_group': row['target_group'] or 'Abe_armygroup',
                'daily_limit': row['daily_limit'] or 30,
                'delay_seconds': row['delay_seconds'] or 45,
                'added_today': row['added_today'] or 0,
                'last_reset': row['last_reset'],
                'source_groups': json.loads(row['source_groups']) if row['source_groups'] else ['@telegram', '@durov'],
                'use_contacts': bool(row['use_contacts']) if row['use_contacts'] is not None else True,
                'use_recent_chats': bool(row['use_recent_chats']) if row['use_recent_chats'] is not None else True,
                'use_scraping': bool(row['use_scraping']) if row['use_scraping'] is not None else True,
                'scrape_limit': row['scrape_limit'] or 100,
                'skip_bots': bool(row['skip_bots']) if row['skip_bots'] is not None else True,
                'skip_inaccessible': bool(row['skip_inaccessible']) if row['skip_inaccessible'] is not None else True,
                'auto_join': bool(row['auto_join']) if row['auto_join'] is not None else True
            }
        return {
            'enabled': False,
            'target_group': 'Abe_armygroup',
            'daily_limit': 30,
            'delay_seconds': 45,
            'added_today': 0,
            'last_reset': None,
            'source_groups': ['@telegram', '@durov'],
            'use_contacts': True,
            'use_recent_chats': True,
            'use_scraping': True,
            'scrape_limit': 100,
            'skip_bots': True,
            'skip_inaccessible': True,
            'auto_join': True
        }

def save_auto_add_settings(account_id, settings):
    """Save auto-add settings"""
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO auto_add_settings 
            (account_id, enabled, target_group, daily_limit, delay_seconds, added_today, last_reset, 
             source_groups, use_contacts, use_recent_chats, use_scraping, scrape_limit, skip_bots, skip_inaccessible, auto_join)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            account_id,
            1 if settings.get('enabled') else 0,
            settings.get('target_group', 'Abe_armygroup'),
            settings.get('daily_limit', 30),
            settings.get('delay_seconds', 45),
            settings.get('added_today', 0),
            settings.get('last_reset'),
            json.dumps(settings.get('source_groups', [])),
            1 if settings.get('use_contacts', True) else 0,
            1 if settings.get('use_recent_chats', True) else 0,
            1 if settings.get('use_scraping', True) else 0,
            settings.get('scrape_limit', 100),
            1 if settings.get('skip_bots', True) else 0,
            1 if settings.get('skip_inaccessible', True) else 0,
            1 if settings.get('auto_join', True) else 0
        ))

def add_auto_add_log(account_id, action, user_id, username, status, message):
    """Add log entry for auto-add"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO auto_add_log (account_id, action, user_id, username, status, message)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, action, user_id, username, status, message))

def get_auto_add_logs(account_id, limit=100):
    """Get auto-add logs"""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM auto_add_log 
            WHERE account_id = ? 
            ORDER BY timestamp DESC LIMIT ?
        ''', (account_id, limit)).fetchall()
        return [dict(row) for row in rows]

def reset_daily_counter(account_id):
    """Reset daily counter if new day"""
    with get_db() as conn:
        settings = conn.execute('SELECT last_reset, added_today FROM auto_add_settings WHERE account_id = ?', (account_id,)).fetchone()
        if settings:
            today = datetime.now().strftime('%Y-%m-%d')
            if settings['last_reset'] != today:
                conn.execute('UPDATE auto_add_settings SET added_today = 0, last_reset = ? WHERE account_id = ?', (today, account_id))
                return True
        return False

def increment_added_today(account_id):
    """Increment added today counter"""
    with get_db() as conn:
        conn.execute('UPDATE auto_add_settings SET added_today = added_today + 1 WHERE account_id = ?', (account_id,))

# Load accounts on startup
init_db()
load_accounts_from_db()

# ==================== AUTO-ADD FUNCTIONS ====================

async def get_members_from_contacts(client, settings):
    """Get members from contacts"""
    members = []
    try:
        contacts = await client(functions.contacts.GetContactsRequest(0))
        for user in contacts.users:
            if settings.get('skip_bots', True) and user.bot:
                continue
            members.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name
            })
        logger.info(f"Found {len(members)} contacts")
        return members
    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
        return []

async def get_members_from_recent_chats(client, settings):
    """Get members from recent chats"""
    members = []
    try:
        dialogs = await client.get_dialogs(limit=200)
        for dialog in dialogs:
            if dialog.is_user and dialog.entity:
                user = dialog.entity
                if settings.get('skip_bots', True) and user.bot:
                    continue
                members.append({
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name
                })
        logger.info(f"Found {len(members)} users from recent chats")
        return members
    except Exception as e:
        logger.error(f"Error getting recent chats: {e}")
        return []

async def get_members_from_groups(client, settings):
    """Get members from source groups"""
    members = []
    source_groups = settings.get('source_groups', [])
    limit = settings.get('scrape_limit', 100)
    
    for group_ref in source_groups[:5]:
        if not group_ref:
            continue
        try:
            group_ref_clean = group_ref.strip()
            if group_ref_clean.startswith('https://t.me/'):
                group_ref_clean = group_ref_clean.replace('https://t.me/', '@')
            elif not group_ref_clean.startswith('@'):
                group_ref_clean = '@' + group_ref_clean
            
            try:
                source_group = await client.get_entity(group_ref_clean)
                logger.info(f"Scraping group: {source_group.title if hasattr(source_group, 'title') else group_ref_clean}")
            except Exception as e:
                logger.warning(f"Could not find group {group_ref_clean}: {e}")
                continue
            
            try:
                count = 0
                async for user in client.iter_participants(source_group, limit=limit):
                    if user and user.id:
                        if settings.get('skip_bots', True) and user.bot:
                            continue
                        members.append({
                            'id': user.id,
                            'username': user.username,
                            'first_name': user.first_name
                        })
                        count += 1
                        if count >= limit:
                            break
                logger.info(f"Scraped {count} members from {group_ref_clean}")
            except errors.ChatAdminRequiredError:
                logger.warning(f"Admin required to view members in {group_ref_clean}")
            except Exception as e:
                logger.error(f"Error scraping {group_ref_clean}: {e}")
        except Exception as e:
            logger.error(f"Error processing group {group_ref}: {e}")
    
    return members

async def auto_join_target_group(client, target_group):
    """Auto-join target group"""
    try:
        group_name = target_group
        if group_name.startswith('https://t.me/'):
            group_name = group_name.replace('https://t.me/', '@')
        elif not group_name.startswith('@'):
            group_name = '@' + group_name
        
        group = await client.get_entity(group_name)
        await client(functions.channels.JoinChannelRequest(group))
        logger.info(f"✅ Auto-joined group: {group_name}")
        return True
    except Exception as e:
        logger.warning(f"Could not auto-join: {e}")
        return False

async def add_member_to_group(client, group, user_id, username):
    """Add a single member to group"""
    try:
        await client(functions.channels.InviteToChannelRequest(
            group,
            [await client.get_input_entity(user_id)]
        ))
        return True, None
    except FloodWaitError as e:
        return False, f"Flood wait: {e.seconds} seconds"
    except errors.UserPrivacyRestrictedError:
        return False, "Privacy restricted"
    except errors.UserNotMutualContactError:
        return False, "Not mutual contact"
    except Exception as e:
        return False, str(e)

async def auto_add_worker(account_id):
    """Background worker for auto-add"""
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        logger.error(f"Account {account_id} not found")
        return
    
    logger.info(f"Starting auto-add worker for account {account['name']}")
    
    while True:
        try:
            settings = get_auto_add_settings(account_id)
            
            if not settings.get('enabled'):
                logger.info(f"Auto-add disabled for account {account_id}, stopping")
                break
            
            reset_daily_counter(account_id)
            settings = get_auto_add_settings(account_id)
            
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
                
                target_group = settings['target_group']
                if settings.get('auto_join', True):
                    await auto_join_target_group(client, target_group)
                
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
                
                existing_members = set()
                try:
                    async for user in client.iter_participants(group, limit=1000):
                        if user and user.id:
                            existing_members.add(user.id)
                    logger.info(f"Group has {len(existing_members)} existing members")
                except Exception as e:
                    logger.error(f"Error getting existing members: {e}")
                
                all_members = []
                
                if settings.get('use_contacts', True):
                    contacts = await get_members_from_contacts(client, settings)
                    all_members.extend(contacts)
                    add_auto_add_log(account_id, 'source_contacts', None, None, 'success', f'Found {len(contacts)} contacts')
                
                if settings.get('use_recent_chats', True):
                    recent = await get_members_from_recent_chats(client, settings)
                    all_members.extend(recent)
                    add_auto_add_log(account_id, 'source_chats', None, None, 'success', f'Found {len(recent)} users from chats')
                
                if settings.get('use_scraping', True):
                    scraped = await get_members_from_groups(client, settings)
                    all_members.extend(scraped)
                    add_auto_add_log(account_id, 'source_groups', None, None, 'success', f'Scraped {len(scraped)} members')
                
                unique_members = {}
                for member in all_members:
                    if member['id'] not in existing_members:
                        unique_members[member['id']] = member
                
                new_members = list(unique_members.values())
                logger.info(f"Found {len(new_members)} new members to add")
                
                added = 0
                for member in new_members:
                    if settings['added_today'] >= settings['daily_limit']:
                        break
                    
                    success, error = await add_member_to_group(client, group, member['id'], member.get('username'))
                    
                    if success:
                        added += 1
                        increment_added_today(account_id)
                        settings = get_auto_add_settings(account_id)
                        add_auto_add_log(
                            account_id, 'add_member', str(member['id']), 
                            member.get('username') or member.get('first_name', 'Unknown'),
                            'success', 'Added to group'
                        )
                        logger.info(f"✅ Added member {member['id']} to {target_group}")
                        await asyncio.sleep(settings['delay_seconds'])
                    else:
                        add_auto_add_log(
                            account_id, 'add_member', str(member['id']),
                            member.get('username') or member.get('first_name', 'Unknown'),
                            'failed', error
                        )
                        logger.warning(f"❌ Failed to add {member['id']}: {error}")
                
                logger.info(f"Added {added} members this cycle. Total today: {settings['added_today']}")
                
            except Exception as e:
                logger.error(f"Error in auto-add loop: {e}")
            finally:
                await client.disconnect()
            
            wait_time = random.randint(1800, 3600)
            logger.info(f"Waiting {wait_time} seconds before next cycle...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Critical error in auto-add worker: {e}")
            await asyncio.sleep(300)

def start_auto_add_thread(account_id):
    """Start auto-add worker thread"""
    if account_id in auto_add_tasks and auto_add_tasks[account_id].is_alive():
        logger.info(f"Auto-add already running for account {account_id}")
        return
    
    def run_worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auto_add_worker(account_id))
        loop.close()
    
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    auto_add_tasks[account_id] = thread
    logger.info(f"Started auto-add thread for account {account_id}")

def stop_auto_add_thread(account_id):
    """Stop auto-add worker thread"""
    if account_id in auto_add_tasks:
        del auto_add_tasks[account_id]
        logger.info(f"Stopped auto-add thread for account {account_id}")

def start_all_auto_add():
    """Start auto-add for all enabled accounts"""
    with get_db() as conn:
        rows = conn.execute('SELECT account_id FROM auto_add_settings WHERE enabled = 1').fetchall()
        for row in rows:
            start_auto_add_thread(row['account_id'])

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

# ==================== ACCOUNT API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    try:
        formatted = []
        for acc in accounts:
            formatted.append({
                'id': acc.get('id'),
                'phone': acc.get('phone', ''),
                'name': acc.get('name', 'Unknown'),
                'username': acc.get('username', ''),
                'auto_reply_enabled': False
            })
        return jsonify({'success': True, 'accounts': formatted})
    except Exception as e:
        logger.error(f"Error in get_accounts: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/account-info', methods=['POST'])
def get_account_info():
    """Get detailed account information with photo"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_info():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                me = await client.get_me()
                
                # Get profile photo
                photo_base64 = None
                try:
                    photo = await client.download_profile_photo(me, file=bytes)
                    if photo:
                        photo_base64 = base64.b64encode(photo).decode('utf-8')
                        update_account_photo(account_id, photo_base64)
                except:
                    pass
                
                return {
                    'success': True,
                    'name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'username': me.username or '',
                    'phone': me.phone or '',
                    'id': me.id,
                    'is_bot': me.bot or False,
                    'photo': photo_base64 or get_account_photo(account_id)
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(get_info(), timeout=20)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in account-info: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start account addition process"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data'})
        
        phone = data.get('phone')
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'})
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Adding account for phone: {phone}")
        
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
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send_code(), timeout=20)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in add_account: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and complete account addition"""
    try:
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
                
                # Get profile photo
                photo_base64 = None
                try:
                    photo = await client.download_profile_photo(me, file=bytes)
                    if photo:
                        photo_base64 = base64.b64encode(photo).decode('utf-8')
                except:
                    pass
                
                new_id = add_account_to_db(
                    me.phone or session_data['phone'],
                    me.first_name or 'User',
                    me.username or '',
                    client.session.save(),
                    photo_base64
                )
                
                new_account = {
                    'id': new_id,
                    'phone': me.phone or session_data['phone'],
                    'name': me.first_name or 'User',
                    'username': me.username or '',
                    'session': client.session.save(),
                    'photo': photo_base64
                }
                accounts.append(new_account)
                
                # Create default auto-add settings
                save_auto_add_settings(new_id, {
                    'enabled': False,
                    'target_group': 'Abe_armygroup',
                    'daily_limit': 30,
                    'delay_seconds': 45,
                    'added_today': 0,
                    'last_reset': datetime.now().strftime('%Y-%m-%d'),
                    'source_groups': ['@telegram', '@durov'],
                    'use_contacts': True,
                    'use_recent_chats': True,
                    'use_scraping': True,
                    'scrape_limit': 100,
                    'skip_bots': True,
                    'skip_inaccessible': True,
                    'auto_join': True
                })
                
                # Create backup after successful account addition
                backup_database()
                
                return {'success': True, 'account': new_account}
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(verify(), timeout=30)
        
        if session_id in temp_sessions:
            del temp_sessions[session_id]
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in verify_code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove an account"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        global accounts
        stop_auto_add_thread(int(account_id))
        remove_account_from_db(int(account_id))
        accounts = [acc for acc in accounts if acc['id'] != account_id]
        
        # Backup after removal
        backup_database()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error removing account: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    """Update account profile"""
    try:
        data = request.json
        account_id = data.get('accountId')
        first_name = data.get('firstName')
        
        if not first_name:
            return jsonify({'success': False, 'error': 'First name required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def update():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.UpdateProfileRequest(
                    first_name=first_name
                ))
                account['name'] = first_name
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                                (first_name, account_id))
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(update(), timeout=15)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-username', methods=['POST'])
def update_username():
    """Update account username"""
    try:
        data = request.json
        account_id = data.get('accountId')
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'success': False, 'error': 'Username required'})
        
        if username.startswith('@'):
            username = username[1:]
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def update():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.UpdateUsernameRequest(username))
                
                account['username'] = username
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET username = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                                (username, account_id))
                
                return {'success': True}
            except errors.UsernameNotOccupiedError:
                return {'success': False, 'error': 'Username not available'}
            except errors.UsernameInvalidError:
                return {'success': False, 'error': 'Invalid username format'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(update(), timeout=15)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error updating username: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== CHAT API ROUTES ====================

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats list"""
    try:
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
                
                dialogs = await client.get_dialogs(limit=50)
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
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(fetch(), timeout=25)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-messages', methods=['POST'])
def get_chat_messages():
    """Get messages from a specific chat"""
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        limit = data.get('limit', 50)
        
        if not account_id or not chat_id:
            return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch_messages():
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
                
                messages = []
                async for msg in client.iter_messages(entity, limit=limit):
                    message_data = {
                        'id': msg.id,
                        'text': msg.text or '',
                        'date': int(msg.date.timestamp()) if msg.date else 0,
                        'out': msg.out,
                        'has_media': msg.media is not None
                    }
                    messages.append(message_data)
                
                chat_info = {
                    'id': str(entity.id),
                    'title': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 
                            'group' if hasattr(entity, 'megagroup') else 'user',
                    'username': getattr(entity, 'username', None),
                }
                
                return {'success': True, 'messages': messages, 'chat_info': chat_info}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(fetch_messages(), timeout=30)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-photo', methods=['POST'])
def get_chat_photo():
    """Get profile photo of a chat/user with caching"""
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        
        if not account_id or not chat_id:
            return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
        
        # Check cache first
        cached_photo = get_cached_chat_photo(account_id, chat_id)
        if cached_photo:
            return jsonify({'success': True, 'photo': cached_photo})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch_photo():
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
                
                photo = await client.download_profile_photo(entity, file=bytes)
                if photo:
                    photo_base64 = base64.b64encode(photo).decode('utf-8')
                    # Save to cache
                    save_chat_photo(account_id, chat_id, photo_base64)
                    return {'success': True, 'photo': photo_base64}
                
                return {'success': True, 'photo': None}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(fetch_photo(), timeout=15)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting chat photo: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message"""
    try:
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
                
                # Save to conversation history
                chat_title = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
                with get_db() as conn:
                    conn.execute('''
                        INSERT INTO conversation_history (account_id, chat_id, chat_title, role, message)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (account_id, chat_id, chat_title, 'user', message))
                
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send(), timeout=20)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/conversation-history', methods=['GET'])
def get_conversation_history_api():
    """Get conversation history"""
    try:
        account_id = request.args.get('accountId')
        chat_id = request.args.get('chatId')
        
        if not account_id or not chat_id:
            return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
        
        with get_db() as conn:
            rows = conn.execute('''
                SELECT role, message, timestamp 
                FROM conversation_history 
                WHERE account_id = ? AND chat_id = ?
                ORDER BY timestamp DESC LIMIT 50
            ''', (account_id, chat_id)).fetchall()
            
            history = [{'role': row['role'], 'message': row['message'], 'time': row['timestamp']} 
                      for row in reversed(rows)]
        
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear-history', methods=['POST'])
def clear_conversation_history_api():
    """Clear conversation history"""
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        
        if not account_id or not chat_id:
            return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
        
        with get_db() as conn:
            conn.execute('DELETE FROM conversation_history WHERE account_id = ? AND chat_id = ?',
                        (account_id, chat_id))
        
        return jsonify({'success': True, 'message': 'History cleared'})
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== EMAIL & 2FA ROUTES ====================
@app.route('/api/request-email-code', methods=['POST'])
def request_email_code():
    """Request email verification code"""
    try:
        data = request.json
        account_id = data.get('accountId')
        email = data.get('email')
        
        if not account_id or not email:
            return jsonify({'success': False, 'error': 'Account ID and email required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def request_code():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # First check if account has password
                password_info = await client(functions.account.GetPasswordRequest())
                
                # Request verification email
                result = await client(functions.account.SendVerifyEmailCodeRequest(
                    purpose=types.account.EmailPurposeLoginSetup(
                        email=email
                    )
                ))
                
                # Store email in session for verification
                if 'pending_emails' not in temp_sessions:
                    temp_sessions['pending_emails'] = {}
                temp_sessions['pending_emails'][str(account_id)] = {
                    'email': email,
                    'timeout': result.timeout
                }
                
                return {
                    'success': True,
                    'email': email,
                    'message': f'Verification code sent to {email}',
                    'timeout': result.timeout
                }
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
            except Exception as e:
                error_msg = str(e)
                if 'EMAIL_VERIFICATION_NEEDED' in error_msg:
                    return {'success': False, 'error': 'Email verification is required first'}
                logger.error(f"Email request error: {e}")
                return {'success': False, 'error': error_msg}
            finally:
                await client.disconnect()
        
        result = run_async(request_code(), timeout=30)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error requesting email code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set-2fa-password', methods=['POST'])
def set_2fa_password():
    """Set up two-step verification"""
    try:
        data = request.json
        account_id = data.get('accountId')
        current_password = data.get('currentPassword', '')
        new_password = data.get('newPassword')
        hint = data.get('hint', '')
        email = data.get('email', '')
        
        if not account_id or not new_password:
            return jsonify({'success': False, 'error': 'Account ID and new password required'})
        
        if len(new_password) < 4:
            return jsonify({'success': False, 'error': 'Password must be at least 4 characters'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def set_2fa():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # Get current password info
                password_info = await client(functions.account.GetPasswordRequest())
                
                # Prepare new password
                new_password_bytes = new_password.encode('utf-8')
                
                # Create new password settings
                new_settings = types.account.PasswordInputSettings(
                    new_algo=password_info.new_algo,
                    new_password_hash=password_info.new_algo.hash(new_password_bytes),
                    hint=hint if hint else ""
                )
                
                # Add recovery email if provided
                if email:
                    new_settings.email = email
                
                # Update password
                if current_password:
                    # If current password exists, use it
                    current_password_hash = password_info.current_algo.hash(current_password.encode('utf-8'))
                    await client(functions.account.UpdatePasswordSettingsRequest(
                        password=current_password_hash,
                        new_settings=new_settings
                    ))
                else:
                    # No current password
                    await client(functions.account.UpdatePasswordSettingsRequest(
                        password=password_info.current_password,
                        new_settings=new_settings
                    ))
                
                return {'success': True, 'message': '2FA password set successfully'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Invalid current password'}
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
            except Exception as e:
                logger.error(f"2FA error: {e}")
                error_msg = str(e)
                if 'PASSWORD_HASH_INVALID' in error_msg:
                    return {'success': False, 'error': 'Invalid current password'}
                elif 'EMAIL_UNCONFIRMED' in error_msg:
                    return {'success': False, 'error': 'Please verify your email first'}
                return {'success': False, 'error': error_msg}
            finally:
                await client.disconnect()
        
        result = run_async(set_2fa(), timeout=30)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error setting 2FA: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-account-email', methods=['POST'])
def get_account_email():
    """Get account email status"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_email():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # Get password info
                password_info = await client(functions.account.GetPasswordRequest())
                
                # Check if email is set
                email = None
                has_password = password_info.has_password
                
                if hasattr(password_info, 'email') and password_info.email:
                    email = password_info.email
                elif hasattr(password_info, 'has_recovery') and password_info.has_recovery:
                    email = "Recovery email set"
                
                return {
                    'success': True, 
                    'email': email, 
                    'has_password': has_password,
                    'has_recovery': getattr(password_info, 'has_recovery', False)
                }
            except Exception as e:
                logger.error(f"Get email error: {e}")
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(get_email(), timeout=15)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting account email: {e}")
        return jsonify({'success': False, 'error': str(e)})
# ==================== SESSION ROUTES ====================

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    """Get active sessions"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_sessions_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                sessions = []
                for auth in result.authorizations:
                    sessions.append({
                        'hash': auth.hash,
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
        
        result = run_async(get_sessions_async(), timeout=20)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    """Terminate all other sessions"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
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
        
        result = run_async(terminate(), timeout=30)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error terminating sessions: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== SEARCH & JOIN ROUTES ====================

@app.route('/api/search', methods=['POST'])
def search_entities():
    """Search for groups and channels"""
    try:
        data = request.json
        account_id = data.get('accountId')
        query = data.get('query')
        
        if not query:
            return jsonify({'success': False, 'error': 'Query required'})
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def search():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                results = []
                try:
                    found = await client(functions.contacts.SearchRequest(q=query, limit=10))
                    for chat in found.chats:
                        if hasattr(chat, 'title'):
                            results.append({
                                'id': str(chat.id),
                                'title': chat.title,
                                'type': 'channel' if hasattr(chat, 'broadcast') and chat.broadcast else 'group',
                                'username': getattr(chat, 'username', '')
                            })
                except Exception as e:
                    logger.error(f"Search error: {e}")
                
                return {'success': True, 'results': results}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(search(), timeout=15)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error searching: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/join-entity', methods=['POST'])
def join_entity():
    """Join a group or channel"""
    try:
        data = request.json
        account_id = data.get('accountId')
        entity_id = data.get('entityId')
        
        account = next((acc for acc in accounts if acc['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def join():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    entity = await client.get_entity(entity_id)
                except:
                    if not entity_id.startswith('@'):
                        entity = await client.get_entity('@' + entity_id)
                    else:
                        raise
                
                await client(functions.channels.JoinChannelRequest(entity))
                return {'success': True, 'title': getattr(entity, 'title', 'Entity')}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(join(), timeout=20)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error joining: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== AUTO-ADD API ROUTES ====================

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings_api():
    """Get auto-add settings for an account"""
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        settings = get_auto_add_settings(int(account_id))
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        logger.error(f"Error getting auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings_api():
    """Update auto-add settings"""
    try:
        data = request.json
        account_id = data.get('accountId')
        
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        settings = {
            'enabled': data.get('enabled', False),
            'target_group': data.get('target_group', 'Abe_armygroup'),
            'daily_limit': data.get('daily_limit', 30),
            'delay_seconds': data.get('delay_seconds', 45),
            'source_groups': data.get('source_groups', ['@telegram', '@durov']),
            'use_contacts': data.get('use_contacts', True),
            'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True),
            'scrape_limit': data.get('scrape_limit', 100),
            'skip_bots': data.get('skip_bots', True),
            'skip_inaccessible': data.get('skip_inaccessible', True),
            'auto_join': data.get('auto_join', True),
            'added_today': 0,
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        }
        
        save_auto_add_settings(int(account_id), settings)
        
        if settings['enabled']:
            start_auto_add_thread(int(account_id))
        else:
            stop_auto_add_thread(int(account_id))
        
        return jsonify({'success': True, 'message': 'Settings saved'})
    except Exception as e:
        logger.error(f"Error updating auto-add settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats_api():
    """Get auto-add statistics"""
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        settings = get_auto_add_settings(int(account_id))
        return jsonify({
            'success': True,
            'added_today': settings.get('added_today', 0),
            'daily_limit': settings.get('daily_limit', 30),
            'enabled': settings.get('enabled', False),
            'last_reset': settings.get('last_reset')
        })
    except Exception as e:
        logger.error(f"Error getting auto-add stats: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-logs', methods=['GET'])
def get_auto_add_logs_api():
    """Get auto-add logs"""
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        
        logs = get_auto_add_logs(int(account_id), 100)
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        logger.error(f"Error getting auto-add logs: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add_api():
    """Test auto-add functionality"""
    try:
        data = request.json
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
                    return {'success': False, 'error': 'Account not authorized'}
                
                target_group = 'Abe_armygroup'
                group_name = '@' + target_group
                try:
                    group = await client.get_entity(group_name)
                    group_found = True
                    group_title = group.title
                except Exception as e:
                    group_found = False
                    group_title = str(e)
                
                contacts = await get_members_from_contacts(client, {'skip_bots': True})
                recent = await get_members_from_recent_chats(client, {'skip_bots': True})
                scraped = await get_members_from_groups(client, {'source_groups': ['@telegram'], 'scrape_limit': 10, 'skip_bots': True})
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'contacts_count': len(contacts),
                    'recent_chats_count': len(recent),
                    'scraped_count': len(scraped),
                    'can_add_members': group_found and (len(contacts) > 0 or len(recent) > 0 or len(scraped) > 0)
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(test(), timeout=30)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error testing auto-add: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ==================== HEALTH & UTILITY ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_add_tasks': len(auto_add_tasks),
        'db_size': os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
        'time': datetime.now().isoformat()
    })

@app.route('/api/backup', methods=['POST'])
def create_backup():
    """Manually create a backup"""
    try:
        success = backup_database()
        if success:
            return jsonify({'success': True, 'message': 'Backup created successfully'})
        else:
            return jsonify({'success': False, 'error': 'Backup failed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/ping')
def ping():
    return "pong"

@app.errorhandler(Exception)
def handle_error(e):
    """Global error handler"""
    logger.error(f"Unhandled error: {e}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ==================== KEEP ALIVE ====================

def keep_alive():
    """Keep the server alive and backup periodically"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    last_backup = datetime.now()
    
    while True:
        try:
            requests.get(f"{app_url}/ping", timeout=5)
            
            # Backup every 6 hours
            if (datetime.now() - last_backup).seconds >= 21600:
                backup_database()
                last_backup = datetime.now()
                
            logger.info("Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(180)

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM ACCOUNT MANAGER WITH PERMANENT STORAGE')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print(f'✅ Auto-add tasks: {len(auto_add_tasks)}')
    print(f'✅ Database: {DB_PATH}')
    print('='*70)
    print('\n💾 PERMANENT STORAGE FEATURES:')
    print('   • SQLite database with all data')
    print('   • Automatic daily backups')
    print('   • Account profile photos stored')
    print('   • Chat photos cached')
    print('   • Session validation on startup')
    print('   • Auto-reconnect on failure')
    print('='*70 + '\n')
    
    # Start keep-alive thread
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    # Start auto-add for enabled accounts
    start_all_auto_add()
    
    # Run Flask
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
