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
import sqlite3
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

# Database setup
DB_PATH = 'telegram_bot.db'

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Auto-add settings
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auto_add_settings (
                account_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                target_group TEXT,
                daily_limit INTEGER DEFAULT 30,
                delay_seconds INTEGER DEFAULT 45,
                added_today INTEGER DEFAULT 0,
                last_reset TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Chat photos cache
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_photos (
                account_id INTEGER,
                chat_id TEXT,
                photo BLOB,
                PRIMARY KEY (account_id, chat_id)
            )
        ''')
        
        logger.info("✅ Database initialized")

# Global storage
accounts = []
temp_sessions = {}
auto_add_threads = {}

def run_async(coro, timeout=30):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Timeout'}
        finally:
            loop.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Database functions
def load_accounts():
    global accounts
    accounts = []
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM accounts ORDER BY id').fetchall()
            for row in rows:
                accounts.append({
                    'id': row['id'], 'phone': row['phone'], 'name': row['name'],
                    'username': row['username'], 'session': row['session'], 'photo': row['photo']
                })
        logger.info(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        init_db()

def add_account(phone, name, username, session_string, photo=None):
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO accounts (phone, name, username, session, photo) VALUES (?, ?, ?, ?, ?)',
            (phone, name, username, session_string, photo)
        )
        return cursor.lastrowid

def remove_account_db(account_id):
    with get_db() as conn:
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        conn.execute('DELETE FROM auto_add_settings WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM chat_photos WHERE account_id = ?', (account_id,))

def save_chat_photo(account_id, chat_id, photo):
    with get_db() as conn:
        conn.execute('INSERT OR REPLACE INTO chat_photos (account_id, chat_id, photo) VALUES (?, ?, ?)',
                    (account_id, chat_id, photo))

def get_chat_photo_db(account_id, chat_id):
    with get_db() as conn:
        row = conn.execute('SELECT photo FROM chat_photos WHERE account_id = ? AND chat_id = ?',
                          (account_id, chat_id)).fetchone()
        return row['photo'] if row else None

# Auto-add functions
def get_auto_settings(account_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM auto_add_settings WHERE account_id = ?', (account_id,)).fetchone()
        if row:
            return {
                'enabled': bool(row['enabled']),
                'target_group': row['target_group'] or 'Abe_armygroup',
                'daily_limit': row['daily_limit'] or 30,
                'delay_seconds': row['delay_seconds'] or 45,
                'added_today': row['added_today'] or 0,
                'last_reset': row['last_reset']
            }
    return {
        'enabled': False, 'target_group': 'Abe_armygroup', 'daily_limit': 30,
        'delay_seconds': 45, 'added_today': 0, 'last_reset': None
    }

def save_auto_settings(account_id, settings):
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO auto_add_settings 
            (account_id, enabled, target_group, daily_limit, delay_seconds, added_today, last_reset)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            account_id, 1 if settings.get('enabled') else 0,
            settings.get('target_group', 'Abe_armygroup'),
            settings.get('daily_limit', 30),
            settings.get('delay_seconds', 45),
            settings.get('added_today', 0),
            settings.get('last_reset')
        ))

async def auto_add_worker(account_id):
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return
    
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
                await asyncio.sleep(3600)
                continue
            
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                group = await client.get_entity('@' + settings['target_group'])
                
                # Get existing members
                existing = set()
                async for user in client.iter_participants(group, limit=500):
                    if user and user.id:
                        existing.add(user.id)
                
                # Get contacts
                contacts = await client(functions.contacts.GetContactsRequest(0))
                new_members = []
                for user in contacts.users:
                    if user.id not in existing and not user.bot:
                        new_members.append(user)
                
                # Add members
                for user in new_members[:settings['daily_limit'] - settings['added_today']]:
                    try:
                        await client(functions.channels.InviteToChannelRequest(
                            group, [await client.get_input_entity(user.id)]
                        ))
                        settings['added_today'] += 1
                        save_auto_settings(account_id, settings)
                        await asyncio.sleep(settings['delay_seconds'])
                    except:
                        pass
            except Exception as e:
                logger.error(f"Auto-add error: {e}")
            finally:
                await client.disconnect()
            
            await asyncio.sleep(1800)
        except Exception as e:
            logger.error(f"Auto-add worker error: {e}")
            await asyncio.sleep(300)

def start_auto_add(account_id):
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(auto_add_worker(account_id))
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    auto_add_threads[account_id] = thread

# Initialize
init_db()
load_accounts()

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

# ==================== API ROUTES ====================
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
def add_account_route():
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
                
                new_id = add_account(me.phone, me.first_name or 'User', me.username or '', client.session.save(), photo)
                accounts.append({'id': new_id, 'phone': me.phone, 'name': me.first_name or 'User', 
                                'username': me.username or '', 'session': client.session.save(), 'photo': photo})
                save_auto_settings(new_id, get_auto_settings(new_id))
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
        global accounts
        accounts = [a for a in accounts if a['id'] != account_id]
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
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(update()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    try:
        account = next((a for a in accounts if a['id'] == request.json.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                dialogs = await client.get_dialogs(limit=50)
                chats = []
                for dialog in dialogs:
                    if not dialog: continue
                    chat_type = 'channel' if dialog.is_channel else 'group' if dialog.is_group else 'user'
                    chats.append({
                        'id': str(dialog.id), 'title': dialog.name or 'Unknown', 'type': chat_type,
                        'unread': dialog.unread_count or 0,
                        'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else '',
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
                    'username': getattr(entity, 'username', None)
                }
                
                # Last seen for users
                if chat_info['type'] == 'user' and hasattr(entity, 'status'):
                    if hasattr(entity.status, 'was_online'):
                        chat_info['last_seen'] = int(entity.status.was_online.timestamp())
                    elif hasattr(entity.status, 'expires'):
                        chat_info['online'] = True
                
                # Get messages
                messages = []
                async for msg in client.iter_messages(entity, limit=data.get('limit', 50)):
                    message = {
                        'id': msg.id, 'text': msg.text or '', 'date': int(msg.date.timestamp()) if msg.date else 0,
                        'out': msg.out, 'has_media': msg.media is not None, 'media_type': None, 'media_data': None
                    }
                    
                    # Simple media detection
                    if msg.media:
                        if hasattr(msg.media, 'photo'):
                            message['media_type'] = 'photo'
                            try:
                                thumb = await client.download_file(msg.media, bytes)
                                if thumb:
                                    message['media_data'] = base64.b64encode(thumb[:5000]).decode('utf-8')
                            except: pass
                        elif hasattr(msg.media, 'document'):
                            message['media_type'] = 'document'
                        elif hasattr(msg.media, 'video'):
                            message['media_type'] = 'video'
                        elif hasattr(msg.media, 'audio'):
                            message['media_type'] = 'audio'
                    
                    messages.append(message)
                
                return {'success': True, 'messages': messages, 'chat_info': chat_info}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch(), timeout=45))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-chat-photo', methods=['POST'])
def get_chat_photo():
    try:
        data = request.json
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        # Check cache first
        cached = get_chat_photo_db(data.get('accountId'), data.get('chatId'))
        if cached:
            return jsonify({'success': True, 'photo': cached})
        
        async def fetch():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('chatId')))
                photo = await client.download_profile_photo(entity, file=bytes)
                if photo:
                    photo_base64 = base64.b64encode(photo).decode('utf-8')
                    save_chat_photo(data.get('accountId'), data.get('chatId'), photo_base64)
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
        account = next((a for a in accounts if a['id'] == data.get('accountId')), None)
        if not account: return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(int(data.get('chatId')))
                await client.send_message(entity, data.get('message'))
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
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(set_2fa_async()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
                sessions = [{'device_model': a.device_model, 'platform': a.platform, 'ip': a.ip, 
                            'country': a.country, 'date_active': a.date_active, 'current': a.current}
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

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add():
    try:
        settings = get_auto_settings(int(request.args.get('accountId')))
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add():
    try:
        data = request.json
        settings = {
            'enabled': data.get('enabled', False),
            'target_group': data.get('target_group', 'Abe_armygroup'),
            'daily_limit': data.get('daily_limit', 30),
            'delay_seconds': data.get('delay_seconds', 45),
            'added_today': 0,
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        }
        account_id = int(data.get('accountId'))
        save_auto_settings(account_id, settings)
        if settings['enabled']:
            start_auto_add(account_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_stats():
    try:
        settings = get_auto_settings(int(request.args.get('accountId')))
        return jsonify({'success': True, 'added_today': settings.get('added_today', 0),
                       'daily_limit': settings.get('daily_limit', 30), 'enabled': settings.get('enabled', False)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'accounts': len(accounts)})

@app.route('/ping')
def ping():
    return 'pong'

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Error: {e}")
    return jsonify({'success': False, 'error': str(e)}), 500

# ==================== STARTUP ====================
def start_all_auto_add():
    with get_db() as conn:
        rows = conn.execute('SELECT account_id FROM auto_add_settings WHERE enabled = 1').fetchall()
        for row in rows:
            start_auto_add(row['account_id'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*60)
    print('🤖 TELEGRAM ACCOUNT MANAGER')
    print('='*60)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    print('='*60)
    
    start_all_auto_add()
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
