from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError, FloodWaitError
from telethon.tl.types import (
    InputPeerUser, InputPeerChat, InputPeerChannel,
    MessageMediaPhoto, MessageMediaDocument, MessageMediaVideo, MessageMediaAudio,
    DocumentAttributeFilename, DocumentAttributeAudio, DocumentAttributeVideo, DocumentAttributeSticker,
    MessageEntityUrl, MessageEntityEmail, MessageEntityPhone, MessageEntityHashtag,
    MessageEntityCashtag, MessageEntityBotCommand, MessageEntityMentionName, MessageEntityTextUrl,
    MessageEntityPre, MessageEntityCode, MessageEntityItalic, MessageEntityBold,
    MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntitySpoiler
)
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
from datetime import datetime, timedelta
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Database setup
DB_PATH = 'telegram_bot.db'
BACKUP_DIR = 'backups'
os.makedirs(BACKUP_DIR, exist_ok=True)

@contextmanager
def get_db():
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
                role TEXT,
                message TEXT,
                media_type TEXT,
                media_data TEXT,
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
                auto_join BOOLEAN DEFAULT 1,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Chat photos cache
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_photos (
                account_id INTEGER,
                chat_id TEXT,
                photo BLOB,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (account_id, chat_id)
            )
        ''')
        
        logger.info("✅ Database initialized")

# Global storage
accounts = []
temp_sessions = {}
auto_add_tasks = {}

def run_async(coro, timeout=60):
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

# Database functions
def load_accounts_from_db():
    global accounts
    accounts = []
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM accounts WHERE is_valid = 1 ORDER BY id').fetchall()
            for row in rows:
                accounts.append({
                    'id': row['id'], 'phone': row['phone'], 'name': row['name'],
                    'username': row['username'], 'session': row['session'], 'photo': row['photo']
                })
        logger.info(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        init_db()

def add_account_to_db(phone, name, username, session_string, photo=None):
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO accounts (phone, name, username, session, photo, last_active) VALUES (?, ?, ?, ?, ?, ?)',
            (phone, name, username, session_string, photo, datetime.now().isoformat())
        )
        return cursor.lastrowid

def remove_account_from_db(account_id):
    with get_db() as conn:
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        conn.execute('DELETE FROM conversation_history WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM auto_add_settings WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM chat_photos WHERE account_id = ?', (account_id,))

def save_conversation(account_id, chat_id, chat_title, role, message, media_type=None, media_data=None):
    with get_db() as conn:
        conn.execute('''
            INSERT INTO conversation_history (account_id, chat_id, chat_title, role, message, media_type, media_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (account_id, chat_id, chat_title, role, message, media_type, media_data))

def get_conversation_history(account_id, chat_id, limit=50):
    with get_db() as conn:
        rows = conn.execute('''
            SELECT role, message, media_type, media_data, timestamp 
            FROM conversation_history 
            WHERE account_id = ? AND chat_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (account_id, chat_id, limit)).fetchall()
        return [{'role': r['role'], 'message': r['message'], 'media_type': r['media_type'], 
                 'media_data': r['media_data'], 'time': r['timestamp']} for r in reversed(rows)]

def clear_conversation_history(account_id, chat_id):
    with get_db() as conn:
        conn.execute('DELETE FROM conversation_history WHERE account_id = ? AND chat_id = ?', (account_id, chat_id))

def backup_database():
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'telegram_bot_{timestamp}.db')
        shutil.copy2(DB_PATH, backup_path)
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('telegram_bot_')])
        for old in backups[:-10]:
            os.remove(os.path.join(BACKUP_DIR, old))
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False

# Auto-add functions
def get_auto_add_settings(account_id):
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
                'use_contacts': bool(row['use_contacts']),
                'use_recent_chats': bool(row['use_recent_chats']),
                'use_scraping': bool(row['use_scraping']),
                'scrape_limit': row['scrape_limit'] or 100,
                'skip_bots': bool(row['skip_bots']),
                'auto_join': bool(row['auto_join'])
            }
    return {
        'enabled': False, 'target_group': 'Abe_armygroup', 'daily_limit': 30, 'delay_seconds': 45,
        'added_today': 0, 'last_reset': None, 'source_groups': ['@telegram', '@durov'],
        'use_contacts': True, 'use_recent_chats': True, 'use_scraping': True,
        'scrape_limit': 100, 'skip_bots': True, 'auto_join': True
    }

def save_auto_add_settings(account_id, settings):
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO auto_add_settings 
            (account_id, enabled, target_group, daily_limit, delay_seconds, added_today, last_reset, 
             source_groups, use_contacts, use_recent_chats, use_scraping, scrape_limit, skip_bots, auto_join)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            account_id, 1 if settings.get('enabled') else 0,
            settings.get('target_group', 'Abe_armygroup'), settings.get('daily_limit', 30),
            settings.get('delay_seconds', 45), settings.get('added_today', 0), settings.get('last_reset'),
            json.dumps(settings.get('source_groups', [])), 1 if settings.get('use_contacts', True) else 0,
            1 if settings.get('use_recent_chats', True) else 0, 1 if settings.get('use_scraping', True) else 0,
            settings.get('scrape_limit', 100), 1 if settings.get('skip_bots', True) else 0,
            1 if settings.get('auto_join', True) else 0
        ))

async def auto_add_worker(account_id):
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return
    
    while True:
        try:
            settings = get_auto_add_settings(account_id)
            if not settings.get('enabled'):
                break
            
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
                group = await client.get_entity('@' + settings['target_group'])
                
                # Get existing members
                existing = set()
                async for user in client.iter_participants(group, limit=1000):
                    if user and user.id:
                        existing.add(user.id)
                
                # Get new members from contacts
                new_members = []
                if settings.get('use_contacts'):
                    contacts = await client(functions.contacts.GetContactsRequest(0))
                    for user in contacts.users:
                        if user.id not in existing and (not settings.get('skip_bots') or not user.bot):
                            new_members.append(user)
                
                # Add members
                for user in new_members[:settings['daily_limit'] - settings['added_today']]:
                    try:
                        await client(functions.channels.InviteToChannelRequest(
                            group, [await client.get_input_entity(user.id)]
                        ))
                        settings['added_today'] += 1
                        save_auto_add_settings(account_id, settings)
                        await asyncio.sleep(settings['delay_seconds'])
                    except Exception as e:
                        logger.error(f"Failed to add {user.id}: {e}")
            finally:
                await client.disconnect()
            
            await asyncio.sleep(1800)
        except Exception as e:
            logger.error(f"Auto-add error: {e}")
            await asyncio.sleep(300)

def start_auto_add_thread(account_id):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auto_add_worker(account_id))
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    auto_add_tasks[account_id] = thread

# Initialize
init_db()
load_accounts_from_db()

# ==================== PAGE ROUTES ====================
@app.route('/')
def home(): return send_file('login.html')
@app.route('/login')
def login(): return send_file('login.html')
@app.route('/dashboard')
def dashboard(): return send_file('dashboard.html')
@app.route('/dash')
def dash(): return send_file('dash.html')
@app.route('/all')
def all_sessions(): return send_file('all.html')
@app.route('/auto-add')
def auto_add(): return send_file('auto_add.html')
@app.route('/settings')
def settings(): return send_file('settings.html')

# ==================== ACCOUNT ROUTES ====================
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({'success': True, 'accounts': [{'id': a['id'], 'phone': a['phone'], 'name': a['name'], 'username': a['username']} for a in accounts]})

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
                except:
                    pass
                return {'success': True, 'name': me.first_name or '', 'username': me.username or '', 
                        'phone': me.phone or '', 'photo': photo}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get_info()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        phone = request.json.get('phone')
        if not phone.startswith('+'): phone = '+' + phone
        
        async def send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                session_id = str(int(time.time()))
                temp_sessions[session_id] = {'phone': phone, 'hash': result.phone_code_hash, 'session': client.session.save()}
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
                    if not password: return {'need_password': True}
                    await client.sign_in(password=password)
                
                me = await client.get_me()
                photo = None
                try:
                    photo_data = await client.download_profile_photo(me, file=bytes)
                    if photo_data: photo = base64.b64encode(photo_data).decode('utf-8')
                except: pass
                
                new_id = add_account_to_db(me.phone, me.first_name or 'User', me.username or '', client.session.save(), photo)
                accounts.append({'id': new_id, 'phone': me.phone, 'name': me.first_name or 'User', 
                                'username': me.username or '', 'session': client.session.save(), 'photo': photo})
                save_auto_add_settings(new_id, get_auto_add_settings(new_id))
                backup_database()
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
        backup_database()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    try:
        account_id, first_name = request.json.get('accountId'), request.json.get('firstName')
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
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
        if username.startswith('@'): username = username[1:]
        
        account = next((a for a in accounts if a['id'] == account_id), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
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
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                dialogs = await client.get_dialogs(limit=100)
                chats = []
                for dialog in dialogs:
                    if not dialog: continue
                    chat_type = 'channel' if dialog.is_channel else 'group' if dialog.is_group else 'user'
                    chats.append({
                        'id': str(dialog.id), 'title': dialog.name or 'Unknown', 'type': chat_type,
                        'unread': dialog.unread_count or 0, 'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else '',
                        'lastMessageDate': int(dialog.message.date.timestamp()) if dialog.message and dialog.message.date else 0
                    })
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('chatId')))
                
                # Chat info
                chat_info = {
                    'id': str(entity.id), 'title': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                    'type': 'channel' if hasattr(entity, 'broadcast') and entity.broadcast else 
                            'group' if hasattr(entity, 'megagroup') else 'user',
                    'username': getattr(entity, 'username', None),
                    'participants_count': getattr(entity, 'participants_count', None)
                }
                
                # Last seen for users
                if chat_info['type'] == 'user' and hasattr(entity, 'status'):
                    if hasattr(entity.status, 'was_online'):
                        chat_info['last_seen'] = int(entity.status.was_online.timestamp())
                    elif hasattr(entity.status, 'expires'):
                        chat_info['online'] = True
                
                # Get messages
                messages = []
                async for msg in client.iter_messages(entity, limit=data.get('limit', 100)):
                    message = {
                        'id': msg.id, 'text': msg.text or '', 'date': int(msg.date.timestamp()) if msg.date else 0,
                        'out': msg.out, 'has_media': msg.media is not None, 'media_type': None, 'media_data': None
                    }
                    
                    # Handle media
                    if msg.media:
                        if hasattr(msg.media, 'photo'):
                            message['media_type'] = 'photo'
                            try:
                                thumb = await client.download_file(msg.media, bytes)
                                if thumb:
                                    message['media_data'] = base64.b64encode(thumb[:10000]).decode('utf-8')
                            except: pass
                        elif hasattr(msg.media, 'document'):
                            for attr in msg.media.document.attributes:
                                if isinstance(attr, DocumentAttributeSticker):
                                    message['media_type'] = 'sticker'
                                    message['text'] = f"🎨 {attr.alt}" if attr.alt else "🎨 Sticker"
                                    break
                            else:
                                message['media_type'] = 'document'
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('chatId')))
                photo = await client.download_profile_photo(entity, file=bytes)
                if photo:
                    return {'success': True, 'photo': base64.b64encode(photo).decode('utf-8')}
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('chatId')))
                await client.send_message(entity, data.get('message'))
                save_conversation(data.get('accountId'), data.get('chatId'), getattr(entity, 'title', 'Chat'), 'user', data.get('message'))
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
        
        if not file: return jsonify({'success': False, 'error': 'No file'})
        
        account = next((a for a in accounts if a['id'] == int(account_id)), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(chat_id))
                await client.send_file(entity, file.read(), caption=caption)
                return {'success': True}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send(), timeout=60))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/conversation-history', methods=['GET'])
def conversation_history():
    try:
        history = get_conversation_history(int(request.args.get('accountId')), request.args.get('chatId'))
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    try:
        data = request.json
        clear_conversation_history(data.get('accountId'), data.get('chatId'))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== EMAIL & 2FA ROUTES ====================
@app.route('/api/check-email-status', methods=['POST'])
def check_email_status():
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def check():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                pwd = await client(functions.account.GetPasswordRequest())
                return {'success': True, 'has_password': pwd.has_password, 'has_recovery': getattr(pwd, 'has_recovery', False),
                        'email': getattr(pwd, 'email', None), 'hint': getattr(pwd, 'hint', None)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(check()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-email-code', methods=['POST'])
def send_email_code():
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.SendVerifyEmailCodeRequest(
                    purpose=types.account.EmailPurposeLoginSetup(email=data.get('email'))
                ))
                return {'success': True, 'email': data.get('email')}
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def verify():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                await client(functions.account.VerifyEmailRequest(email=data.get('email'), code=data.get('code')))
                return {'success': True}
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def set_2fa_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                pwd = await client(functions.account.GetPasswordRequest())
                new_settings = types.account.PasswordInputSettings(
                    new_algo=pwd.new_algo,
                    new_password_hash=pwd.new_algo.hash(data.get('newPassword').encode('utf-8')),
                    hint=data.get('hint', '')
                )
                if data.get('email'): new_settings.email = data.get('email')
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=data.get('currentPassword', '') if data.get('currentPassword') else pwd.current_password,
                    new_settings=new_settings
                ))
                return {'success': True}
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
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def disable():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                pwd = await client(functions.account.GetPasswordRequest())
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=password if password else pwd.current_password,
                    new_settings=types.account.PasswordInputSettings(
                        new_algo=pwd.new_algo, new_password_hash=b''
                    )
                ))
                return {'success': True}
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def search_async():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                results = []
                found = await client(functions.contacts.SearchRequest(q=data.get('query'), limit=30))
                for chat in found.chats:
                    if hasattr(chat, 'title'):
                        results.append({
                            'id': str(chat.id), 'title': chat.title,
                            'type': 'channel' if hasattr(chat, 'broadcast') and chat.broadcast else 'group',
                            'username': getattr(chat, 'username', '')
                        })
                return {'success': True, 'results': results}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(search_async()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/join-entity', methods=['POST'])
def join_entity():
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def join():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(data.get('entityId'))
                await client(functions.channels.JoinChannelRequest(entity))
                return {'success': True, 'title': getattr(entity, 'title', 'Entity')}
            except errors.InviteHashInvalidError:
                return {'success': False, 'error': 'Invalid invite link'}
            except errors.InviteHashExpiredError:
                return {'success': False, 'error': 'Invite link expired'}
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get_info():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('channelId')))
                full = await client(functions.channels.GetFullChannelRequest(entity))
                return {
                    'success': True, 'title': entity.title, 'username': entity.username,
                    'participants_count': full.full_chat.participants_count if hasattr(full.full_chat, 'participants_count') else None,
                    'online_count': getattr(full.full_chat, 'online_count', 0),
                    'description': full.full_chat.about if hasattr(full.full_chat, 'about') else '',
                    'is_verified': getattr(entity, 'verified', False)
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get_info()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== SESSION ROUTES ====================
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def get():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                sessions = [{'hash': a.hash, 'device_model': a.device_model, 'platform': a.platform,
                            'ip': a.ip, 'country': a.country, 'date_active': a.date_active, 'current': a.current}
                           for a in result.authorizations]
                return {'success': True, 'sessions': sessions}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(get()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                current = next((a.hash for a in result.authorizations if a.current), None)
                count = 0
                for auth in result.authorizations:
                    if auth.hash != current:
                        try:
                            await client(functions.account.ResetAuthorizationRequest(auth.hash))
                            count += 1
                        except: pass
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
        settings = get_auto_add_settings(int(request.args.get('accountId')))
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings_api():
    try:
        data = request.json
        settings = {
            'enabled': data.get('enabled', False), 'target_group': data.get('target_group', 'Abe_armygroup'),
            'daily_limit': data.get('daily_limit', 30), 'delay_seconds': data.get('delay_seconds', 45),
            'source_groups': data.get('source_groups', ['@telegram', '@durov']),
            'use_contacts': data.get('use_contacts', True), 'use_recent_chats': data.get('use_recent_chats', True),
            'use_scraping': data.get('use_scraping', True), 'scrape_limit': data.get('scrape_limit', 100),
            'skip_bots': data.get('skip_bots', True), 'auto_join': data.get('auto_join', True),
            'added_today': 0, 'last_reset': datetime.now().strftime('%Y-%m-%d')
        }
        save_auto_add_settings(int(data.get('accountId')), settings)
        if settings['enabled']:
            start_auto_add_thread(int(data.get('accountId')))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    try:
        settings = get_auto_add_settings(int(request.args.get('accountId')))
        return jsonify({'success': True, 'added_today': settings.get('added_today', 0),
                       'daily_limit': settings.get('daily_limit', 30), 'enabled': settings.get('enabled', False)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== HEALTH & UTILITY ====================
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'accounts': len(accounts), 'auto_add_tasks': len(auto_add_tasks)})

@app.route('/ping')
def ping(): return 'pong'

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Error: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500

# ==================== KEEP ALIVE ====================
def keep_alive():
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    last_backup = datetime.now()
    while True:
        try:
            requests.get(f"{app_url}/ping", timeout=5)
            if (datetime.now() - last_backup).seconds >= 21600:
                backup_database()
                last_backup = datetime.now()
        except: pass
        time.sleep(180)

# ==================== STARTUP ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM ACCOUNT MANAGER - COMPLETE')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print(f'✅ Auto-add: {len(auto_add_tasks)}')
    print('='*70)
    print('\n🚀 FEATURES:')
    print('   • Auto-add members to groups')
    print('   • Media send/receive (photos, videos, docs, stickers)')
    print('   • Email management & 2FA')
    print('   • Last seen status')
    print('   • Search & join groups/channels')
    print('   • Profile photos & chat avatars')
    print('   • Session management')
    print('   • Automatic database backups')
    print('='*70 + '\n')
    
    threading.Thread(target=keep_alive, daemon=True).start()
    
    with get_db() as conn:
        rows = conn.execute('SELECT account_id FROM auto_add_settings WHERE enabled = 1').fetchall()
        for row in rows:
            start_auto_add_thread(row['account_id'])
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
