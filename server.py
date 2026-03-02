from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import nest_asyncio
from datetime import datetime
import threading
import concurrent.futures

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# Your API credentials from environment variables
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Store temporary data for OTP
temp_data = {}

# Store accounts persistently
accounts = []
if os.path.exists('accounts.json'):
    try:
        with open('accounts.json', 'r') as f:
            accounts = json.load(f)
    except:
        accounts = []

# Create a ThreadPoolExecutor for running async functions
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# Helper function to run async functions in a separate event loop
def run_async(coro):
    """Run an async coroutine in a new event loop"""
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def index():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    return send_file('dashboard.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({'success': True, 'accounts': accounts})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    # Create a unique ID for this session
    session_id = str(len(temp_data) + 1) + "_" + str(datetime.now().timestamp())
    
    try:
        # Start client - create new client for each request
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        # Run async operations
        async def login_flow():
            await client.connect()
            
            if not await client.is_user_authorized():
                # Send code request
                await client.send_code_request(phone)
                return {'status': 'need_code', 'client': client}
            else:
                # Already authorized
                me = await client.get_me()
                session_string = client.session.save()
                await client.disconnect()
                return {
                    'status': 'authorized',
                    'me': me,
                    'session': session_string
                }
        
        result = run_async(login_flow())
        
        if result['status'] == 'need_code':
            # Store client for later use
            temp_data[session_id] = {
                'client': result['client'],
                'phone': phone,
                'step': 'waiting_code'
            }
            
            return jsonify({
                'success': True,
                'session_id': session_id,
                'next_step': 'code'
            })
        else:
            # Account already authorized
            me = result['me']
            session_string = result['session']
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                'session': session_string,
                'added': datetime.now().isoformat()
            }
            
            accounts.append(account)
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f)
            
            return jsonify({
                'success': True,
                'account': account
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    session_id = data.get('session_id')
    code = data.get('code')
    password = data.get('password', '')
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    temp = temp_data[session_id]
    client = temp['client']
    phone = temp['phone']
    
    try:
        async def verify_flow():
            if temp.get('step') == 'waiting_code':
                try:
                    await client.sign_in(phone, code)
                except errors.SessionPasswordNeededError:
                    return {'need_password': True}
                
                me = await client.get_me()
                session_string = client.session.save()
                await client.disconnect()
                return {
                    'success': True,
                    'me': me,
                    'session': session_string
                }
                
            elif temp.get('step') == 'need_password' and password:
                await client.sign_in(password=password)
                me = await client.get_me()
                session_string = client.session.save()
                await client.disconnect()
                return {
                    'success': True,
                    'me': me,
                    'session': session_string
                }
            
            return {'error': 'Invalid state'}
        
        result = run_async(verify_flow())
        
        if result.get('need_password'):
            temp['step'] = 'need_password'
            return jsonify({
                'success': False,
                'need_password': True,
                'message': '2FA password required'
            })
        elif result.get('success'):
            me = result['me']
            session_string = result['session']
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                'session': session_string,
                'added': datetime.now().isoformat()
            }
            
            accounts.append(account)
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f)
            
            del temp_data[session_id]
            
            return jsonify({
                'success': True,
                'account': account
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Verification failed')})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        async def get_messages_flow():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {'error': 'Not authorized'}
            
            # Get dialogs (chats)
            dialogs = await client.get_dialogs()
            
            chats = []
            messages = []
            
            for dialog in dialogs[:20]:  # Limit to 20 chats
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'unread': dialog.unread_count,
                    'lastMessage': dialog.message.text[:50] + '...' if dialog.message and dialog.message.text else '',
                    'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
                }
                chats.append(chat)
                
                # Get recent messages for this chat
                try:
                    msg_list = await client.get_messages(dialog.entity, limit=20)
                    for msg in msg_list:
                        if msg.message:
                            messages.append({
                                'chatId': str(dialog.id),
                                'text': msg.message,
                                'date': msg.date.timestamp(),
                                'out': msg.out
                            })
                except:
                    pass  # Skip if messages can't be loaded
            
            await client.disconnect()
            return {'chats': chats, 'messages': messages}
        
        result = run_async(get_messages_flow())
        
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})
        
        return jsonify({
            'success': True,
            'chats': result['chats'],
            'messages': result['messages']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        async def send_message_flow():
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {'error': 'Not authorized'}
            
            # Get entity
            entity = await client.get_entity(int(chat_id))
            
            # Send message
            await client.send_message(entity, message)
            
            await client.disconnect()
            return {'success': True}
        
        result = run_async(send_message_flow())
        
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    
    with open('accounts.json', 'w') as f:
        json.dump(accounts, f)
    
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
