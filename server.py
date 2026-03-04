import os
import json
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    MessageMediaContact, MessageMediaGeo, MessageMediaPoll,
    DocumentAttributeFilename, DocumentAttributeAudio
)
import logging
from datetime import datetime
import secrets
import time

# Apply nest_asyncio to allow running asyncio in Flask
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File to store accounts data
ACCOUNTS_FILE = 'telegram_accounts.json'

# Store active clients
active_clients = {}

# Helper functions
def load_accounts():
    """Load accounts from JSON file"""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
    return []

def save_accounts(accounts):
    """Save accounts to JSON file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")

def get_next_id(accounts):
    """Get next available ID"""
    if not accounts:
        return 1
    return max(a.get('id', 0) for a in accounts) + 1

async def get_client(account_id):
    """Get or create Telegram client for account"""
    account_id = int(account_id)
    
    if account_id in active_clients:
        client = active_clients[account_id]
        if client.is_connected():
            return client
    
    accounts = load_accounts()
    account = next((a for a in accounts if a['id'] == account_id), None)
    
    if not account:
        return None
    
    # Create new client
    client = TelegramClient(
        f'session_{account_id}',
        int(os.environ.get('API_ID', 33465589)),
        os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
    )
    
    try:
        await client.start(phone=account['phone'])
        active_clients[account_id] = client
        return client
    except Exception as e:
        logger.error(f"Error starting client: {e}")
        return None

# Routes
@app.route('/')
def index():
    """Redirect to dashboard"""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Render dashboard"""
    return render_template('dashboard.html')

@app.route('/login')
def login():
    """Render login page"""
    return render_template('login.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    accounts = load_accounts()
    return jsonify({'success': True, 'accounts': accounts})

@app.route('/api/send-code', methods=['POST'])
def send_code():
    """Send verification code to phone"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    try:
        # Create temporary client
        client = TelegramClient(
            f'temp_{phone}',
            int(os.environ.get('API_ID', 33465589)),
            os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                # Store phone in session
                session['temp_phone'] = phone
                session['temp_session'] = f'temp_{phone}'
                return True
            return False
        
        result = loop.run_until_complete(send())
        
        if result:
            return jsonify({'success': True, 'message': 'Code sent successfully'})
        else:
            return jsonify({'success': False, 'error': 'Already authorized'})
            
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and add account"""
    data = request.json
    code = data.get('code')
    password = data.get('password', '')
    
    if not code:
        return jsonify({'success': False, 'error': 'Code required'})
    
    phone = session.get('temp_phone')
    if not phone:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    try:
        client = TelegramClient(
            session.get('temp_session'),
            int(os.environ.get('API_ID', 33465589)),
            os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def verify():
            await client.connect()
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            # Get user info
            me = await client.get_me()
            
            # Load existing accounts
            accounts = load_accounts()
            
            # Check if account already exists
            if any(a.get('phone') == me.phone for a in accounts):
                return {'error': 'Account already exists'}
            
            # Add new account
            new_account = {
                'id': get_next_id(accounts),
                'phone': me.phone,
                'name': me.first_name or 'User',
                'username': me.username,
                'added_at': time.time()
            }
            accounts.append(new_account)
            save_accounts(accounts)
            
            # Clean up session
            session.pop('temp_phone', None)
            session.pop('temp_session', None)
            
            return {'success': True, 'account': new_account}
        
        result = loop.run_until_complete(verify())
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        elif result.get('error'):
            return jsonify({'success': False, 'error': result['error']})
        else:
            return jsonify({'success': True, 'account': result['account']})
            
    except Exception as e:
        logger.error(f"Error verifying code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats and messages for account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def fetch():
            client = await get_client(account_id)
            if not client:
                return {'error': 'Client not available'}
            
            chats_data = []
            messages_data = []
            
            # Get dialogs (chats)
            async for dialog in client.iter_dialogs():
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                
                # Get last message
                last_msg = dialog.message
                last_msg_text = ''
                last_msg_media = None
                
                if last_msg:
                    last_msg_text = last_msg.text or ''
                    if last_msg.media:
                        if hasattr(last_msg.media, 'photo'):
                            last_msg_media = 'photo'
                        elif hasattr(last_msg.media, 'document'):
                            last_msg_media = 'document'
                
                chats_data.append({
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count,
                    'lastMessage': last_msg_text[:50],
                    'lastMessageMedia': last_msg_media,
                    'lastMessageDate': last_msg.date.timestamp() if last_msg else None
                })
                
                # Get last 50 messages for this chat
                async for msg in client.iter_messages(dialog.entity, limit=50):
                    msg_data = {
                        'id': msg.id,
                        'chatId': str(dialog.id),
                        'text': msg.text or '',
                        'date': msg.date.timestamp(),
                        'out': msg.out,
                        'hasMedia': bool(msg.media),
                        'views': getattr(msg, 'views', None),
                        'forwards': getattr(msg, 'forwards', None)
                    }
                    
                    # Handle media
                    if msg.media:
                        if hasattr(msg.media, 'photo'):
                            msg_data['mediaType'] = 'photo'
                        elif hasattr(msg.media, 'document'):
                            # Check if it's a sticker, gif, etc.
                            for attr in msg.media.document.attributes:
                                if isinstance(attr, DocumentAttributeFilename):
                                    if attr.file_name.endswith(('.mp4', '.gif')):
                                        msg_data['mediaType'] = 'gif'
                                    elif attr.file_name.endswith(('.webp', '.tgs')):
                                        msg_data['mediaType'] = 'sticker'
                                    else:
                                        msg_data['mediaType'] = 'document'
                                    msg_data['fileName'] = attr.file_name
                                    break
                            
                            # Check if it's audio
                            for attr in msg.media.document.attributes:
                                if isinstance(attr, DocumentAttributeAudio):
                                    if attr.voice:
                                        msg_data['mediaType'] = 'voice'
                                    else:
                                        msg_data['mediaType'] = 'audio'
                                    msg_data['duration'] = attr.duration
                                    msg_data['title'] = attr.title
                                    msg_data['performer'] = attr.performer
                                    break
                        elif hasattr(msg.media, 'webpage'):
                            msg_data['mediaType'] = 'webpage'
                            msg_data['webpageUrl'] = msg.media.webpage.url
                            msg_data['webpageTitle'] = msg.media.webpage.title
                        elif hasattr(msg.media, 'contact'):
                            msg_data['mediaType'] = 'contact'
                            msg_data['contactName'] = f"{msg.media.first_name} {msg.media.last_name or ''}"
                            msg_data['contactPhone'] = msg.media.phone_number
                        elif hasattr(msg.media, 'geo'):
                            msg_data['mediaType'] = 'location'
                        elif hasattr(msg.media, 'poll'):
                            msg_data['mediaType'] = 'poll'
                            msg_data['pollQuestion'] = msg.media.poll.question
                            msg_data['pollOptions'] = [opt.text for opt in msg.media.poll.answers]
                    
                    messages_data.append(msg_data)
            
            return {
                'success': True,
                'chats': chats_data,
                'messages': messages_data
            }
        
        result = loop.run_until_complete(fetch())
        
        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']})
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send message to chat"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id, message]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            client = await get_client(account_id)
            if not client:
                return {'error': 'Client not available'}
            
            # Get chat entity
            try:
                if chat_id.startswith('-100'):
                    entity = await client.get_entity(int(chat_id))
                else:
                    entity = await client.get_entity(int(chat_id))
            except:
                # Try as username
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'error': 'Chat not found'}
            
            # Send message
            sent = await client.send_message(entity, message)
            return {'success': True, 'message_id': sent.id}
        
        result = loop.run_until_complete(send())
        
        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']})
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    try:
        accounts = load_accounts()
        accounts = [a for a in accounts if a['id'] != account_id]
        save_accounts(accounts)
        
        # Remove client if exists
        if int(account_id) in active_clients:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(active_clients[int(account_id)].disconnect())
            del active_clients[int(account_id)]
        
        # Remove session file
        session_file = f'session_{account_id}.session'
        if os.path.exists(session_file):
            os.remove(session_file)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error removing account: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/media/<int:account_id>/<int:message_id>')
def get_media(account_id, message_id):
    """Get media file"""
    return jsonify({'error': 'Media download not implemented yet'}), 501

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
