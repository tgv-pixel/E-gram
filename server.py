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
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # If loop is already running, create a new loop in a new thread
        import threading
        result = []
        error = []
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                r = new_loop.run_until_complete(coro)
                result.append(r)
            except Exception as e:
                error.append(e)
            finally:
                new_loop.close()
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        
        if error:
            raise error[0]
        return result[0]
    else:
        return loop.run_until_complete(coro)

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
        client = None
        try:
            # Using an empty StringSession starts a new session
            client = TelegramClient(StringSession(), api_id, api_hash)
            await client.connect()
            
            # Check if already authorized
            if await client.is_user_authorized():
                return {'error': 'Already authorized with this session'}
            
            sent_code = await client.send_code_request(phone)
            phone_code_hash = sent_code.phone_code_hash
            session_str = client.session.save()
            return {'phone_code_hash': phone_code_hash, 'session_str': session_str}
        except errors.FloodWaitError as e:
            return {'error': f'Too many requests. Try again after {e.seconds} seconds'}
        except Exception as e:
            return {'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(send_code())
        
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})
        
        phone_code_hash = result['phone_code_hash']
        session_str = result['session_str']
        
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
    
    if not code or not session_id:
        return jsonify({'success': False, 'error': 'Code and session ID required'})
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired or invalid. Please start over.'})
    
    temp = temp_data[session_id]
    
    async def verify():
        client = None
        try:
            client = TelegramClient(StringSession(temp['session_str']), api_id, api_hash)
            await client.connect()
            
            try:
                await client.sign_in(temp['phone'], code, phone_code_hash=temp['phone_code_hash'])
            except errors.SessionPasswordNeededError:
                # Return a flag indicating password is needed
                return {'need_password': True}
            except errors.PhoneCodeInvalidError:
                return {'error': 'Invalid code. Please try again.'}
            except errors.PhoneCodeExpiredError:
                return {'error': 'Code expired. Please request a new code.'}
            
            me = await client.get_me()
            final_session = client.session.save()
            
            # Verify we got user info
            if not me:
                return {'error': 'Failed to get user information'}
                
            return {
                'success': True, 
                'me': {
                    'id': me.id,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'username': me.username,
                    'phone': me.phone
                }, 
                'session': final_session
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(verify())
        
        if result.get('need_password'):
            return jsonify({'success': False, 'need_password': True})
        
        if result.get('error'):
            return jsonify({'success': False, 'error': result['error']})
        
        if result.get('success'):
            me = result['me']
            new_account = {
                'id': len(accounts) + 1,
                'phone': temp['phone'],
                'name': f"{me.get('first_name', '')} {me.get('last_name', '')}".strip() or "User",
                'username': me.get('username', ''),
                'user_id': me.get('id'),
                'session': result['session'],
                'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            accounts.append(new_account)
            save_accounts()
            del temp_data[session_id]
            return jsonify({'success': True, 'account': new_account})
        else:
            return jsonify({'success': False, 'error': 'Unknown error during verification'})
            
    except Exception as e:
        print(f"Error in verify_code: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('account_id')
    chat_username = data.get('chat_username')
    
    if not account_id or not chat_username:
        return jsonify({'success': False, 'error': 'Account ID and chat username required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def fetch_messages():
        client = None
        try:
            client = TelegramClient(StringSession(account['session']), api_id, api_hash)
            await client.connect()
            
            # Check if authorized
            if not await client.is_user_authorized():
                return {'error': 'Session expired. Please add account again.'}
            
            # Get entity
            try:
                entity = await client.get_entity(chat_username)
            except ValueError:
                return {'error': f'Chat "{chat_username}" not found'}
            except Exception as e:
                return {'error': f'Error accessing chat: {str(e)}'}
            
            # Get last 50 messages
            messages = []
            async for msg in client.iter_messages(entity, limit=50):
                messages.append({
                    'id': msg.id,
                    'text': msg.text or '[Media or non-text message]',
                    'date': msg.date.strftime("%Y-%m-%d %H:%M:%S"),
                    'sender_id': msg.sender_id,
                    'from_user': msg.sender.first_name if msg.sender else 'Unknown'
                })
            
            return {'success': True, 'messages': messages}
        except Exception as e:
            return {'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(fetch_messages())
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})
        return jsonify({'success': True, 'messages': result['messages']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    account_id = data.get('account_id')
    chat_username = data.get('chat_username')
    message_text = data.get('message')
    
    if not all([account_id, chat_username, message_text]):
        return jsonify({'success': False, 'error': 'All fields are required'})
    
    # Find account
    account = next((acc for acc in accounts if acc['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def send_msg():
        client = None
        try:
            client = TelegramClient(StringSession(account['session']), api_id, api_hash)
            await client.connect()
            
            # Check if authorized
            if not await client.is_user_authorized():
                return {'error': 'Session expired. Please add account again.'}
            
            # Get entity
            try:
                entity = await client.get_entity(chat_username)
            except ValueError:
                return {'error': f'Chat "{chat_username}" not found'}
            
            # Send message
            sent_msg = await client.send_message(entity, message_text)
            
            return {
                'success': True, 
                'message': {
                    'id': sent_msg.id,
                    'text': sent_msg.text,
                    'date': sent_msg.date.strftime("%Y-%m-%d %H:%M:%S")
                }
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            if client:
                await client.disconnect()
    
    try:
        result = run_async(send_msg())
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']})
        return jsonify({'success': True, 'message': result['message']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
