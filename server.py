from flask import Flask, send_file, jsonify, request, abort
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
from datetime import datetime
import logging
import threading

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Your API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Store temporary data for OTP
temp_data = {}

# Store accounts persistently
accounts = []
ACCOUNTS_FILE = 'accounts.json'

# Create a global event loop for the main thread
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Load existing accounts if file exists
if os.path.exists(ACCOUNTS_FILE):
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)
        logger.info(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"⚠️ Error loading accounts: {e}")
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        logger.info(f"💾 Saved {len(accounts)} accounts")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accounts: {e}")
        return False

# Fixed helper to run async functions
def run_async(coro):
    """Run async coroutine in the existing event loop"""
    global loop
    try:
        # If we're in a thread, create a new event loop
        if threading.current_thread() is not threading.main_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        else:
            # In main thread, use the existing loop
            return loop.run_until_complete(coro)
    except RuntimeError:
        # If no event loop is running, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

# -------------------- SERVE HTML FILES --------------------
@app.route('/')
def serve_index():
    """Serve the login/index page"""
    try:
        return send_file('index.html')
    except FileNotFoundError:
        logger.error("index.html not found!")
        return send_file('login.html')  # Try login.html as fallback

@app.route('/dashboard')
def serve_dashboard():
    """Serve the dashboard page"""
    try:
        return send_file('dashboard.html')
    except FileNotFoundError:
        logger.error("dashboard.html not found!")
        return "dashboard.html not found", 404

# -------------------- GET ALL ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Return all accounts with proper formatting for dashboard"""
    account_list = []
    for acc in accounts:
        account_list.append({
            'id': acc['id'],
            'phone': acc['phone'],
            'name': acc.get('name', 'User'),
            'username': acc.get('username', ''),
            'session': acc.get('session', acc.get('string_session', ''))
        })
    return jsonify({'success': True, 'accounts': account_list})

# -------------------- ADD ACCOUNT (SEND OTP) --------------------
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH, timeout=30)
        await client.connect()
        try:
            # Add a small delay to ensure connection is established
            await asyncio.sleep(1)
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            return {
                'success': True,
                'phone_code_hash': result.phone_code_hash,
                'session_str': session_str
            }
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Too many attempts. Wait {e.seconds} seconds'}
        except Exception as e:
            logger.error(f"Error in send_code: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send_code())
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
        
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': result['phone_code_hash'],
            'session_str': result['session_str']
        }
        logger.info(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
        
    except Exception as e:
        logger.error(f"Error in add-account: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- VERIFY CODE --------------------
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not session_id or session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'})
    
    session = temp_data[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session['session_str']), API_ID, API_HASH, timeout=30)
        await client.connect()
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if password:
                # 2FA login
                await client.sign_in(password=password)
            else:
                # Normal login with code
                await client.sign_in(
                    session['phone'], 
                    code, 
                    phone_code_hash=session['phone_code_hash']
                )
            
            # Get user info
            me = await client.get_me()
            final_session = client.session.save()
            
            return {
                'success': True,
                'me': {
                    'id': me.id,
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'username': me.username or '',
                    'phone': me.phone or session['phone']
                },
                'session': final_session
            }
            
        except errors.SessionPasswordNeededError:
            return {'success': False, 'need_password': True}
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except Exception as e:
            logger.error(f"Error in verify: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Verification failed')})
        
        # Create new account with a unique ID
        me = result['me']
        new_account = {
            'id': max([acc['id'] for acc in accounts], default=0) + 1,
            'phone': session['phone'],
            'name': f"{me.get('first_name', '')} {me.get('last_name', '')}".strip() or 'User',
            'username': me.get('username', ''),
            'user_id': me.get('id'),
            'session': result['session'],
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        accounts.append(new_account)
        save_accounts()
        
        # Clean up temp data
        if session_id in temp_data:
            del temp_data[session_id]
        
        logger.info(f"✅ Account added: {session['phone']}")
        return jsonify({'success': True, 'account': new_account})
        
    except Exception as e:
        logger.error(f"Error in verify-code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET MESSAGES (CHATS) --------------------
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=30)
        await client.connect()
        
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs (chats)
            dialogs = await client.get_dialogs(limit=30)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                # Get chat name
                if dialog.is_user:
                    name = dialog.entity.first_name or ''
                    if dialog.entity.last_name:
                        name += f" {dialog.entity.last_name}"
                    if not name:
                        name = dialog.entity.username or 'Unknown User'
                elif dialog.is_group or dialog.is_channel:
                    name = dialog.name or 'Unknown Group'
                else:
                    name = dialog.name or 'Unknown'
                
                chat_id = str(dialog.id)
                
                # Add chat to list
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': dialog.message.text[:50] + '...' if dialog.message and dialog.message.text else '',
                    'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
                })
                
                # Get last 15 messages for this chat
                try:
                    msgs = await client.get_messages(dialog.entity, limit=15)
                    for msg in msgs:
                        if msg and msg.text:
                            all_messages.append({
                                'chatId': chat_id,
                                'text': msg.text,
                                'date': msg.date.timestamp(),
                                'out': msg.out
                            })
                except Exception as e:
                    logger.error(f"Error fetching messages for chat {chat_id}: {e}")
                    continue
            
            return {
                'success': True,
                'chats': chats,
                'messages': all_messages
            }
            
        except Exception as e:
            logger.error(f"Error in fetch_chats: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch_chats())
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to fetch chats')})
        
        return jsonify({
            'success': True,
            'chats': result['chats'],
            'messages': result['messages']
        })
        
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- SEND MESSAGE --------------------
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id, message]):
        return jsonify({'success': False, 'error': 'Account ID, Chat ID, and message required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=30)
        await client.connect()
        
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get entity
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            # Send message
            await client.send_message(entity, message)
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        
        if result.get('success'):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send message')})
            
    except Exception as e:
        logger.error(f"Error in send-message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    original_count = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_count:
        save_accounts()
        logger.info(f"🗑️ Removed account {account_id}")
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Account not found'})

# -------------------- HEALTH CHECK --------------------
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_data)
    })

# Error handler for 404
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

# Error handler for 500
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - FIXED VERSION')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print('✅ Fixed event loop handling')
    print('✅ Endpoints ready:')
    print('   - GET  /')
    print('   - GET  /dashboard')
    print('   - GET  /api/accounts')
    print('   - POST /api/add-account')
    print('   - POST /api/verify-code')
    print('   - POST /api/get-messages')
    print('   - POST /api/send-message')
    print('   - POST /api/remove-account')
    print('   - GET  /api/health')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
