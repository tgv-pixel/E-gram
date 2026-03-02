from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
from datetime import datetime
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Your API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Simple in-memory storage
accounts = []
temp_data = {}

# Load accounts if exists
if os.path.exists('accounts.json'):
    try:
        with open('accounts.json', 'r') as f:
            accounts = json.load(f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except:
        accounts = []

def run_async(coro):
    """Simple async runner"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/')
def index():
    """Serve login page"""
    logger.info("Serving login page")
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    """Serve dashboard page"""
    logger.info("Serving dashboard page")
    return send_file('dashboard.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    return jsonify({'success': True, 'accounts': accounts})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Add new account"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone required'})
    
    session_id = f"session_{len(temp_data)}"
    
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            run_async(client.send_code_request(phone))
            temp_data[session_id] = {
                'client': client,
                'phone': phone
            }
            return jsonify({
                'success': True,
                'session_id': session_id,
                'next_step': 'code'
            })
        else:
            me = run_async(client.get_me())
            session_string = run_async(client.session.save())
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                'session': session_string
            }
            
            accounts.append(account)
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f)
            
            run_async(client.disconnect())
            return jsonify({'success': True, 'account': account})
            
    except Exception as e:
        logger.error(f"Add account error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify OTP code"""
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
        try:
            run_async(client.sign_in(phone, code))
        except errors.SessionPasswordNeededError:
            if password:
                run_async(client.sign_in(password=password))
            else:
                return jsonify({
                    'success': False,
                    'need_password': True,
                    'message': '2FA required'
                })
        
        me = run_async(client.get_me())
        session_string = run_async(client.session.save())
        
        account = {
            'id': len(accounts) + 1,
            'phone': phone,
            'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
            'session': session_string
        }
        
        accounts.append(account)
        with open('accounts.json', 'w') as f:
            json.dump(accounts, f)
        
        run_async(client.disconnect())
        del temp_data[session_id]
        
        return jsonify({'success': True, 'account': account})
        
    except Exception as e:
        logger.error(f"Verify code error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats"""
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        dialogs = run_async(client.get_dialogs())
        chats = []
        
        for dialog in dialogs[:20]:
            chat = {
                'id': str(dialog.id),
                'title': dialog.name or 'Unknown',
                'unread': dialog.unread_count,
                'lastMessage': dialog.message.text[:50] + '...' if dialog.message and dialog.message.text else '',
                'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
            }
            chats.append(chat)
        
        run_async(client.disconnect())
        return jsonify({'success': True, 'chats': chats, 'messages': []})
        
    except Exception as e:
        logger.error(f"Get messages error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send message"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        entity = run_async(client.get_entity(int(chat_id)))
        run_async(client.send_message(entity, message))
        run_async(client.disconnect())
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Send message error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove account"""
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    
    with open('accounts.json', 'w') as f:
        json.dump(accounts, f)
    
    return jsonify({'success': True})

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok'})

# This is critical for Render
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
