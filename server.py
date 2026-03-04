from flask import Flask, send_file, jsonify, request, render_template_string
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

# Simple HTML templates as fallback
INDEX_HTML = '''
<!DOCTYPE html>
<html>
<head><title>Telegram Manager</title></head>
<body>
    <h1>Telegram Manager</h1>
    <p>Server is running!</p>
    <a href="/login">Login</a> | <a href="/dashboard">Dashboard</a>
</body>
</html>
'''

# Load accounts on startup
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read().strip()
                accounts = json.loads(content) if content else []
                logger.info(f"✅ Loaded {len(accounts)} accounts")
                return
        accounts = []
        logger.info("📝 No accounts found, starting fresh")
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

# Load accounts at startup
load_accounts()

# -------------------- HTML PAGES --------------------
@app.route('/')
def serve_index():
    try:
        return send_file('login.html')
    except:
        return render_template_string(INDEX_HTML)

@app.route('/login')
def serve_login():
    try:
        return send_file('login.html')
    except:
        return "Login page - Please ensure login.html exists"

@app.route('/dashboard')
def serve_dashboard():
    try:
        return send_file('dashboard.html')
    except:
        return "Dashboard - Please ensure dashboard.html exists"

@app.route('/home')
def serve_home():
    try:
        return send_file('home.html')
    except:
        return "<h1>Home</h1><p>Account added successfully!</p>"

# -------------------- API ENDPOINTS --------------------

# Get all accounts
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    try:
        load_accounts()  # Reload to ensure latest
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
                'username': acc.get('username', '')
            })
        return jsonify({'success': True, 'accounts': account_list})
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        return jsonify({'success': False, 'error': str(e)})

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
    save_accounts()
    
    if session_id in temp_data:
        del temp_data[session_id]
    
    return jsonify({'success': True, 'account': new_account})

# Get messages and chats - SIMPLIFIED VERSION
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', '')
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs
            dialogs = await client.get_dialogs(limit=100)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                try:
                    if not dialog or not dialog.entity:
                        continue
                    
                    # Determine chat type and name
                    entity = dialog.entity
                    chat_id = str(dialog.id)
                    
                    # Get name based on type
                    if hasattr(entity, 'title'):  # Channel or Group
                        name = entity.title or 'Unknown'
                        if hasattr(entity, 'broadcast') and entity.broadcast:
                            chat_type = 'channel'
                        elif hasattr(entity, 'megagroup') and entity.megagroup:
                            chat_type = 'group'
                        else:
                            chat_type = 'group'
                    else:  # User or Bot
                        name = get_display_name(entity) or 'User'
                        if hasattr(entity, 'bot') and entity.bot:
                            chat_type = 'bot'
                        else:
                            chat_type = 'user'
                    
                    # Get last message info safely
                    last_msg_text = ''
                    last_date = 0
                    
                    if dialog.message:
                        if dialog.message.text:
                            last_msg_text = dialog.message.text[:100]
                        elif dialog.message.media:
                            last_msg_text = '📎 Media'
                        
                        if dialog.message.date:
                            last_date = int(dialog.message.date.timestamp())
                    
                    # Add chat to list
                    chats.append({
                        'id': chat_id,
                        'title': name,
                        'type': chat_type,
                        'unread': dialog.unread_count or 0,
                        'lastMessage': last_msg_text,
                        'lastMessageDate': last_date,
                        'pinned': dialog.pinned or False
                    })
                    
                    # Get recent messages (last 15 for each chat)
                    try:
                        msgs = await client.get_messages(entity, limit=15)
                        
                        for msg in msgs:
                            if not msg:
                                continue
                            
                            # Basic message info
                            msg_date = int(msg.date.timestamp()) if msg.date else 0
                            msg_data = {
                                'chatId': chat_id,
                                'text': msg.text or '',
                                'date': msg_date,
                                'out': msg.out or False,
                                'id': msg.id,
                                'hasMedia': msg.media is not None
                            }
                            
                            # Detect media type
                            if msg.media:
                                if isinstance(msg.media, MessageMediaPhoto):
                                    msg_data['mediaType'] = 'photo'
                                    if not msg.text:
                                        msg_data['text'] = '📷 Photo'
                                elif isinstance(msg.media, MessageMediaDocument):
                                    # Check document attributes
                                    if msg.file and msg.file.mime_type:
                                        if msg.file.mime_type.startswith('video/'):
                                            msg_data['mediaType'] = 'video'
                                            msg_data['text'] = '🎥 Video'
                                        elif msg.file.mime_type.startswith('audio/'):
                                            msg_data['mediaType'] = 'audio'
                                            msg_data['text'] = '🎵 Audio'
                                        elif 'image' in msg.file.mime_type:
                                            msg_data['mediaType'] = 'photo'
                                            msg_data['text'] = '📷 Photo'
                                        else:
                                            msg_data['mediaType'] = 'document'
                                            msg_data['text'] = '📎 Document'
                                    else:
                                        msg_data['mediaType'] = 'document'
                                        msg_data['text'] = '📎 Document'
                                elif isinstance(msg.media, MessageMediaWebPage):
                                    msg_data['mediaType'] = 'link'
                                    msg_data['text'] = '🔗 Link'
                                else:
                                    msg_data['mediaType'] = 'media'
                                    msg_data['text'] = '📎 Media'
                            
                            all_messages.append(msg_data)
                            
                    except Exception as e:
                        logger.error(f"Error getting messages for {chat_id}: {e}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error processing dialog: {e}")
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
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in get-messages: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Get media file
@app.route('/api/media/<int:account_id>/<int:message_id>')
def get_media(account_id, message_id):
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    
    session_string = account.get('session', '')
    
    async def download_media():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}, 401
            
            # Get the message
            msg = await client.get_messages(None, ids=message_id)
            if not msg or not msg.media:
                return {'success': False, 'error': 'Media not found'}, 404
            
            # Download media
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
            logger.error(f"Error downloading media: {e}")
            return {'success': False, 'error': str(e)}, 500
        finally:
            await client.disconnect()
    
    try:
        result = run_async(download_media())
        
        if isinstance(result, tuple):
            return jsonify({'success': False, 'error': result[0]['error']}), result[1]
        
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed')}), 500
        
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
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', '')
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
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
            
            # Send message
            if message:
                await client.send_message(entity, message)
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    result = run_async(send())
    return jsonify(result)

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
        save_accounts()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Account not found'})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'accounts_file': ACCOUNTS_FILE,
        'file_exists': os.path.exists(ACCOUNTS_FILE)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - SIMPLIFIED VERSION')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ Accounts saved in: {ACCOUNTS_FILE}')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=True)
