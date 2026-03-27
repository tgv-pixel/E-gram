#!/usr/bin/env python3
"""
Database Backup Script for Render
Runs daily to backup the SQLite database
"""

import sqlite3
import os
import shutil
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'telegram_bot.db'
BACKUP_DIR = 'backups'

def backup_database():
    try:
        if not os.path.exists(DB_PATH):
            logger.warning(f"Database {DB_PATH} not found")
            return False
        
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'telegram_bot_{timestamp}.db')
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"✅ Database backed up to: {backup_path}")
        
        # Keep only last 10 backups
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('telegram_bot_')])
        for old in backups[:-10]:
            os.remove(os.path.join(BACKUP_DIR, old))
        
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False

if __name__ == '__main__':
    backup_database()
    print("Backup completed")
