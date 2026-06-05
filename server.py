from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import json
import hashlib
import random
import string
import time
import requests
from functools import wraps

app = Flask(__name__, static_folder='.')
CORS(app)

# ============================================
# FIREBASE CONFIG - Using REST API
# ============================================
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyD4t4GUzN1xkyia0o3zx9i2cX2004Epv7A",
    "authDomain": "webapp-fc856.firebaseapp.com",
    "projectId": "webapp-fc856",
    "storageBucket": "webapp-fc856.appspot.com",
    "messagingSenderId": "892830607693",
    "appId": "1:892830607693:web:a3a886c142586665fc2f04"
}

PROJECT_ID = "webapp-fc856"
FIRESTORE_BASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
RTDB_BASE_URL = f"https://webapp-fc856-default-rtdb.firebaseio.com"

# ============================================
# CONFIGURATION
# ============================================
TELEBIRR_NUMBER = '0949399753'
TELEBIRR_NAME = 'Abinet'
WALLET_ADDRESS = 'UQB37g1e9sANIvwdJd3mmxtqveSBae0y-bpqX7DXQPH3c9Lb'
REFERRAL_BONUS_PERCENTAGE = 10
REFERRAL_POINTS_PERCENTAGE = 10
MIN_DEPOSIT = 10
MIN_WITHDRAW = 20
MAX_WITHDRAW_DAILY = 500
WEEKEND_DAYS = [5, 6]
WITHDRAW_POINTS_FEE_PERCENTAGE = 10  # 10% points fee for withdrawals

# ============================================
# PRODUCTS CONFIG
# ============================================
PRODUCTS = [
    {'name': 'Level 1', 'price': 30, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'Level 2', 'price': 50, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'Level 3', 'price': 100, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'VIP 1', 'price': 300, 'dailyEarnings': 15, 'duration': 130, 'isFixed': True, 'category': 'vip'},
    {'name': 'VIP 2', 'price': 500, 'dailyEarnings': 25, 'duration': 130, 'isFixed': True, 'category': 'vip'},
    {'name': 'VIP 3', 'price': 1000, 'dailyEarnings': 50, 'duration': 130, 'isFixed': True, 'category': 'vip'},
]

# ============================================
# UTILITY FUNCTIONS
# ============================================
def generate_id(length=12):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_security_code():
    return str(random.randint(1000, 9999))

def is_weekend():
    return datetime.now().weekday() in WEEKEND_DAYS

def get_timestamp():
    return datetime.utcnow().isoformat()

def calculate_referral_bonus(deposit_amount):
    return round(deposit_amount * REFERRAL_BONUS_PERCENTAGE / 100, 2)

def calculate_withdraw_points_fee(amount):
    """Calculate 10% points fee for withdrawal"""
    return round(amount * WITHDRAW_POINTS_FEE_PERCENTAGE / 100, 2)

# ============================================
# FIREBASE REST API HELPERS
# ============================================
def firestore_request(method, path, data=None):
    """Make request to Firestore REST API"""
    url = f"{FIRESTORE_BASE_URL}/{path}"
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            return None
        
        if response.status_code in [200, 201]:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            print(f"Firestore API Error: {response.status_code} - {response.text[:200]}")
            return None
    except Exception as e:
        print(f"Firestore Request Error: {e}")
        return None

def rtdb_request(method, path, data=None):
    """Make request to Realtime Database REST API"""
    url = f"{RTDB_BASE_URL}/{path}.json"
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            return None
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            print(f"RTDB API Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"RTDB Request Error: {e}")
        return None

# ============================================
# FIREBASE CRUD OPERATIONS
# ============================================

def get_user(user_id):
    """Get user from Firestore - with RTDB fallback"""
    if not user_id:
        return None
    
    # First try Firestore
    result = firestore_request('GET', f'users/{user_id}')
    if result and 'fields' in result:
        user_data = firestore_to_dict(result['fields'])
        user_data['userId'] = user_id
        return user_data
    
    # Fallback to RTDB
    rtdb_result = rtdb_request('GET', f'users/{user_id}')
    if rtdb_result:
        rtdb_result['userId'] = user_id
        return rtdb_result
    
    return None

def save_user(user_id, user_data):
    """Save/Update user in both Firestore and RTDB"""
    if not user_id:
        return False
    
    # Always ensure email and name are preserved
    existing_user = get_user(user_id) or {}
    
    # Merge with existing data to prevent losing fields
    merged_data = {**existing_user, **user_data}
    merged_data.pop('userId', None)  # Remove userId from data to save
    
    firestore_data = dict_to_firestore(merged_data)
    
    # Save to Firestore
    result = firestore_request('PATCH', f'users/{user_id}', {'fields': firestore_data})
    
    # Also save to RTDB for quick access (always include email and name)
    rtdb_data = {
        'email': merged_data.get('email', ''),
        'fullName': merged_data.get('fullName', ''),
        'firstName': merged_data.get('firstName', ''),
        'lastName': merged_data.get('lastName', ''),
        'referralCode': merged_data.get('referralCode', ''),
        'referredBy': merged_data.get('referredBy'),
        'status': merged_data.get('status', 'active'),
        'depositBalance': merged_data.get('depositBalance', 0),
        'taskEarnings': merged_data.get('taskEarnings', 0),
        'points': merged_data.get('points', 0),
        'referralCount': merged_data.get('referralCount', 0)
    }
    rtdb_request('PUT', f'users/{user_id}', rtdb_data)
    
    return result is not None

def get_all_users():
    """Get all users from Firestore and RTDB combined"""
    users = {}
    
    # Get from Firestore
    result = firestore_request('GET', 'users')
    if result and 'documents' in result:
        for doc in result['documents']:
            user_id = doc['name'].split('/')[-1]
            fields = doc.get('fields', {})
            user_data = firestore_to_dict(fields)
            user_data['userId'] = user_id
            users[user_id] = user_data
    
    # Also check RTDB for any users not in Firestore
    rtdb_result = rtdb_request('GET', 'users')
    if rtdb_result:
        for user_id, user_data in rtdb_result.items():
            if user_id not in users:
                user_data['userId'] = user_id
                users[user_id] = user_data
            else:
                # Merge RTDB data (fill missing fields)
                for key, value in user_data.items():
                    if key not in users[user_id] or users[user_id].get(key) is None:
                        users[user_id][key] = value
    
    return users

def add_document(collection, data, doc_id=None):
    """Add document to Firestore collection"""
    if doc_id:
        path = f'{collection}/{doc_id}'
    else:
        doc_id = generate_id()
        path = f'{collection}/{doc_id}'
    
    result = firestore_request('PATCH', path, {'fields': dict_to_firestore(data)})
    return doc_id if result else None

def get_collection(collection, filters=None):
    """Get documents from Firestore collection"""
    result = firestore_request('GET', collection)
    if result and 'documents' in result:
        docs = []
        for doc in result['documents']:
            data = firestore_to_dict(doc.get('fields', {}))
            data['id'] = doc['name'].split('/')[-1]
            
            if filters:
                match = True
                for key, value in filters.items():
                    actual_value = data.get(key)
                    if actual_value is None:
                        match = False
                        break
                    if isinstance(value, (int, float)) and isinstance(actual_value, (int, float)):
                        if actual_value != value:
                            match = False
                            break
                    elif str(actual_value).lower() != str(value).lower():
                        match = False
                        break
                if not match:
                    continue
            docs.append(data)
        return docs
    return []

def update_document(collection, doc_id, update_data):
    """Update document in Firestore"""
    if not doc_id:
        return False
    path = f'{collection}/{doc_id}'
    result = firestore_request('PATCH', path, {'fields': dict_to_firestore(update_data)})
    return result is not None

def add_notification(user_id, message, notif_type, extra_data=None):
    """Add notification for user"""
    notif_data = {
        'userId': user_id,
        'type': notif_type,
        'message': message,
        'read': False,
        'timestamp': get_timestamp()
    }
    if extra_data:
        notif_data.update(extra_data)
    
    doc_id = generate_id()
    add_document('notifications', notif_data, doc_id)
    rtdb_request('PUT', f'notifications/{user_id}/{doc_id}', notif_data)

# ============================================
# DATA CONVERSION HELPERS
# ============================================
def firestore_to_dict(fields):
    """Convert Firestore fields to Python dict"""
    if not fields:
        return {}
    result = {}
    for key, value in fields.items():
        if 'stringValue' in value:
            result[key] = value['stringValue']
        elif 'integerValue' in value:
            result[key] = int(value['integerValue'])
        elif 'doubleValue' in value:
            result[key] = float(value['doubleValue'])
        elif 'booleanValue' in value:
            result[key] = value['booleanValue']
        elif 'nullValue' in value:
            result[key] = None
        elif 'timestampValue' in value:
            result[key] = value['timestampValue']
        elif 'mapValue' in value:
            result[key] = firestore_to_dict(value['mapValue'].get('fields', {}))
        elif 'arrayValue' in value:
            arr = []
            for v in value['arrayValue'].get('values', []):
                if 'mapValue' in v:
                    arr.append(firestore_to_dict(v['mapValue'].get('fields', {})))
                elif 'stringValue' in v:
                    arr.append(v['stringValue'])
                elif 'integerValue' in v:
                    arr.append(int(v['integerValue']))
                elif 'doubleValue' in v:
                    arr.append(float(v['doubleValue']))
                else:
                    arr.append(str(v))
            result[key] = arr
        else:
            result[key] = value
    return result

def dict_to_firestore(data):
    """Convert Python dict to Firestore format"""
    if not data:
        return {}
    result = {}
    for key, value in data.items():
        if value is None:
            result[key] = {'nullValue': None}
        elif isinstance(value, bool):
            result[key] = {'booleanValue': value}
        elif isinstance(value, int):
            result[key] = {'integerValue': value}
        elif isinstance(value, float):
            result[key] = {'doubleValue': value}
        elif isinstance(value, str):
            result[key] = {'stringValue': value}
        elif isinstance(value, dict):
            result[key] = {'mapValue': {'fields': dict_to_firestore(value)}}
        elif isinstance(value, list):
            values = []
            for v in value:
                if isinstance(v, dict):
                    values.append({'mapValue': {'fields': dict_to_firestore(v)}})
                elif isinstance(v, str):
                    values.append({'stringValue': v})
                elif isinstance(v, int):
                    values.append({'integerValue': v})
                elif isinstance(v, float):
                    values.append({'doubleValue': v})
                else:
                    values.append({'stringValue': str(v)})
            result[key] = {'arrayValue': {'values': values}}
        else:
            result[key] = {'stringValue': str(value)}
    return result

# ============================================
# STATIC FILE SERVING
# ============================================
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(path):
        return send_from_directory('.', path)
    if '.' not in path:
        html_path = f"{path}.html"
        if os.path.exists(html_path):
            return send_from_directory('.', html_path)
    return send_from_directory('.', 'index.html')

# ============================================
# API: HEALTH CHECK
# ============================================
@app.route('/api/health')
def health_check():
    try:
        users = get_all_users()
        return jsonify({
            'status': 'ok',
            'message': 'SAFE Platform Running',
            'database': 'Firebase (REST API)',
            'total_users': len(users),
            'timestamp': get_timestamp()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================
# API: SERVER INFO
# ============================================
@app.route('/api/info')
def server_info():
    return jsonify({
        'name': 'SAFE Platform',
        'version': '3.0.0',
        'database': 'Firebase Firestore',
        'telebirr_number': TELEBIRR_NUMBER,
        'telebirr_name': TELEBIRR_NAME,
        'wallet_address': WALLET_ADDRESS,
        'referral_bonus_percentage': f'{REFERRAL_BONUS_PERCENTAGE}%',
        'referral_points_percentage': REFERRAL_POINTS_PERCENTAGE,
        'min_deposit': MIN_DEPOSIT,
        'min_withdraw': MIN_WITHDRAW,
        'withdraw_points_fee_percentage': f'{WITHDRAW_POINTS_FEE_PERCENTAGE}%'
    })

# ============================================
# API: USER MANAGEMENT
# ============================================
@app.route('/api/user/create', methods=['POST'])
def create_user():
    try:
        data = request.json
        user_id = data.get('userId')
        email = data.get('email', '').strip()
        full_name = data.get('fullName', '').strip()
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        # Check if user exists
        existing = get_user(user_id)
        if existing:
            # Update existing user with any new info
            update_data = {}
            if not existing.get('email') and email:
                update_data['email'] = email
            if not existing.get('fullName') and full_name:
                update_data['fullName'] = full_name
            if not existing.get('firstName') and data.get('firstName'):
                update_data['firstName'] = data.get('firstName')
            
            if update_data:
                save_user(user_id, update_data)
                existing.update(update_data)
            
            return jsonify({
                'success': True,
                'message': 'User already exists',
                'user': existing,
                'referralCode': existing.get('referralCode'),
                'securityCode': existing.get('securityCode')
            })
        
        referral_code = generate_referral_code()
        security_code = generate_security_code()
        
        user_data = {
            'userId': user_id,
            'email': email,
            'fullName': full_name,
            'firstName': data.get('firstName', full_name.split(' ')[0] if full_name else ''),
            'lastName': data.get('lastName', ''),
            'phone': data.get('phone', ''),
            'referralCode': referral_code,
            'referredBy': data.get('referredBy'),
            'referredByName': data.get('referredByName'),
            'depositBalance': 0.0,
            'taskEarnings': 0.0,
            'points': 0.0,
            'referralCount': 0,
            'referralBonus': 0.0,
            'totalReferralPoints': 0.0,
            'firstDepositCompleted': False,
            'status': 'active',
            'securityCode': security_code,
            'createdAt': get_timestamp(),
            'lastLogin': get_timestamp()
        }
        
        if save_user(user_id, user_data):
            # Handle referral
            referred_by = data.get('referredBy')
            if referred_by:
                referrer = get_user(referred_by)
                if referrer:
                    referral_data = {
                        'referrerId': referred_by,
                        'referrerName': referrer.get('fullName', referrer.get('email', referred_by)),
                        'referredUserId': user_id,
                        'referredEmail': email,
                        'referredName': full_name,
                        'bonusEarned': 0,
                        'pointsAwarded': 0,
                        'status': 'pending_first_deposit',
                        'timestamp': get_timestamp()
                    }
                    add_document('referrals', referral_data)
                    
                    current_count = referrer.get('referralCount', 0) or 0
                    save_user(referred_by, {'referralCount': current_count + 1})
                    
                    add_notification(referred_by, 
                        f"🎉 {full_name or 'New user'} joined using your referral link!", 
                        'referral_signup',
                        {'referredUserId': user_id, 'referredName': full_name})
            
            return jsonify({
                'success': True,
                'message': 'User created successfully',
                'user': user_data,
                'referralCode': referral_code,
                'securityCode': security_code
            }), 201
        
        return jsonify({'success': False, 'error': 'Failed to create user'}), 500
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user_api(user_id):
    try:
        user = get_user(user_id)
        if user:
            # ALWAYS ensure email and name are present
            user['email'] = user.get('email', '')
            user['fullName'] = user.get('fullName', user.get('firstName', 'User'))
            user['firstName'] = user.get('firstName', user.get('fullName', 'User'))
            user['referralLink'] = f"{request.host_url}?ref={user.get('referralCode', user_id)}"
            user['totalBalance'] = (user.get('depositBalance', 0) or 0) + (user.get('taskEarnings', 0) or 0)
            user['userId'] = user_id
            return jsonify({'success': True, 'user': user})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/<user_id>/balance', methods=['GET'])
def get_user_balance(user_id):
    try:
        user = get_user(user_id)
        if user:
            return jsonify({
                'success': True,
                'email': user.get('email', ''),
                'fullName': user.get('fullName', ''),
                'depositBalance': user.get('depositBalance', 0) or 0,
                'taskEarnings': user.get('taskEarnings', 0) or 0,
                'totalBalance': (user.get('depositBalance', 0) or 0) + (user.get('taskEarnings', 0) or 0),
                'points': user.get('points', 0) or 0,
                'referralBonus': user.get('referralBonus', 0) or 0,
                'referralCount': user.get('referralCount', 0) or 0
            })
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: USER BALANCE UPDATE (for Balance Manager)
# ============================================
@app.route('/api/user/<user_id>/update', methods=['POST'])
def update_user_balance(user_id):
    """Update user fields - Used by Balance Manager admin page"""
    try:
        data = request.json
        field = data.get('field')
        value = data.get('value')
        
        if not field:
            return jsonify({'success': False, 'error': 'Field name required'}), 400
        
        if value is None:
            return jsonify({'success': False, 'error': 'Value required'}), 400
        
        allowed_fields = [
            'depositBalance', 'taskEarnings', 'points', 
            'referralCount', 'referralBonus', 'totalReferralPoints',
            'status', 'firstDepositCompleted', 'phone', 'fullName', 
            'email', 'firstName', 'lastName', 'securityCode'
        ]
        
        if field not in allowed_fields:
            return jsonify({
                'success': False,
                'error': f'Invalid field. Allowed: {", ".join(allowed_fields)}'
            }), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        try:
            if field in ['depositBalance', 'taskEarnings', 'referralBonus', 'totalReferralPoints']:
                value = float(value)
            elif field in ['points', 'referralCount']:
                value = int(float(value))
            elif field == 'firstDepositCompleted':
                value = value in [True, 'true', 'True', 1, '1']
            else:
                value = str(value)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': f'Invalid value type for {field}'}), 400
        
        update_data = {field: value}
        
        if save_user(user_id, update_data):
            print(f"✅ Updated {user_id}: {field} = {value}")
            
            try:
                log_data = {
                    'userId': user_id,
                    'field': field,
                    'newValue': value,
                    'previousValue': user.get(field, 'N/A'),
                    'timestamp': get_timestamp(),
                    'type': 'admin_update'
                }
                add_document('balance_logs', log_data)
            except:
                pass
            
            return jsonify({
                'success': True,
                'message': f'Updated {field} to {value}',
                'userId': user_id,
                'field': field,
                'previousValue': user.get(field, 0),
                'newValue': value
            })
        
        return jsonify({'success': False, 'error': 'Failed to update user'}), 500
        
    except Exception as e:
        print(f"Error updating user balance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/users/all', methods=['GET'])
def get_all_users_api():
    try:
        users = get_all_users()
        users_list = []
        for uid, data in users.items():
            # ALWAYS include email and fullName - these are required by all pages
            user_entry = {
                'userId': uid,
                'email': data.get('email', ''),
                'fullName': data.get('fullName', data.get('firstName', 'User')),
                'firstName': data.get('firstName', data.get('fullName', '').split(' ')[0] if data.get('fullName') else ''),
                'lastName': data.get('lastName', ''),
                'depositBalance': data.get('depositBalance', 0) or 0,
                'taskEarnings': data.get('taskEarnings', 0) or 0,
                'points': data.get('points', 0) or 0,
                'referralCount': data.get('referralCount', 0) or 0,
                'referralCode': data.get('referralCode', ''),
                'referredBy': data.get('referredBy'),
                'status': data.get('status', 'active'),
                'createdAt': data.get('createdAt', ''),
                'firstDepositCompleted': data.get('firstDepositCompleted', False),
                'securityCode': data.get('securityCode', '')
            }
            users_list.append(user_entry)
        
        return jsonify({
            'success': True, 
            'users': users_list, 
            'total': len(users_list)
        })
    except Exception as e:
        print(f"Error getting all users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: USER LOGIN (by email)
# ============================================
@app.route('/api/user/login', methods=['POST'])
def login_user():
    try:
        data = request.json
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        users = get_all_users()
        
        for uid, user_data in users.items():
            stored_email = (user_data.get('email') or '').lower().strip()
            if stored_email == email:
                # Update last login
                save_user(uid, {'lastLogin': get_timestamp()})
                
                # Build complete user response
                user_response = {
                    'userId': uid,
                    'email': user_data.get('email', email),
                    'fullName': user_data.get('fullName', user_data.get('firstName', 'User')),
                    'firstName': user_data.get('firstName', ''),
                    'lastName': user_data.get('lastName', ''),
                    'phone': user_data.get('phone', ''),
                    'depositBalance': user_data.get('depositBalance', 0) or 0,
                    'taskEarnings': user_data.get('taskEarnings', 0) or 0,
                    'points': user_data.get('points', 0) or 0,
                    'referralCount': user_data.get('referralCount', 0) or 0,
                    'referralCode': user_data.get('referralCode', ''),
                    'referredBy': user_data.get('referredBy'),
                    'securityCode': user_data.get('securityCode', ''),
                    'firstDepositCompleted': user_data.get('firstDepositCompleted', False),
                    'status': user_data.get('status', 'active'),
                    'referralLink': f"{request.host_url}?ref={user_data.get('referralCode', uid)}",
                    'totalBalance': (user_data.get('depositBalance', 0) or 0) + (user_data.get('taskEarnings', 0) or 0)
                }
                
                return jsonify({
                    'success': True,
                    'message': 'Login successful',
                    'user': user_response,
                    'referralCode': user_response['referralCode'],
                    'securityCode': user_response['securityCode']
                })
        
        return jsonify({'success': False, 'error': 'Email not found. Please register first.'}), 404
        
    except Exception as e:
        print(f"Error logging in: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: REFERRAL VALIDATION
# ============================================
@app.route('/api/referral/validate/<code>', methods=['GET'])
@app.route('/api/referral/check/<code>', methods=['GET'])
def validate_referral(code):
    try:
        if not code:
            return jsonify({'success': True, 'valid': False, 'message': 'No code provided'})
        
        users = get_all_users()
        
        for uid, user_data in users.items():
            if user_data.get('referralCode') == code:
                return jsonify({
                    'success': True,
                    'valid': True,
                    'referrerId': uid,
                    'referrerName': user_data.get('fullName', user_data.get('firstName', 'User')),
                    'referrerEmail': user_data.get('email', ''),
                    'referralCode': code
                })
        
        user = get_user(code)
        if user:
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': code,
                'referrerName': user.get('fullName', user.get('firstName', 'User')),
                'referrerEmail': user.get('email', ''),
                'referralCode': user.get('referralCode', code)
            })
        
        return jsonify({
            'success': True,
            'valid': False,
            'message': 'Invalid referral code'
        })
        
    except Exception as e:
        print(f"Error validating referral: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: REFERRAL STATS
# ============================================
@app.route('/api/referral/stats/<user_id>', methods=['GET'])
def get_referral_stats(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        all_referrals = get_collection('referrals')
        user_referrals = [r for r in all_referrals if r.get('referrerId') == user_id]
        
        total_referrals = len(user_referrals)
        active_referrals = len([r for r in user_referrals if r.get('status') == 'active'])
        pending_referrals = len([r for r in user_referrals if r.get('status') == 'pending_first_deposit'])
        
        total_bonus = sum(r.get('bonusEarned', 0) or 0 for r in user_referrals)
        total_points = sum(r.get('pointsAwarded', 0) or 0 for r in user_referrals)
        
        referral_link = f"{request.host_url}?ref={user.get('referralCode', user_id)}"
        
        return jsonify({
            'success': True,
            'referralCode': user.get('referralCode'),
            'referralLink': referral_link,
            'stats': {
                'totalReferrals': total_referrals,
                'activeReferrals': active_referrals,
                'pendingReferrals': pending_referrals,
                'totalBonusEarned': total_bonus,
                'totalPointsEarned': total_points,
                'referralBonusPercentage': REFERRAL_BONUS_PERCENTAGE,
                'pointsPerReferral': REFERRAL_POINTS_PERCENTAGE
            },
            'referrals': user_referrals[:20]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/referral/all', methods=['GET'])
def get_all_referrals():
    try:
        referrals = get_collection('referrals')
        referrals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'referrals': referrals, 'total': len(referrals)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: DEPOSIT
# ============================================
@app.route('/api/deposit', methods=['POST'])
def submit_deposit():
    try:
        data = request.json
        user_id = data.get('userId')
        amount = float(data.get('amount', 0))
        method = data.get('method', 'crypto')
        reference = data.get('reference', '')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400
        
        if amount < MIN_DEPOSIT:
            return jsonify({'success': False, 'error': f'Minimum deposit is {MIN_DEPOSIT} USDT'}), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        is_first_deposit = not user.get('firstDepositCompleted', False)
        
        deposit_data = {
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'userName': user.get('fullName', user.get('firstName', 'User')),
            'amount': amount,
            'method': method,
            'reference': reference,
            'status': 'pending',
            'isFirstDeposit': is_first_deposit,
            'referralBonusPaid': False,
            'timestamp': get_timestamp()
        }
        
        deposit_id = add_document('deposits', deposit_data)
        
        add_notification(user_id, 
            f'💰 Deposit of {amount} USDT submitted via {method}. Pending approval.', 
            'deposit',
            {'amount': amount, 'method': method})
        
        print(f"📥 New deposit: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit submitted successfully. Waiting for approval.',
            'deposit': {**deposit_data, 'id': deposit_id},
            'isFirstDeposit': is_first_deposit
        }), 201
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    except Exception as e:
        print(f"Error submitting deposit: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/deposit/<user_id>', methods=['GET'])
def get_user_deposits(user_id):
    try:
        deposits = get_collection('deposits')
        user_deposits = [d for d in deposits if d.get('userId') == user_id]
        user_deposits.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        user = get_user(user_id)
        return jsonify({
            'success': True,
            'deposits': user_deposits[:20],
            'firstDepositCompleted': user.get('firstDepositCompleted', False) if user else False
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/deposit/all', methods=['GET'])
def get_all_deposits():
    try:
        deposits = get_collection('deposits')
        deposits.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'deposits': deposits, 'total': len(deposits)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/approve', methods=['POST'])
def approve_deposit(deposit_id):
    try:
        deposits = get_collection('deposits')
        deposit = next((d for d in deposits if d.get('id') == deposit_id), None)
        
        if not deposit:
            return jsonify({'success': False, 'error': 'Deposit not found'}), 404
        
        user_id = deposit.get('userId')
        amount = deposit.get('amount', 0)
        is_first_deposit = deposit.get('isFirstDeposit', False)
        
        update_document('deposits', deposit_id, {
            'status': 'approved',
            'approvedAt': get_timestamp()
        })
        
        user = get_user(user_id)
        if user:
            current_balance = user.get('depositBalance', 0) or 0
            update_data = {
                'depositBalance': current_balance + amount
            }
            
            if is_first_deposit and not user.get('firstDepositCompleted', False):
                update_data['firstDepositCompleted'] = True
                
                referred_by = user.get('referredBy')
                if referred_by:
                    referrer = get_user(referred_by)
                    if referrer:
                        bonus_amount = calculate_referral_bonus(amount)
                        points_awarded = round(amount * REFERRAL_POINTS_PERCENTAGE / 100, 2)
                        
                        ref_deposit_balance = referrer.get('depositBalance', 0) or 0
                        ref_bonus = referrer.get('referralBonus', 0) or 0
                        ref_points = referrer.get('points', 0) or 0
                        ref_total_points = referrer.get('totalReferralPoints', 0) or 0
                        
                        save_user(referred_by, {
                            'depositBalance': ref_deposit_balance + bonus_amount,
                            'referralBonus': ref_bonus + bonus_amount,
                            'totalReferralPoints': ref_total_points + points_awarded,
                            'points': ref_points + points_awarded
                        })
                        
                        all_referrals = get_collection('referrals')
                        for ref in all_referrals:
                            if ref.get('referrerId') == referred_by and ref.get('referredUserId') == user_id:
                                update_document('referrals', ref['id'], {
                                    'status': 'active',
                                    'bonusEarned': bonus_amount,
                                    'pointsAwarded': points_awarded,
                                    'firstDepositDate': get_timestamp()
                                })
                                break
                        
                        add_notification(referred_by,
                            f"🎉 Referral Bonus! {user.get('fullName', 'User')} deposited ${amount}. You earned ${bonus_amount} + {points_awarded} points!",
                            'referral_bonus',
                            {'amount': bonus_amount, 'points': points_awarded})
                
                user_points = user.get('points', 0) or 0
                update_data['points'] = user_points + 0.5
                
                add_notification(user_id,
                    "🎁 Welcome Bonus! You earned 0.5 points for your first deposit!",
                    'welcome_bonus',
                    {'points': 0.5})
            
            save_user(user_id, update_data)
        
        add_notification(user_id,
            f'✅ Deposit of {amount} USDT approved! Funds added to your balance.',
            'deposit_approved',
            {'amount': amount})
        
        print(f"✅ Deposit approved: {deposit_id} - {amount} USDT from {user_id}")
        
        return jsonify({'success': True, 'message': 'Deposit approved successfully'})
        
    except Exception as e:
        print(f"Error approving deposit: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/reject', methods=['POST'])
def reject_deposit(deposit_id):
    try:
        update_document('deposits', deposit_id, {
            'status': 'rejected',
            'rejectedAt': get_timestamp()
        })
        
        deposits = get_collection('deposits')
        deposit = next((d for d in deposits if d.get('id') == deposit_id), None)
        
        if deposit:
            add_notification(deposit.get('userId'),
                f'❌ Deposit of {deposit.get("amount", 0)} USDT rejected.',
                'deposit_rejected')
        
        print(f"❌ Deposit rejected: {deposit_id}")
        
        return jsonify({'success': True, 'message': 'Deposit rejected'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: WITHDRAWAL (WITH 10% POINTS FEE)
# ============================================
@app.route('/api/withdraw', methods=['POST'])
def submit_withdrawal():
    try:
        data = request.json
        user_id = data.get('userId')
        amount = float(data.get('amount', 0))
        method = data.get('method', 'telebirr')
        details = data.get('details', {})
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400
        
        if amount < MIN_WITHDRAW:
            return jsonify({'success': False, 'error': f'Minimum withdrawal is {MIN_WITHDRAW} USDT'}), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # ============================================
        # CHECK 10% POINTS FEE REQUIREMENT
        # ============================================
        points_fee = calculate_withdraw_points_fee(amount)
        user_points = user.get('points', 0) or 0
        
        if user_points < points_fee:
            return jsonify({
                'success': False,
                'error': f'Insufficient points for withdrawal fee',
                'details': {
                    'requiredPoints': points_fee,
                    'yourPoints': user_points,
                    'missingPoints': round(points_fee - user_points, 2),
                    'feePercentage': WITHDRAW_POINTS_FEE_PERCENTAGE,
                    'withdrawalAmount': amount,
                    'message': f'You need {points_fee} points for the {WITHDRAW_POINTS_FEE_PERCENTAGE}% withdrawal fee. You only have {user_points} points. Earn points through referrals and daily claims!'
                }
            }), 400
        
        # Check total balance
        total_balance = (user.get('depositBalance', 0) or 0) + (user.get('taskEarnings', 0) or 0)
        if amount > total_balance:
            return jsonify({'success': False, 'error': 'Insufficient balance'}), 400
        
        # Deduct from task earnings first, then deposit balance
        task_earnings = user.get('taskEarnings', 0) or 0
        deposit_balance = user.get('depositBalance', 0) or 0
        
        if task_earnings >= amount:
            new_task_earnings = task_earnings - amount
            new_deposit_balance = deposit_balance
        else:
            remaining = amount - task_earnings
            new_task_earnings = 0
            new_deposit_balance = deposit_balance - remaining
        
        # Deduct points fee
        new_points = user_points - points_fee
        
        # Update user balances
        save_user(user_id, {
            'taskEarnings': new_task_earnings,
            'depositBalance': new_deposit_balance,
            'points': new_points
        })
        
        if isinstance(details, dict):
            details_str = json.dumps(details)
        else:
            details_str = str(details)
        
        withdrawal_data = {
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'userName': user.get('fullName', user.get('firstName', 'User')),
            'amount': amount,
            'method': method,
            'details': details_str,
            'status': 'pending',
            'pointsFee': points_fee,
            'pointsFeePercentage': WITHDRAW_POINTS_FEE_PERCENTAGE,
            'timestamp': get_timestamp()
        }
        
        withdrawal_id = add_document('withdrawals', withdrawal_data)
        
        # Log the points fee deduction
        points_log_data = {
            'userId': user_id,
            'type': 'withdrawal_fee',
            'amount': -points_fee,
            'withdrawalId': withdrawal_id,
            'withdrawalAmount': amount,
            'description': f'{WITHDRAW_POINTS_FEE_PERCENTAGE}% points fee for {amount} USDT withdrawal',
            'timestamp': get_timestamp()
        }
        add_document('points_logs', points_log_data)
        
        add_notification(user_id,
            f'💸 Withdrawal of {amount} USDT submitted via {method}. {WITHDRAW_POINTS_FEE_PERCENTAGE}% points fee ({points_fee} points) deducted. Pending approval.',
            'withdrawal',
            {'amount': amount, 'method': method, 'pointsFee': points_fee})
        
        print(f"💸 New withdrawal: {amount} USDT from {user_id} via {method} | Points fee: {points_fee} | Remaining points: {new_points}")
        
        return jsonify({
            'success': True,
            'message': f'Withdrawal submitted successfully. {points_fee} points deducted as {WITHDRAW_POINTS_FEE_PERCENTAGE}% fee. Waiting for approval.',
            'withdrawal': {**withdrawal_data, 'id': withdrawal_id},
            'pointsDeducted': points_fee,
            'remainingPoints': new_points
        }), 201
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid amount'}), 400
    except Exception as e:
        print(f"Error submitting withdrawal: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/withdraw/<user_id>', methods=['GET'])
def get_user_withdrawals(user_id):
    try:
        withdrawals = get_collection('withdrawals')
        user_withdrawals = [w for w in withdrawals if w.get('userId') == user_id]
        user_withdrawals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'withdrawals': user_withdrawals[:20]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/withdraw/all', methods=['GET'])
def get_all_withdrawals():
    try:
        withdrawals = get_collection('withdrawals')
        withdrawals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'withdrawals': withdrawals, 'total': len(withdrawals)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/approve', methods=['POST'])
def approve_withdrawal(withdrawal_id):
    try:
        update_document('withdrawals', withdrawal_id, {
            'status': 'completed',
            'completedAt': get_timestamp()
        })
        
        withdrawals = get_collection('withdrawals')
        withdrawal = next((w for w in withdrawals if w.get('id') == withdrawal_id), None)
        
        if withdrawal:
            add_notification(withdrawal.get('userId'),
                f'✅ Withdrawal of {withdrawal.get("amount", 0)} USDT approved!',
                'withdrawal_approved',
                {'amount': withdrawal.get('amount', 0)})
        
        print(f"✅ Withdrawal approved: {withdrawal_id}")
        
        return jsonify({'success': True, 'message': 'Withdrawal approved successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/reject', methods=['POST'])
def reject_withdrawal(withdrawal_id):
    try:
        withdrawals = get_collection('withdrawals')
        withdrawal = next((w for w in withdrawals if w.get('id') == withdrawal_id), None)
        
        if withdrawal:
            user = get_user(withdrawal.get('userId'))
            if user:
                # Refund the amount
                current_balance = user.get('depositBalance', 0) or 0
                refund_amount = withdrawal.get('amount', 0)
                
                # Refund points fee
                points_fee = withdrawal.get('pointsFee', 0) or 0
                current_points = user.get('points', 0) or 0
                
                save_user(withdrawal.get('userId'), {
                    'depositBalance': current_balance + refund_amount,
                    'points': current_points + points_fee
                })
                
                # Log points refund
                points_log_data = {
                    'userId': withdrawal.get('userId'),
                    'type': 'withdrawal_fee_refund',
                    'amount': points_fee,
                    'withdrawalId': withdrawal_id,
                    'description': f'Points fee refunded for rejected withdrawal',
                    'timestamp': get_timestamp()
                }
                add_document('points_logs', points_log_data)
            
            add_notification(withdrawal.get('userId'),
                f'❌ Withdrawal of {withdrawal.get("amount", 0)} USDT rejected. Amount and {withdrawal.get("pointsFee", 0)} points refunded.',
                'withdrawal_rejected',
                {'amount': withdrawal.get('amount', 0)})
        
        update_document('withdrawals', withdrawal_id, {
            'status': 'rejected',
            'rejectedAt': get_timestamp()
        })
        
        print(f"❌ Withdrawal rejected: {withdrawal_id} - Amount and points refunded")
        
        return jsonify({'success': True, 'message': 'Withdrawal rejected - Amount and points refunded'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: POINTS LOGS
# ============================================
@app.route('/api/points/logs/<user_id>', methods=['GET'])
def get_points_logs(user_id):
    try:
        logs = get_collection('points_logs')
        user_logs = [l for l in logs if l.get('userId') == user_id]
        user_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'logs': user_logs[:50]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: PRODUCTS & INVESTMENTS
# ============================================
@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify({'success': True, 'products': PRODUCTS})

@app.route('/api/investment/buy', methods=['POST'])
def buy_investment():
    try:
        data = request.json
        user_id = data.get('userId')
        product_name = data.get('productName')
        
        product = next((p for p in PRODUCTS if p['name'] == product_name), None)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found'}), 404
        
        user = get_user(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404        
        
        user_balance = user.get('depositBalance', 0) or 0
        if user_balance < product['price']:
            return jsonify({'success': False, 'error': 'Insufficient deposit balance'}), 400
        
        save_user(user_id, {
            'depositBalance': user_balance - product['price']
        })
        
        investment_data = {
            'userId': user_id,
            'productName': product['name'],
            'amount': product['price'],
            'dailyEarnings': product['dailyEarnings'],
            'duration': product['duration'],
            'isFixed': product['isFixed'],
            'totalEarned': 0.0,
            'status': 'active',
            'purchaseDate': get_timestamp(),
            'lastClaimDate': get_timestamp(),
            'timestamp': get_timestamp()
        }
        
        investment_id = add_document('investments', investment_data)
        
        add_notification(user_id,
            f'🎯 Investment purchased: {product_name} for ${product["price"]}',
            'investment',
            {'productName': product_name, 'amount': product['price']})
        
        return jsonify({
            'success': True,
            'message': f'Successfully purchased {product_name}',
            'investment': {**investment_data, 'id': investment_id}
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/investment/<user_id>', methods=['GET'])
def get_user_investments(user_id):
    try:
        investments = get_collection('investments')
        user_investments = [i for i in investments if i.get('userId') == user_id]
        active_investments = [i for i in user_investments if i.get('status') == 'active']
        
        for inv in active_investments:
            try:
                purchase_date = datetime.fromisoformat(inv.get('purchaseDate', get_timestamp()).replace('Z', '+00:00'))
                days_elapsed = (datetime.utcnow() - purchase_date.replace(tzinfo=None)).days
                inv['daysLeft'] = max(0, inv.get('duration', 120) - days_elapsed)
                inv['progress'] = min(100, round((days_elapsed / inv.get('duration', 120)) * 100, 1))
            except:
                inv['daysLeft'] = inv.get('duration', 120)
                inv['progress'] = 0
        
        return jsonify({'success': True, 'investments': active_investments})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: DAILY CLAIMS
# ============================================
@app.route('/api/daily/claim', methods=['POST'])
def claim_daily():
    try:
        data = request.json
        user_id = data.get('userId')
        investment_id = data.get('investmentId')
        
        if not user_id or not investment_id:
            return jsonify({'success': False, 'error': 'User ID and Investment ID required'}), 400
        
        if is_weekend():
            return jsonify({'success': False, 'error': 'Cannot claim on weekends', 'isWeekend': True}), 403
        
        investments = get_collection('investments')
        investment = next((i for i in investments if i.get('id') == investment_id), None)
        
        if not investment:
            return jsonify({'success': False, 'error': 'Investment not found'}), 404
        
        if investment.get('status') != 'active':
            return jsonify({'success': False, 'error': 'Investment is not active'}), 400
        
        if investment.get('isFixed'):
            earnings = float(investment.get('dailyEarnings', 0))
        else:
            earnings = (float(investment.get('amount', 0)) * float(investment.get('dailyEarnings', 0))) / 100
        
        total_earned = (investment.get('totalEarned', 0) or 0) + earnings
        update_document('investments', investment_id, {
            'totalEarned': total_earned,
            'lastClaimDate': get_timestamp()
        })
        
        user = get_user(user_id)
        if user:
            current_earnings = user.get('taskEarnings', 0) or 0
            save_user(user_id, {
                'taskEarnings': current_earnings + earnings
            })
        
        return jsonify({
            'success': True,
            'message': f'Claimed {earnings:.2f} USDT',
            'earnings': round(earnings, 2),
            'totalEarned': round(total_earned, 2)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily/check/<user_id>', methods=['GET'])
def check_daily(user_id):
    try:
        if is_weekend():
            return jsonify({
                'success': True,
                'canClaim': False, 
                'reason': 'Weekend - No claims allowed on Saturday and Sunday', 
                'isWeekend': True
            })
        return jsonify({
            'success': True,
            'canClaim': True, 
            'isWeekend': False
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: NOTIFICATIONS
# ============================================
@app.route('/api/notifications/<user_id>', methods=['GET'])
def get_user_notifications(user_id):
    try:
        notifications = get_collection('notifications')
        user_notifications = [n for n in notifications if n.get('userId') == user_id]
        user_notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        unread_count = len([n for n in user_notifications if not n.get('read', False)])
        
        return jsonify({
            'success': True,
            'notifications': user_notifications[:50],
            'unreadCount': unread_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_read():
    try:
        data = request.json
        user_id = data.get('userId')
        
        notifications = get_collection('notifications')
        user_notifications = [n for n in notifications if n.get('userId') == user_id]
        
        count = 0
        for notif in user_notifications:
            if not notif.get('read', False):
                update_document('notifications', notif['id'], {'read': True})
                count += 1
        
        return jsonify({'success': True, 'message': f'{count} notifications marked as read'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: SECURITY
# ============================================
@app.route('/api/security/<user_id>', methods=['GET'])
def get_security_code(user_id):
    try:
        user = get_user(user_id)
        if user and user.get('securityCode'):
            return jsonify({'success': True, 'code': user['securityCode']})
        
        new_code = generate_security_code()
        save_user(user_id, {'securityCode': new_code})
        return jsonify({'success': True, 'code': new_code})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/security/reset', methods=['POST'])
def reset_security():
    try:
        data = request.json
        user_id = data.get('userId')
        new_code = generate_security_code()
        save_user(user_id, {'securityCode': new_code})
        return jsonify({'success': True, 'newCode': new_code})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API: ADMIN STATS
# ============================================
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    try:
        users = get_all_users()
        deposits = get_collection('deposits')
        withdrawals = get_collection('withdrawals')
        referrals = get_collection('referrals')
        investments = get_collection('investments')
        
        approved_deposits = sum(d.get('amount', 0) or 0 for d in deposits if d.get('status') == 'approved')
        completed_withdrawals = sum(w.get('amount', 0) or 0 for w in withdrawals if w.get('status') == 'completed')
        active_investments = len([i for i in investments if i.get('status') == 'active'])
        pending_deposits = len([d for d in deposits if d.get('status') == 'pending'])
        pending_withdrawals = len([w for w in withdrawals if w.get('status') == 'pending'])
        
        total_points_fees = sum(w.get('pointsFee', 0) or 0 for w in withdrawals if w.get('status') == 'completed')
        
        return jsonify({
            'success': True,
            'stats': {
                'totalUsers': len(users),
                'totalDeposits': approved_deposits,
                'totalWithdrawals': completed_withdrawals,
                'activeInvestments': active_investments,
                'totalReferrals': len(referrals),
                'pendingDeposits': pending_deposits,
                'pendingWithdrawals': pending_withdrawals,
                'totalPointsFeesCollected': total_points_fees,
                'withdrawPointsFeePercentage': WITHDRAW_POINTS_FEE_PERCENTAGE
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# ERROR HANDLERS
# ============================================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    return send_from_directory('.', 'index.html')

@app.errorhandler(500)
def server_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 SAFE Platform v3.1 - Firebase REST API")
    print(f"📍 Port: {port}")
    print(f"🗄️  Database: Firebase Firestore + RTDB (REST API)")
    print(f"📱 Telebirr: {TELEBIRR_NUMBER} ({TELEBIRR_NAME})")
    print(f"💎 Wallet: {WALLET_ADDRESS}")
    print(f"👥 Referral Bonus: {REFERRAL_BONUS_PERCENTAGE}%")
    print(f"💰 Min Deposit: ${MIN_DEPOSIT} | Min Withdraw: ${MIN_WITHDRAW}")
    print(f"🔒 Withdraw Points Fee: {WITHDRAW_POINTS_FEE_PERCENTAGE}%")
    print("=" * 60)
    print("📡 All API Endpoints Ready:")
    print("   ✅ POST /api/user/create")
    print("   ✅ POST /api/user/login")
    print("   ✅ GET  /api/user/<id>")
    print("   ✅ POST /api/user/<id>/update")
    print("   ✅ GET  /api/users/all")
    print("   ✅ POST /api/deposit")
    print("   ✅ GET  /api/deposit/all")
    print("   ✅ POST /api/deposit/<id>/approve")
    print("   ✅ POST /api/deposit/<id>/reject")
    print("   ✅ POST /api/withdraw (10% points fee)")
    print("   ✅ GET  /api/withdraw/all")
    print("   ✅ POST /api/withdraw/<id>/approve")
    print("   ✅ POST /api/withdraw/<id>/reject (refunds points)")
    print("   ✅ GET  /api/points/logs/<user_id>")
    print("   ✅ GET  /api/referral/all")
    print("   ✅ GET  /api/referral/check/<code>")
    print("   ✅ GET  /api/referral/stats/<id>")
    print("   ✅ GET  /api/products")
    print("   ✅ POST /api/investment/buy")
    print("   ✅ GET  /api/investment/<id>")
    print("   ✅ POST /api/daily/claim")
    print("   ✅ GET  /api/notifications/<id>")
    print("   ✅ POST /api/notifications/read-all")
    print("   ✅ GET  /api/security/<id>")
    print("   ✅ GET  /api/admin/stats")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=True)
