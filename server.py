from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    DocumentAttributeVideo, DocumentAttributeAudio
)
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

# Store temporary data for OTP (in memory only)
temp_data = {}

# Store accounts - USE ENVIRONMENT VARIABLE FOR PERSISTENCE ON RENDER
ACCOUNTS_ENV_VAR = 'TELEGRAM_ACCOUNTS'

def load_accounts_from_env():
    """Load accounts from environment variable"""
    accounts_json = os.environ.get(ACCOUNTS_ENV_VAR)
    if accounts_json:
        try:
            accounts = json.loads(accounts_json)
            logger.info(f"✅ Loaded {len(accounts)} accounts from environment variable")
            return accounts
        except Exception as e:
            logger.error(f"❌ Error parsing accounts from env: {e}")
            return []
    else:
        logger.info("📝 No accounts found in environment variable")
        return []

def save_accounts_to_env(accounts):
    """Save accounts to environment variable"""
    try:
        accounts_json = json.dumps(accounts)
        # Note: On Render, you need to set this manually in the dashboard
        # We'll log it so you can copy-paste
        print("\n" + "="*70)
        print("🔑 IMPORTANT: Copy this and add to your Render environment variables:")
        print(f"Variable name: {ACCOUNTS_ENV_VAR}")
        print("Value:")
        print(accounts_json)
        print("="*70 + "\n")
        
        # Also save to a file as backup (might work on some Render setups)
        try:
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f, indent=2)
            logger.info("💾 Also saved to accounts.json as backup")
        except:
            pass
            
        return True
    except Exception as e:
        logger.error(f"❌ Error preparing accounts for env: {e}")
        return False

# Initialize accounts from environment
accounts = load_accounts_from_env()

print("\n" + "="*60)
print("🚀 TELEGRAM MANAGER - RENDER DEPLOYMENT")
print("="*60)
print(f"✅ Loaded {len(accounts)} accounts from environment")
print("="*60 + "\n")

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
    global accounts
    # Reload from env to ensure latest
    accounts = load_accounts_from_env()
    
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
            'session': 'exists' if acc.get('session') else ''  # Don't send full session
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
    
    # Reload current accounts
    global accounts
    accounts = load_accounts_from_env()
    
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
    
    # Save to environment
    save_success = save_accounts_to_env(accounts)
    print(f"📝 Account save attempt: {'✅ SUCCESS' if save_success else '❌ FAILED'}")
    
    if session_id in temp_data:
        del temp_data[session_id]
    
    return jsonify({'success': True, 'account': {
        'id': new_account['id'],
        'phone': new_account['phone'],
        'name': new_account['name']
    }})

# Get messages and chats
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    # Reload accounts from env
    global accounts
    accounts = load_accounts_from_env()
    
    print(f"\n🔍 Looking for account with ID: {account_id}")
    print(f"📊 Total accounts in memory: {len(accounts)}")
    
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        print(f"❌ Account NOT found for ID: {account_id}")
        return jsonify({'success': False, 'error': 'Account not found'})
    
    print(f"✅ Account found: {account.get('phone')}")
    
    session_string = account.get('session', '')
    
    if not session_string:
        print(f"❌ No session found for account {account_id}")
        return jsonify({'success': False, 'error': 'No session found for account'})
    
    async def fetch_chats():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Not authorized'}
            
            dialogs = await client.get_dialogs(limit=100)
            
            if not dialogs:
                return {'success': True, 'chats': [], 'messages': []}
            
            chats = []
            all_messages = []
            
            for dialog in dialogs:
                if not dialog or not dialog.entity:
                    continue
                
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
                    
                    if dialog.message.media:
                        if isinstance(dialog.message.media, MessageMediaPhoto):
                            last_msg_media = 'photo'
                        elif isinstance(dialog.message.media, MessageMediaDocument):
                            last_msg_media = 'document'
                        elif isinstance(dialog.message.media, MessageMediaWebPage):
                            last_msg_media = 'webpage'
                        else:
                            last_msg_media = 'media'
                    
                    if dialog.message.date:
                        last_date = dialog.message.date.timestamp()
                
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
                
                # Get messages
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
                    logger.error(f"Error getting messages: {e}")
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
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    save_accounts_to_env(accounts)
    return jsonify({'success': True})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_data)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '='*60)
    print('📱 TELEGRAM MANAGER - RENDER READY')
    print('='*60)
    print(f'✅ Loaded {len(accounts)} accounts from environment')
    print('='*60 + '\n')
    
    app.run(host='0.0.0.0', port=port, debug=False)
