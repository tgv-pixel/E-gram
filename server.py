from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Your API credentials
api_id = 33465589
api_hash = '08bdab35790bf1fdf20c16a50bd323b8'

# Global storage
temp_data = {}
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

def run_async(coro):
    """Improved helper to run async tasks in a sync Flask environment"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/')
def serve_login():
    return send_file('login.html')

@app.route('/dashboard')
def serve_dashboard():
    return send_file('dashboard.html')

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify({'success': True, 'accounts': accounts})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'})
    
    async def send_code():
        # Using an empty StringSession starts a new session
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        try:
            # We must keep the client connected or save the session properly
            sent_code = await client.send_code_request(phone)
            phone_code_hash = sent_code.phone_code_hash
            session_str = client.session.save()
            return phone_code_hash, session_str
        finally:
            await client.disconnect()
    
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
        print(f"Error in add-account: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data.get('code')
    session_id = data.get('session_id')
    password = data.get('password', '')
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired or invalid'})
    
    temp = temp_data[session_id]
    
    async def verify():
        client = TelegramClient(StringSession(temp['session_str']), api_id, api_hash)
        await client.connect()
        try:
            try:
                await client.sign_in(temp['phone'], code, phone_code_hash=temp['phone_code_hash'])
            except errors.SessionPasswordNeededError:
                if not password:
                    return {'need_password': True}
                await client.sign_in(password=password)
            
            me = await client.get_me()
            final_session = client.session.save()
            return {'success': True, 'me': me, 'session': final_session}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            await client.disconnect()
    
    try:
        result = run_async(verify())
        if result.get('success'):
            me = result['me']
            new_account = {
                'id': len(accounts) + 1,
                'phone': temp['phone'],
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or "User",
                'username': me.username or '',
                'session': result['session'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            accounts.append(new_account)
            save_accounts()
            del temp_data[session_id]
            return jsonify({'success': True, 'account': new_account})
        elif result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        else:
            return jsonify({'success': False, 'error': result.get('error')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ... Rest of your get_messages and send_message routes remain the same ...

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
