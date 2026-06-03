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
# IN-MEMORY STORAGE (Lightweight for 512MB RAM)
# ============================================
# In production, replace with SQLite for persistence
data_store = {
    'users': {},
    'deposits': [],
    'withdrawals': [],
    'investments': [],
    'referrals': [],
    'notifications': [],
    'withdrawal_security': {},
    'daily_claims': {}
}

# ============================================
# CONFIGURATION
# ============================================
ADMIN_EMAILS = ['admin@safe.com']  # Add admin emails
TELEBIRR_NUMBER = '0949399753'
TELEBIRR_NAME = 'Abinet'
WALLET_ADDRESS = 'TK3RviHLX31oC6qNdfaF9Wuh8JJ4bQqAXu'
REFERRAL_BONUS = 10  # $10 per referral
MIN_DEPOSIT = 10
MIN_WITHDRAW = 20
MAX_WITHDRAW_DAILY = 500
WEEKEND_DAYS = [5, 6]  # Saturday=5, Sunday=6 (Python weekday)

# ============================================
# UTILITY FUNCTIONS
# ============================================
def generate_id(length=12):
    """Generate random ID"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_referral_code():
    """Generate 8-char referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_security_code():
    """Generate 4-digit security code"""
    return str(random.randint(1000, 9999))

def is_weekend():
    """Check if today is weekend"""
    return datetime.now().weekday() in WEEKEND_DAYS

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_timestamp():
    """Get current timestamp"""
    return datetime.utcnow().isoformat()

def format_date(dt_string):
    """Format date string"""
    try:
        dt = datetime.fromisoformat(dt_string)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return dt_string

# ============================================
# STATIC FILE SERVING - MAIN ROUTES
# ============================================

@app.route('/')
def index():
    """Main index page"""
    return send_from_directory('.', 'index.html')

@app.route('/home')
def home():
    """Home page"""
    return send_from_directory('.', 'home.html')

@app.route('/referral')
def referral():
    """Referral page"""
    return send_from_directory('.', 'referral.html')

@app.route('/notification')
def notification():
    """Notification page"""
    return send_from_directory('.', 'notification.html')

@app.route('/product')
def product():
    """Product/Investment page"""
    return send_from_directory('.', 'product.html')

@app.route('/daily')
def daily():
    """Daily earnings page"""
    return send_from_directory('.', 'daily.html')

@app.route('/withdraw')
def withdraw():
    """Withdrawal page"""
    return send_from_directory('.', 'withdraw.html')

@app.route('/deposite')
def deposite():
    """Deposit page"""
    return send_from_directory('.', 'deposite.html')

# Fallback for any other paths
@app.route('/<path:path>')
def serve_static(path):
    """Serve static files or fallback to index"""
    if os.path.exists(path):
        return send_from_directory('.', path)
    # Check if it's an HTML file without extension
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
        'memory_usage': f"{len(json.dumps(data_store)) / 1024:.2f} KB"
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
        'referral_bonus': REFERRAL_BONUS,
        'min_deposit': MIN_DEPOSIT,
        'min_withdraw': MIN_WITHDRAW,
        'routes': {
            'home': '/home',
            'referral': '/referral',
            'notification': '/notification',
            'product': '/product',
            'daily': '/daily',
            'withdraw': '/withdraw',
            'deposite': '/deposite'
        }
    })

# ============================================
# API: USER MANAGEMENT
# ============================================
@app.route('/api/user/create', methods=['POST'])
def create_user():
    """Create new user record"""
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
        
        # Handle referral
        if data.get('referredBy'):
            referrer_id = data['referredBy']
            if referrer_id in data_store['users']:
                data_store['users'][referrer_id]['referralCount'] += 1
                data_store['users'][referrer_id]['referralBonus'] += REFERRAL_BONUS
                
                data_store['referrals'].append({
                    'referrerId': referrer_id,
                    'referredUserId': user_id,
                    'referredEmail': data.get('email', ''),
                    'bonusEarned': REFERRAL_BONUS,
                    'timestamp': get_timestamp(),
                    'status': 'active'
                })
                
                # Notification to referrer
                data_store['notifications'].append({
                    'userId': referrer_id,
                    'type': 'referral',
                    'message': f"New referral joined! +${REFERRAL_BONUS} bonus earned.",
                    'referredUserId': user_id,
                    'read': False,
                    'timestamp': get_timestamp()
                })
        
        return jsonify({
            'success': True,
            'message': 'User created successfully',
            'referralCode': referral_code,
            'securityCode': security_code
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get user data"""
    try:
        if user_id in data_store['users']:
            return jsonify({
                'success': True,
                'user': data_store['users'][user_id]
            })
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/<user_id>/balance', methods=['GET'])
def get_balance(user_id):
    """Get user balance"""
    try:
        if user_id in data_store['users']:
            user = data_store['users'][user_id]
            return jsonify({
                'success': True,
                'depositBalance': user['depositBalance'],
                'taskEarnings': user['taskEarnings'],
                'points': user['points'],
                'totalBalance': user['depositBalance'] + user['taskEarnings']
            })
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: DEPOSIT
# ============================================
@app.route('/api/deposit', methods=['POST'])
def submit_deposit():
    """Submit deposit request"""
    try:
        data = request.json
        user_id = data.get('userId')
        amount = float(data.get('amount', 0))
        method = data.get('method', 'crypto')  # telebirr or crypto
        reference = data.get('reference', '')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        if amount < MIN_DEPOSIT:
            return jsonify({'error': f'Minimum deposit is {MIN_DEPOSIT} USDT'}), 400
        
        deposit = {
            'id': generate_id(),
            'userId': user_id,
            'amount': amount,
            'method': method,
            'reference': reference,
            'status': 'pending',
            'timestamp': get_timestamp()
        }
        
        data_store['deposits'].append(deposit)
        
        # Notification
        data_store['notifications'].append({
            'userId': user_id,
            'type': 'deposit',
            'message': f'Deposit of {amount} USDT submitted via {method}. Pending approval.',
            'amount': amount,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        return jsonify({
            'success': True,
            'message': 'Deposit submitted successfully',
            'deposit': deposit
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<user_id>', methods=['GET'])
def get_deposits(user_id):
    """Get user deposits"""
    try:
        user_deposits = [d for d in data_store['deposits'] if d['userId'] == user_id]
        user_deposits.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'deposits': user_deposits[-20:]  # Last 20
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deposit/<deposit_id>/approve', methods=['POST'])
def approve_deposit(deposit_id):
    """Approve deposit (admin)"""
    try:
        for deposit in data_store['deposits']:
            if deposit['id'] == deposit_id:
                deposit['status'] = 'approved'
                user_id = deposit['userId']
                
                if user_id in data_store['users']:
                    data_store['users'][user_id]['depositBalance'] += deposit['amount']
                
                # Notification
                data_store['notifications'].append({
                    'userId': user_id,
                    'type': 'deposit_approved',
                    'message': f'Deposit of {deposit["amount"]} USDT approved!',
                    'amount': deposit['amount'],
                    'read': False,
                    'timestamp': get_timestamp()
                })
                
                return jsonify({
                    'success': True,
                    'message': 'Deposit approved',
                    'deposit': deposit
                })
        
        return jsonify({'error': 'Deposit not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: WITHDRAWAL
# ============================================
@app.route('/api/withdraw', methods=['POST'])
def submit_withdrawal():
    """Submit withdrawal request"""
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
            if w['userId'] == user_id and w['timestamp'].startswith(today)
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
        
        # Notification
        data_store['notifications'].append({
            'userId': user_id,
            'type': 'withdrawal',
            'message': f'Withdrawal of {amount} USDT via {method} submitted.',
            'amount': amount,
            'read': False,
            'timestamp': get_timestamp()
        })
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal submitted successfully',
            'withdrawal': withdrawal
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/withdraw/<user_id>', methods=['GET'])
def get_withdrawals(user_id):
    """Get user withdrawals"""
    try:
        user_withdrawals = [w for w in data_store['withdrawals'] if w['userId'] == user_id]
        user_withdrawals.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'withdrawals': user_withdrawals[-20:]
        })
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
    """Get all products"""
    return jsonify({
        'success': True,
        'products': PRODUCTS
    })

@app.route('/api/investment/buy', methods=['POST'])
def buy_investment():
    """Purchase investment product"""
    try:
        data = request.json
        user_id = data.get('userId')
        product_name = data.get('productName')
        
        if not user_id or not product_name:
            return jsonify({'error': 'User ID and product name required'}), 400
        
        # Find product
        product = next((p for p in PRODUCTS if p['name'] == product_name), None)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Check balance
        if user_id not in data_store['users']:
            return jsonify({'error': 'User not found'}), 404
        
        user = data_store['users'][user_id]
        if user['depositBalance'] < product['price']:
            return jsonify({'error': 'Insufficient balance'}), 400
        
        # Deduct balance
        user['depositBalance'] -= product['price']
        
        # Create investment
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
        
        return jsonify({
            'success': True,
            'message': f'Successfully purchased {product_name}',
            'investment': investment
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/investment/<user_id>', methods=['GET'])
def get_investments(user_id):
    """Get user investments"""
    try:
        user_investments = [i for i in data_store['investments'] if i['userId'] == user_id and i['status'] == 'active']
        
        # Calculate days remaining for each
        for inv in user_investments:
            purchase_date = datetime.fromisoformat(inv['purchaseDate'])
            days_elapsed = (datetime.now() - purchase_date).days
            inv['daysLeft'] = max(0, inv['duration'] - days_elapsed)
            inv['progress'] = min(100, (days_elapsed / inv['duration']) * 100)
        
        return jsonify({
            'success': True,
            'investments': user_investments
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: DAILY CLAIMS
# ============================================
@app.route('/api/daily/claim', methods=['POST'])
def claim_daily_earnings():
    """Claim daily earnings from investment"""
    try:
        data = request.json
        user_id = data.get('userId')
        investment_id = data.get('investmentId')
        
        if not user_id or not investment_id:
            return jsonify({'error': 'User ID and Investment ID required'}), 400
        
        # Check weekend
        if is_weekend():
            return jsonify({'error': 'Cannot claim on weekends'}), 403
        
        # Find investment
        investment = next((i for i in data_store['investments'] if i['id'] == investment_id and i['userId'] == user_id), None)
        if not investment:
            return jsonify({'error': 'Investment not found'}), 404
        
        # Check if already claimed today
        last_claim = datetime.fromisoformat(investment['lastClaimDate'])
        if last_claim.date() == datetime.now().date():
            return jsonify({'error': 'Already claimed today'}), 400
        
        # Calculate earnings
        if investment['isFixed']:
            earnings = investment['dailyEarnings']
        else:
            earnings = (investment['amount'] * investment['dailyEarnings']) / 100
        
        # Update investment
        investment['totalEarned'] += earnings
        investment['lastClaimDate'] = get_timestamp()
        
        # Update user
        if user_id in data_store['users']:
            data_store['users'][user_id]['taskEarnings'] += earnings
        
        # Track claim
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
    """Check if user can claim today"""
    try:
        if is_weekend():
            return jsonify({
                'canClaim': False,
                'reason': 'Weekend - no claims allowed',
                'isWeekend': True
            })
        
        return jsonify({
            'canClaim': True,
            'isWeekend': False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: REFERRAL SYSTEM
# ============================================
@app.route('/api/referral/stats/<user_id>', methods=['GET'])
def get_referral_stats(user_id):
    """Get referral statistics"""
    try:
        if user_id not in data_store['users']:
            return jsonify({'error': 'User not found'}), 404
        
        user = data_store['users'][user_id]
        user_referrals = [r for r in data_store['referrals'] if r['referrerId'] == user_id]
        
        # Updated referral link to use /referral route
        referral_link = f"{request.host_url}referral?ref={user_id}"
        
        return jsonify({
            'success': True,
            'referralCode': user['referralCode'],
            'referralLink': referral_link,
            'referralCount': user['referralCount'],
            'referralBonus': user['referralBonus'],
            'referrals': user_referrals
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: NOTIFICATIONS
# ============================================
@app.route('/api/notifications/<user_id>', methods=['GET'])
def get_notifications(user_id):
    """Get user notifications"""
    try:
        user_notifications = [n for n in data_store['notifications'] if n['userId'] == user_id]
        user_notifications.sort(key=lambda x: x['timestamp'], reverse=True)
        
        unread_count = len([n for n in user_notifications if not n.get('read', False)])
        
        return jsonify({
            'success': True,
            'notifications': user_notifications[-50:],  # Last 50
            'unreadCount': unread_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notification/read', methods=['POST'])
def mark_notification_read():
    """Mark notification as read"""
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

# ============================================
# API: SECURITY
# ============================================
@app.route('/api/security/<user_id>', methods=['GET'])
def get_security_code(user_id):
    """Get user security code (masked)"""
    try:
        if user_id in data_store['withdrawal_security']:
            code = data_store['withdrawal_security'][user_id]['code']
            return jsonify({
                'success': True,
                'code': code  # In production, mask this
            })
        return jsonify({'error': 'Security code not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/security/reset', methods=['POST'])
def reset_security_code():
    """Reset security code"""
    try:
        data = request.json
        user_id = data.get('userId')
        
        new_code = generate_security_code()
        data_store['withdrawal_security'][user_id] = {
            'code': new_code,
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        }
        
        return jsonify({
            'success': True,
            'newCode': new_code
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API: ADMIN
# ============================================
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    """Get platform statistics (admin)"""
    try:
        total_users = len(data_store['users'])
        total_deposits = sum(d['amount'] for d in data_store['deposits'] if d['status'] == 'approved')
        total_withdrawals = sum(w['amount'] for w in data_store['withdrawals'] if w['status'] == 'completed')
        active_investments = len([i for i in data_store['investments'] if i['status'] == 'active'])
        total_referrals = len(data_store['referrals'])
        
        return jsonify({
            'success': True,
            'stats': {
                'totalUsers': total_users,
                'totalDeposits': total_deposits,
                'totalWithdrawals': total_withdrawals,
                'activeInvestments': active_investments,
                'totalReferrals': total_referrals,
                'pendingDeposits': len([d for d in data_store['deposits'] if d['status'] == 'pending']),
                'pendingWithdrawals': len([w for w in data_store['withdrawals'] if w['status'] == 'pending'])
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/deposits/pending', methods=['GET'])
def get_pending_deposits():
    """Get pending deposits (admin)"""
    try:
        pending = [d for d in data_store['deposits'] if d['status'] == 'pending']
        return jsonify({
            'success': True,
            'deposits': pending
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/withdrawals/pending', methods=['GET'])
def get_pending_withdrawals():
    """Get pending withdrawals (admin)"""
    try:
        pending = [w for w in data_store['withdrawals'] if w['status'] == 'pending']
        return jsonify({
            'success': True,
            'withdrawals': pending
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# ERROR HANDLERS
# ============================================
@app.errorhandler(404)
def not_found(e):
    # Check if it's an API request
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    # For web requests, return index.html (SPA fallback)
    return send_from_directory('.', 'index.html')

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 50)
    print("SAFE Platform Server")
    print(f"Running on port: {port}")
    print(f"Telebirr: {TELEBIRR_NUMBER} ({TELEBIRR_NAME})")
    print(f"Wallet: {WALLET_ADDRESS}")
    print(f"Referral Bonus: ${REFERRAL_BONUS}")
    print("")
    print("Available Routes:")
    print("  /              - Home/Index")
    print("  /home          - Home Dashboard")
    print("  /referral      - Referral Page")
    print("  /notification  - Notifications")
    print("  /product       - Products/Investments")
    print("  /daily         - Daily Earnings")
    print("  /withdraw      - Withdrawals")
    print("  /deposite      - Deposits")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=False)
