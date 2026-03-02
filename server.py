<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Telegram Multi-Account Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }

        body {
            background: #0e1621;
            height: 100vh;
            display: flex;
            flex-direction: column;
            color: #fff;
            overflow: hidden;
        }

        /* ----- Header with account switcher ----- */
        .app-header {
            background: #17212b;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #2b3945;
            flex-shrink: 0;
            z-index: 10;
        }

        .account-switcher {
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            padding: 6px 12px;
            border-radius: 30px;
            transition: background 0.2s;
            position: relative;
        }

        .account-switcher:hover {
            background: #242f3d;
        }

        .current-avatar {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            background: linear-gradient(145deg, #2b5278, #4c9ce0);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.4rem;
            font-weight: 600;
            color: white;
        }

        .current-info {
            display: flex;
            flex-direction: column;
        }

        .current-name {
            font-size: 1rem;
            font-weight: 600;
            color: #fff;
        }

        .current-phone {
            font-size: 0.75rem;
            color: #8e9fad;
        }

        .dropdown-icon {
            color: #8e9fad;
            font-size: 1.2rem;
            margin-left: 8px;
        }

        /* Dropdown menu */
        .account-dropdown {
            position: absolute;
            top: 60px;
            left: 16px;
            background: #17212b;
            border: 1px solid #2b3945;
            border-radius: 12px;
            width: 280px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.5);
            display: none;
            z-index: 100;
            max-height: 400px;
            overflow-y: auto;
        }

        .account-dropdown.show {
            display: block;
        }

        .dropdown-item {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            gap: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }

        .dropdown-item:hover {
            background: #242f3d;
        }

        .dropdown-item:first-child {
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        }

        .dropdown-item:last-child {
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
        }

        .dropdown-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: #2b5278;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            color: white;
            flex-shrink: 0;
        }

        .dropdown-info {
            flex: 1;
            min-width: 0;
        }

        .dropdown-name {
            font-weight: 600;
            font-size: 0.95rem;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .dropdown-phone {
            font-size: 0.7rem;
            color: #8e9fad;
        }

        .header-actions {
            display: flex;
            gap: 8px;
        }

        .header-actions a, .header-actions button {
            background: #2b3945;
            color: #6ab2f2;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 30px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: 0.2s;
            white-space: nowrap;
            border: none;
            cursor: pointer;
        }

        .header-actions a:hover, .header-actions button:hover {
            background: #3a4a5a;
        }

        .refresh-btn {
            background: #2b3945;
            color: #6ab2f2;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: 0.2s;
        }

        .refresh-btn:hover {
            background: #3a4a5a;
            transform: rotate(180deg);
        }

        .refresh-btn.refreshing {
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        /* ----- Main layout (two columns) ----- */
        .main-layout {
            display: flex;
            flex: 1;
            overflow: hidden;
            min-height: 0;
        }

        /* Chats sidebar */
        .chats-panel {
            width: 360px;
            background: #17212b;
            border-right: 1px solid #2b3945;
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }

        .chats-panel-header {
            padding: 16px;
            border-bottom: 1px solid #2b3945;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chats-panel-header h3 {
            color: #8e9fad;
            font-weight: 500;
            font-size: 0.95rem;
            letter-spacing: 0.5px;
        }

        .chats-panel-header .badge {
            background: #2b5278;
            color: white;
            padding: 4px 8px;
            border-radius: 20px;
            font-size: 0.75rem;
        }

        .chats-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        .chat-item {
            display: flex;
            align-items: center;
            padding: 12px;
            border-radius: 12px;
            cursor: pointer;
            transition: background 0.2s;
            margin-bottom: 4px;
        }

        .chat-item:hover {
            background: #242f3d;
        }

        .chat-item.active {
            background: #2b5278;
        }

        .chat-avatar {
            width: 54px;
            height: 54px;
            border-radius: 50%;
            background: linear-gradient(145deg, #2b5278, #4c9ce0);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            font-weight: 600;
            color: white;
            margin-right: 12px;
            flex-shrink: 0;
        }

        .chat-info {
            flex: 1;
            min-width: 0;
        }

        .chat-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
        }

        .chat-name {
            font-weight: 600;
            font-size: 1rem;
            color: #fff;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 180px;
        }

        .chat-time {
            font-size: 0.75rem;
            color: #8e9fad;
            flex-shrink: 0;
            margin-left: 8px;
        }

        .chat-last-msg {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chat-last-text {
            font-size: 0.85rem;
            color: #8e9fad;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 200px;
        }

        .chat-unread {
            background: #4c9ce0;
            color: white;
            font-size: 0.7rem;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 12px;
            min-width: 20px;
            text-align: center;
            margin-left: 8px;
        }

        /* Messages panel */
        .messages-panel {
            flex: 1;
            background: #0e1621;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .messages-header {
            background: #17212b;
            padding: 16px 20px;
            border-bottom: 1px solid #2b3945;
            flex-shrink: 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .messages-header h2 {
            font-size: 1.2rem;
            font-weight: 500;
            color: #fff;
        }

        .messages-header-actions {
            display: flex;
            gap: 8px;
        }

        .messages-header-actions button {
            background: #2b3945;
            color: #6ab2f2;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: 0.2s;
        }

        .messages-header-actions button:hover {
            background: #3a4a5a;
        }

        .messages-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .message-wrapper {
            display: flex;
            flex-direction: column;
        }

        .message-wrapper.outgoing {
            align-items: flex-end;
        }

        .message-bubble {
            max-width: 75%;
            padding: 12px 16px;
            border-radius: 20px;
            word-wrap: break-word;
            line-height: 1.5;
            font-size: 0.95rem;
            position: relative;
        }

        .incoming .message-bubble {
            background: #17212b;
            color: #fff;
            border-bottom-left-radius: 4px;
        }

        .outgoing .message-bubble {
            background: #2b5278;
            color: #fff;
            border-bottom-right-radius: 4px;
        }

        .media-message {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255,255,255,0.05);
            padding: 8px 12px;
            border-radius: 12px;
            margin-bottom: 4px;
        }

        .media-icon {
            font-size: 1.5rem;
        }

        .media-label {
            font-size: 0.9rem;
            color: #8e9fad;
        }

        .message-meta {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 4px;
            margin-top: 4px;
            font-size: 0.7rem;
            color: #8e9fad;
            padding-right: 4px;
        }

        .outgoing .message-meta {
            color: #a0c0e0;
        }

        .compose-area {
            background: #17212b;
            padding: 16px 20px;
            border-top: 1px solid #2b3945;
            display: flex;
            gap: 12px;
            align-items: center;
            flex-shrink: 0;
        }

        .compose-input {
            flex: 1;
            background: #242f3d;
            border: none;
            border-radius: 30px;
            padding: 14px 18px;
            color: #fff;
            font-size: 1rem;
            outline: none;
        }

        .compose-input::placeholder {
            color: #8e9fad;
        }

        .compose-input:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .send-btn {
            background: #4c9ce0;
            border: none;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: 0.2s;
            color: white;
            font-size: 1.3rem;
        }

        .send-btn:hover:not(:disabled) {
            background: #6ab2f2;
        }

        .send-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .loading, .empty-state {
            text-align: center;
            padding: 40px;
            color: #8e9fad;
            font-size: 1rem;
        }

        .error-message {
            background: #8e2b2b;
            color: white;
            padding: 12px;
            border-radius: 8px;
            margin: 16px;
            text-align: center;
        }

        .toast {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: #17212b;
            color: white;
            padding: 12px 24px;
            border-radius: 30px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            border: 1px solid #2b3945;
            z-index: 1000;
            display: none;
            animation: slideUp 0.3s ease;
        }

        @keyframes slideUp {
            from {
                transform: translate(-50%, 100%);
                opacity: 0;
            }
            to {
                transform: translate(-50%, 0);
                opacity: 1;
            }
        }

        .toast.show {
            display: block;
        }

        .toast.success {
            border-left: 4px solid #4c9ce0;
        }

        .toast.error {
            border-left: 4px solid #e04c4c;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1001;
            align-items: center;
            justify-content: center;
        }

        .modal.show {
            display: flex;
        }

        .modal-content {
            background: #17212b;
            border-radius: 16px;
            padding: 24px;
            width: 90%;
            max-width: 400px;
            border: 1px solid #2b3945;
        }

        .modal-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 16px;
            color: #fff;
        }

        .modal-body {
            margin-bottom: 24px;
            color: #8e9fad;
        }

        .modal-actions {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
        }

        .modal-btn {
            padding: 10px 20px;
            border-radius: 30px;
            border: none;
            font-size: 0.95rem;
            cursor: pointer;
            transition: 0.2s;
        }

        .modal-btn.cancel {
            background: #2b3945;
            color: #fff;
        }

        .modal-btn.confirm {
            background: #8e2b2b;
            color: #fff;
        }

        .modal-btn.confirm:hover {
            background: #b33a3a;
        }

        /* Responsive */
        @media (max-width: 700px) {
            .chats-panel {
                width: 280px;
            }
        }

        @media (max-width: 550px) {
            .main-layout {
                flex-direction: column;
            }
            .chats-panel {
                width: 100%;
                height: 40%;
                border-right: none;
                border-bottom: 1px solid #2b3945;
            }
            .messages-panel {
                height: 60%;
            }
        }
    </style>
</head>
<body>
    <div class="app-header">
        <!-- Account switcher -->
        <div class="account-switcher" id="accountSwitcher">
            <div class="current-avatar" id="currentAvatar">?</div>
            <div class="current-info">
                <span class="current-name" id="currentName">Loading...</span>
                <span class="current-phone" id="currentPhone"></span>
            </div>
            <span class="dropdown-icon">▼</span>
        </div>

        <!-- Dropdown menu -->
        <div class="account-dropdown" id="accountDropdown"></div>

        <div class="header-actions">
            <button class="refresh-btn" id="refreshBtn" title="Refresh chats">↻</button>
            <a href="/login">➕ Add Account</a>
        </div>
    </div>

    <div class="main-layout">
        <!-- Chats Panel -->
        <div class="chats-panel">
            <div class="chats-panel-header">
                <h3>CHATS</h3>
                <span class="badge" id="totalChats">0</span>
            </div>
            <div class="chats-scroll" id="chatsList">
                <div class="loading">Loading chats...</div>
            </div>
        </div>

        <!-- Messages Panel -->
        <div class="messages-panel">
            <div class="messages-header" id="messagesHeader" style="display: none;">
                <h2 id="currentChatTitle"></h2>
                <div class="messages-header-actions">
                    <button onclick="refreshMessages()" title="Refresh messages">↻</button>
                </div>
            </div>
            <div class="messages-scroll" id="messagesList">
                <div class="empty-state">👈 Select a chat to start messaging</div>
            </div>
            <div class="compose-area" id="composeArea" style="display: none;">
                <input type="text" class="compose-input" id="messageInput" placeholder="Type a message..." autocomplete="off">
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">📤</button>
            </div>
        </div>
    </div>

    <!-- Remove Account Modal -->
    <div class="modal" id="removeModal">
        <div class="modal-content">
            <div class="modal-title">Remove Account</div>
            <div class="modal-body" id="removeModalBody">Are you sure you want to remove this account?</div>
            <div class="modal-actions">
                <button class="modal-btn cancel" onclick="hideRemoveModal()">Cancel</button>
                <button class="modal-btn confirm" onclick="confirmRemoveAccount()">Remove</button>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast" id="toast"></div>

    <script>
        // ---------- State ----------
        let accounts = [];
        let currentAccount = null;
        let currentChat = null;
        let chats = [];
        let messages = [];
        let refreshInterval = null;
        let accountToRemove = null;

        // ---------- DOM elements ----------
        const dropdown = document.getElementById('accountDropdown');
        const switcher = document.getElementById('accountSwitcher');
        const currentAvatar = document.getElementById('currentAvatar');
        const currentName = document.getElementById('currentName');
        const currentPhone = document.getElementById('currentPhone');
        const chatsListDiv = document.getElementById('chatsList');
        const messagesHeader = document.getElementById('messagesHeader');
        const currentChatTitle = document.getElementById('currentChatTitle');
        const messagesListDiv = document.getElementById('messagesList');
        const composeArea = document.getElementById('composeArea');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const totalChatsSpan = document.getElementById('totalChats');
        const refreshBtn = document.getElementById('refreshBtn');
        const removeModal = document.getElementById('removeModal');
        const removeModalBody = document.getElementById('removeModalBody');
        const toast = document.getElementById('toast');

        // ---------- Helper Functions ----------
        function showToast(message, type = 'success') {
            toast.textContent = message;
            toast.className = `toast show ${type}`;
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }

        function showError(message) {
            showToast(message, 'error');
        }

        function setLoading(element, isLoading) {
            if (isLoading) {
                element.classList.add('refreshing');
                element.disabled = true;
            } else {
                element.classList.remove('refreshing');
                element.disabled = false;
            }
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', function(event) {
            if (!switcher.contains(event.target) && !dropdown.contains(event.target)) {
                dropdown.classList.remove('show');
            }
        });

        // Toggle dropdown
        switcher.addEventListener('click', function(event) {
            event.stopPropagation();
            dropdown.classList.toggle('show');
        });

        // ---------- Load Accounts on Page Load ----------
        window.addEventListener('load', async () => {
            await loadAccounts();
            
            // Auto-refresh every 30 seconds if an account is selected
            refreshInterval = setInterval(() => {
                if (currentAccount) {
                    loadChatsForCurrentAccount(false);
                }
            }, 30000);
        });

        window.addEventListener('beforeunload', () => {
            if (refreshInterval) {
                clearInterval(refreshInterval);
            }
        });

        // Load all accounts from server
        async function loadAccounts() {
            try {
                const res = await fetch('/api/accounts');
                const data = await res.json();
                
                if (data.success) {
                    accounts = data.accounts || [];
                    
                    if (accounts.length > 0) {
                        // Check if there's a previously selected account in localStorage
                        const lastAccountId = localStorage.getItem('lastSelectedAccount');
                        if (lastAccountId) {
                            const savedAccount = accounts.find(a => a.id == lastAccountId);
                            if (savedAccount) {
                                currentAccount = savedAccount;
                            } else {
                                currentAccount = accounts[0];
                            }
                        } else {
                            currentAccount = accounts[0];
                        }
                        
                        updateHeaderForCurrentAccount();
                        renderDropdown();
                        await loadChatsForCurrentAccount();
                    } else {
                        // No accounts found
                        currentAccount = null;
                        updateHeaderForNoAccount();
                        renderDropdown();
                        showNoAccountState();
                    }
                } else {
                    showError('Failed to load accounts');
                }
            } catch (err) {
                console.error('Error fetching accounts:', err);
                showError('Failed to load accounts. Check server connection.');
                chatsListDiv.innerHTML = '<div class="empty-state">Cannot connect to server. <a href="/dashboard" style="color:#6ab2f2;">Retry</a></div>';
            }
        }

        function updateHeaderForCurrentAccount() {
            if (!currentAccount) return;
            
            const name = currentAccount.name || 'User';
            const phone = currentAccount.phone || '';
            const initial = name.charAt(0).toUpperCase() || '?';
            
            currentAvatar.textContent = initial;
            currentName.textContent = name;
            currentPhone.textContent = phone;
            
            // Save last selected account
            localStorage.setItem('lastSelectedAccount', currentAccount.id);
        }

        function updateHeaderForNoAccount() {
            currentAvatar.textContent = '?';
            currentName.textContent = 'No Account';
            currentPhone.textContent = '';
            localStorage.removeItem('lastSelectedAccount');
        }

        function showNoAccountState() {
            chatsListDiv.innerHTML = '<div class="empty-state">No accounts. <a href="/login" style="color:#6ab2f2;">Add one</a>.</div>';
            messagesHeader.style.display = 'none';
            composeArea.style.display = 'none';
            messagesListDiv.innerHTML = '<div class="empty-state">Add an account to start messaging</div>';
            totalChatsSpan.textContent = '0';
        }

        function renderDropdown() {
            if (!accounts.length) {
                dropdown.innerHTML = '<div class="dropdown-item">No accounts</div>';
                return;
            }
            
            let html = '';
            accounts.forEach(acc => {
                const accName = acc.name || 'User';
                const accPhone = acc.phone || '';
                const initial = accName.charAt(0).toUpperCase() || '?';
                const isCurrent = acc.id === currentAccount?.id ? '✓' : '';
                
                html += `
                    <div class="dropdown-item" onclick="switchAccount(${acc.id})">
                        <div class="dropdown-avatar">${escapeHtml(initial)}</div>
                        <div class="dropdown-info">
                            <div class="dropdown-name">${escapeHtml(accName)}</div>
                            <div class="dropdown-phone">${escapeHtml(accPhone)}</div>
                        </div>
                        <span style="color:#6ab2f2;">${isCurrent}</span>
                    </div>
                `;
            });
            
            // Add remove account option if there are accounts
            if (accounts.length > 0) {
                html += `
                    <div class="dropdown-item" style="border-top: 1px solid #2b3945;" onclick="showRemoveModal()">
                        <div class="dropdown-avatar" style="background: #8e2b2b;">−</div>
                        <div class="dropdown-info">
                            <div class="dropdown-name" style="color: #ff6b6b;">Remove Current Account</div>
                        </div>
                    </div>
                `;
            }
            
            dropdown.innerHTML = html;
        }

        // Switch to another account
        window.switchAccount = async function(accountId) {
            accountId = parseInt(accountId);
            const newAccount = accounts.find(a => a.id === accountId);
            
            if (!newAccount || newAccount.id === currentAccount?.id) {
                dropdown.classList.remove('show');
                return;
            }
            
            currentAccount = newAccount;
            currentChat = null;
            
            updateHeaderForCurrentAccount();
            renderDropdown();
            dropdown.classList.remove('show');
            
            // Reset UI
            messagesHeader.style.display = 'none';
            composeArea.style.display = 'none';
            messagesListDiv.innerHTML = '<div class="empty-state">👈 Select a chat to start messaging</div>';
            
            await loadChatsForCurrentAccount();
        };

        // Remove account modal
        function showRemoveModal() {
            if (!currentAccount) return;
            accountToRemove = currentAccount.id;
            removeModalBody.textContent = `Are you sure you want to remove account "${currentAccount.name || currentAccount.phone}"?`;
            removeModal.classList.add('show');
            dropdown.classList.remove('show');
        }

        function hideRemoveModal() {
            removeModal.classList.remove('show');
            accountToRemove = null;
        }

        window.confirmRemoveAccount = async function() {
            if (!accountToRemove) return;
            
            hideRemoveModal();
            
            try {
                const res = await fetch('/api/remove-account', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ accountId: accountToRemove })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    showToast('Account removed successfully');
                    await loadAccounts(); // Refresh accounts list
                } else {
                    showError('Failed to remove account');
                }
            } catch (err) {
                console.error('Error removing account:', err);
                showError('Error removing account');
            }
        };

        // Refresh current account
        window.refreshCurrentAccount = async function() {
            if (!currentAccount) return;
            
            setLoading(refreshBtn, true);
            await loadChatsForCurrentAccount(true);
            setLoading(refreshBtn, false);
            showToast('Chats refreshed');
        };

        refreshBtn.addEventListener('click', refreshCurrentAccount);

        // ---------- Chat Management ----------
        async function loadChatsForCurrentAccount(showLoading = true) {
            if (!currentAccount) return;
            
            if (showLoading) {
                chatsListDiv.innerHTML = '<div class="loading">Loading chats...</div>';
            }
            
            try {
                const res = await fetch('/api/get-messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ accountId: currentAccount.id })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    chats = data.chats || [];
                    messages = data.messages || [];
                    totalChatsSpan.textContent = chats.length;
                    displayChats();
                    
                    // If we had a selected chat, try to reselect it
                    if (currentChat) {
                        const stillExists = chats.find(c => c.id === currentChat.id);
                        if (stillExists) {
                            displayMessages(currentChat.id);
                        } else {
                            currentChat = null;
                            messagesHeader.style.display = 'none';
                            composeArea.style.display = 'none';
                            messagesListDiv.innerHTML = '<div class="empty-state">👈 Select a chat to start messaging</div>';
                        }
                    }
                } else {
                    if (showLoading) {
                        chatsListDiv.innerHTML = `<div class="empty-state">Error: ${escapeHtml(data.error || 'Failed to load chats')}</div>`;
                    }
                    showError(data.error || 'Failed to load chats');
                }
            } catch (err) {
                console.error('Error loading chats:', err);
                if (showLoading) {
                    chatsListDiv.innerHTML = '<div class="empty-state">Failed to load chats. Check connection.</div>';
                }
                showError('Failed to load chats');
            }
        }

        function displayChats() {
            if (!chats || chats.length === 0) {
                chatsListDiv.innerHTML = '<div class="empty-state">No chats found</div>';
                return;
            }
            
            let html = '';
            chats.forEach(chat => {
                const activeClass = (currentChat && currentChat.id === chat.id) ? 'active' : '';
                let lastMsg = chat.lastMessage || '';
                
                // Add media emoji to last message if it's media
                if (chat.lastMessageMedia) {
                    switch(chat.lastMessageMedia) {
                        case 'photo':
                            lastMsg = '📷 ' + (lastMsg || 'Photo');
                            break;
                        case 'video':
                            lastMsg = '🎥 ' + (lastMsg || 'Video');
                            break;
                        case 'voice':
                            lastMsg = '🎤 ' + (lastMsg || 'Voice message');
                            break;
                        case 'audio':
                            lastMsg = '🎵 ' + (lastMsg || 'Audio');
                            break;
                        case 'document':
                            lastMsg = '📎 ' + (lastMsg || 'Document');
                            break;
                        case 'webpage':
                            lastMsg = '🔗 ' + (lastMsg || 'Link');
                            break;
                        default:
                            lastMsg = lastMsg || 'No messages yet';
                    }
                } else if (!lastMsg) {
                    lastMsg = 'No messages yet';
                }
                
                const time = chat.lastMessageDate ? formatTime(chat.lastMessageDate) : '';
                const unread = chat.unread ? `<span class="chat-unread">${chat.unread}</span>` : '';
                const avatarLetter = (chat.title || '?').charAt(0).toUpperCase();
                
                html += `
                    <div class="chat-item ${activeClass}" onclick="selectChat('${escapeJsString(chat.id)}', '${escapeJsString(chat.title || 'Unknown')}')">
                        <div class="chat-avatar">${escapeHtml(avatarLetter)}</div>
                        <div class="chat-info">
                            <div class="chat-row">
                                <span class="chat-name" title="${escapeHtml(chat.title || 'Unknown')}">${escapeHtml(chat.title || 'Unknown')}</span>
                                <span class="chat-time">${escapeHtml(time)}</span>
                            </div>
                            <div class="chat-last-msg">
                                <span class="chat-last-text">${escapeHtml(lastMsg)}</span>
                                ${unread}
                            </div>
                        </div>
                    </div>
                `;
            });
            
            chatsListDiv.innerHTML = html;
        }

        // ---------- Message Management ----------
        window.selectChat = function(chatId, chatTitle) {
            currentChat = { id: chatId, title: chatTitle };
            currentChatTitle.textContent = chatTitle;
            messagesHeader.style.display = 'block';
            composeArea.style.display = 'flex';
            messageInput.disabled = false;
            sendBtn.disabled = false;
            displayMessages(chatId);
            displayChats(); // Re-render to highlight active chat
        };

        window.refreshMessages = function() {
            if (currentChat) {
                displayMessages(currentChat.id);
                showToast('Messages refreshed');
            }
        };

        function displayMessages(chatId) {
            const chatMessages = messages
                .filter(m => m.chatId === chatId)
                .sort((a, b) => a.date - b.date);
                
            if (!chatMessages || chatMessages.length === 0) {
                messagesListDiv.innerHTML = '<div class="empty-state">No messages in this chat</div>';
                return;
            }
            
            let html = '';
            chatMessages.forEach(msg => {
                const date = new Date(msg.date * 1000);
                const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const bubbleClass = msg.out ? 'outgoing' : 'incoming';
                
                let messageContent = '';
                
                // Check if message has media
                if (msg.hasMedia || msg.mediaType) {
                    let mediaIcon = '📎';
                    let mediaText = 'Media';
                    
                    switch(msg.mediaType) {
                        case 'photo':
                            mediaIcon = '📷';
                            mediaText = 'Photo';
                            break;
                        case 'video':
                            mediaIcon = '🎥';
                            mediaText = 'Video';
                            break;
                        case 'voice':
                            mediaIcon = '🎤';
                            mediaText = 'Voice message';
                            break;
                        case 'audio':
                            mediaIcon = '🎵';
                            mediaText = 'Audio';
                            break;
                        case 'document':
                            mediaIcon = '📎';
                            mediaText = 'Document';
                            break;
                        case 'webpage':
                            mediaIcon = '🔗';
                            mediaText = 'Link';
                            break;
                    }
                    
                    messageContent = `
                        <div class="media-message">
                            <span class="media-icon">${mediaIcon}</span>
                            <span class="media-label">${mediaText}</span>
                        </div>
                    `;
                    
                    // Add text if present
                    if (msg.text) {
                        messageContent += `<div>${escapeHtml(msg.text)}</div>`;
                    }
                } else {
                    // Text only message
                    messageContent = `<div>${escapeHtml(msg.text || '')}</div>`;
                }
                
                html += `
                    <div class="message-wrapper ${bubbleClass}">
                        <div class="message-bubble">
                            ${messageContent}
                            <div class="message-meta">
                                <span>${escapeHtml(timeStr)}</span>
                                ${msg.out ? '✓✓' : ''}
                            </div>
                        </div>
                    </div>
                `;
            });
            
            messagesListDiv.innerHTML = html;
            
            // Scroll to bottom
            setTimeout(() => {
                messagesListDiv.scrollTop = messagesListDiv.scrollHeight;
            }, 100);
        }

        window.sendMessage = async function() {
            const message = messageInput.value.trim();
            
            if (!message || !currentAccount || !currentChat) {
                if (!message) {
                    messageInput.focus();
                }
                return;
            }
            
            const messageText = message;
            messageInput.value = '';
            messageInput.disabled = true;
            sendBtn.disabled = true;
            
            try {
                const res = await fetch('/api/send-message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        accountId: currentAccount.id,
                        chatId: currentChat.id,
                        message: messageText
                    })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    // Add message to local cache
                    const newMsg = {
                        chatId: currentChat.id,
                        text: messageText,
                        date: Date.now() / 1000,
                        out: true,
                        id: Date.now(),
                        hasMedia: false
                    };
                    messages.push(newMsg);
                    displayMessages(currentChat.id);
                    showToast('Message sent');
                } else {
                    showError('Failed to send message: ' + (data.error || 'Unknown error'));
                    messageInput.value = messageText; // Restore message
                }
            } catch (err) {
                console.error('Error sending message:', err);
                showError('Error sending message. Check connection.');
                messageInput.value = messageText; // Restore message
            } finally {
                messageInput.disabled = false;
                sendBtn.disabled = false;
                messageInput.focus();
            }
        };

        // Enter key to send
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // ---------- Utility Functions ----------
        function formatTime(timestamp) {
            if (!timestamp) return '';
            try {
                const d = new Date(timestamp * 1000);
                const now = new Date();
                if (d.toDateString() === now.toDateString()) {
                    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                }
                return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
            } catch (e) {
                return '';
            }
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function escapeJsString(str) {
            if (!str) return '';
            return str.replace(/[\\']/g, '\\$&').replace(/"/g, '&quot;');
        }
    </script>
</body>
</html>
