from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
import json
import os
import asyncio
import nest_asyncio
from datetime import datetime

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# Your API credentials - Using environment variables for security
API_ID = int(os.environ.get('API_ID', 33465589))
API_HASH = os.environ.get('API_HASH', '08bdab35790bf1fdf20c16a50bd323b8')

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

# Helper function to run async functions
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/')
def index():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard():
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
    
    # Create a unique ID for this session
    session_id = str(len(temp_data) + 1)
    
    # Start client
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    try:
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            # Send code request
            run_async(client.send_code_request(phone))
            
            # Store client for later use
            temp_data[session_id] = {
                'client': client,
                'phone': phone,
                'step': 'waiting_code'
            }
            
            return jsonify({
                'success': True,
                'session_id': session_id,
                'message': 'Code sent successfully'
            })
        else:
            # Already authorized
            me = run_async(client.get_me())
            session_string = run_async(client.session.save())
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                'session': session_string,
                'added': datetime.now().isoformat()
            }
            
            accounts.append(account)
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f, indent=2)
            
            run_async(client.disconnect())
            
            return jsonify({
                'success': True,
                'account': account
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    session_id = data.get('session_id')
    code = data.get('code')
    password = data.get('password', '')
    
    if session_id not in temp_data:
        return jsonify({'success': False, 'error': 'Session expired'})
    
    temp = temp_data[session_id]
    client = temp['client']
    phone = temp['phone']
    
    try:
        if temp.get('step') == 'waiting_code':
            try:
                run_async(client.sign_in(phone, code))
            except errors.SessionPasswordNeededError:
                temp['step'] = 'need_password'
                return jsonify({
                    'success': False,
                    'need_password': True,
                    'message': '2FA password required'
                })
            
            me = run_async(client.get_me())
            
            # Save session
            session_string = run_async(client.session.save())
            
            account = {
                'id': len(accounts) + 1,
                'phone': phone,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                'session': session_string,
                'added': datetime.now().isoformat()
            }
            
            accounts.append(account)
            with open('accounts.json', 'w') as f:
                json.dump(accounts, f, indent=2)
            
            run_async(client.disconnect())
            del temp_data[session_id]
            
            return jsonify({
                'success': True,
                'account': account
            })
            
        elif temp.get('step') == 'need_password':
            if password:
                try:
                    run_async(client.sign_in(password=password))
                except Exception as e:
                    return jsonify({'success': False, 'error': 'Invalid password'})
                
                me = run_async(client.get_me())
                session_string = run_async(client.session.save())
                
                account = {
                    'id': len(accounts) + 1,
                    'phone': phone,
                    'name': f"{me.first_name or ''} {me.last_name or ''}".strip() or 'User',
                    'session': session_string,
                    'added': datetime.now().isoformat()
                }
                
                accounts.append(account)
                with open('accounts.json', 'w') as f:
                    json.dump(accounts, f, indent=2)
                
                run_async(client.disconnect())
                del temp_data[session_id]
                
                return jsonify({
                    'success': True,
                    'account': account
                })
            else:
                return jsonify({
                    'success': False,
                    'need_password': True,
                    'message': '2FA password required'
                })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    try:
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Get dialogs (chats)
        dialogs = run_async(client.get_dialogs())
        
        chats = []
        messages = []
        
        for dialog in dialogs[:20]:  # Limit to 20 chats
            chat = {
                'id': str(dialog.id),
                'title': dialog.name or 'Unknown',
                'unread': dialog.unread_count,
                'lastMessage': dialog.message.text[:50] + '...' if dialog.message and dialog.message.text else '',
                'lastMessageDate': dialog.message.date.timestamp() if dialog.message else None
            }
            chats.append(chat)
            
            # Get recent messages for this chat
            try:
                msg_list = run_async(client.get_messages(dialog.entity, limit=20))
                for msg in msg_list:
                    if msg.message:
                        messages.append({
                            'chatId': str(dialog.id),
                            'text': msg.message,
                            'date': msg.date.timestamp(),
                            'out': msg.out
                        })
            except:
                continue  # Skip if can't get messages for this chat
        
        run_async(client.disconnect())
        
        return jsonify({
            'success': True,
            'chats': chats,
            'messages': messages
        })
        
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
    
    try:
        client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
        run_async(client.connect())
        
        if not run_async(client.is_user_authorized()):
            return jsonify({'success': False, 'error': 'Not authorized'})
        
        # Get entity
        try:
            entity = run_async(client.get_entity(int(chat_id)))
        except:
            # Try as username
            entity = run_async(client.get_entity(chat_id))
        
        # Send message
        run_async(client.send_message(entity, message))
        
        run_async(client.disconnect())
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    data = request.json
    account_id = data.get('accountId')
    
    global accounts
    accounts = [a for a in accounts if a['id'] != account_id]
    
    with open('accounts.json', 'w') as f:
        json.dump(accounts, f, indent=2)
    
    return jsonify({'success': True})

@app.route('/api/logout', methods=['POST'])
def logout():
    data = request.json
    account_id = data.get('accountId')
    
    account = next((a for a in accounts if a['id'] == account_id), None)
    if account:
        try:
            client = TelegramClient(StringSession(account['session']), API_ID, API_HASH)
            run_async(client.connect())
            run_async(client.log_out())
            run_async(client.disconnect())
        except:
            pass
    
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'gunicorn':
        # This is just a marker, gunicorn will handle it
        pass
    else:
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)
