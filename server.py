from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import json
import hashlib
import random
import string
import time
from functools import wraps
import firebase_admin
from firebase_admin import credentials, firestore, db

app = Flask(__name__, static_folder='.')
CORS(app)

# ============================================
# FIREBASE INITIALIZATION
# ============================================
# Option 1: Using service account JSON file (Recommended for production)
# Download service account key from Firebase Console > Project Settings > Service Accounts
# Save it as 'serviceAccountKey.json' in the same directory

try:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://webapp-fc856-default-rtdb.firebaseio.com',  # Your RTDB URL
        'projectId': 'webapp-fc856'
    })
    print("✅ Firebase initialized with service account")
except Exception as e:
    print(f"⚠️ Service account not found, trying application default credentials...")
    try:
        firebase_admin.initialize_app(options={
            'databaseURL': 'https://webapp-fc856-default-rtdb.firebaseio.com',
            'projectId': 'webapp-fc856'
        })
        print("✅ Firebase initialized with default credentials")
    except Exception as e2:
        print(f"❌ Firebase initialization failed: {e2}")
        print("⚠️ Falling back to environment variables method...")
        # Option 3: Use environment variables (for platforms like Render, Railway, etc.)
        # Set these in your hosting platform's environment variables
        firebase_config = {
            "type": "service_account",
            "project_id": os.environ.get('FIREBASE_PROJECT_ID', 'webapp-fc856'),
            "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID', ''),
            "private_key": os.environ.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
            "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL', ''),
            "client_id": os.environ.get('FIREBASE_CLIENT_ID', ''),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ.get('FIREBASE_CLIENT_CERT_URL', '')
        }
        
        try:
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://webapp-fc856-default-rtdb.firebaseio.com'
            })
            print("✅ Firebase initialized with environment variables")
        except Exception as e3:
            print(f"❌ All Firebase initialization methods failed: {e3}")
            raise

# Get Firestore and RTDB clients
db_firestore = firestore.client()
rtdb = db.reference() if hasattr(db, 'reference') else None

# ============================================
# CONFIGURATION
# ============================================
ADMIN_EMAILS = ['admin@safe.com']
TELEBIRR_NUMBER = '0949399753'
TELEBIRR_NAME = 'Abinet'
WALLET_ADDRESS = 'TK3RviHLX31oC6qNdfaF9Wuh8JJ4bQqAXu'
REFERRAL_BONUS = 10
REFERRAL_BONUS_PERCENTAGE = 10
REFERRAL_POINTS = 100
MIN_DEPOSIT = 10
MIN_WITHDRAW = 20
MAX_WITHDRAW_DAILY = 500
WEEKEND_DAYS = [5, 6]

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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_timestamp():
    return datetime.utcnow().isoformat()

def format_date(dt):
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(dt, str):
        return dt
    return str(dt)

def calculate_referral_bonus(deposit_amount):
    return round(deposit_amount * REFERRAL_BONUS_PERCENTAGE / 100, 2)

# ============================================
# FIREBASE HELPER FUNCTIONS
# ============================================
def get_user_from_firestore(user_id):
    """Get user data from Firestore"""
    try:
        doc_ref = db_firestore.collection('users').document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"Error getting user from Firestore: {e}")
        return None

def save_user_to_firestore(user_id, user_data):
    """Save user data to Firestore"""
    try:
        db_firestore.collection('users').document(user_id).set(user_data, merge=True)
        return True
    except Exception as e:
        print(f"Error saving user to Firestore: {e}")
        return False

def get_all_users_from_firestore():
    """Get all users from Firestore"""
    try:
        users_ref = db_firestore.collection('users')
        docs = users_ref.stream()
        users = {}
        for doc in docs:
            users[doc.id] = doc.to_dict()
        return users
    except Exception as e:
        print(f"Error getting all users: {e}")
        return {}

def add_deposit_to_firestore(deposit_data):
    """Add deposit to Firestore"""
    try:
        doc_ref = db_firestore.collection('deposits').document()
        deposit_data['id'] = doc_ref.id
        doc_ref.set(deposit_data)
        return doc_ref.id
    except Exception as e:
        print(f"Error adding deposit: {e}")
        return None

def get_deposits_from_firestore(user_id=None):
    """Get deposits from Firestore"""
    try:
        deposits_ref = db_firestore.collection('deposits')
        if user_id:
            query = deposits_ref.where('userId', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
        else:
            query = deposits_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        docs = query.stream()
        deposits = []
        for doc in docs:
            deposit = doc.to_dict()
            deposit['id'] = doc.id
            deposits.append(deposit)
        return deposits
    except Exception as e:
        print(f"Error getting deposits: {e}")
        return []

def update_deposit_in_firestore(deposit_id, update_data):
    """Update deposit in Firestore"""
    try:
        db_firestore.collection('deposits').document(deposit_id).update(update_data)
        return True
    except Exception as e:
        print(f"Error updating deposit: {e}")
        return False

def add_withdrawal_to_firestore(withdrawal_data):
    """Add withdrawal to Firestore"""
    try:
        doc_ref = db_firestore.collection('withdrawals').document()
        withdrawal_data['id'] = doc_ref.id
        doc_ref.set(withdrawal_data)
        return doc_ref.id
    except Exception as e:
        print(f"Error adding withdrawal: {e}")
        return None

def get_withdrawals_from_firestore(user_id=None):
    """Get withdrawals from Firestore"""
    try:
        withdrawals_ref = db_firestore.collection('withdrawals')
        if user_id:
            query = withdrawals_ref.where('userId', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
        else:
            query = withdrawals_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        docs = query.stream()
        withdrawals = []
        for doc in docs:
            withdrawal = doc.to_dict()
            withdrawal['id'] = doc.id
            withdrawals.append(withdrawal)
        return withdrawals
    except Exception as e:
        print(f"Error getting withdrawals: {e}")
        return []

def update_withdrawal_in_firestore(withdrawal_id, update_data):
    """Update withdrawal in Firestore"""
    try:
        db_firestore.collection('withdrawals').document(withdrawal_id).update(update_data)
        return True
    except Exception as e:
        print(f"Error updating withdrawal: {e}")
        return False

def add_referral_to_firestore(referral_data):
    """Add referral to Firestore"""
    try:
        doc_ref = db_firestore.collection('referrals').document()
        referral_data['id'] = doc_ref.id
        doc_ref.set(referral_data)
        return doc_ref.id
    except Exception as e:
        print(f"Error adding referral: {e}")
        return None

def get_referrals_from_firestore(referrer_id=None):
    """Get referrals from Firestore"""
    try:
        referrals_ref = db_firestore.collection('referrals')
        if referrer_id:
            query = referrals_ref.where('referrerId', '==', referrer_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
        else:
            query = referrals_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)
        
        docs = query.stream()
        referrals = []
        for doc in docs:
            referral = doc.to_dict()
            referral['id'] = doc.id
            referrals.append(referral)
        return referrals
    except Exception as e:
        print(f"Error getting referrals: {e}")
        return []

def add_notification_to_firestore(notification_data):
    """Add notification to Firestore"""
    try:
        doc_ref = db_firestore.collection('notifications').document()
        notification_data['id'] = doc_ref.id
        doc_ref.set(notification_data)
        return doc_ref.id
    except Exception as e:
        print(f"Error adding notification: {e}")
        return None

def get_notifications_from_firestore(user_id):
    """Get notifications from Firestore"""
    try:
        notif_ref = db_firestore.collection('notifications')
        query = notif_ref.where('userId', '==', user_id).order_by('timestamp', direction=firestore.Query.DESCENDING)
        docs = query.stream()
        notifications = []
        for doc in docs:
            notif = doc.to_dict()
            notif['id'] = doc.id
            notifications.append(notif)
        return notifications
    except Exception as e:
        print(f"Error getting notifications: {e}")
        return []

def add_investment_to_firestore(investment_data):
    """Add investment to Firestore"""
    try:
        doc_ref = db_firestore.collection('investments').document()
        investment_data['id'] = doc_ref.id
        doc_ref.set(investment_data)
        return doc_ref.id
    except Exception as e:
        print(f"Error adding investment: {e}")
        return None

def get_investments_from_firestore(user_id):
    """Get investments from Firestore"""
    try:
        inv_ref = db_firestore.collection('investments')
        query = inv_ref.where('userId', '==', user_id).where('status', '==', 'active')
        docs = query.stream()
        investments = []
        for doc in docs:
            inv = doc.to_dict()
            inv['id'] = doc.id
            investments.append(inv)
        return investments
    except Exception as e:
        print(f"Error getting investments: {e}")
        return []

def update_investment_in_firestore(investment_id, update_data):
    """Update investment in Firestore"""
    try:
        db_firestore.collection('investments').document(investment_id).update(update_data)
        return True
    except Exception as e:
        print(f"Error updating investment: {e}")
        return False

# ============================================
# STATIC FILE SERVING - MAIN ROUTES
# ============================================
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/home')
def home():
    return send_from_directory('.', 'home.html')

@app.route('/referral')
def referral():
    return send_from_directory('.', 'referral.html')

@app.route('/notification')
def notification():
    return send_from_directory('.', 'notification.html')

@app.route('/product')
def product():
    return send_from_directory('.', 'product.html')

@app.route('/daily')
def daily():
    return send_from_directory('.', 'daily.html')

@app.route('/withdraw')
def withdraw():
    return send_from_directory('.', 'withdraw.html')

@app.route('/deposite')
def deposite():
    return send_from_directory('.', 'deposite.html')

@app.route('/admin.html')
def admin_panel():
    return send_from_directory('.', 'admin.html')

# Fallback for any other paths
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
        users = get_all_users_from_firestore()
        return jsonify({
            'status': 'ok',
            'message': 'SAFE Platform Running with Firebase',
            'timestamp': get_timestamp(),
            'referral_system': 'active',
            'referral_bonus_percentage': f'{REFERRAL_BONUS_PERCENTAGE}%',
            'total_users': len(users),
            'database': 'Firebase Firestore'
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
        'referral_bonus_base': REFERRAL_BONUS,
        'referral_points': REFERRAL_POINTS,
        'min_deposit': MIN_DEPOSIT,
        'min_withdraw': MIN_WITHDRAW
    })

# ============================================
# API: USER MANAGEMENT (Using Firebase)
# ============================================
@app.route('/api/user/create', methods=['POST'])
def create_user():
    try:
        data = request.json
        user_id = data.get('userId')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # Check if user exists in Firebase
        existing_user = get_user_from_firestore(user_id)
        if existing_user:
            return jsonify({'error': 'User already exists'}), 409
        
        referral_code = generate_referral_code()
        security_code = generate_security_code()
        
        user_data = {
            'userId': user_id,
            'email': data.get('email', ''),
            'fullName': data.get('fullName', ''),
            'firstName': data.get('firstName', data.get('fullName', '').split(' ')[0] if data.get('fullName') else ''),
            'lastName': data.get('lastName', ' '.join(data.get('fullName', '').split(' ')[1:]) if data.get('fullName') else ''),
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
            'createdAt': firestore.SERVER_TIMESTAMP,
            'lastLogin': None,
            'securityCode': security_code
        }
        
        # Save to Firestore
        save_user_to_firestore(user_id, user_data)
        
        # Also save basic info to RTDB for quick access
        if rtdb:
            rtdb.child('users').child(user_id).set({
                'email': user_data['email'],
                'fullName': user_data['fullName'],
                'referralCode': referral_code,
                'referredBy': user_data['referredBy'],
                'status': 'active',
                'lastLogin': None
            })
        
        # Handle referral on signup
        referred_by = data.get('referredBy')
        referral_record = None
        
        if referred_by:
            referrer = get_user_from_firestore(referred_by)
            if referrer:
                referral_record = {
                    'referrerId': referred_by,
                    'referredUserId': user_id,
                    'referredEmail': data.get('email', ''),
                    'referredName': data.get('fullName', data.get('firstName', '')),
                    'bonusEarned': 0,
                    'pointsAwarded': 0,
                    'status': 'pending_first_deposit',
                    'signupDate': get_timestamp(),
                    'firstDepositDate': None,
                    'timestamp': firestore.SERVER_TIMESTAMP
                }
                
                referral_id = add_referral_to_firestore(referral_record)
                
                # Update referrer's count
                save_user_to_firestore(referred_by, {
                    'referralCount': firestore.Increment(1)
                })
                
                # Add notification for referrer
                notification_data = {
                    'userId': referred_by,
                    'type': 'referral_signup',
                    'message': f"🎉 {data.get('fullName', data.get('firstName', 'New user'))} joined using your referral link!",
                    'referredUserId': user_id,
                    'referredName': data.get('fullName', data.get('firstName', 'New User')),
                    'read': False,
                    'timestamp': firestore.SERVER_TIMESTAMP
                }
                add_notification_to_firestore(notification_data)
                
                print(f"✅ Referral tracked: {referred_by} referred {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'User created successfully in Firebase',
            'referralCode': referral_code,
            'securityCode': security_code,
            'referredBy': referred_by,
            'referralStatus': 'pending_first_deposit' if referral_record else None
        }), 201
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = get_user_from_firestore(user_id)
        if user:
            user['referralLink'] = f"{request.host_url}?ref={user.get('referralCode', user_id)}"
            user['totalBalance'] = user.get('depositBalance', 0) + user.get('taskEarnings', 0)
            return jsonify({
                'success': True,
                'user': user
            })
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>/balance', methods=['GET'])
def get_user_balance(user_id):
    try:
        user = get_user_from_firestore(user_id)
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
def get_all_users():
    """Get all users (admin)"""
    try:
        users = get_all_users_from_firestore()
        users_list = []
        for user_id, user_data in users.items():
            users_list.append({
                'userId': user_id,
                'email': user_data.get('email', ''),
                'fullName': user_data.get('fullName', ''),
                'firstName': user_data.get('firstName', ''),
                'depositBalance': user_data.get('depositBalance', 0),
                'taskEarnings': user_data.get('taskEarnings', 0),
                'referralCount': user_data.get('referralCount', 0),
                'status': user_data.get('status', 'active'),
                'createdAt': str(user_data.get('createdAt', ''))
            })
        return jsonify({'success': True, 'users': users_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: VALIDATE REFERRAL CODE (Using Firebase)
# ============================================
@app.route('/api/referral/validate/<code>', methods=['GET'])
@app.route('/api/referral/check/<code>', methods=['GET'])
def validate_referral_code(code):
    try:
        # First try by referralCode field
        users_ref = db_firestore.collection('users')
        query = users_ref.where('referralCode', '==', code).limit(1)
        results = query.stream()
        
        for doc in results:
            user_data = doc.to_dict()
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': doc.id,
                'referrerName': user_data.get('firstName', user_data.get('fullName', 'User')),
                'referrerEmail': user_data.get('email', ''),
                'referralCode': code
            })
        
        # Try by user ID (in case code is a user ID)
        user_doc = db_firestore.collection('users').document(code).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': code,
                'referrerName': user_data.get('firstName', user_data.get('fullName', 'User')),
                'referrerEmail': user_data.get('email', ''),
                'referralCode': user_data.get('referralCode', code)
            })
        
        return jsonify({
            'success': True,
            'valid': False,
            'message': 'Invalid referral code'
        }), 200
        
    except Exception as e:
        print(f"Error validating referral: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# API: DEPOSIT (Using Firebase)
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
        
        user = get_user_from_firestore(user_id)
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
            'timestamp': firestore.SERVER_TIMESTAMP,
            'createdAt': get_timestamp()
        }
        
        deposit_id = add_deposit_to_firestore(deposit_data)
        
        # Notification to user
        notification_data = {
            'userId': user_id,
            'type': 'deposit',
            'message': f'Deposit of {amount} USDT submitted via {method}. Pending approval.',
            'amount': amount,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        add_notification_to_firestore(notification_data)
        
        print(f"📥 New deposit: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit submitted successfully',
            'deposit': {**deposit_data, 'id': deposit_id},
            'isFirstDeposit': is_first_deposit
        }), 201
        
    except Exception as e:
        print(f"Error submitting deposit: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<user_id>', methods=['GET'])
def get_deposits(user_id):
    try:
        deposits = get_deposits_from_firestore(user_id)
        user = get_user_from_firestore(user_id)
        
        return jsonify({
            'success': True,
            'deposits': deposits,
            'firstDepositCompleted': user.get('firstDepositCompleted', False) if user else False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/all', methods=['GET'])
def get_all_deposits():
    """Get all deposits (admin)"""
    try:
        deposits = get_deposits_from_firestore()
        return jsonify({
            'success': True,
            'deposits': deposits
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/approve', methods=['POST'])
def approve_deposit(deposit_id):
    try:
        # Get deposit from Firestore
        deposit_ref = db_firestore.collection('deposits').document(deposit_id)
        deposit_doc = deposit_ref.get()
        
        if not deposit_doc.exists:
            return jsonify({'error': 'Deposit not found'}), 404
        
        deposit = deposit_doc.to_dict()
        
        if deposit.get('status') == 'approved':
            return jsonify({'error': 'Deposit already approved'}), 400
        
        user_id = deposit['userId']
        amount = deposit['amount']
        is_first_deposit = deposit.get('isFirstDeposit', False)
        
        # Update deposit status
        update_data = {
            'status': 'approved',
            'approvedAt': firestore.SERVER_TIMESTAMP
        }
        update_deposit_in_firestore(deposit_id, update_data)
        
        # Update user balance
        user = get_user_from_firestore(user_id)
        if user:
            user_update = {
                'depositBalance': firestore.Increment(amount)
            }
            
            if is_first_deposit and not user.get('firstDepositCompleted', False):
                user_update['firstDepositCompleted'] = True
                
                # Process referral bonus
                referral_bonus = process_referral_bonus_firebase(user_id, amount, deposit_id)
                if referral_bonus:
                    update_deposit_in_firestore(deposit_id, {
                        'referralBonusPaid': True,
                        'referralBonusDetails': referral_bonus
                    })
            
            save_user_to_firestore(user_id, user_update)
        
        # Notification to user
        notification_data = {
            'userId': user_id,
            'type': 'deposit_approved',
            'message': f'✅ Deposit of {amount} USDT approved!',
            'amount': amount,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        add_notification_to_firestore(notification_data)
        
        print(f"✅ Deposit approved: {deposit_id} - {amount} USDT")
        
        return jsonify({
            'success': True,
            'message': 'Deposit approved successfully',
            'deposit': {**deposit, **update_data}
        })
        
    except Exception as e:
        print(f"Error approving deposit: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/reject', methods=['POST'])
def reject_deposit(deposit_id):
    try:
        deposit_ref = db_firestore.collection('deposits').document(deposit_id)
        deposit_doc = deposit_ref.get()
        
        if not deposit_doc.exists:
            return jsonify({'error': 'Deposit not found'}), 404
        
        deposit = deposit_doc.to_dict()
        
        update_data = {
            'status': 'rejected',
            'rejectedAt': firestore.SERVER_TIMESTAMP
        }
        update_deposit_in_firestore(deposit_id, update_data)
        
        # Notification to user
        notification_data = {
            'userId': deposit['userId'],
            'type': 'deposit_rejected',
            'message': f'❌ Deposit of {deposit["amount"]} USDT was rejected.',
            'amount': deposit['amount'],
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        add_notification_to_firestore(notification_data)
        
        print(f"❌ Deposit rejected: {deposit_id}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit rejected',
            'deposit': {**deposit, **update_data}
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_referral_bonus_firebase(new_user_id, deposit_amount, deposit_id):
    """Process referral bonus using Firebase"""
    try:
        new_user = get_user_from_firestore(new_user_id)
        if not new_user:
            return None
        
        referred_by = new_user.get('referredBy')
        if not referred_by:
            return None
        
        referrer = get_user_from_firestore(referred_by)
        if not referrer:
            return None
        
        bonus_amount = calculate_referral_bonus(deposit_amount)
        points_awarded = REFERRAL_POINTS
        
        # Update referrer's balance and points
        save_user_to_firestore(referred_by, {
            'depositBalance': firestore.Increment(bonus_amount),
            'referralBonus': firestore.Increment(bonus_amount),
            'totalReferralPoints': firestore.Increment(points_awarded),
            'points': firestore.Increment(points_awarded)
        })
        
        # Update referral record
        referrals = get_referrals_from_firestore(referred_by)
        for ref in referrals:
            if ref.get('referredUserId') == new_user_id:
                update_data = {
                    'status': 'active',
                    'bonusEarned': bonus_amount,
                    'pointsAwarded': points_awarded,
                    'firstDepositDate': get_timestamp(),
                    'depositAmount': deposit_amount,
                    'bonusPercentage': REFERRAL_BONUS_PERCENTAGE,
                    'depositId': deposit_id
                }
                # Update the referral document
                db_firestore.collection('referrals').document(ref['id']).update(update_data)
                break
        
        # Add bonus record
        bonus_record = {
            'referrerId': referred_by,
            'referredUserId': new_user_id,
            'depositId': deposit_id,
            'depositAmount': deposit_amount,
            'bonusPercentage': REFERRAL_BONUS_PERCENTAGE,
            'bonusAmount': bonus_amount,
            'pointsAwarded': points_awarded,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        db_firestore.collection('referral_bonuses').add(bonus_record)
        
        # Give welcome bonus to new user
        save_user_to_firestore(new_user_id, {
            'points': firestore.Increment(50)
        })
        
        # Notifications
        new_user_name = new_user.get('fullName', new_user.get('firstName', 'User'))
        
        # Notify referrer
        add_notification_to_firestore({
            'userId': referred_by,
            'type': 'referral_bonus',
            'message': f"🎉 Referral Bonus! {new_user_name} made first deposit of ${deposit_amount}. You earned ${bonus_amount} + {points_awarded} points!",
            'amount': bonus_amount,
            'points': points_awarded,
            'referredUserName': new_user_name,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        
        # Notify new user
        add_notification_to_firestore({
            'userId': new_user_id,
            'type': 'referral_welcome_bonus',
            'message': f"🎁 Welcome Bonus! You earned 50 points for joining with a referral link!",
            'points': 50,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        
        print(f"✅ Referral Bonus: {referred_by} received ${bonus_amount}")
        
        return {
            'referrerId': referred_by,
            'bonusAmount': bonus_amount,
            'bonusPercentage': REFERRAL_BONUS_PERCENTAGE,
            'pointsAwarded': points_awarded,
            'depositAmount': deposit_amount
        }
        
    except Exception as e:
        print(f"Error processing referral bonus: {e}")
        return None

# ============================================
# API: REFERRAL SYSTEM (Using Firebase)
# ============================================
@app.route('/api/referral/stats/<user_id>', methods=['GET'])
def get_referral_stats(user_id):
    try:
        user = get_user_from_firestore(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        referrals = get_referrals_from_firestore(user_id)
        
        total_referrals = len(referrals)
        active_referrals = len([r for r in referrals if r.get('status') == 'active'])
        pending_referrals = len([r for r in referrals if r.get('status') == 'pending_first_deposit'])
        
        # Get bonuses
        bonuses_ref = db_firestore.collection('referral_bonuses')
        bonus_query = bonuses_ref.where('referrerId', '==', user_id)
        bonus_docs = bonus_query.stream()
        bonuses = []
        total_bonus = 0
        total_points = 0
        for doc in bonus_docs:
            b = doc.to_dict()
            bonuses.append(b)
            total_bonus += b.get('bonusAmount', 0)
            total_points += b.get('pointsAwarded', 0)
        
        referral_link = f"{request.host_url}?ref={user.get('referralCode', user_id)}"
        
        return jsonify({
            'success': True,
            'referralCode': user.get('referralCode'),
            'referralLink': referral_link,
            'stats': {
                'totalReferrals': total_referrals,
                'activeReferrals': active_referrals,
                'pendingReferrals': pending_referrals,
                'totalBonusEarned': round(total_bonus, 2),
                'totalPointsEarned': total_points,
                'referralBonusPercentage': REFERRAL_BONUS_PERCENTAGE,
                'pointsPerReferral': REFERRAL_POINTS
            },
            'referrals': referrals[:10],
            'bonuses': bonuses[:20]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: WITHDRAWAL (Using Firebase)
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
        
        # Check daily limit
        today = datetime.now().strftime('%Y-%m-%d')
        all_withdrawals = get_withdrawals_from_firestore(user_id)
        daily_total = sum(
            w['amount'] for w in all_withdrawals
            if w.get('timestamp') and today in str(w['timestamp']) and w.get('status') != 'rejected'
        )
        if daily_total + amount > MAX_WITHDRAW_DAILY:
            return jsonify({'error': f'Daily withdrawal limit is {MAX_WITHDRAW_DAILY} USDT'}), 400
        
        # Check balance
        user = get_user_from_firestore(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        total_balance = user.get('depositBalance', 0) + user.get('taskEarnings', 0)
        if amount > total_balance:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Deduct from balance
        if user.get('taskEarnings', 0) >= amount:
            save_user_to_firestore(user_id, {'taskEarnings': firestore.Increment(-amount)})
        else:
            remaining = amount - user.get('taskEarnings', 0)
            save_user_to_firestore(user_id, {
                'taskEarnings': 0,
                'depositBalance': firestore.Increment(-remaining)
            })
        
        withdrawal_data = {
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'userName': user.get('fullName', ''),
            'amount': amount,
            'method': method,
            'details': details,
            'status': 'pending',
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        
        withdrawal_id = add_withdrawal_to_firestore(withdrawal_data)
        
        # Notification
        add_notification_to_firestore({
            'userId': user_id,
            'type': 'withdrawal',
            'message': f'Withdrawal of {amount} USDT via {method} submitted.',
            'amount': amount,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        
        print(f"💸 New withdrawal: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal submitted successfully',
            'withdrawal': {**withdrawal_data, 'id': withdrawal_id}
        }), 201
        
    except Exception as e:
        print(f"Error submitting withdrawal: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<user_id>', methods=['GET'])
def get_withdrawals(user_id):
    try:
        withdrawals = get_withdrawals_from_firestore(user_id)
        return jsonify({
            'success': True,
            'withdrawals': withdrawals
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/approve', methods=['POST'])
def approve_withdrawal(withdrawal_id):
    try:
        withdrawal_ref = db_firestore.collection('withdrawals').document(withdrawal_id)
        withdrawal_doc = withdrawal_ref.get()
        
        if not withdrawal_doc.exists:
            return jsonify({'error': 'Withdrawal not found'}), 404
        
        withdrawal = withdrawal_doc.to_dict()
        
        update_data = {
            'status': 'completed',
            'completedAt': firestore.SERVER_TIMESTAMP
        }
        update_withdrawal_in_firestore(withdrawal_id, update_data)
        
        # Notification
        add_notification_to_firestore({
            'userId': withdrawal['userId'],
            'type': 'withdrawal_approved',
            'message': f'✅ Withdrawal of {withdrawal["amount"]} USDT approved!',
            'amount': withdrawal['amount'],
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        
        print(f"✅ Withdrawal approved: {withdrawal_id}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal approved',
            'withdrawal': {**withdrawal, **update_data}
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/reject', methods=['POST'])
def reject_withdrawal(withdrawal_id):
    try:
        withdrawal_ref = db_firestore.collection('withdrawals').document(withdrawal_id)
        withdrawal_doc = withdrawal_ref.get()
        
        if not withdrawal_doc.exists:
            return jsonify({'error': 'Withdrawal not found'}), 404
        
        withdrawal = withdrawal_doc.to_dict()
        
        # Refund the amount
        user_id = withdrawal['userId']
        amount = withdrawal['amount']
        save_user_to_firestore(user_id, {'depositBalance': firestore.Increment(amount)})
        
        update_data = {
            'status': 'rejected',
            'rejectedAt': firestore.SERVER_TIMESTAMP
        }
        update_withdrawal_in_firestore(withdrawal_id, update_data)
        
        # Notification
        add_notification_to_firestore({
            'userId': user_id,
            'type': 'withdrawal_rejected',
            'message': f'❌ Withdrawal of {amount} USDT rejected. Amount refunded.',
            'amount': amount,
            'read': False,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        
        print(f"❌ Withdrawal rejected: {withdrawal_id}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal rejected',
            'withdrawal': {**withdrawal, **update_data}
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: PRODUCTS & INVESTMENTS
# ============================================
PRODUCTS = [
    {'name': 'Level 1', 'price': 30, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'Level 2', 'price': 50, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'Level 3', 'price': 100, 'dailyEarnings': 4, 'duration': 120, 'isFixed': False, 'category': 'basic'},
    {'name': 'VIP 1', 'price': 300, 'dailyEarnings': 15, 'duration': 130, 'isFixed': True, 'category': 'vip'},
    {'name': 'VIP 2', 'price': 500, 'dailyEarnings': 25, 'duration': 130, 'isFixed': True, 'category': 'vip'},
    {'name': 'VIP 3', 'price': 1000, 'dailyEarnings': 50, 'duration': 130, 'isFixed': True, 'category': 'vip'},
]

@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify({'success': True, 'products': PRODUCTS})

@app.route('/api/investment/buy', methods=['POST'])
def buy_investment():
    try:
        data = request.json
        user_id = data.get('userId')
        product_name = data.get('productName')
        
        if not user_id or not product_name:
            return jsonify({'error': 'User ID and product name required'}), 400
        
        product = next((p for p in PRODUCTS if p['name'] == product_name), None)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        user = get_user_from_firestore(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.get('depositBalance', 0) < product['price']:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Deduct balance
        save_user_to_firestore(user_id, {'depositBalance': firestore.Increment(-product['price'])})
        
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
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        
        investment_id = add_investment_to_firestore(investment_data)
        
        return jsonify({
            'success': True,
            'message': f'Successfully purchased {product_name}',
            'investment': {**investment_data, 'id': investment_id}
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/investment/<user_id>', methods=['GET'])
def get_investments(user_id):
    try:
        investments = get_investments_from_firestore(user_id)
        
        for inv in investments:
            purchase_date = datetime.fromisoformat(inv.get('purchaseDate', get_timestamp()))
            days_elapsed = (datetime.now() - purchase_date).days
            inv['daysLeft'] = max(0, inv.get('duration', 120) - days_elapsed)
            inv['progress'] = min(100, (days_elapsed / inv.get('duration', 120)) * 100)
        
        return jsonify({'success': True, 'investments': investments})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: DAILY CLAIMS
# ============================================
@app.route('/api/daily/claim', methods=['POST'])
def claim_daily_earnings():
    try:
        data = request.json
        user_id = data.get('userId')
        investment_id = data.get('investmentId')
        
        if not user_id or not investment_id:
            return jsonify({'error': 'User ID and Investment ID required'}), 400
        
        if is_weekend():
            return jsonify({'error': 'Cannot claim on weekends'}), 403
        
        # Get investment
        inv_ref = db_firestore.collection('investments').document(investment_id)
        inv_doc = inv_ref.get()
        
        if not inv_doc.exists:
            return jsonify({'error': 'Investment not found'}), 404
        
        investment = inv_doc.to_dict()
        
        last_claim = datetime.fromisoformat(investment.get('lastClaimDate', '2000-01-01'))
        if last_claim.date() == datetime.now().date():
            return jsonify({'error': 'Already claimed today'}), 400
        
        if investment.get('isFixed'):
            earnings = investment['dailyEarnings']
        else:
            earnings = (investment['amount'] * investment['dailyEarnings']) / 100
        
        # Update investment
        update_investment_in_firestore(investment_id, {
            'totalEarned': firestore.Increment(earnings),
            'lastClaimDate': get_timestamp()
        })
        
        # Update user balance
        save_user_to_firestore(user_id, {'taskEarnings': firestore.Increment(earnings)})
        
        return jsonify({
            'success': True,
            'message': f'Claimed {earnings:.2f} USDT',
            'earnings': earnings
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily/check/<user_id>', methods=['GET'])
def check_daily_status(user_id):
    try:
        if is_weekend():
            return jsonify({'canClaim': False, 'reason': 'Weekend - no claims allowed', 'isWeekend': True})
        return jsonify({'canClaim': True, 'isWeekend': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: NOTIFICATIONS (Using Firebase)
# ============================================
@app.route('/api/notifications/<user_id>', methods=['GET'])
def get_notifications(user_id):
    try:
        notifications = get_notifications_from_firestore(user_id)
        unread_count = len([n for n in notifications if not n.get('read', False)])
        
        return jsonify({
            'success': True,
            'notifications': notifications[:50],
            'unreadCount': unread_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    try:
        data = request.json
        user_id = data.get('userId')
        
        # Get all unread notifications
        notif_ref = db_firestore.collection('notifications')
        query = notif_ref.where('userId', '==', user_id).where('read', '==', False)
        docs = query.stream()
        
        # Mark all as read
        batch = db_firestore.batch()
        for doc in docs:
            batch.update(doc.reference, {'read': True})
        batch.commit()
        
        return jsonify({'success': True, 'message': 'All notifications marked as read'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: SECURITY
# ============================================
@app.route('/api/security/<user_id>', methods=['GET'])
def get_security_code(user_id):
    try:
        user = get_user_from_firestore(user_id)
        if user and user.get('securityCode'):
            return jsonify({'success': True, 'code': user['securityCode']})
        
        # Generate new one if doesn't exist
        new_code = generate_security_code()
        save_user_to_firestore(user_id, {'securityCode': new_code})
        return jsonify({'success': True, 'code': new_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/security/reset', methods=['POST'])
def reset_security_code():
    try:
        data = request.json
        user_id = data.get('userId')
        
        new_code = generate_security_code()
        save_user_to_firestore(user_id, {'securityCode': new_code})
        
        return jsonify({'success': True, 'newCode': new_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: ADMIN
# ============================================
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    try:
        users = get_all_users_from_firestore()
        deposits = get_deposits_from_firestore()
        withdrawals = get_withdrawals_from_firestore()
        referrals = get_referrals_from_firestore()
        
        total_users = len(users)
        total_deposits = sum(d['amount'] for d in deposits if d.get('status') == 'approved')
        total_withdrawals = sum(w['amount'] for w in withdrawals if w.get('status') == 'completed')
        total_referrals = len(referrals)
        
        # Get bonuses
        bonuses_ref = db_firestore.collection('referral_bonuses')
        bonus_docs = bonuses_ref.stream()
        total_bonuses = sum(doc.to_dict().get('bonusAmount', 0) for doc in bonus_docs)
        
        # Active investments
        inv_ref = db_firestore.collection('investments')
        inv_query = inv_ref.where('status', '==', 'active')
        active_investments = len(list(inv_query.stream()))
        
        return jsonify({
            'success': True,
            'stats': {
                'totalUsers': total_users,
                'totalDeposits': total_deposits,
                'totalWithdrawals': total_withdrawals,
                'activeInvestments': active_investments,
                'totalReferrals': total_referrals,
                'totalReferralBonusesPaid': round(total_bonuses, 2),
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
    print("🚀 SAFE Platform Server v3.0 - Firebase Edition")
    print(f"📍 Running on port: {port}")
    print(f"🗄️  Database: Firebase Firestore")
    print(f"📱 Telebirr: {TELEBIRR_NUMBER} ({TELEBIRR_NAME})")
    print(f"💳 Wallet: {WALLET_ADDRESS}")
    print(f"👥 Referral Bonus: {REFERRAL_BONUS_PERCENTAGE}% of first deposit")
    print(f"⭐ Referral Points: {REFERRAL_POINTS}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
