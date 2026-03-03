from flask import Flask, send_file, jsonify, request, abort
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    DocumentAttributeVideo, DocumentAttributeAudio, DocumentAttributeFilename,
    MessageMediaPoll, MessageMediaContact, MessageMediaGeo, MessageMediaVenue,
    MessageMediaGame, MessageMediaInvoice
)
from telethon.utils import get_display_name
from telethon.tl.types import PeerUser, PeerChat, PeerChannel
import json
import os
import asyncio
from datetime import datetime
import logging
import threading
import base64
import io
import mimetypes
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Create a global event loop for the main thread
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Media cache directory
MEDIA_CACHE_DIR = 'media_cache'
if not os.path.exists(MEDIA_CACHE_DIR):
    os.makedirs(MEDIA_CACHE_DIR)

# Load existing accounts if file exists
if os.path.exists(ACCOUNTS_FILE):
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)
        logger.info(f"✅ Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"⚠️ Error loading accounts: {e}")
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        logger.info(f"💾 Saved {len(accounts)} accounts")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accounts: {e}")
        return False

# Fixed helper to run async functions
def run_async(coro):
    """Run async coroutine in the existing event loop"""
    global loop
    try:
        # If we're in a thread, create a new event loop
        if threading.current_thread() is not threading.main_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        else:
            # In main thread, use the existing loop
            return loop.run_until_complete(coro)
    except RuntimeError:
        # If no event loop is running, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

# -------------------- SERVE HTML FILES --------------------
@app.route('/')
def serve_index():
    """Serve the login/index page"""
    try:
        return send_file('login.html')
    except FileNotFoundError:
        logger.error("login.html not found!")
        return "login.html not found. Please check your repository.", 404

@app.route('/login')
def serve_login():
    """Serve the login page"""
    try:
        return send_file('login.html')
    except FileNotFoundError:
        logger.error("login.html not found!")
        return "login.html not found. Please check your repository.", 404

@app.route('/dashboard')
def serve_dashboard():
    """Serve the dashboard page"""
    try:
        return send_file('dashboard.html')
    except FileNotFoundError:
        logger.error("dashboard.html not found!")
        return "dashboard.html not found. Please check your repository.", 404

@app.route('/home')
def serve_home():
    """Serve the home dashboard page"""
    try:
        return send_file('home.html')
    except FileNotFoundError:
        logger.error("home.html not found!")
        return "home.html not found. Please check your repository.", 404

# -------------------- GET ALL ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Return all accounts with proper formatting for dashboard"""
    account_list = []
    for acc in accounts:
        account_list.append({
            'id': acc['id'],
            'phone': acc['phone'],
            'name': acc.get('name', 'User'),
            'username': acc.get('username', ''),
            'session': acc.get('session', acc.get('string_session', ''))
        })
    return jsonify({'success': True, 'accounts': account_list})

# -------------------- ADD ACCOUNT (SEND OTP) --------------------
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        client = TelegramClient(StringSession(), API_ID, API_HASH, timeout=30)
        await client.connect()
        try:
            # Add a small delay to ensure connection is established
            await asyncio.sleep(1)
            result = await client.send_code_request(phone)
            session_str = client.session.save()
            return {
                'success': True,
                'phone_code_hash': result.phone_code_hash,
                'session_str': session_str
            }
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Too many attempts. Wait {e.seconds} seconds'}
        except Exception as e:
            logger.error(f"Error in send_code: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send_code())
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
        
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': result['phone_code_hash'],
            'session_str': result['session_str']
        }
        logger.info(f"📱 OTP sent to {phone}")
        return jsonify({'success': True, 'session_id': session_id})
        
    except Exception as e:
        logger.error(f"Error in add-account: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- VERIFY CODE --------------------
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if not session_id or session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired. Please start over.'})
    
    session = temp_data[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(session['session_str']), API_ID, API_HASH, timeout=30)
        await client.connect()
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if password:
                # 2FA login
                await client.sign_in(password=password)
            else:
                # Normal login with code
                await client.sign_in(
                    session['phone'], 
                    code, 
                    phone_code_hash=session['phone_code_hash']
                )
            
            # Get user info
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
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except Exception as e:
            logger.error(f"Error in verify: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Verification failed')})
        
        # Create new account with a unique ID
        me = result['me']
        new_account = {
            'id': max([acc['id'] for acc in accounts], default=0) + 1,
            'phone': session['phone'],
            'name': f"{me.get('first_name', '')} {me.get('last_name', '')}".strip() or 'User',
            'username': me.get('username', ''),
            'user_id': me.get('id'),
            'session': result['session'],
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        accounts.append(new_account)
        save_accounts()
        
        # Clean up temp data
        if session_id in temp_data:
            del temp_data[session_id]
        
        logger.info(f"✅ Account added: {session['phone']}")
        return jsonify({'success': True, 'account': new_account})
        
    except Exception as e:
        logger.error(f"Error in verify-code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET MESSAGES (FULL MEDIA SUPPORT) --------------------
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=30)
        await client.connect()
        
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs (chats)
            dialogs = await client.get_dialogs(limit=100)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                # Get chat name and type
                if dialog.is_user:
                    name = get_display_name(dialog.entity)
                    chat_type = 'user'
                    if dialog.entity.bot:
                        chat_type = 'bot'
                elif dialog.is_group:
                    name = dialog.name or 'Unknown Group'
                    chat_type = 'group'
                elif dialog.is_channel:
                    name = dialog.name or 'Unknown Channel'
                    chat_type = 'channel'
                else:
                    name = dialog.name or 'Unknown'
                    chat_type = 'unknown'
                
                chat_id = str(dialog.id)
                
                # Get last message with media info
                last_msg_text = ''
                last_msg_media = None
                last_msg_media_type = None
                
                if dialog.message:
                    last_msg_text, last_msg_media, last_msg_media_type = await extract_message_info(dialog.message, client)
                
                # Add chat to list with media info
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': last_msg_text,
                    'lastMessageMedia': last_msg_media,
                    'lastMessageMediaType': last_msg_media_type,
                    'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None,
                    'pinned': dialog.pinned or False
                })
                
                # Get last 30 messages for this chat with full media support
                try:
                    msgs = await client.get_messages(dialog.entity, limit=30)
                    for msg in msgs:
                        if msg:
                            message_data = await create_message_data(msg, chat_id, client)
                            all_messages.append(message_data)
                except Exception as e:
                    logger.error(f"Error fetching messages for chat {chat_id}: {e}")
                    continue
            
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
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to fetch chats')})
        
        return jsonify({
            'success': True,
            'chats': result['chats'],
            'messages': result['messages']
        })
        
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET MEDIA FILE --------------------
@app.route('/api/media/<int:account_id>/<path:media_id>')
def get_media(account_id, media_id):
    """Get media file by ID"""
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def download_media():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=60)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}, 401
            
            # Get message by ID (assuming media_id is message_id)
            try:
                # Try to get the message
                msg = await client.get_messages(None, ids=int(media_id))
                if not msg or not msg.media:
                    return {'success': False, 'error': 'Media not found'}, 404
                
                # Download media to memory
                media_data = await client.download_media(msg, file=bytes)
                
                # Determine mime type
                mime_type = 'application/octet-stream'
                if msg.file and msg.file.mime_type:
                    mime_type = msg.file.mime_type
                elif isinstance(msg.media, MessageMediaPhoto):
                    mime_type = 'image/jpeg'
                
                return {
                    'success': True,
                    'data': media_data,
                    'mime_type': mime_type
                }
                
            except Exception as e:
                logger.error(f"Error getting media: {e}")
                return {'success': False, 'error': str(e)}, 500
                
        finally:
            await client.disconnect()
    
    try:
        result = run_async(download_media())
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to get media')}), 500
        
        # Return media file
        return send_file(
            io.BytesIO(result['data']),
            mimetype=result['mime_type'],
            as_attachment=False,
            download_name=f"media_{media_id}"
        )
        
    except Exception as e:
        logger.error(f"Error in get-media: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# -------------------- SEND MESSAGE (WITH MEDIA SUPPORT) --------------------
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    media_type = data.get('mediaType')  # 'photo', 'video', 'document', etc.
    media_data = data.get('mediaData')  # Base64 encoded media data
    
    if not all([account_id, chat_id]):
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=30)
        await client.connect()
        
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get entity
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            # Send message with media if provided
            if media_type and media_data:
                # Decode base64 media
                import base64
                media_bytes = base64.b64decode(media_data.split(',')[1] if ',' in media_data else media_data)
                
                # Create temporary file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=get_extension(media_type)) as tmp:
                    tmp.write(media_bytes)
                    tmp_path = tmp.name
                
                try:
                    # Send media
                    if media_type.startswith('image/'):
                        await client.send_file(entity, tmp_path, caption=message)
                    elif media_type.startswith('video/'):
                        await client.send_file(entity, tmp_path, caption=message, supports_streaming=True)
                    else:
                        await client.send_file(entity, tmp_path, caption=message)
                    
                    # Clean up temp file
                    os.unlink(tmp_path)
                except Exception as e:
                    os.unlink(tmp_path)
                    raise e
            else:
                # Send text message
                if message:
                    await client.send_message(entity, message)
                else:
                    return {'success': False, 'error': 'Message or media required'}
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        
        if result.get('success'):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to send message')})
            
    except Exception as e:
        logger.error(f"Error in send-message: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- REMOVE ACCOUNT --------------------
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    global accounts
    original_count = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    
    if len(accounts) < original_count:
        save_accounts()
        logger.info(f"🗑️ Removed account {account_id}")
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

# -------------------- HELPER FUNCTIONS --------------------
async def extract_message_info(message, client):
    """Extract message text and media info"""
    text = ''
    media_type = None
    media_subtype = None
    
    if message.text:
        text = message.text[:100]
        if len(message.text) > 100:
            text += '...'
    
    if message.media:
        if isinstance(message.media, MessageMediaPhoto):
            media_type = 'photo'
            text = text or '📷 Photo'
        elif isinstance(message.media, MessageMediaDocument):
            media_type = 'document'
            attrs = message.media.document.attributes
            
            # Check for video
            if any(isinstance(attr, DocumentAttributeVideo) for attr in attrs):
                media_type = 'video'
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeVideo):
                        text = f'🎥 Video ({attr.duration}s)'
                        break
            # Check for audio/voice
            elif any(isinstance(attr, DocumentAttributeAudio) for attr in attrs):
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeAudio):
                        if attr.voice:
                            media_type = 'voice'
                            text = f'🎤 Voice message ({attr.duration}s)'
                        else:
                            media_type = 'audio'
                            text = f'🎵 Audio: {attr.title or "Unknown"}'
                        break
            # Check for sticker
            elif message.file and message.file.mime_type == 'image/webp' and any(isinstance(attr, DocumentAttributeFilename) and attr.file_name.endswith('.webp') for attr in attrs):
                media_type = 'sticker'
                text = '🎯 Sticker'
            # Check for GIF
            elif message.file and message.file.mime_type == 'video/mp4' and any(isinstance(attr, DocumentAttributeFilename) and attr.file_name.endswith('.gif') for attr in attrs):
                media_type = 'gif'
                text = '🎬 GIF'
            else:
                # Regular document
                filename = 'Unknown'
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeFilename):
                        filename = attr.file_name
                        break
                media_type = 'document'
                text = f'📎 {filename}'
        elif isinstance(message.media, MessageMediaWebPage):
            media_type = 'webpage'
            text = '🔗 Link'
        elif isinstance(message.media, MessageMediaPoll):
            media_type = 'poll'
            text = f'📊 Poll: {message.media.poll.question}'
        elif isinstance(message.media, MessageMediaContact):
            media_type = 'contact'
            text = f'👤 Contact: {message.media.first_name} {message.media.last_name or ""}'
        elif isinstance(message.media, MessageMediaGeo) or isinstance(message.media, MessageMediaVenue):
            media_type = 'location'
            text = '📍 Location'
        elif isinstance(message.media, MessageMediaGame):
            media_type = 'game'
            text = f'🎮 Game: {message.media.game.title}'
        elif isinstance(message.media, MessageMediaInvoice):
            media_type = 'invoice'
            text = f'💰 Invoice: {message.media.title}'
        else:
            media_type = 'media'
            text = text or '📎 Media'
    
    return text, media_type, media_type

async def create_message_data(message, chat_id, client):
    """Create message data dictionary with full media info"""
    message_data = {
        'chatId': chat_id,
        'text': message.text or '',
        'date': message.date.timestamp(),
        'out': message.out,
        'id': message.id,
        'hasMedia': message.media is not None,
        'views': getattr(message, 'views', 0),
        'forwards': getattr(message, 'forwards', 0),
        'reply_to_msg_id': message.reply_to_msg_id if hasattr(message, 'reply_to_msg_id') else None
    }
    
    # Add media type info
    if message.media:
        if isinstance(message.media, MessageMediaPhoto):
            message_data['mediaType'] = 'photo'
            message_data['mediaPreview'] = '📷 Photo'
            message_data['mediaId'] = message.id
            # Try to get photo dimensions
            if hasattr(message.media, 'photo') and hasattr(message.media.photo, 'sizes'):
                sizes = message.media.photo.sizes
                if sizes:
                    last_size = sizes[-1]
                    if hasattr(last_size, 'w') and hasattr(last_size, 'h'):
                        message_data['mediaWidth'] = last_size.w
                        message_data['mediaHeight'] = last_size.h
            
        elif isinstance(message.media, MessageMediaDocument):
            attrs = message.media.document.attributes
            message_data['mediaId'] = message.id
            
            # Get file info
            if message.file:
                message_data['fileName'] = message.file.name
                message_data['fileSize'] = message.file.size
                message_data['mimeType'] = message.file.mime_type
            
            # Check for video
            if any(isinstance(attr, DocumentAttributeVideo) for attr in attrs):
                message_data['mediaType'] = 'video'
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeVideo):
                        message_data['mediaPreview'] = f'🎥 Video ({attr.duration}s)'
                        message_data['duration'] = attr.duration
                        message_data['mediaWidth'] = getattr(attr, 'w', 0)
                        message_data['mediaHeight'] = getattr(attr, 'h', 0)
                        break
            
            # Check for audio/voice
            elif any(isinstance(attr, DocumentAttributeAudio) for attr in attrs):
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeAudio):
                        if attr.voice:
                            message_data['mediaType'] = 'voice'
                            message_data['mediaPreview'] = f'🎤 Voice message ({attr.duration}s)'
                        else:
                            message_data['mediaType'] = 'audio'
                            message_data['mediaPreview'] = f'🎵 Audio: {attr.title or "Unknown"}'
                        message_data['duration'] = attr.duration
                        message_data['title'] = attr.title
                        message_data['performer'] = attr.performer
                        break
            
            # Check for sticker
            elif message.file and message.file.mime_type == 'image/webp':
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeFilename) and attr.file_name.endswith('.webp'):
                        message_data['mediaType'] = 'sticker'
                        message_data['mediaPreview'] = '🎯 Sticker'
                        message_data['stickerSet'] = getattr(message.media.document, 'sticker_set', None)
                        break
            
            # Check for GIF
            elif message.file and message.file.mime_type == 'video/mp4':
                for attr in attrs:
                    if isinstance(attr, DocumentAttributeFilename) and attr.file_name.endswith('.gif'):
                        message_data['mediaType'] = 'gif'
                        message_data['mediaPreview'] = '🎬 GIF'
                        break
            else:
                # Regular document
                message_data['mediaType'] = 'document'
                message_data['mediaPreview'] = '📎 Document'
        
        elif isinstance(message.media, MessageMediaWebPage):
            message_data['mediaType'] = 'webpage'
            message_data['mediaPreview'] = '🔗 Link'
            message_data['webpageUrl'] = message.media.webpage.url if hasattr(message.media.webpage, 'url') else ''
            message_data['webpageTitle'] = message.media.webpage.title if hasattr(message.media.webpage, 'title') else ''
            
        elif isinstance(message.media, MessageMediaPoll):
            message_data['mediaType'] = 'poll'
            message_data['mediaPreview'] = f'📊 Poll: {message.media.poll.question}'
            message_data['pollQuestion'] = message.media.poll.question
            message_data['pollOptions'] = [opt.text for opt in message.media.poll.answers]
            
        elif isinstance(message.media, MessageMediaContact):
            message_data['mediaType'] = 'contact'
            message_data['mediaPreview'] = f'👤 Contact: {message.media.first_name} {message.media.last_name or ""}'
            message_data['contactName'] = f"{message.media.first_name} {message.media.last_name or ''}"
            message_data['contactPhone'] = message.media.phone_number
            
        elif isinstance(message.media, MessageMediaGeo) or isinstance(message.media, MessageMediaVenue):
            message_data['mediaType'] = 'location'
            message_data['mediaPreview'] = '📍 Location'
            if isinstance(message.media, MessageMediaVenue):
                message_data['venueTitle'] = message.media.title
                message_data['venueAddress'] = message.media.address
            
        elif isinstance(message.media, MessageMediaGame):
            message_data['mediaType'] = 'game'
            message_data['mediaPreview'] = f'🎮 Game: {message.media.game.title}'
            
        elif isinstance(message.media, MessageMediaInvoice):
            message_data['mediaType'] = 'invoice'
            message_data['mediaPreview'] = f'💰 Invoice: {message.media.title}'
            message_data['amount'] = message.media.total_amount if hasattr(message.media, 'total_amount') else 0
            
        else:
            message_data['mediaType'] = 'media'
            message_data['mediaPreview'] = '📎 Media'
    
    # Check for emoji-only message
    if message.text and len(message.text) < 10:
        import re
        emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]|[\u2000-\u3300]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDE4F]|\uD83D[\uDE80-\uDEFF]|\uD83E[\uDD00-\uDDFF]', re.UNICODE)
        if emoji_pattern.sub('', message.text).strip() == '':
            message_data['isEmoji'] = True
    
    return message_data

def get_extension(mime_type):
    """Get file extension from mime type"""
    ext_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'video/mp4': '.mp4',
        'video/webm': '.webm',
        'audio/mpeg': '.mp3',
        'audio/ogg': '.ogg',
        'audio/mp4': '.m4a',
        'application/pdf': '.pdf',
        'text/plain': '.txt'
    }
    return ext_map.get(mime_type, '.bin')

# Error handler for 404
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

# Error handler for 500
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - FULL MEDIA SUPPORT')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print('✅ Full Media Support:')
    print('   - Photos (with dimensions)')
    print('   - Videos (with duration)')
    print('   - Voice messages')
    print('   - Audio files')
    print('   - Stickers')
    print('   - GIFs')
    print('   - Documents')
    print('   - Webpage previews')
    print('   - Polls')
    print('   - Contacts')
    print('   - Locations')
    print('   - Games')
    print('   - Invoices')
    print('✅ Endpoints ready:')
    print('   - GET  /')
    print('   - GET  /login')
    print('   - GET  /dashboard')
    print('   - GET  /home')
    print('   - GET  /api/accounts')
    print('   - POST /api/add-account')
    print('   - POST /api/verify-code')
    print('   - POST /api/get-messages')
    print('   - GET  /api/media/<account_id>/<media_id>')
    print('   - POST /api/send-message')
    print('   - POST /api/remove-account')
    print('   - GET  /api/health')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
