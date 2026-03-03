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
import json
import os
import asyncio
from datetime import datetime
import logging
import threading
import base64
import io
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

# Store accounts persistently
accounts = []
ACCOUNTS_FILE = 'accounts.json'

# Media cache directory
MEDIA_CACHE_DIR = 'media_cache'
if not os.path.exists(MEDIA_CACHE_DIR):
    os.makedirs(MEDIA_CACHE_DIR)

# Load existing accounts if file exists
def load_accounts():
    global accounts
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    accounts = json.loads(content)
                    logger.info(f"✅ Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")
                else:
                    accounts = []
        except Exception as e:
            logger.error(f"⚠️ Error loading accounts: {e}")
            accounts = []
    else:
        accounts = []

# Load accounts at startup
load_accounts()

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        logger.info(f"💾 Saved {len(accounts)} accounts to {ACCOUNTS_FILE}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accounts: {e}")
        return False

# Helper to run async functions
def run_async(coro):
    """Run async coroutine"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Error in run_async: {e}")
        raise
    finally:
        try:
            loop.close()
        except:
            pass

# -------------------- SERVE HTML FILES --------------------
@app.route('/')
def serve_index():
    try:
        return send_file('login.html')
    except FileNotFoundError:
        return "login.html not found", 404

@app.route('/login')
def serve_login():
    try:
        return send_file('login.html')
    except FileNotFoundError:
        return "login.html not found", 404

@app.route('/dashboard')
def serve_dashboard():
    try:
        return send_file('dashboard.html')
    except FileNotFoundError:
        return "dashboard.html not found", 404

@app.route('/home')
def serve_home():
    try:
        return send_file('home.html')
    except FileNotFoundError:
        return "home.html not found", 404

# -------------------- GET ALL ACCOUNTS --------------------
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Return all accounts"""
    global accounts
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
            'username': acc.get('username', ''),
            'session': acc.get('session', '')
        })
    
    logger.info(f"📋 Returning {len(account_list)} accounts")
    return jsonify({'success': True, 'accounts': account_list})

# -------------------- ADD ACCOUNT (SEND OTP) --------------------
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
            return {'success': False, 'error': f'Too many attempts. Wait {e.seconds} seconds'}
        except Exception as e:
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
        client = TelegramClient(StringSession(session['session_str']), API_ID, API_HASH)
        await client.connect()
        try:
            if password:
                await client.sign_in(password=password)
            else:
                await client.sign_in(
                    session['phone'], 
                    code, 
                    phone_code_hash=session['phone_code_hash']
                )
            
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
    
    try:
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
        
        logger.info(f"✅ Account added: {session['phone']} (ID: {new_id})")
        return jsonify({'success': True, 'account': new_account})
        
    except Exception as e:
        logger.error(f"Error in verify-code: {e}")
        return jsonify({'success': False, 'error': str(e)})

# -------------------- GET MESSAGES --------------------
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
    
    session_string = account.get('session', '')
    
    if not session_string:
        return jsonify({'success': False, 'error': 'No session found for account'})
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            # Check if authorized
            if not await client.is_user_authorized():
                logger.error(f"Account {account_id} not authorized")
                return {'success': False, 'error': 'Not authorized'}
            
            # Get all dialogs
            dialogs = await client.get_dialogs(limit=100)
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                # Get chat info
                if dialog.is_user:
                    name = get_display_name(dialog.entity)
                    chat_type = 'bot' if (hasattr(dialog.entity, 'bot') and dialog.entity.bot) else 'user'
                elif dialog.is_group:
                    name = dialog.name or 'Group'
                    chat_type = 'group'
                elif dialog.is_channel:
                    name = dialog.name or 'Channel'
                    chat_type = 'channel'
                else:
                    name = dialog.name or 'Unknown'
                    chat_type = 'unknown'
                
                chat_id = str(dialog.id)
                
                # Get last message
                last_msg_text = ''
                last_msg_media = None
                
                if dialog.message:
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
                        elif isinstance(dialog.message.media, MessageMediaWebPage):
                            last_msg_text = '🔗 Link'
                            last_msg_media = 'webpage'
                        else:
                            last_msg_text = '📎 Media'
                            last_msg_media = 'media'
                
                chats.append({
                    'id': chat_id,
                    'title': name,
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': last_msg_text,
                    'lastMessageMedia': last_msg_media,
                    'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None,
                    'pinned': dialog.pinned or False
                })
                
                # Get last 20 messages
                try:
                    msgs = await client.get_messages(dialog.entity, limit=20)
                    for msg in msgs:
                        if msg:
                            message_data = {
                                'chatId': chat_id,
                                'text': msg.text or '',
                                'date': msg.date.timestamp(),
                                'out': msg.out,
                                'id': msg.id,
                                'hasMedia': msg.media is not None
                            }
                            
                            if msg.media:
                                if isinstance(msg.media, MessageMediaPhoto):
                                    message_data['mediaType'] = 'photo'
                                elif isinstance(msg.media, MessageMediaDocument):
                                    message_data['mediaType'] = 'document'
                                elif isinstance(msg.media, MessageMediaWebPage):
                                    message_data['mediaType'] = 'webpage'
                                else:
                                    message_data['mediaType'] = 'media'
                            
                            all_messages.append(message_data)
                except Exception as e:
                    logger.error(f"Error fetching messages: {e}")
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

# -------------------- SEND MESSAGE --------------------
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
            
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            
            if message:
                await client.send_message(entity, message)
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(send())
        return jsonify(result)
            
    except Exception as e:
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
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Account not found'})

# -------------------- HEALTH CHECK --------------------
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'accounts_file_exists': os.path.exists(ACCOUNTS_FILE)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - FIXED VERSION')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=True)
