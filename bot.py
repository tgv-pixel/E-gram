import sqlite3
import json
import os
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = 'telegram_data.db'
lock = threading.Lock()

def init_db():
    """Create database tables if they don't exist"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS accounts
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     phone TEXT,
                     name TEXT,
                     session TEXT,
                     created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Reply settings table
        c.execute('''CREATE TABLE IF NOT EXISTS reply_settings
                    (account_id TEXT PRIMARY KEY,
                     settings TEXT,
                     updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Auto-add settings table
        c.execute('''CREATE TABLE IF NOT EXISTS auto_add_settings
                    (account_id TEXT PRIMARY KEY,
                     settings TEXT,
                     updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # Conversation history table
        c.execute('''CREATE TABLE IF NOT EXISTS conversation_history
                    (account_id TEXT,
                     chat_id TEXT,
                     history TEXT,
                     updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                     PRIMARY KEY (account_id, chat_id))''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")

# ============ ACCOUNTS ============

def db_load_accounts():
    """Load all accounts from database"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, phone, name, session FROM accounts ORDER BY id')
        rows = c.fetchall()
        conn.close()
        
        accounts = []
        for row in rows:
            accounts.append({
                'id': row[0],
                'phone': row[1],
                'name': row[2],
                'session': row[3]
            })
        return accounts

def db_save_account(account):
    """Save or update a single account"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO accounts (id, phone, name, session)
                    VALUES (?, ?, ?, ?)''',
                 (account['id'], account['phone'], account['name'], account['session']))
        conn.commit()
        conn.close()

def db_save_all_accounts(accounts):
    """Save all accounts (used for sync)"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM accounts')
        for acc in accounts:
            c.execute('''INSERT INTO accounts (id, phone, name, session)
                        VALUES (?, ?, ?, ?)''',
                     (acc['id'], acc['phone'], acc['name'], acc['session']))
        conn.commit()
        conn.close()
    logger.info(f"💾 Saved {len(accounts)} accounts to database")

def db_delete_account(account_id):
    """Delete an account from database"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
        conn.commit()
        conn.close()

# ============ REPLY SETTINGS ============

def db_load_reply_settings():
    """Load reply settings"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT account_id, settings FROM reply_settings')
        rows = c.fetchall()
        conn.close()
        
        settings = {}
        for row in rows:
            settings[row[0]] = json.loads(row[1])
        return settings

def db_save_reply_settings(account_id, settings):
    """Save reply settings for an account"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO reply_settings (account_id, settings)
                    VALUES (?, ?)''',
                 (str(account_id), json.dumps(settings)))
        conn.commit()
        conn.close()

# ============ AUTO-ADD SETTINGS ============

def db_load_auto_add_settings():
    """Load auto-add settings"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT account_id, settings FROM auto_add_settings')
        rows = c.fetchall()
        conn.close()
        
        settings = {}
        for row in rows:
            settings[row[0]] = json.loads(row[1])
        return settings

def db_save_auto_add_settings(account_id, settings):
    """Save auto-add settings for an account"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO auto_add_settings (account_id, settings)
                    VALUES (?, ?)''',
                 (str(account_id), json.dumps(settings)))
        conn.commit()
        conn.close()

# ============ CONVERSATION HISTORY ============

def db_load_conversation_history():
    """Load all conversation history"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT account_id, chat_id, history FROM conversation_history')
        rows = c.fetchall()
        conn.close()
        
        history = {}
        for row in rows:
            account_key = row[0]
            chat_key = row[1]
            if account_key not in history:
                history[account_key] = {}
            history[account_key][chat_key] = json.loads(row[2])
        return history

def db_save_conversation_history(account_id, chat_id, history):
    """Save conversation history"""
    with lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO conversation_history (account_id, chat_id, history)
                    VALUES (?, ?, ?)''',
                 (str(account_id), str(chat_id), json.dumps(history)))
        conn.commit()
        conn.close()

# Initialize database on import
init_db()
