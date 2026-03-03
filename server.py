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
        
        # Also save to environment variable for Render (optional but helpful)
        # Note: This won't persist across deployments, but helps during runtime
        logger.info(f"💾 Saved {len(accounts)} accounts to {ACCOUNTS_FILE}")
        
        # Create backup with timestamp
        backup_file = f"accounts_backup_{int(time.time())}.json"
        with open(backup_file, 'w') as f:
            json.dump(accounts, f, indent=2)
        
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accounts: {e}")
        return False

# Load accounts at startup
load_accounts()

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
            'session': acc.get('session', '')
        })
    
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

# Get messages and chats
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
            # Get all dialogs
            dialogs = await client.get_dialogs(limit=100)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                # Skip if no dialog
                if not dialog:
                    continue
                
                # Get chat info
                if dialog.is_user:
                    name = get_display_name(dialog.entity) if dialog.entity else 'User'
                    chat_type = 'bot' if (dialog.entity and hasattr(dialog.entity, 'bot') and dialog.entity.bot) else 'user'
                elif dialog.is_group:
                    name = dialog.name or 'Group'
                    chat_type = 'group'
                elif dialog.is_channel:
                    name = dialog.name or 'Channel'
                    chat_type = 'channel'
                else:
                    name = dialog.name or 'Unknown'
                    chat_type = 'unknown'
                
                chat_id = str(dialog.id) if dialog.id else '0'
                
                # SAFELY get last message
                last_msg_text = ''
                last_msg_media = None
                last_date = 0
                
                if dialog.message:
                    # Get message text
                    if dialog.message.text:
                        last_msg_text = dialog.message.text[:50]
                        if len(dialog.message.text) > 50:
                            last_msg_text += '...'
                    elif dialog.message.media:
                        if isinstance(dialog.message.media, MessageMediaPhoto):
                            last_msg_text = '📷 Photo'
                            last_msg_media = 'photo'
                        elif isinstance(dialog.message.media, MessageMediaDocument):
                            last_msg_text = '📎 Document'
                            last_msg_media = 'document'
                        else:
                            last_msg_text = '📎 Media'
                            last_msg_media = 'media'
                    
                    # SAFELY get date
                    try:
                        if hasattr(dialog.message, 'date') and dialog.message.date:
                            last_date = dialog.message.date.timestamp()
                    except:
                        last_date = 0
                
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'type': chat_type,
                    'unread': dialog.unread_count if hasattr(dialog, 'unread_count') else 0,
                    'lastMessage': last_msg_text,
                    'lastMessageMedia': last_msg_media,
                    'lastMessageDate': last_date,
                    'pinned': dialog.pinned if hasattr(dialog, 'pinned') else False
                })
                
                # Get last 20 messages
                try:
                    if dialog.entity:
                        msgs = await client.get_messages(dialog.entity, limit=20)
                        
                        for msg in msgs:
                            if not msg:
                                continue
                            
                            # SAFELY get message data
                            msg_date = 0
                            try:
                                if hasattr(msg, 'date') and msg.date:
                                    msg_date = msg.date.timestamp()
                            except:
                                msg_date = 0
                            
                            message_data = {
                                'chatId': chat_id,
                                'text': msg.text or '' if msg.text else '',
                                'date': msg_date,
                                'out': msg.out if hasattr(msg, 'out') else False,
                                'id': msg.id if msg.id else 0,
                                'hasMedia': msg.media is not None if hasattr(msg, 'media') else False
                            }
                            
                            # Add media type
                            if msg.media:
                                if isinstance(msg.media, MessageMediaPhoto):
                                    message_data['mediaType'] = 'photo'
                                elif isinstance(msg.media, MessageMediaDocument):
                                    message_data['mediaType'] = 'document'
                                else:
                                    message_data['mediaType'] = 'media'
                            
                            all_messages.append(message_data)
                except Exception as e:
                    logger.error(f"Error getting messages for {chat_id}: {e}")
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

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not all([account_id, chat_id]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', '')
    
    async def send():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
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
        'temp_sessions': len(temp_data),
        'accounts_file_exists': os.path.exists(ACCOUNTS_FILE)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - PERSISTENT STORAGE VERSION')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print(f'✅ Accounts file: {ACCOUNTS_FILE}')
    print(f'✅ File exists: {os.path.exists(ACCOUNTS_FILE)}')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=True)
