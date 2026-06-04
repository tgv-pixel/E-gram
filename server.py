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

app = Flask(__name__, static_folder='.')
CORS(app)

# ============================================
# IN-MEMORY STORAGE
# ============================================
data_store = {
    'users': {},
    'deposits': [],
    'withdrawals': [],
    'investments': [],
    'referrals': [],
    'referral_bonuses': [],
    'notifications': [],
    'withdrawal_security': {},
    'daily_claims': {},
    'pending_referral_bonuses': {}
}

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

def format_date(dt_string):
    try:
        dt = datetime.fromisoformat(dt_string)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return dt_string

def calculate_referral_bonus(deposit_amount):
    return round(deposit_amount * REFERRAL_BONUS_PERCENTAGE / 100, 2)

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
    return jsonify({
        'status': 'ok',
        'message': 'SAFE Platform Running',
        'timestamp': get_timestamp(),
        'referral_system': 'active',
        'referral_bonus_percentage': f'{REFERRAL_BONUS_PERCENTAGE}%',
        'total_users': len(data_store['users']),
        'total_deposits': len(data_store['deposits']),
        'total_withdrawals': len(data_store['withdrawals'])
    })

# ============================================
# API: SERVER INFO
# ============================================
@app.route('/api/info')
def server_info():
    return jsonify({
        'name': 'SAFE Platform',
        'version': '2.0.0',
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
# API: USER MANAGEMENT
# ============================================
@app.route('/api/user/create', methods=['POST'])
def create_user():
    try:
        data = request.json
        user_id = data.get('userId')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        if user_id in data_store['users']:
            return jsonify({'error': 'User already exists'}), 409
        
        referral_code = generate_referral_code()
        security_code = generate_security_code()
        
        user_data = {
            'userId': user_id,
            'email': data.get('email', ''),
            'firstName': data.get('firstName', ''),
            'lastName': data.get('lastName', ''),
            'phone': data.get('phone', ''),
            'referralCode': referral_code,
            'referredBy': data.get('referredBy', None),
            'depositBalance': 0.0,
            'taskEarnings': 0.0,
            'points': 0,
            'referralCount': 0,
            'referralBonus': 0.0,
            'totalReferralPoints': 0,
            'firstDepositCompleted': False,
            'status': 'active',
            'createdAt': get_timestamp(),
            'lastLogin': None
        }
        
        data_store['users'][user_id] = user_data
        data_store['withdrawal_security'][user_id] = {
            'code': security_code,
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        }
        
        # Handle referral on signup
        referred_by = data.get('referredBy')
        referral_record = None
        
        if referred_by and referred_by in data_store['users']:
            referrer = data_store['users'][referred_by]
            
            referral_record = {
                'id': generate_id(),
                'referrerId': referred_by,
                'referredUserId': user_id,
                'referredEmail': data.get('email', ''),
                'referredName': data.get('firstName', ''),
                'bonusEarned': 0,
                'pointsAwarded': 0,
                'status': 'pending_first_deposit',
                'signupDate': get_timestamp(),
                'firstDepositDate': None,
                'timestamp': get_timestamp()
            }
            
            data_store['referrals'].append(referral_record)
            
            data_store['pending_referral_bonuses'][user_id] = {
                'referrerId': referred_by,
                'referralId': referral_record['id'],
                'bonusPercentage': REFERRAL_BONUS_PERCENTAGE
            }
            
            referrer['referralCount'] = referrer.get('referralCount', 0) + 1
            
            data_store['notifications'].append({
                'userId': referred_by,
                'type': 'referral_signup',
                'message': f"🎉 {data.get('firstName', 'New user')} joined using your referral link! Bonus will be awarded after their first deposit.",
                'referredUserId': user_id,
                'referredName': data.get('firstName', 'New User'),
                'read': False,
                'timestamp': get_timestamp()
            })
            
            print(f"✅ Referral tracked: {referred_by} referred {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'referralCode': referral_code,
            'securityCode': security_code,
            'referredBy': referred_by,
            'referralStatus': referral_record['status'] if referral_record else None
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        if user_id in data_store['users']:
            user = data_store['users'][user_id].copy()
            user['referralLink'] = f"{request.host_url}?ref={user['referralCode']}"
            
            # Calculate total balance
            user['totalBalance'] = user['depositBalance'] + user['taskEarnings']
            
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
        if user_id in data_store['users']:
            user = data_store['users'][user_id]
            return jsonify({
                'success': True,
                'depositBalance': user['depositBalance'],
                'taskEarnings': user['taskEarnings'],
                'totalBalance': user['depositBalance'] + user['taskEarnings'],
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
        users_list = []
        for user_id, user_data in data_store['users'].items():
            users_list.append({
                'userId': user_id,
                'email': user_data.get('email', ''),
                'firstName': user_data.get('firstName', ''),
                'depositBalance': user_data.get('depositBalance', 0),
                'taskEarnings': user_data.get('taskEarnings', 0),
                'referralCount': user_data.get('referralCount', 0),
                'status': user_data.get('status', 'active'),
                'createdAt': user_data.get('createdAt', '')
            })
        return jsonify({'success': True, 'users': users_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: VALIDATE REFERRAL CODE
# ============================================
@app.route('/api/referral/validate/<code>', methods=['GET'])
def validate_referral_code(code):
    try:
        for user_id, user_data in data_store['users'].items():
            if user_data.get('referralCode') == code:
                return jsonify({
                    'success': True,
                    'valid': True,
                    'referrerId': user_id,
                    'referrerName': user_data.get('firstName', 'User'),
                    'referrerEmail': user_data.get('email', ''),
                    'referralCode': code
                })
        
        if code in data_store['users']:
            user_data = data_store['users'][code]
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': code,
                'referrerName': user_data.get('firstName', 'User'),
                'referrerEmail': user_data.get('email', ''),
                'referralCode': user_data.get('referralCode', code)
            })
        
        return jsonify({
            'success': True,
            'valid': False,
            'message': 'Invalid referral code'
        }), 200
        
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
        
        if user_id not in data_store['users']:
            return jsonify({'error': 'User not found'}), 404
        
        user = data_store['users'][user_id]
        is_first_deposit = not user.get('firstDepositCompleted', False)
        
        deposit = {
            'id': generate_id(),
            'userId': user_id,
            'userEmail': user.get('email', ''),
            'amount': amount,
            'method': method,
            'reference': reference,
            'status': 'pending',
            'isFirstDeposit': is_first_deposit,
            'referralBonusPaid': False,
            'timestamp': get_timestamp()
        }
        
        data_store['deposits'].append(deposit)
        
        # Notification to user
        data_store['notifications'].append({
            'userId': user_id,
            'type': 'deposit',
            'message': f'Deposit of {amount} USDT submitted via {method}. Pending approval.',
            'amount': amount,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        print(f"📥 New deposit: {amount} USDT from {user_id} via {method}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit submitted successfully',
            'deposit': deposit,
            'isFirstDeposit': is_first_deposit
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<user_id>', methods=['GET'])
def get_deposits(user_id):
    try:
        user_deposits = [d for d in data_store['deposits'] if d['userId'] == user_id]
        user_deposits.sort(key=lambda x: x['timestamp'], reverse=True)
        
        for deposit in user_deposits:
            if deposit.get('referralBonusPaid'):
                deposit['referralBonusInfo'] = deposit.get('referralBonusDetails', {})
        
        return jsonify({
            'success': True,
            'deposits': user_deposits[-20:],
            'firstDepositCompleted': data_store['users'].get(user_id, {}).get('firstDepositCompleted', False)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/all', methods=['GET'])
def get_all_deposits():
    """Get all deposits (admin)"""
    try:
        all_deposits = sorted(data_store['deposits'], key=lambda x: x['timestamp'], reverse=True)
        return jsonify({
            'success': True,
            'deposits': all_deposits
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/approve', methods=['POST'])
def approve_deposit(deposit_id):
    try:
        deposit = None
        for d in data_store['deposits']:
            if d['id'] == deposit_id:
                deposit = d
                break
        
        if not deposit:
            return jsonify({'error': 'Deposit not found'}), 404
        
        if deposit['status'] == 'approved':
            return jsonify({'error': 'Deposit already approved'}), 400
        
        deposit['status'] = 'approved'
        deposit['approvedAt'] = get_timestamp()
        user_id = deposit['userId']
        amount = deposit['amount']
        is_first_deposit = deposit.get('isFirstDeposit', False)
        
        if user_id in data_store['users']:
            user = data_store['users'][user_id]
            user['depositBalance'] += amount
            
            if is_first_deposit and not user.get('firstDepositCompleted', False):
                user['firstDepositCompleted'] = True
                deposit['firstDepositProcessed'] = True
                
                # Process referral bonus
                referral_bonus_result = process_referral_bonus(user_id, amount, deposit_id)
                
                if referral_bonus_result:
                    deposit['referralBonusPaid'] = True
                    deposit['referralBonusDetails'] = referral_bonus_result
        
        # Notification to user
        data_store['notifications'].append({
            'userId': user_id,
            'type': 'deposit_approved',
            'message': f'✅ Deposit of {amount} USDT approved!',
            'amount': amount,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        print(f"✅ Deposit approved: {deposit_id} - {amount} USDT")
        
        return jsonify({
            'success': True,
            'message': 'Deposit approved successfully',
            'deposit': deposit,
            'firstDepositBonus': deposit.get('referralBonusDetails') if is_first_deposit else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/reject', methods=['POST'])
def reject_deposit(deposit_id):
    try:
        for deposit in data_store['deposits']:
            if deposit['id'] == deposit_id:
                deposit['status'] = 'rejected'
                deposit['rejectedAt'] = get_timestamp()
                
                data_store['notifications'].append({
                    'userId': deposit['userId'],
                    'type': 'deposit_rejected',
                    'message': f'❌ Deposit of {deposit["amount"]} USDT was rejected.',
                    'amount': deposit['amount'],
                    'read': False,
                    'timestamp': get_timestamp()
                })
                
                print(f"❌ Deposit rejected: {deposit_id}")
                
                return jsonify({
                    'success': True,
                    'message': 'Deposit rejected',
                    'deposit': deposit
                })
        
        return jsonify({'error': 'Deposit not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_referral_bonus(new_user_id, deposit_amount, deposit_id):
    try:
        if new_user_id not in data_store['pending_referral_bonuses']:
            if new_user_id in data_store['users']:
                user = data_store['users'][new_user_id]
                referred_by = user.get('referredBy')
                if not referred_by or referred_by not in data_store['users']:
                    print(f"No referrer found for user {new_user_id}")
                    return None
            else:
                return None
        
        if new_user_id in data_store['pending_referral_bonuses']:
            bonus_info = data_store['pending_referral_bonuses'][new_user_id]
            referrer_id = bonus_info['referrerId']
            referral_id = bonus_info['referralId']
        else:
            referrer_id = data_store['users'][new_user_id].get('referredBy')
            referral_id = None
        
        if not referrer_id or referrer_id not in data_store['users']:
            return None
        
        referrer = data_store['users'][referrer_id]
        
        bonus_amount = calculate_referral_bonus(deposit_amount)
        points_awarded = REFERRAL_POINTS
        
        referrer['depositBalance'] = referrer.get('depositBalance', 0) + bonus_amount
        referrer['referralBonus'] = referrer.get('referralBonus', 0) + bonus_amount
        referrer['totalReferralPoints'] = referrer.get('totalReferralPoints', 0) + points_awarded
        referrer['points'] = referrer.get('points', 0) + points_awarded
        
        for ref in data_store['referrals']:
            if ref['referredUserId'] == new_user_id and ref['referrerId'] == referrer_id:
                ref['status'] = 'active'
                ref['bonusEarned'] = bonus_amount
                ref['pointsAwarded'] = points_awarded
                ref['firstDepositDate'] = get_timestamp()
                ref['depositAmount'] = deposit_amount
                ref['bonusPercentage'] = REFERRAL_BONUS_PERCENTAGE
                ref['depositId'] = deposit_id
                break
        
        bonus_record = {
            'id': generate_id(),
            'referrerId': referrer_id,
            'referredUserId': new_user_id,
            'depositId': deposit_id,
            'depositAmount': deposit_amount,
            'bonusPercentage': REFERRAL_BONUS_PERCENTAGE,
            'bonusAmount': bonus_amount,
            'pointsAwarded': points_awarded,
            'timestamp': get_timestamp()
        }
        data_store['referral_bonuses'].append(bonus_record)
        
        if new_user_id in data_store['pending_referral_bonuses']:
            del data_store['pending_referral_bonuses'][new_user_id]
        
        new_user = data_store['users'].get(new_user_id, {})
        new_user_name = new_user.get('firstName', 'User')
        
        data_store['notifications'].append({
            'userId': referrer_id,
            'type': 'referral_bonus',
            'message': f"🎉 Referral Bonus! {new_user_name} made their first deposit of ${deposit_amount}. You earned ${bonus_amount} ({REFERRAL_BONUS_PERCENTAGE}%) + {points_awarded} points!",
            'amount': bonus_amount,
            'points': points_awarded,
            'referredUserName': new_user_name,
            'referredUserId': new_user_id,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        if new_user_id in data_store['users']:
            new_user_data = data_store['users'][new_user_id]
            new_user_data['points'] = new_user_data.get('points', 0) + 50
            
            data_store['notifications'].append({
                'userId': new_user_id,
                'type': 'referral_welcome_bonus',
                'message': f"🎁 Welcome Bonus! You earned 50 points for joining with a referral link!",
                'points': 50,
                'read': False,
                'timestamp': get_timestamp()
            })
        
        print(f"✅ Referral Bonus Paid: {referrer_id} received ${bonus_amount} from {new_user_id}'s first deposit of ${deposit_amount}")
        
        return {
            'referrerId': referrer_id,
            'bonusAmount': bonus_amount,
            'bonusPercentage': REFERRAL_BONUS_PERCENTAGE,
            'pointsAwarded': points_awarded,
            'depositAmount': deposit_amount
        }
        
    except Exception as e:
        print(f"Error processing referral bonus: {e}")
        return None

# ============================================
# API: REFERRAL SYSTEM
# ============================================
@app.route('/api/referral/stats/<user_id>', methods=['GET'])
def get_referral_stats(user_id):
    try:
        if user_id not in data_store['users']:
            return jsonify({'error': 'User not found'}), 404
        
        user = data_store['users'][user_id]
        user_referrals = [r for r in data_store['referrals'] if r['referrerId'] == user_id]
        user_bonuses = [b for b in data_store['referral_bonuses'] if b['referrerId'] == user_id]
        
        total_referrals = len(user_referrals)
        active_referrals = len([r for r in user_referrals if r['status'] == 'active'])
        pending_referrals = len([r for r in user_referrals if r['status'] == 'pending_first_deposit'])
        total_bonus_earned = sum(b['bonusAmount'] for b in user_bonuses)
        total_points_earned = sum(b['pointsAwarded'] for b in user_bonuses)
        
        referral_link = f"{request.host_url}?ref={user['referralCode']}"
        recent_referrals = sorted(user_referrals, key=lambda x: x['timestamp'], reverse=True)[:10]
        
        pending_bonuses = []
        for user_id_key, bonus_info in data_store['pending_referral_bonuses'].items():
            if bonus_info['referrerId'] == user_id:
                pending_user = data_store['users'].get(user_id_key, {})
                pending_bonuses.append({
                    'userId': user_id_key,
                    'userName': pending_user.get('firstName', 'User'),
                    'userEmail': pending_user.get('email', ''),
                    'bonusPercentage': bonus_info['bonusPercentage']
                })
        
        return jsonify({
            'success': True,
            'referralCode': user['referralCode'],
            'referralLink': referral_link,
            'stats': {
                'totalReferrals': total_referrals,
                'activeReferrals': active_referrals,
                'pendingReferrals': pending_referrals,
                'totalBonusEarned': round(total_bonus_earned, 2),
                'totalPointsEarned': total_points_earned,
                'referralBonusPercentage': REFERRAL_BONUS_PERCENTAGE,
                'pointsPerReferral': REFERRAL_POINTS
            },
            'referrals': recent_referrals,
            'bonuses': user_bonuses[-20:],
            'pendingBonuses': pending_bonuses
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/referral/bonuses/<user_id>', methods=['GET'])
def get_referral_bonuses(user_id):
    try:
        user_bonuses = [b for b in data_store['referral_bonuses'] if b['referrerId'] == user_id]
        user_bonuses.sort(key=lambda x: x['timestamp'], reverse=True)
        
        total_bonus = sum(b['bonusAmount'] for b in user_bonuses)
        total_points = sum(b['pointsAwarded'] for b in user_bonuses)
        
        return jsonify({
            'success': True,
            'totalBonus': round(total_bonus, 2),
            'totalPoints': total_points,
            'bonusCount': len(user_bonuses),
            'bonuses': user_bonuses
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/referral/pending/<user_id>', methods=['GET'])
def get_pending_referrals(user_id):
    try:
        pending = []
        for referred_user_id, bonus_info in data_store['pending_referral_bonuses'].items():
            if bonus_info['referrerId'] == user_id:
                if referred_user_id in data_store['users']:
                    pending_user = data_store['users'][referred_user_id]
                    pending.append({
                        'userId': referred_user_id,
                        'userName': pending_user.get('firstName', 'User'),
                        'userEmail': pending_user.get('email', ''),
                        'signupDate': pending_user.get('createdAt', ''),
                        'bonusPercentage': bonus_info['bonusPercentage'],
                        'potentialBonus': f"{bonus_info['bonusPercentage']}% of first deposit"
                    })
        
        return jsonify({
            'success': True,
            'pendingCount': len(pending),
            'pendingReferrals': pending
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/referral/check/<code>', methods=['GET'])
def check_referral_code(code):
    try:
        for user_id, user_data in data_store['users'].items():
            if user_data.get('referralCode') == code:
                return jsonify({
                    'success': True,
                    'valid': True,
                    'referrerId': user_id,
                    'referrerName': user_data.get('firstName', 'Friend'),
                    'referrerEmail': user_data.get('email', ''),
                    'message': f"Valid referral from {user_data.get('firstName', 'Friend')}"
                })
        
        if code in data_store['users']:
            user_data = data_store['users'][code]
            return jsonify({
                'success': True,
                'valid': True,
                'referrerId': code,
                'referrerName': user_data.get('firstName', 'Friend'),
                'referrerEmail': user_data.get('email', ''),
                'message': f"Valid referral from {user_data.get('firstName', 'Friend')}"
            })
        
        return jsonify({
            'success': True,
            'valid': False,
            'message': 'Invalid referral code'
        }), 200
        
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
        security_code = data.get('securityCode', '')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        if amount < MIN_WITHDRAW:
            return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAW} USDT'}), 400
        
        # Check daily limit
        today = datetime.now().strftime('%Y-%m-%d')
        daily_total = sum(
            w['amount'] for w in data_store['withdrawals']
            if w['userId'] == user_id and w['timestamp'].startswith(today) and w['status'] != 'rejected'
        )
        if daily_total + amount > MAX_WITHDRAW_DAILY:
            return jsonify({'error': f'Daily withdrawal limit is {MAX_WITHDRAW_DAILY} USDT'}), 400
        
        # Verify security code
        if user_id in data_store['withdrawal_security']:
            stored_code = data_store['withdrawal_security'][user_id]['code']
            if security_code != stored_code:
                return jsonify({'error': 'Invalid security code'}), 403
        
        # Check balance
        if user_id in data_store['users']:
            user = data_store['users'][user_id]
            total_balance = user['depositBalance'] + user['taskEarnings']
            if amount > total_balance:
                return jsonify({'error': 'Insufficient balance'}), 400
        
        withdrawal = {
            'id': generate_id(),
            'userId': user_id,
            'amount': amount,
            'method': method,
            'details': details,
            'status': 'pending',
            'timestamp': get_timestamp()
        }
        
        data_store['withdrawals'].append(withdrawal)
        
        data_store['notifications'].append({
            'userId': user_id,
            'type': 'withdrawal',
            'message': f'Withdrawal of {amount} USDT via {method} submitted.',
            'amount': amount,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        print(f"💸 New withdrawal: {amount} USDT from {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal submitted successfully',
            'withdrawal': withdrawal
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<user_id>', methods=['GET'])
def get_withdrawals(user_id):
    try:
        user_withdrawals = [w for w in data_store['withdrawals'] if w['userId'] == user_id]
        user_withdrawals.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'withdrawals': user_withdrawals[-20:]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/approve', methods=['POST'])
def approve_withdrawal(withdrawal_id):
    try:
        for withdrawal in data_store['withdrawals']:
            if withdrawal['id'] == withdrawal_id:
                withdrawal['status'] = 'completed'
                withdrawal['completedAt'] = get_timestamp()
                
                # Deduct from balance
                user_id = withdrawal['userId']
                if user_id in data_store['users']:
                    user = data_store['users'][user_id]
                    amount = withdrawal['amount']
                    if user['taskEarnings'] >= amount:
                        user['taskEarnings'] -= amount
                    else:
                        remaining = amount - user['taskEarnings']
                        user['taskEarnings'] = 0
                        user['depositBalance'] -= remaining
                
                data_store['notifications'].append({
                    'userId': user_id,
                    'type': 'withdrawal_approved',
                    'message': f'✅ Withdrawal of {withdrawal["amount"]} USDT approved!',
                    'amount': withdrawal['amount'],
                    'read': False,
                    'timestamp': get_timestamp()
                })
                
                print(f"✅ Withdrawal approved: {withdrawal_id}")
                
                return jsonify({
                    'success': True,
                    'message': 'Withdrawal approved',
                    'withdrawal': withdrawal
                })
        
        return jsonify({'error': 'Withdrawal not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<withdrawal_id>/reject', methods=['POST'])
def reject_withdrawal(withdrawal_id):
    try:
        for withdrawal in data_store['withdrawals']:
            if withdrawal['id'] == withdrawal_id:
                withdrawal['status'] = 'rejected'
                withdrawal['rejectedAt'] = get_timestamp()
                
                data_store['notifications'].append({
                    'userId': withdrawal['userId'],
                    'type': 'withdrawal_rejected',
                    'message': f'❌ Withdrawal of {withdrawal["amount"]} USDT was rejected.',
                    'amount': withdrawal['amount'],
                    'read': False,
                    'timestamp': get_timestamp()
                })
                
                print(f"❌ Withdrawal rejected: {withdrawal_id}")
                
                return jsonify({
                    'success': True,
                    'message': 'Withdrawal rejected',
                    'withdrawal': withdrawal
                })
        
        return jsonify({'error': 'Withdrawal not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdrawals/pending', methods=['GET'])
def get_pending_withdrawals():
    """Get all pending withdrawals (admin)"""
    try:
        pending = [w for w in data_store['withdrawals'] if w['status'] == 'pending']
        return jsonify({'success': True, 'withdrawals': pending})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: INVESTMENTS / PRODUCTS
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
        
        if user_id not in data_store['users']:
            return jsonify({'error': 'User not found'}), 404
        
        user = data_store['users'][user_id]
        if user['depositBalance'] < product['price']:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        user['depositBalance'] -= product['price']
        
        investment = {
            'id': generate_id(),
            'userId': user_id,
            'productName': product['name'],
            'amount': product['price'],
            'dailyEarnings': product['dailyEarnings'],
            'duration': product['duration'],
            'isFixed': product['isFixed'],
            'totalEarned': 0,
            'status': 'active',
            'purchaseDate': get_timestamp(),
            'lastClaimDate': get_timestamp()
        }
        
        data_store['investments'].append(investment)
        
        print(f"📊 Investment purchased: {product_name} by {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully purchased {product_name}',
            'investment': investment
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/investment/<user_id>', methods=['GET'])
def get_investments(user_id):
    try:
        user_investments = [i for i in data_store['investments'] if i['userId'] == user_id and i['status'] == 'active']
        
        for inv in user_investments:
            purchase_date = datetime.fromisoformat(inv['purchaseDate'])
            days_elapsed = (datetime.now() - purchase_date).days
            inv['daysLeft'] = max(0, inv['duration'] - days_elapsed)
            inv['progress'] = min(100, (days_elapsed / inv['duration']) * 100)
        
        return jsonify({'success': True, 'investments': user_investments})
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
        
        investment = next((i for i in data_store['investments'] if i['id'] == investment_id and i['userId'] == user_id), None)
        if not investment:
            return jsonify({'error': 'Investment not found'}), 404
        
        last_claim = datetime.fromisoformat(investment['lastClaimDate'])
        if last_claim.date() == datetime.now().date():
            return jsonify({'error': 'Already claimed today'}), 400
        
        if investment['isFixed']:
            earnings = investment['dailyEarnings']
        else:
            earnings = (investment['amount'] * investment['dailyEarnings']) / 100
        
        investment['totalEarned'] += earnings
        investment['lastClaimDate'] = get_timestamp()
        
        if user_id in data_store['users']:
            data_store['users'][user_id]['taskEarnings'] += earnings
        
        claim_key = f"{user_id}_{datetime.now().strftime('%Y%m%d')}"
        if claim_key not in data_store['daily_claims']:
            data_store['daily_claims'][claim_key] = []
        data_store['daily_claims'][claim_key].append({
            'investmentId': investment_id,
            'amount': earnings,
            'timestamp': get_timestamp()
        })
        
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
# API: NOTIFICATIONS
# ============================================
@app.route('/api/notifications/<user_id>', methods=['GET'])
def get_notifications(user_id):
    try:
        user_notifications = [n for n in data_store['notifications'] if n['userId'] == user_id]
        user_notifications.sort(key=lambda x: x['timestamp'], reverse=True)
        
        unread_count = len([n for n in user_notifications if not n.get('read', False)])
        
        return jsonify({
            'success': True,
            'notifications': user_notifications[-50:],
            'unreadCount': unread_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notification/read', methods=['POST'])
def mark_notification_read():
    try:
        data = request.json
        user_id = data.get('userId')
        notification_index = data.get('index')
        
        user_notifications = [n for n in data_store['notifications'] if n['userId'] == user_id]
        if notification_index < len(user_notifications):
            user_notifications[notification_index]['read'] = True
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    try:
        data = request.json
        user_id = data.get('userId')
        
        for notification in data_store['notifications']:
            if notification['userId'] == user_id:
                notification['read'] = True
        
        return jsonify({'success': True, 'message': 'All notifications marked as read'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: SECURITY
# ============================================
@app.route('/api/security/<user_id>', methods=['GET'])
def get_security_code(user_id):
    try:
        if user_id in data_store['withdrawal_security']:
            code = data_store['withdrawal_security'][user_id]['code']
            return jsonify({'success': True, 'code': code})
        return jsonify({'error': 'Security code not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/security/reset', methods=['POST'])
def reset_security_code():
    try:
        data = request.json
        user_id = data.get('userId')
        
        new_code = generate_security_code()
        data_store['withdrawal_security'][user_id] = {
            'code': new_code,
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        }
        
        return jsonify({'success': True, 'newCode': new_code})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: ADMIN
# ============================================
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    try:
        total_users = len(data_store['users'])
        total_deposits = sum(d['amount'] for d in data_store['deposits'] if d['status'] == 'approved')
        total_withdrawals = sum(w['amount'] for w in data_store['withdrawals'] if w['status'] == 'completed')
        active_investments = len([i for i in data_store['investments'] if i['status'] == 'active'])
        total_referrals = len(data_store['referrals'])
        total_referral_bonuses = sum(b['bonusAmount'] for b in data_store['referral_bonuses'])
        
        return jsonify({
            'success': True,
            'stats': {
                'totalUsers': total_users,
                'totalDeposits': total_deposits,
                'totalWithdrawals': total_withdrawals,
                'activeInvestments': active_investments,
                'totalReferrals': total_referrals,
                'totalReferralBonusesPaid': round(total_referral_bonuses, 2),
                'pendingDeposits': len([d for d in data_store['deposits'] if d['status'] == 'pending']),
                'pendingWithdrawals': len([w for w in data_store['withdrawals'] if w['status'] == 'pending']),
                'pendingReferralBonuses': len(data_store['pending_referral_bonuses'])
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/deposits/pending', methods=['GET'])
def get_pending_deposits():
    try:
        pending = [d for d in data_store['deposits'] if d['status'] == 'pending']
        return jsonify({'success': True, 'deposits': pending})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/referrals', methods=['GET'])
def get_all_referrals():
    try:
        return jsonify({
            'success': True,
            'totalReferrals': len(data_store['referrals']),
            'totalBonusesPaid': sum(b['bonusAmount'] for b in data_store['referral_bonuses']),
            'pendingBonuses': len(data_store['pending_referral_bonuses']),
            'referrals': data_store['referrals'][-50:],
            'bonuses': data_store['referral_bonuses'][-50:]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# DATA PERSISTENCE (Save/Load)
# ============================================
@app.route('/api/data/save', methods=['POST'])
def save_data():
    """Save current data to file"""
    try:
        with open('data_backup.json', 'w') as f:
            json.dump(data_store, f, indent=2)
        return jsonify({'success': True, 'message': 'Data saved successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/data/load', methods=['POST'])
def load_data():
    """Load data from file"""
    try:
        if os.path.exists('data_backup.json'):
            with open('data_backup.json', 'r') as f:
                loaded_data = json.load(f)
                data_store.update(loaded_data)
            return jsonify({'success': True, 'message': 'Data loaded successfully'})
        return jsonify({'error': 'No backup file found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Auto-save on startup
if os.path.exists('data_backup.json'):
    try:
        with open('data_backup.json', 'r') as f:
            loaded_data = json.load(f)
            data_store.update(loaded_data)
        print("✅ Data loaded from backup")
    except:
        print("⚠️ Could not load backup, starting fresh")

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
    print("🚀 SAFE Platform Server v2.0")
    print(f"📍 Running on port: {port}")
    print(f"📱 Telebirr: {TELEBIRR_NUMBER} ({TELEBIRR_NAME})")
    print(f"💳 Wallet: {WALLET_ADDRESS}")
    print(f"👥 Referral Bonus: {REFERRAL_BONUS_PERCENTAGE}% of first deposit")
    print(f"⭐ Referral Points: {REFERRAL_POINTS}")
    print(f"👤 Users: {len(data_store['users'])}")
    print(f"💰 Deposits: {len(data_store['deposits'])}")
    print(f"💸 Withdrawals: {len(data_store['withdrawals'])}")
    print("")
    print("📋 Available Routes:")
    print("  /              - Home/Login")
    print("  /home          - Dashboard")
    print("  /deposite      - Deposit Page")
    print("  /withdraw      - Withdrawal Page")
    print("  /product       - Investments")
    print("  /referral      - Referral Page")
    print("  /notification  - Notifications")
    print("  /daily         - Daily Earnings")
    print("  /admin.html    - Admin Panel")
    print("")
    print("🔗 API Endpoints:")
    print("  POST /api/deposit              - Submit deposit")
    print("  GET  /api/deposit/<user_id>    - Get user deposits")
    print("  GET  /api/deposit/all          - Get all deposits (admin)")
    print("  POST /api/deposit/<id>/approve - Approve deposit")
    print("  POST /api/deposit/<id>/reject  - Reject deposit")
    print("  POST /api/withdraw             - Submit withdrawal")
    print("  POST /api/withdraw/<id>/approve- Approve withdrawal")
    print("  POST /api/withdraw/<id>/reject - Reject withdrawal")
    print("  GET  /api/admin/stats          - Admin statistics")
    print("  POST /api/data/save            - Save data to file")
    print("  POST /api/data/load            - Load data from file")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False)
