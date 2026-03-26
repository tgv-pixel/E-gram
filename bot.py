import sqlite3
import os
import shutil
from datetime import datetime

def backup_database():
    db_path = 'telegram_bot.db'
    if os.path.exists(db_path):
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(backup_dir, f'telegram_bot_{timestamp}.db')
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_path}")
        
        # Keep only last 10 backups
        backups = sorted(os.listdir(backup_dir))
        for old_backup in backups[:-10]:
            os.remove(os.path.join(backup_dir, old_backup))

if __name__ == '__main__':
    backup_database()
