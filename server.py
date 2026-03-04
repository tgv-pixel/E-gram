import os
import json
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from telethon import TelegramClient
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

app = Flask(__name__, template_folder='templates')
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
        await client.start(phone=account.get('phone'))  # Use .get() to avoid KeyError
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
        # Create a unique session name
        session_name = f'temp_{phone.replace("+", "")}_{int(time.time())}'
        
        # Create temporary client
        client = TelegramClient(
            session_name,
            int(os.environ.get('API_ID', 33465589)),
            os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
        )
        
        # Create new event loop for this operation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                # Store phone and session name in session
                session['temp_phone'] = phone
                session['temp_session'] = session_name
                return True
            return False
        
        result = loop.run_until_complete(send())
        loop.close()
        
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
    session_name = session.get('temp_session')
    
    if not phone or not session_name:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'})
    
    try:
        client = TelegramClient(
            session_name,
            int(os.environ.get('API_ID', 33465589)),
            os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')
        )
        
        # Create new event loop for this operation
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
            except Exception as e:
                return {'error': str(e)}
            
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
            
            # Store client for future use
            active_clients[new_account['id']] = client
            
            return {'success': True, 'account': new_account}
        
        result = loop.run_until_complete(verify())
        loop.close()
        
        # Clean up session
        session.pop('temp_phone', None)
        session.pop('temp_session', None)
        
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
        # Create new event loop for this operation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def fetch():
            client = await get_client(account_id)
            if not client:
                return {'error': 'Client not available'}
            
            chats_data = []
            messages_data = []
            
            try:
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
                    
                    chat_id = str(dialog.id)
                    if hasattr(dialog.entity, 'username') and dialog.entity.username:
                        chat_id = f"@{dialog.entity.username}"
                    
                    chats_data.append({
                        'id': chat_id,
                        'title': dialog.name or 'Unknown',
                        'type': chat_type,
                        'unread': dialog.unread_count,
                        'lastMessage': (last_msg_text or '')[:50],
                        'lastMessageMedia': last_msg_media,
                        'lastMessageDate': last_msg.date.timestamp() if last_msg and last_msg.date else None
                    })
                    
                    # Get last 20 messages for this chat (limited to avoid timeout)
                    try:
                        async for msg in client.iter_messages(dialog.entity, limit=20):
                            msg_data = {
                                'id': msg.id,
                                'chatId': chat_id,
                                'text': msg.text or '',
                                'date': msg.date.timestamp() if msg.date else time.time(),
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
                                    msg_data['mediaType'] = 'document'
                                    # Check for filename
                                    for attr in msg.media.document.attributes:
                                        if isinstance(attr, DocumentAttributeFilename):
                                            msg_data['fileName'] = attr.file_name
                                            break
                                elif hasattr(msg.media, 'webpage'):
                                    msg_data['mediaType'] = 'webpage'
                                    if hasattr(msg.media.webpage, 'url'):
                                        msg_data['webpageUrl'] = msg.media.webpage.url
                                    if hasattr(msg.media.webpage, 'title'):
                                        msg_data['webpageTitle'] = msg.media.webpage.title
                            
                            messages_data.append(msg_data)
                    except Exception as e:
                        logger.error(f"Error getting messages for chat {dialog.id}: {e}")
                        continue
                    
            except Exception as e:
                logger.error(f"Error in fetch loop: {e}")
                return {'error': str(e)}
            
            return {
                'success': True,
                'chats': chats_data,
                'messages': messages_data
            }
        
        result = loop.run_until_complete(fetch())
        loop.close()
        
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
        # Create new event loop for this operation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            client = await get_client(account_id)
            if not client:
                return {'error': 'Client not available'}
            
            # Get chat entity
            try:
                # Try to get entity by ID or username
                if chat_id.startswith('@'):
                    entity = await client.get_entity(chat_id)
                elif chat_id.startswith('-100'):
                    entity = await client.get_entity(int(chat_id))
                else:
                    # Try as integer ID
                    try:
                        entity = await client.get_entity(int(chat_id))
                    except ValueError:
                        # Try as username without @
                        entity = await client.get_entity(f"@{chat_id}")
            except Exception as e:
                logger.error(f"Error getting entity: {e}")
                return {'error': f'Chat not found: {str(e)}'}
            
            # Send message
            try:
                sent = await client.send_message(entity, message)
                return {'success': True, 'message_id': sent.id}
            except Exception as e:
                return {'error': f'Failed to send: {str(e)}'}
        
        result = loop.run_until_complete(send())
        loop.close()
        
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
        accounts = [a for a in accounts if a['id'] != int(account_id)]
        save_accounts(accounts)
        
        # Remove client if exists
        if int(account_id) in active_clients:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def disconnect():
                try:
                    await active_clients[int(account_id)].disconnect()
                except:
                    pass
            
            loop.run_until_complete(disconnect())
            loop.close()
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

@app.errorhandler(404)
def not_found(error):
    return render_template('dashboard.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # Set debug=False for production
