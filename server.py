from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    DocumentAttributeVideo, DocumentAttributeAudio
)
from telethon.utils import get_display_name
import json
import os
import asyncio
from datetime import datetime
import logging
import time
import io

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

# Store accounts
accounts = []
ACCOUNTS_FILE = 'accounts.json'

# Debug startup
print("\n" + "="*60)
print("🚀 TELEGRAM MANAGER - STARTING UP")
print("="*60)

# Check if accounts.json exists and is writable
if os.path.exists(ACCOUNTS_FILE):
    print(f"✅ {ACCOUNTS_FILE} exists")
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            content = f.read()
            print(f"📄 File size: {len(content)} bytes")
            if content.strip():
                print(f"📄 Content preview: {content[:100]}")
            else:
                print("⚠️ File is empty")
    except Exception as e:
        print(f"❌ Error reading file: {e}")
else:
    print(f"❌ {ACCOUNTS_FILE} does not exist - will be created on first account add")
    
    # Try to create it
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump([], f)
        print(f"✅ Created empty {ACCOUNTS_FILE}")
    except Exception as e:
        print(f"❌ Could not create {ACCOUNTS_FILE}: {e}")

print("="*60 + "\n")

# IMPORTANT: This function ensures accounts persist across restarts
def load_accounts():
    global accounts
    try:
        # Try to load from current directory first
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read().strip()
                accounts = json.loads(content) if content else []
                logger.info(f"✅ Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")
                return
        
        # If not found, try to load from environment variable (for Render)
        accounts_json = os.environ.get('ACCOUNTS_JSON')
        if accounts_json:
            accounts = json.loads(accounts_json)
            logger.info(f"✅ Loaded {len(accounts)} accounts from environment variable")
            # Save to file for next time
            save_accounts()
            return
        
        # If no accounts found anywhere, start fresh
        accounts = []
        logger.info("📝 No accounts found, starting fresh")
        
    except Exception as e:
        logger.error(f"⚠️ Error loading accounts: {e}")
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        
        logger.info(f"💾 Saved {len(accounts)} accounts to {ACCOUNTS_FILE}")
        
        # Also print to console for debugging
        print(f"\n📝 Accounts saved: {len(accounts)} account(s)")
        for i, acc in enumerate(accounts):
            print(f"   {i+1}. ID: {acc.get('id')}, Phone: {acc.get('phone')}, Name: {acc.get('name')}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accounts: {e}")
        return False

def debug_accounts():
    """Print debug info about accounts"""
    print("\n" + "="*50)
    print("🔍 ACCOUNTS DEBUG INFO")
    print("="*50)
    print(f"Total accounts in memory: {len(accounts)}")
    for i, acc in enumerate(accounts):
        print(f"\nAccount {i+1}:")
        print(f"  ID: {acc.get('id')}")
        print(f"  Phone: {acc.get('phone')}")
        print(f"  Name: {acc.get('name')}")
        print(f"  Username: {acc.get('username')}")
        print(f"  Has session: {'✅ Yes' if acc.get('session') else '❌ No'}")
        if acc.get('session'):
            print(f"  Session length: {len(acc.get('session', ''))} chars")
    print("="*50 + "\n")

# Load accounts at startup
load_accounts()
debug_accounts()

# Run async function
def run_async(coro):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except:
            pass

# -------------------- HTML PAGES --------------------
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

# -------------------- API ENDPOINTS --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    load_accounts()  # Always reload to ensure latest
    account_list = []
    
    for acc in accounts:
        name = acc.get('name', '')
        if not name:
            first = acc.get('first_name', '')
            last = acc.get('last_name', '')
            name = f"{first} {last}".strip() or acc.get('phone', 'Unknown')
        
        account_list.append({
            'id': acc['id'],
            'phone': acc.get('phone', ''),
            'name': name,
            'first_name': acc.get('first_name', ''),
            'last_name': acc.get('last_name', ''),
            'username': acc.get('username', ''),
            'session': acc.get('session', '')[:20] + '...' if acc.get('session') else ''  # Truncate for security
        })
    
    print(f"📊 Returning {len(account_list)} accounts to client")
    return jsonify({'success': True, 'accounts': account_list})

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
        except errors.FloodWaitError as e:
            return {'success': False, 'error': f'Please wait {e.seconds} seconds'}
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

# Verify code - FIXED VERSION
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
    
    # Load existing accounts to get the next ID
    load_accounts()  # Reload to ensure we have latest
    
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
    
    # Force save immediately
    save_success = save_accounts()
    print(f"📝 Account save attempt: {'✅ SUCCESS' if save_success else '❌ FAILED'}")
    print(f"📝 Accounts now: {len(accounts)}")
    
    if session_id in temp_data:
        del temp_data[session_id]
    
    return jsonify({'success': True, 'account': new_account})

# Get messages and chats - IMPROVED VERSION WITH BETTER ERROR HANDLING
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Print debug info
    print(f"\n🔍 Looking for account with ID: {account_id}")
    print(f"📊 Total accounts in memory: {len(accounts)}")
    
    # Debug: Show all accounts
    for acc in accounts:
        print(f"   - ID: {acc.get('id')}, Phone: {acc.get('phone')}, Name: {acc.get('name')}")
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        print(f"❌ Account NOT found for ID: {account_id}")
        return jsonify({'success': False, 'error': 'Account not found'})
    
    print(f"✅ Account found: {account.get('phone')}")
    
    session_string = account.get('session', '')
    
    if not session_string:
        print(f"❌ No session found for account {account_id}")
        return jsonify({'success': False, 'error': 'No session found for account'})
    
    print(f"✅ Session found, length: {len(session_string)}")
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs (chats)
            print("📱 Fetching dialogs...")
            dialogs = await client.get_dialogs(limit=100)
            
            if not dialogs:
                print("📭 No dialogs found")
                return {'success': True, 'chats': [], 'messages': []}
            
            print(f"📱 Found {len(dialogs)} dialogs")
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                if not dialog or not dialog.entity:
                    continue
                
                # Get chat info
                entity = dialog.entity
                chat_id = str(dialog.id)
                
                # Determine chat type
                if hasattr(entity, 'bot') and entity.bot:
                    chat_type = 'bot'
                elif hasattr(entity, 'broadcast') and entity.broadcast:
                    chat_type = 'channel'
                elif hasattr(entity, 'megagroup') and entity.megagroup:
                    chat_type = 'supergroup'
                elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                    chat_type = 'group'
                elif hasattr(entity, 'title'):
                    chat_type = 'group'
                else:
                    chat_type = 'user'
                
                # Get name
                if hasattr(entity, 'title') and entity.title:
                    name = entity.title
                elif hasattr(entity, 'first_name') and entity.first_name:
                    last = entity.last_name or ''
                    name = f"{entity.first_name} {last}".strip()
                else:
                    name = 'Unknown'
                
                # Get last message info
                last_msg_text = ''
                last_msg_media = None
                last_date = 0
                
                if dialog.message:
                    if dialog.message.text:
                        last_msg_text = dialog.message.text[:50]
                        if len(dialog.message.text) > 50:
                            last_msg_text += '...'
                    
                    # Check media type
                    if dialog.message.media:
                        if isinstance(dialog.message.media, MessageMediaPhoto):
                            last_msg_media = 'photo'
                            last_msg_text = last_msg_text or '📷 Photo'
                        elif isinstance(dialog.message.media, MessageMediaDocument):
                            # Check if it's a video/voice/audio
                            if hasattr(dialog.message.media, 'document'):
                                for attr in dialog.message.media.document.attributes:
                                    if isinstance(attr, DocumentAttributeVideo):
                                        last_msg_media = 'video'
                                        last_msg_text = '🎥 Video'
                                        break
                                    elif isinstance(attr, DocumentAttributeAudio):
                                        if attr.voice:
                                            last_msg_media = 'voice'
                                            last_msg_text = '🎤 Voice message'
                                        else:
                                            last_msg_media = 'audio'
                                            last_msg_text = '🎵 Audio'
                                        break
                                else:
                                    last_msg_media = 'document'
                                    last_msg_text = '📎 Document'
                            else:
                                last_msg_media = 'document'
                                last_msg_text = '📎 Document'
                        elif isinstance(dialog.message.media, MessageMediaWebPage):
                            last_msg_media = 'webpage'
                            last_msg_text = '🔗 Link'
                        else:
                            last_msg_media = 'media'
                            last_msg_text = '📎 Media'
                    
                    # Get date
                    if dialog.message.date:
                        last_date = dialog.message.date.timestamp()
                
                # Get unread count
                unread_count = 0
                if hasattr(dialog, 'unread_count'):
                    unread_count = dialog.unread_count
                
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'type': chat_type,
                    'unread': unread_count,
                    'lastMessage': last_msg_text,
                    'lastMessageMedia': last_msg_media,
                    'lastMessageDate': last_date,
                    'pinned': dialog.pinned if hasattr(dialog, 'pinned') else False
                })
                
                # Get last 20 messages for this chat
                try:
                    messages = await client.get_messages(entity, limit=20)
                    
                    for msg in messages:
                        if not msg:
                            continue
                        
                        msg_date = 0
                        if msg.date:
                            msg_date = msg.date.timestamp()
                        
                        message_data = {
                            'chatId': chat_id,
                            'text': msg.text or '',
                            'date': msg_date,
                            'out': msg.out if hasattr(msg, 'out') else False,
                            'id': msg.id,
                            'hasMedia': msg.media is not None
                        }
                        
                        # Add media type
                        if msg.media:
                            if isinstance(msg.media, MessageMediaPhoto):
                                message_data['mediaType'] = 'photo'
                            elif isinstance(msg.media, MessageMediaDocument):
                                # Check document type
                                if hasattr(msg.media, 'document'):
                                    is_video = False
                                    is_audio = False
                                    is_voice = False
                                    
                                    for attr in msg.media.document.attributes:
                                        if isinstance(attr, DocumentAttributeVideo):
                                            is_video = True
                                            break
                                        elif isinstance(attr, DocumentAttributeAudio):
                                            is_audio = True
                                            is_voice = attr.voice if hasattr(attr, 'voice') else False
                                            break
                                    
                                    if is_video:
                                        message_data['mediaType'] = 'video'
                                    elif is_voice:
                                        message_data['mediaType'] = 'voice'
                                    elif is_audio:
                                        message_data['mediaType'] = 'audio'
                                    else:
                                        message_data['mediaType'] = 'document'
                                else:
                                    message_data['mediaType'] = 'document'
                            elif isinstance(msg.media, MessageMediaWebPage):
                                message_data['mediaType'] = 'webpage'
                            else:
                                message_data['mediaType'] = 'media'
                        
                        all_messages.append(message_data)
                        
                except Exception as e:
                    logger.error(f"Error getting messages for chat {chat_id}: {e}")
                    continue
            
            print(f"✅ Returning {len(chats)} chats and {len(all_messages)} messages")
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

# Get media file
@app.route('/api/media/<int:account_id>/<int:message_id>')
def get_media(account_id, message_id):
    """Get media file by message ID"""
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    
    session_string = account.get('session', '')
    
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found'}), 404
    
    async def download_media():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=60)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}, 401
            
            # Get the message
            try:
                msg = await client.get_messages(None, ids=message_id)
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
        
        if isinstance(result, tuple):
            return jsonify({'success': False, 'error': result[0]['error']}), result[1]
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to get media')}), 500
        
        # Return media file
        return send_file(
            io.BytesIO(result['data']),
            mimetype=result['mime_type'],
            as_attachment=False,
            download_name=f"media_{message_id}"
        )
        
    except Exception as e:
        logger.error(f"Error in get-media: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id]):
        return jsonify({'success': False, 'error': 'Account ID and Chat ID required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', '')
    
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found for account'})
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH, timeout=30)
        await client.connect()
        
        try:
            await asyncio.sleep(1)  # Small delay for connection
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get entity
            try:
                # Try as integer ID
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    # Try as string
                    entity = await client.get_entity(chat_id)
                except Exception as e:
                    logger.error(f"Error getting entity: {e}")
                    return {'success': False, 'error': 'Chat not found'}
            
            # Send message
            if message:
                await client.send_message(entity, message)
            
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

# Remove account
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
        if save_accounts():
            logger.info(f"🗑️ Removed account {account_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save after removal'})
    else:
        return jsonify({'success': False, 'error': 'Account not found'})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_data),
        'accounts_file_exists': os.path.exists(ACCOUNTS_FILE)
    })

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
    print('📱 TELEGRAM MANAGER - READY TO GO')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}')
    print(f'✅ File exists: {os.path.exists(ACCOUNTS_FILE)}')
    print('✅ Endpoints ready:')
    print('   - GET  /')
    print('   - GET  /login')
    print('   - GET  /dashboard')
    print('   - GET  /home')
    print('   - GET  /api/accounts')
    print('   - POST /api/add-account')
    print('   - POST /api/verify-code')
    print('   - POST /api/get-messages')
    print('   - GET  /api/media/<account_id>/<message_id>')
    print('   - POST /api/send-message')
    print('   - POST /api/remove-account')
    print('   - GET  /api/health')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=True)
