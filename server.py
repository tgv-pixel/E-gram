from flask import Flask, send_file, jsonify, request, Response
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError, FloodWaitError
from telethon.tl.types import MessageEntityMention, MessageEntityTextUrl, TypeMessageEntity, DocumentAttributeSticker, DocumentAttributeEmoji
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
import hashlib
import mimetypes
from datetime import datetime, timedelta
from contextlib import contextmanager
from PIL import Image
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Database setup
DB_PATH = 'telegram_bot.db'
BACKUP_DIR = 'backups'
MEDIA_DIR = 'media_cache'

# Create directories
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

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
                media_path TEXT,
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
                UNIQUE(account_id, chat_id)
            )
        ''')
        
        # Sticker cache
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sticker_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sticker_id TEXT UNIQUE,
                emoji TEXT,
                file_path TEXT,
                width INTEGER,
                height INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        logger.info("✅ Database initialized")

# Global storage
accounts = []
temp_sessions = {}
auto_add_tasks = {}
media_cache = {}

# Helper to run async functions with timeout
def run_async(coro, timeout=60):
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
        run_async(validate(), timeout=10)
    except:
        pass

def add_account_to_db(phone, name, username, session_string, photo=None):
    """Add account to database"""
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO accounts (phone, name, username, session, photo, last_active) VALUES (?, ?, ?, ?, ?, ?)',
            (phone, name, username, session_string, photo, datetime.now().isoformat())
        )
        return cursor.lastrowid

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

# ==================== AUTO-ADD FUNCTIONS ====================

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
            
            source_group = await client.get_entity(group_ref_clean)
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
        except Exception as e:
            logger.error(f"Error scraping group: {e}")
    
    return members

async def auto_add_worker(account_id):
    """Background worker for auto-add"""
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return
    
    while True:
        try:
            settings = get_auto_add_settings(account_id)
            if not settings.get('enabled'):
                break
            
            # Reset daily counter
            today = datetime.now().strftime('%Y-%m-%d')
            if settings.get('last_reset') != today:
                settings['added_today'] = 0
                settings['last_reset'] = today
                save_auto_add_settings(account_id, settings)
            
            if settings['added_today'] >= settings['daily_limit']:
                await asyncio.sleep(3600)
                continue
            
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                # Get target group
                group = await client.get_entity('@' + settings['target_group'])
                
                # Get existing members
                existing = set()
                async for user in client.iter_participants(group, limit=1000):
                    if user and user.id:
                        existing.add(user.id)
                
                # Get new members
                new_members = []
                if settings.get('use_contacts'):
                    new_members.extend(await get_members_from_contacts(client, settings))
                if settings.get('use_recent_chats'):
                    new_members.extend(await get_members_from_recent_chats(client, settings))
                if settings.get('use_scraping'):
                    new_members.extend(await get_members_from_groups(client, settings))
                
                # Filter existing
                unique = {}
                for m in new_members:
                    if m['id'] not in existing:
                        unique[m['id']] = m
                
                # Add members
                for member in list(unique.values())[:settings['daily_limit'] - settings['added_today']]:
                    try:
                        await client(functions.channels.InviteToChannelRequest(
                            group, [await client.get_input_entity(member['id'])]
                        ))
                        settings['added_today'] += 1
                        save_auto_add_settings(account_id, settings)
                        await asyncio.sleep(settings['delay_seconds'])
                    except Exception as e:
                        logger.error(f"Failed to add {member['id']}: {e}")
                        
            finally:
                await client.disconnect()
            
            await asyncio.sleep(1800)  # 30 minutes
            
        except Exception as e:
            logger.error(f"Auto-add error: {e}")
            await asyncio.sleep(300)

def start_auto_add_thread(account_id):
    """Start auto-add worker thread"""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auto_add_worker(account_id))
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    auto_add_tasks[account_id] = thread

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

# ==================== ACCOUNT ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    try:
        formatted = [{'id': a['id'], 'phone': a['phone'], 'name': a['name'], 'username': a['username']} for a in accounts]
        return jsonify({'success': True, 'accounts': formatted})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/account-info', methods=['POST'])
def get_account_info():
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
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
                except:
                    pass
                
                return {
                    'success': True,
                    'name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'username': me.username or '',
                    'phone': me.phone or '',
                    'id': me.id,
                    'photo': photo
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get_info()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account():
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
        code = data.get('code')
        session_id = data.get('session_id')
        password = data.get('password', '')
        
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
                
                new_id = add_account_to_db(me.phone, me.first_name or 'User', me.username or '', client.session.save(), photo)
                accounts.append({
                    'id': new_id, 'phone': me.phone, 'name': me.first_name or 'User',
                    'username': me.username or '', 'session': client.session.save(), 'photo': photo
                })
                
                # Initialize auto-add settings
                save_auto_add_settings(new_id, {
                    'enabled': False, 'target_group': 'Abe_armygroup', 'daily_limit': 30,
                    'delay_seconds': 45, 'added_today': 0, 'last_reset': datetime.now().strftime('%Y-%m-%d'),
                    'source_groups': ['@telegram', '@durov'], 'use_contacts': True, 'use_recent_chats': True,
                    'use_scraping': True, 'scrape_limit': 100, 'skip_bots': True, 'skip_inaccessible': True, 'auto_join': True
                })
                
                return {'success': True}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        del temp_sessions[session_id]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    try:
        account_id = request.json.get('accountId')
        remove_account_from_db(account_id)
        global accounts
        accounts = [a for a in accounts if a['id'] != account_id]
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    try:
        account_id = request.json.get('accountId')
        first_name = request.json.get('firstName')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def update():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.UpdateProfileRequest(first_name=first_name))
                account['name'] = first_name
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET name = ? WHERE id = ?', (first_name, account_id))
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
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET username = ? WHERE id = ?', (username, account_id))
                return {'success': True}
            except errors.UsernameNotOccupiedError:
                return {'success': False, 'error': 'Username not available'}
            except errors.UsernameInvalidError:
                return {'success': False, 'error': 'Invalid username'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(update()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== CHAT & MESSAGE ROUTES ====================

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    try:
        account_id = request.json.get('accountId')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                dialogs = await client.get_dialogs(limit=100)
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
                        'lastMessageDate': 0,
                        'participants_count': None
                    }
                    
                    if dialog.message:
                        if dialog.message.text:
                            chat['lastMessage'] = dialog.message.text[:50]
                        elif dialog.message.media:
                            chat['lastMessage'] = '📎 Media'
                        if dialog.message.date:
                            chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                    
                    # Get participants count for groups
                    if dialog.is_group and hasattr(dialog.entity, 'participants_count'):
                        chat['participants_count'] = dialog.entity.participants_count
                    
                    chats.append(chat)
                
                return {'success': True, 'chats': chats}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-messages', methods=['POST'])
def get_chat_messages():
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        limit = data.get('limit', 100)
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(chat_id))
                
                # Get chat info with participants
                chat_info = {
                    'id': str(entity.id),
                    'title': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 
                            'group' if hasattr(entity, 'megagroup') else 'user',
                    'username': getattr(entity, 'username', None),
                    'participants_count': getattr(entity, 'participants_count', None),
                    'online_count': None
                }
                
                # Get online status for groups
                if hasattr(entity, 'online_count'):
                    chat_info['online_count'] = entity.online_count
                
                # Get last seen status for users
                if chat_info['type'] == 'user':
                    user = entity
                    if hasattr(user, 'status'):
                        if hasattr(user.status, 'was_online'):
                            chat_info['last_seen'] = int(user.status.was_online.timestamp())
                        elif hasattr(user.status, 'expires'):
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
                        'media_url': None,
                        'media_name': None,
                        'media_size': None,
                        'sticker_emoji': None,
                        'sticker_url': None
                    }
                    
                    # Handle media
                    if msg.media:
                        if hasattr(msg.media, 'photo'):
                            message['media_type'] = 'photo'
                            # Get photo thumbnail
                            try:
                                thumb = await client.download_file(msg.media, bytes)
                                if thumb:
                                    message['media_thumb'] = base64.b64encode(thumb[:10000]).decode('utf-8')
                            except:
                                pass
                        elif hasattr(msg.media, 'document'):
                            for attr in msg.media.document.attributes:
                                if isinstance(attr, DocumentAttributeSticker):
                                    message['media_type'] = 'sticker'
                                    message['sticker_emoji'] = attr.alt
                                    break
                            else:
                                message['media_type'] = 'document'
                                message['media_name'] = msg.media.document.attributes[0].file_name if msg.media.document.attributes else 'File'
                                message['media_size'] = msg.media.document.size
                        elif hasattr(msg.media, 'video'):
                            message['media_type'] = 'video'
                        elif hasattr(msg.media, 'audio'):
                            message['media_type'] = 'audio'
                    
                    messages.append(message)
                
                return {'success': True, 'messages': messages, 'chat_info': chat_info}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch(), timeout=60))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-photo', methods=['POST'])
def get_chat_photo():
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        
        # Check cache
        cached = get_cached_chat_photo(account_id, chat_id)
        if cached:
            return jsonify({'success': True, 'photo': cached})
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(chat_id))
                photo = await client.download_profile_photo(entity, file=bytes)
                if photo:
                    photo_base64 = base64.b64encode(photo).decode('utf-8')
                    save_chat_photo(account_id, chat_id, photo_base64)
                    return {'success': True, 'photo': photo_base64}
                return {'success': True, 'photo': None}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    try:
        data = request.json
        account_id = data.get('accountId')
        chat_id = data.get('chatId')
        message = data.get('message')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
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
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-media', methods=['POST'])
def send_media():
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
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send(), timeout=60))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== EMAIL MANAGEMENT ROUTES ====================

@app.route('/api/check-email-status', methods=['POST'])
def check_email_status():
    try:
        account_id = request.json.get('accountId')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def check():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                password_info = await client(functions.account.GetPasswordRequest())
                return {
                    'success': True,
                    'has_password': password_info.has_password,
                    'has_recovery': getattr(password_info, 'has_recovery', False),
                    'email': getattr(password_info, 'email', None),
                    'email_unconfirmed': getattr(password_info, 'email_unconfirmed', None),
                    'hint': getattr(password_info, 'hint', None)
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(check()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-email-code', methods=['POST'])
def send_email_code():
    try:
        data = request.json
        account_id = data.get('accountId')
        email = data.get('email')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client(functions.account.SendVerifyEmailCodeRequest(
                    purpose=types.account.EmailPurposeLoginSetup(email=email)
                ))
                
                # Store for verification
                if 'pending_emails' not in temp_sessions:
                    temp_sessions['pending_emails'] = {}
                temp_sessions['pending_emails'][str(account_id)] = {
                    'email': email,
                    'timeout': result.timeout,
                    'expires': time.time() + result.timeout
                }
                
                return {'success': True, 'email': email, 'timeout': result.timeout}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-email-code', methods=['POST'])
def verify_email_code():
    try:
        data = request.json
        account_id = data.get('accountId')
        email = data.get('email')
        code = data.get('code')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def verify():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.VerifyEmailRequest(email=email, code=code))
                
                # Clear pending
                if 'pending_emails' in temp_sessions:
                    temp_sessions['pending_emails'].pop(str(account_id), None)
                
                return {'success': True, 'message': 'Email verified successfully'}
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(verify()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/set-2fa', methods=['POST'])
def set_2fa():
    try:
        data = request.json
        account_id = data.get('accountId')
        current_password = data.get('currentPassword', '')
        new_password = data.get('newPassword')
        hint = data.get('hint', '')
        email = data.get('email', '')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def set_2fa_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                password_info = await client(functions.account.GetPasswordRequest())
                
                # Prepare password hash
                new_password_bytes = new_password.encode('utf-8')
                
                # Create new settings
                new_settings = types.account.PasswordInputSettings(
                    new_algo=password_info.new_algo,
                    new_password_hash=password_info.new_algo.hash(new_password_bytes),
                    hint=hint if hint else ""
                )
                
                if email:
                    new_settings.email = email
                
                # Update password
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=current_password if current_password else password_info.current_password,
                    new_settings=new_settings
                ))
                
                return {'success': True, 'message': '2FA enabled successfully'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Invalid current password'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(set_2fa_async()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/disable-2fa', methods=['POST'])
def disable_2fa():
    try:
        account_id = request.json.get('accountId')
        password = request.json.get('password', '')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def disable():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                password_info = await client(functions.account.GetPasswordRequest())
                
                # Disable password
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=password if password else password_info.current_password,
                    new_settings=types.account.PasswordInputSettings(
                        new_algo=password_info.new_algo,
                        new_password_hash=b''
                    )
                ))
                
                return {'success': True, 'message': '2FA disabled'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Invalid password'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(disable()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== SEARCH & JOIN ROUTES ====================

@app.route('/api/search', methods=['POST'])
def search():
    try:
        data = request.json
        account_id = data.get('accountId')
        query = data.get('query')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def search_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                results = []
                
                # Search contacts
                contacts = await client(functions.contacts.SearchRequest(q=query, limit=20))
                for user in contacts.users:
                    if hasattr(user, 'first_name'):
                        results.append({
                            'id': str(user.id),
                            'title': user.first_name + (' ' + (user.last_name or '') if user.last_name else ''),
                            'type': 'user',
                            'username': user.username or '',
                            'verified': getattr(user, 'verified', False),
                            'participants_count': None
                        })
                
                # Search public groups/channels
                found = await client(functions.contacts.SearchRequest(q=query, limit=30))
                for chat in found.chats:
                    if hasattr(chat, 'title'):
                        chat_type = 'group'
                        if hasattr(chat, 'broadcast') and chat.broadcast:
                            chat_type = 'channel'
                        elif hasattr(chat, 'megagroup') and chat.megagroup:
                            chat_type = 'supergroup'
                        
                        results.append({
                            'id': str(chat.id),
                            'title': chat.title,
                            'type': chat_type,
                            'username': getattr(chat, 'username', ''),
                            'verified': getattr(chat, 'verified', False),
                            'participants_count': getattr(chat, 'participants_count', None)
                        })
                
                # Remove duplicates
                seen = set()
                unique = []
                for r in results:
                    if r['id'] not in seen:
                        seen.add(r['id'])
                        unique.append(r)
                
                return {'success': True, 'results': unique}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(search_async()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/join-entity', methods=['POST'])
def join_entity():
    try:
        data = request.json
        account_id = data.get('accountId')
        entity_id = data.get('entityId')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def join():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # Try to get entity
                try:
                    entity = await client.get_entity(entity_id)
                except:
                    if not entity_id.startswith('@'):
                        entity = await client.get_entity('@' + entity_id)
                    else:
                        raise
                
                # Join channel/group
                await client(functions.channels.JoinChannelRequest(entity))
                
                # Get info
                info = {
                    'title': getattr(entity, 'title', 'Entity'),
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 'group',
                    'participants_count': getattr(entity, 'participants_count', None),
                    'username': getattr(entity, 'username', None)
                }
                
                return {'success': True, 'info': info}
            except errors.InviteHashInvalidError:
                return {'success': False, 'error': 'Invalid invite link'}
            except errors.InviteHashExpiredError:
                return {'success': False, 'error': 'Invite link expired'}
            except errors.UsersTooMuchError:
                return {'success': False, 'error': 'Group is full'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(join()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-channel-info', methods=['POST'])
def get_channel_info():
    try:
        data = request.json
        account_id = data.get('accountId')
        channel_id = data.get('channelId')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_info():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(channel_id))
                
                # Get full channel info
                full = await client(functions.channels.GetFullChannelRequest(entity))
                
                return {
                    'success': True,
                    'title': entity.title,
                    'username': entity.username,
                    'participants_count': full.full_chat.participants_count,
                    'online_count': getattr(full.full_chat, 'online_count', 0),
                    'description': full.full_chat.about,
                    'is_verified': entity.verified,
                    'is_scam': entity.scam,
                    'is_fake': entity.fake,
                    'is_muted': full.full_chat.notify_settings.mute_until > time.time()
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get_info()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/toggle-mute', methods=['POST'])
def toggle_mute():
    try:
        data = request.json
        account_id = data.get('accountId')
        channel_id = data.get('channelId')
        mute = data.get('mute', True)
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def toggle():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(channel_id))
                mute_until = 2**31 - 1 if mute else 0  # Forever or unmute
                await client(functions.account.UpdateNotifySettingsRequest(
                    peer=entity,
                    settings=types.InputPeerNotifySettings(
                        show_previews=True,
                        silent=mute,
                        mute_until=mute_until
                    )
                ))
                return {'success': True, 'muted': mute}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(toggle()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== SESSION ROUTES ====================

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    try:
        account_id = request.json.get('accountId')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get():
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
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    try:
        account_id = request.json.get('accountId')
        session_hash = request.json.get('hash')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
                return {'success': True}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    try:
        account_id = request.json.get('accountId')
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
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
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== AUTO-ADD API ROUTES ====================

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings_api():
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        settings = get_auto_add_settings(int(account_id))
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings_api():
    try:
        data = request.json
        account_id = data.get('accountId')
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
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    try:
        account_id = request.args.get('accountId')
        if not account_id:
            return jsonify({'success': False, 'error': 'Account ID required'})
        settings = get_auto_add_settings(int(account_id))
        return jsonify({
            'success': True,
            'added_today': settings.get('added_today', 0),
            'daily_limit': settings.get('daily_limit', 30),
            'enabled': settings.get('enabled', False)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== HEALTH & UTILITY ====================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'auto_add_tasks': len(auto_add_tasks),
        'time': datetime.now().isoformat()
    })

@app.route('/ping')
def ping():
    return 'pong'

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled error: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500

# ==================== KEEP ALIVE ====================

def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    last_backup = datetime.now()
    
    while True:
        try:
            requests.get(f"{app_url}/ping", timeout=5)
            # Backup every 6 hours
            if (datetime.now() - last_backup).seconds >= 21600:
                backup_database()
                last_backup = datetime.now()
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        time.sleep(180)

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM ACCOUNT MANAGER - COMPLETE EDITION')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print(f'✅ Auto-add tasks: {len(auto_add_tasks)}')
    print('='*70)
    print('\n🚀 FEATURES:')
    print('   • Multi-account management')
    print('   • Auto-add members to groups')
    print('   • Media send & receive (photos, videos, docs)')
    print('   • Sticker & emoji support')
    print('   • Email management & 2FA')
    print('   • Last seen status')
    print('   • Search groups/channels/users')
    print('   • Join groups/channels')
    print('   • Mute/unmute channels')
    print('   • View channel statistics')
    print('   • Profile photos & chat avatars')
    print('   • Session management')
    print('   • Automatic database backups')
    print('='*70 + '\n')
    
    # Start keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start auto-add for enabled accounts
    with get_db() as conn:
        rows = conn.execute('SELECT account_id FROM auto_add_settings WHERE enabled = 1').fetchall()
        for row in rows:
            start_auto_add_thread(row['account_id'])
    
    # Run Flask
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
