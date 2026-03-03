from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
from datetime import datetime
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

temp_data = {}
accounts = []
ACCOUNTS_FILE = 'accounts.json'

# Simple load function
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read()
                print(f"📖 Reading accounts.json: {content}")
                accounts = json.loads(content) if content.strip() else []
        else:
            print("📝 accounts.json not found, creating new one")
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
            accounts = []
        print(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        print(f"❌ Error loading: {e}")
        accounts = []

# Simple save function
def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        print(f"💾 Saved {len(accounts)} accounts to {ACCOUNTS_FILE}")
        # Verify save
        with open(ACCOUNTS_FILE, 'r') as f:
            content = f.read()
            print(f"📖 Verification read: {content}")
        return True
    except Exception as e:
        print(f"❌ Error saving: {e}")
        return False

# Load at startup
load_accounts()

def run_async(coro):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Routes
@app.route('/')
def serve_index():
    return send_file('login.html')

@app.route('/login')
def serve_login():
    return send_file('login.html')

@app.route('/dashboard')
def serve_dashboard():
    return send_file('dashboard.html')

@app.route('/home')
def serve_home():
    return send_file('home.html')

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    load_accounts()  # Reload to ensure latest
    print(f"📊 Returning {len(accounts)} accounts")
    return jsonify({'success': True, 'accounts': accounts})

# Send OTP
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            return {
                'success': True,
                'phone_code_hash': result.phone_code_hash,
                'session_str': session_str
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    result = run_async(send_code())
    
    if not result.get('success'):
        return jsonify({'success': False, 'error': result.get('error', 'Failed')})
    
    session_id = str(int(time.time()))
    temp_data[session_id] = {
        'phone': phone,
        'phone_code_hash': result['phone_code_hash'],
        'session_str': result['session_str']
    }
    
    return jsonify({'success': True, 'session_id': session_id})

# Verify code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not session_id or session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session = temp_data[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session['session_str']), API_ID, API_HASH)
        await client.connect()
        try:
            if password:
                await client.sign_in(password=password)
            else:
                await client.sign_in(session['phone'], code, phone_code_hash=session['phone_code_hash'])
            
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
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    result = run_async(verify())
    
    if result.get('need_password'):
        return jsonify({'success': False, 'need_password': True})
    
    if not result.get('success'):
        return jsonify({'success': False, 'error': result.get('error', 'Verification failed')})
    
    # Create new account
    me = result['me']
    
    # Load existing accounts
    load_accounts()
    
    new_id = 1
    if accounts:
        new_id = max([acc.get('id', 0) for acc in accounts]) + 1
    
    full_name = f"{me.get('first_name', '')} {me.get('last_name', '')}".strip()
    if not full_name:
        full_name = session['phone']
    
    new_account = {
        'id': new_id,
        'phone': session['phone'],
        'name': full_name,
        'first_name': me.get('first_name', ''),
        'last_name': me.get('last_name', ''),
        'username': me.get('username', ''),
        'user_id': me.get('id'),
        'session': result['session'],
        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    accounts.append(new_account)
    
    # SAVE IMMEDIATELY
    print(f"📝 Attempting to save account: {new_account}")
    save_success = save_accounts()
    print(f"📝 Save result: {'SUCCESS' if save_success else 'FAILED'}")
    
    if session_id in temp_data:
        del temp_data[session_id]
    
    return jsonify({'success': True, 'account': new_account})

# Get messages (simplified)
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    print(f"\n🔍 Looking for account ID: {account_id}")
    load_accounts()  # Reload to ensure latest
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        print(f"❌ Account {account_id} not found. Available accounts: {[a['id'] for a in accounts]}")
        return jsonify({'success': False, 'error': 'Account not found'})
    
    print(f"✅ Found account: {account.get('phone')}")
    
    # Return empty chats for now to test
    return jsonify({'success': True, 'chats': [], 'messages': []})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    save_accounts()
    return jsonify({'success': True})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 SIMPLE TELEGRAM MANAGER")
    print("="*60)
    app.run(host='0.0.0.0', port=5000, debug=True)
