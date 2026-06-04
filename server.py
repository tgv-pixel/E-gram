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
WALLET_ADDRESS = 'TK3RviHLX31oC6qNdfaF9Wuh8JJ4bQqAXu'
REFERRAL_BONUS_PERCENTAGE = 10
REFERRAL_POINTS = 0.1
MIN_DEPOSIT = 10
MIN_WITHDRAW = 20
MAX_WITHDRAW_DAILY = 500
WEEKEND_DAYS = [5, 6]

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
            print(f"Firestore API Error: {response.status_code} - {response.text}")
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
    """Get user from Firestore"""
    result = firestore_request('GET', f'users/{user_id}')
    if result and 'fields' in result:
        return firestore_to_dict(result['fields'])
    return None

def save_user(user_id, user_data):
    """Save/Update user in Firestore"""
    firestore_data = dict_to_firestore(user_data)
    
    # Remove userId from data if present (it's the document ID)
    if 'userId' in firestore_data:
        del firestore_data['userId']
    
    # Check if user exists
    existing = get_user(user_id)
    if existing:
        # Update
        result = firestore_request('PATCH', f'users/{user_id}', {'fields': firestore_data})
    else:
        # Create
        result = firestore_request('PATCH', f'users/{user_id}', {'fields': firestore_data})
    
    # Also save basic info to RTDB for quick access
    rtdb_data = {
        'email': user_data.get('email', ''),
        'fullName': user_data.get('fullName', ''),
        'referralCode': user_data.get('referralCode', ''),
        'referredBy': user_data.get('referredBy'),
        'status': user_data.get('status', 'active'),
        'depositBalance': user_data.get('depositBalance', 0)
    }
    rtdb_request('PUT', f'users/{user_id}', rtdb_data)
    
    return result is not None

def get_all_users():
    """Get all users from Firestore"""
    result = firestore_request('GET', 'users')
    if result and 'documents' in result:
        users = {}
        for doc in result['documents']:
            user_id = doc['name'].split('/')[-1]
            users[user_id] = firestore_to_dict(doc.get('fields', {}))
        return users
    return {}

def add_document(collection, data, doc_id=None):
    """Add document to Firestore collection"""
    if doc_id:
        path = f'{collection}/{doc_id}'
        result = firestore_request('PATCH', path, {'fields': dict_to_firestore(data)})
        return doc_id if result else None
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
            
            # Apply filters (basic)
            if filters:
                skip = False
                for key, value in filters.items():
                    if key in data:
                        if isinstance(data[key], dict):
                            actual_value = data[key].get('stringValue') or data[key].get('integerValue')
                        else:
                            actual_value = data[key]
                        if actual_value != value:
                            skip = True
                            break
                if skip:
                    continue
            docs.append(data)
        return docs
    return []

def update_document(collection, doc_id, update_data):
    """Update document in Firestore"""
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
    
    # Also save to RTDB for real-time updates
    rtdb_request('PUT', f'notifications/{user_id}/{doc_id}', notif_data)

# ============================================
# DATA CONVERSION HELPERS
# ============================================
def firestore_to_dict(fields):
    """Convert Firestore fields to Python dict"""
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
            result[key] = [
                firestore_to_dict(v.get('mapValue', {}).get('fields', {})) 
                if 'mapValue' in v else v.get('stringValue', v.get('integerValue', ''))
                for v in value['arrayValue'].get('values', [])
            ]
        else:
            result[key] = value
    return result

def dict_to_firestore(data):
    """Convert Python dict to Firestore format"""
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
            result[key] = {
                'arrayValue': {
                    'values': [{'stringValue': str(v)} if not isinstance(v, dict) 
                              else {'mapValue': {'fields': dict_to_firestore(v)}} 
                              for v in value]
                }
            }
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
    if not '.' in path:
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
        'referral_points': REFERRAL_POINTS,
        'min_deposit': MIN_DEPOSIT,
        'min_withdraw': MIN_WITHDRAW
    })

# ============================================
# API: USER MANAGEMENT
# ============================================
@app.route('/api/user/create', methods=['POST'])
def create_user():
    try:
        data = request.json
        user_id = data.get('userId')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # Check if user exists
        existing = get_user(user_id)
        if existing:
            return jsonify({'error': 'User already exists'}), 409
        
        referral_code = generate_referral_code()
        security_code = generate_security_code()
        
        user_data = {
            'userId': user_id,
            'email': data.get('email', ''),
            'fullName': data.get('fullName', ''),
            'firstName': data.get('firstName', data.get('fullName', '').split(' ')[0] if data.get('fullName') else ''),
            'lastName': data.get('lastName', ''),
            'phone': data.get('phone', ''),
            'referralCode': referral_code,
            'referredBy': data.get('referredBy', None),
            'referredByName': data.get('referredByName', None),
            'depositBalance': 0.0,
            'taskEarnings': 0.0,
            'points': 0,
            'referralCount': 0,
            'referralBonus': 0.0,
            'totalReferralPoints': 0,
            'firstDepositCompleted': False,
            'status': 'active',
            'securityCode': security_code,
            'createdAt': get_timestamp(),
            'lastLogin': None
        }
        
        # Save to Firestore
        if save_user(user_id, user_data):
            # Handle referral
            referred_by = data.get('referredBy')
            if referred_by:
                referrer = get_user(referred_by)
                if referrer:
                    # Create referral record
                    referral_data = {
                        'referrerId': referred_by,
                        'referredUserId': user_id,
                        'referredEmail': data.get('email', ''),
                        'referredName': data.get('fullName', ''),
                        'bonusEarned': 0,
                        'pointsAwarded': 0,
                        'status': 'pending_first_deposit',
                        'timestamp': get_timestamp()
                    }
                    add_document('referrals', referral_data)
                    
                    # Update referrer count
                    current_count = referrer.get('referralCount', 0)
                    save_user(referred_by, {'referralCount': current_count + 1})
                    
                    # Notify referrer
                    add_notification(referred_by, 
                        f"🎉 {data.get('fullName', 'New user')} joined using your referral link!", 
                        'referral_signup',
                        {'referredUserId': user_id, 'referredName': data.get('fullName', '')})
            
            return jsonify({
                'success': True,
                'message': 'User created successfully',
                'referralCode': referral_code,
                'securityCode': security_code
            }), 201
        
        return jsonify({'error': 'Failed to create user'}), 500
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user_api(user_id):
    try:
        user = get_user(user_id)
        if user:
            user['referralLink'] = f"{request.host_url}?ref={user.get('referralCode', user_id)}"
            user['totalBalance'] = user.get('depositBalance', 0) + user.get('taskEarnings', 0)
            return jsonify({'success': True, 'user': user})
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>/balance', methods=['GET'])
def get_user_balance(user_id):
    try:
        user = get_user(user_id)
        if user:
            return jsonify({
                'success': True,
                'depositBalance': user.get('depositBalance', 0),
                'taskEarnings': user.get('taskEarnings', 0),
                'totalBalance': user.get('depositBalance', 0) + user.get('taskEarnings', 0),
                'points': user.get('points', 0),
                'referralBonus': user.get('referralBonus', 0)
            })
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/all', methods=['GET'])
def get_all_users_api():
    try:
        users = get_all_users()
        users_list = []
        for uid, data in users.items():
            users_list.append({
                'userId': uid,
                'email': data.get('email', ''),
                'fullName': data.get('fullName', ''),
                'depositBalance': data.get('depositBalance', 0),
                'taskEarnings': data.get('taskEarnings', 0),
                'referralCount': data.get('referralCount', 0),
                'status': data.get('status', 'active'),
                'createdAt': data.get('createdAt', '')
            })
        return jsonify({'success': True, 'users': users_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: REFERRAL VALIDATION
# ============================================
@app.route('/api/referral/validate/<code>', methods=['GET'])
@app.route('/api/referral/check/<code>', methods=['GET'])
def validate_referral(code):
    try:
        # Search all users for matching referral code
        users = get_all_users()
        
        for uid, user_data in users.items():
            if user_data.get('referralCode') == code:
                return jsonify({
                    'success': True,
                    'valid': True,
                    'referrerId': uid,
                    'referrerName': user_data.get('firstName', user_data.get('fullName', 'User')),
                    'referrerEmail': user_data.get('email', ''),
                    'referralCode': code
                })
        
        # Also check if code is a user ID
        user = get_user(code)
        if user:
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': code,
                'referrerName': user.get('firstName', user.get('fullName', 'User')),
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
        return jsonify({'error': str(e)}), 500

# ============================================
# API: REFERRAL STATS
# ============================================
@app.route('/api/referral/stats/<user_id>', methods=['GET'])
def get_referral_stats(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get all referrals for this user
        all_referrals = get_collection('referrals', {'referrerId': user_id})
        
        total_referrals = len(all_referrals)
        active_referrals = len([r for r in all_referrals if r.get('status') == 'active'])
        pending_referrals = len([r for r in all_referrals if r.get('status') == 'pending_first_deposit'])
        
        # Calculate bonuses
        total_bonus = sum(r.get('bonusEarned', 0) for r in all_referrals)
        total_points = sum(r.get('pointsAwarded', 0) for r in all_referrals)
        
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
                'pointsPerReferral': REFERRAL_POINTS
            },
            'referrals': all_referrals[:10]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            return jsonify({'error': 'User ID required'}), 400
        
        if amount < MIN_DEPOSIT:
            return jsonify({'error': f'Minimum deposit is {MIN_DEPOSIT} USDT'}), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        is_first_deposit = not user.get('firstDepositCompleted', False)
        
        deposit_data = {
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'userName': user.get('fullName', ''),
            'amount': amount,
            'method': method,
            'reference': reference,
            'status': 'pending',
            'isFirstDeposit': is_first_deposit,
            'referralBonusPaid': False,
            'timestamp': get_timestamp()
        }
        
        deposit_id = add_document('deposits', deposit_data)
        
        # Notify user
        add_notification(user_id, 
            f'Deposit of {amount} USDT submitted. Pending approval.', 
            'deposit',
            {'amount': amount})
        
        print(f"📥 New deposit: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit submitted',
            'deposit': {**deposit_data, 'id': deposit_id},
            'isFirstDeposit': is_first_deposit
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<user_id>', methods=['GET'])
def get_deposits(user_id):
    try:
        deposits = get_collection('deposits', {'userId': user_id})
        # Sort by timestamp descending
        deposits.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        user = get_user(user_id)
        return jsonify({
            'success': True,
            'deposits': deposits[:20],
            'firstDepositCompleted': user.get('firstDepositCompleted', False) if user else False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/all', methods=['GET'])
def get_all_deposits():
    try:
        deposits = get_collection('deposits')
        deposits.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'deposits': deposits})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/approve', methods=['POST'])
def approve_deposit(deposit_id):
    try:
        # Get deposit
        deposits = get_collection('deposits')
        deposit = next((d for d in deposits if d.get('id') == deposit_id), None)
        
        if not deposit:
            return jsonify({'error': 'Deposit not found'}), 404
        
        user_id = deposit['userId']
        amount = deposit['amount']
        is_first_deposit = deposit.get('isFirstDeposit', False)
        
        # Update deposit status
        update_document('deposits', deposit_id, {
            'status': 'approved',
            'approvedAt': get_timestamp()
        })
        
        # Update user balance
        user = get_user(user_id)
        if user:
            current_balance = user.get('depositBalance', 0)
            update_data = {
                'depositBalance': current_balance + amount
            }
            
            if is_first_deposit and not user.get('firstDepositCompleted', False):
                update_data['firstDepositCompleted'] = True
                
                # Process referral bonus
                referred_by = user.get('referredBy')
                if referred_by:
                    referrer = get_user(referred_by)
                    if referrer:
                        bonus_amount = calculate_referral_bonus(amount)
                        points_awarded = REFERRAL_POINTS
                        
                        # Update referrer
                        save_user(referred_by, {
                            'depositBalance': referrer.get('depositBalance', 0) + bonus_amount,
                            'referralBonus': referrer.get('referralBonus', 0) + bonus_amount,
                            'totalReferralPoints': referrer.get('totalReferralPoints', 0) + points_awarded,
                            'points': referrer.get('points', 0) + points_awarded
                        })
                        
                        # Update referral record
                        referrals = get_collection('referrals', {'referrerId': referred_by})
                        for ref in referrals:
                            if ref.get('referredUserId') == user_id:
                                update_document('referrals', ref['id'], {
                                    'status': 'active',
                                    'bonusEarned': bonus_amount,
                                    'pointsAwarded': points_awarded,
                                    'firstDepositDate': get_timestamp()
                                })
                        
                        # Notifications
                        add_notification(referred_by,
                            f"🎉 Referral Bonus! {user.get('fullName', 'User')} deposited ${amount}. You earned ${bonus_amount} + {points_awarded} points!",
                            'referral_bonus',
                            {'amount': bonus_amount, 'points': points_awarded})
                        
                        # Welcome bonus for new user
                        update_data['points'] = user.get('points', 0) + 0.5
                        
                        add_notification(user_id,
                            "🎁 Welcome Bonus! You earned 0.5 points for your first deposit!",
                            'welcome_bonus',
                            {'points': 0.5})
            
            save_user(user_id, update_data)
        
        # Notify user
        add_notification(user_id,
            f'✅ Deposit of {amount} USDT approved!',
            'deposit_approved',
            {'amount': amount})
        
        print(f"✅ Deposit approved: {deposit_id} - {amount} USDT")
        
        return jsonify({'success': True, 'message': 'Deposit approved'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            add_notification(deposit['userId'],
                f'❌ Deposit of {deposit["amount"]} USDT rejected.',
                'deposit_rejected')
        
        print(f"❌ Deposit rejected: {deposit_id}")
        
        return jsonify({'success': True, 'message': 'Deposit rejected'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: WITHDRAWAL
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
            return jsonify({'error': 'User ID required'}), 400
        
        if amount < MIN_WITHDRAW:
            return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAW} USDT'}), 400
        
        user = get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        total_balance = user.get('depositBalance', 0) + user.get('taskEarnings', 0)
        if amount > total_balance:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Deduct from balance
        task_earnings = user.get('taskEarnings', 0)
        deposit_balance = user.get('depositBalance', 0)
        
        if task_earnings >= amount:
            save_user(user_id, {'taskEarnings': task_earnings - amount})
        else:
            remaining = amount - task_earnings
            save_user(user_id, {
                'taskEarnings': 0,
                'depositBalance': deposit_balance - remaining
            })
        
        withdrawal_data = {
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'userName': user.get('fullName', ''),
            'amount': amount,
            'method': method,
            'details': str(details),
            'status': 'pending',
            'timestamp': get_timestamp()
        }
        
        withdrawal_id = add_document('withdrawals', withdrawal_data)
        
        add_notification(user_id,
            f'Withdrawal of {amount} USDT submitted.',
            'withdrawal',
            {'amount': amount})
        
        print(f"💸 New withdrawal: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal submitted',
            'withdrawal': {**withdrawal_data, 'id': withdrawal_id}
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<user_id>', methods=['GET'])
def get_withdrawals(user_id):
    try:
        withdrawals = get_collection('withdrawals', {'userId': user_id})
        withdrawals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'withdrawals': withdrawals[:20]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            add_notification(withdrawal['userId'],
                f'✅ Withdrawal of {withdrawal["amount"]} USDT approved!',
                'withdrawal_approved')
        
        print(f"✅ Withdrawal approved: {withdrawal_id}")
        
        return jsonify({'success': True, 'message': 'Withdrawal approved'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/reject', methods=['POST'])
def reject_withdrawal(withdrawal_id):
    try:
        withdrawals = get_collection('withdrawals')
        withdrawal = next((w for w in withdrawals if w.get('id') == withdrawal_id), None)
        
        if withdrawal:
            # Refund amount
            user = get_user(withdrawal['userId'])
            if user:
                save_user(withdrawal['userId'], {
                    'depositBalance': user.get('depositBalance', 0) + withdrawal['amount']
                })
            
            add_notification(withdrawal['userId'],
                f'❌ Withdrawal of {withdrawal["amount"]} USDT rejected. Amount refunded.',
                'withdrawal_rejected')
        
        update_document('withdrawals', withdrawal_id, {
            'status': 'rejected',
            'rejectedAt': get_timestamp()
        })
        
        print(f"❌ Withdrawal rejected: {withdrawal_id}")
        
        return jsonify({'success': True, 'message': 'Withdrawal rejected'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            return jsonify({'error': 'Product not found'}), 404
        
        user = get_user(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404        
        if user.get('depositBalance', 0) < product['price']:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Deduct balance
        save_user(user_id, {
            'depositBalance': user.get('depositBalance', 0) - product['price']
        })
        
        investment_data = {
            'userId': user_id,
            'productName': product['name'],
            'amount': product['price'],
            'dailyEarnings': product['dailyEarnings'],
            'duration': product['duration'],
            'isFixed': product['isFixed'],
            'totalEarned': 0,
            'status': 'active',
            'purchaseDate': get_timestamp(),
            'lastClaimDate': get_timestamp(),
            'timestamp': get_timestamp()
        }
        
        investment_id = add_document('investments', investment_data)
        
        return jsonify({
            'success': True,
            'message': f'Purchased {product_name}',
            'investment': {**investment_data, 'id': investment_id}
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/investment/<user_id>', methods=['GET'])
def get_investments(user_id):
    try:
        investments = get_collection('investments', {'userId': user_id})
        active_investments = [i for i in investments if i.get('status') == 'active']
        
        for inv in active_investments:
            purchase_date = datetime.fromisoformat(inv.get('purchaseDate', get_timestamp()))
            days_elapsed = (datetime.now() - purchase_date).days
            inv['daysLeft'] = max(0, inv.get('duration', 120) - days_elapsed)
            inv['progress'] = min(100, (days_elapsed / inv.get('duration', 120)) * 100)
        
        return jsonify({'success': True, 'investments': active_investments})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            return jsonify({'error': 'User ID and Investment ID required'}), 400
        
        if is_weekend():
            return jsonify({'error': 'Cannot claim on weekends'}), 403
        
        investments = get_collection('investments')
        investment = next((i for i in investments if i.get('id') == investment_id), None)
        
        if not investment:
            return jsonify({'error': 'Investment not found'}), 404
        
        if investment.get('isFixed'):
            earnings = investment['dailyEarnings']
        else:
            earnings = (investment['amount'] * investment['dailyEarnings']) / 100
        
        # Update investment
        update_document('investments', investment_id, {
            'totalEarned': investment.get('totalEarned', 0) + earnings,
            'lastClaimDate': get_timestamp()
        })
        
        # Update user balance
        user = get_user(user_id)
        if user:
            save_user(user_id, {
                'taskEarnings': user.get('taskEarnings', 0) + earnings
            })
        
        return jsonify({
            'success': True,
            'message': f'Claimed {earnings:.2f} USDT',
            'earnings': earnings
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily/check/<user_id>', methods=['GET'])
def check_daily(user_id):
    try:
        if is_weekend():
            return jsonify({'canClaim': False, 'reason': 'Weekend', 'isWeekend': True})
        return jsonify({'canClaim': True, 'isWeekend': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: NOTIFICATIONS
# ============================================
@app.route('/api/notifications/<user_id>', methods=['GET'])
def get_notifications(user_id):
    try:
        notifications = get_collection('notifications', {'userId': user_id})
        notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        unread_count = len([n for n in notifications if not n.get('read', False)])
        
        return jsonify({
            'success': True,
            'notifications': notifications[:50],
            'unreadCount': unread_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_read():
    try:
        data = request.json
        user_id = data.get('userId')
        
        notifications = get_collection('notifications', {'userId': user_id})
        for notif in notifications:
            if not notif.get('read', False):
                update_document('notifications', notif['id'], {'read': True})
        
        return jsonify({'success': True, 'message': 'All marked as read'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

@app.route('/api/security/reset', methods=['POST'])
def reset_security():
    try:
        data = request.json
        user_id = data.get('userId')
        new_code = generate_security_code()
        save_user(user_id, {'securityCode': new_code})
        return jsonify({'success': True, 'newCode': new_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        
        return jsonify({
            'success': True,
            'stats': {
                'totalUsers': len(users),
                'totalDeposits': sum(d.get('amount', 0) for d in deposits if d.get('status') == 'approved'),
                'totalWithdrawals': sum(w.get('amount', 0) for w in withdrawals if w.get('status') == 'completed'),
                'activeInvestments': len(get_collection('investments', {'status': 'active'})),
                'totalReferrals': len(referrals),
                'pendingDeposits': len([d for d in deposits if d.get('status') == 'pending']),
                'pendingWithdrawals': len([w for w in withdrawals if w.get('status') == 'pending'])
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# ERROR HANDLERS
# ============================================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return send_from_directory('.', 'index.html')

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 SAFE Platform v3.0 - Firebase REST API")
    print(f"📍 Port: {port}")
    print(f"🗄️  Database: Firebase Firestore (REST)")
    print(f"📱 Telebirr: {TELEBIRR_NUMBER}")
    print(f"👥 Referral Bonus: {REFERRAL_BONUS_PERCENTAGE}%")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
