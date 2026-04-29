#!/usr/bin/env python3
"""
Simple Telegram Bot - No Flask dependencies
"""

import os
import json
import logging
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==================== CONFIGURATION ====================
BOT_TOKEN = "7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A"
ADMIN_ID = 894002841
CHANNEL_USERNAME = "@abe_army"
USER_DATA_FILE = "bot_users.json"

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== USER DATA ====================
user_data = {}

def load_user_data():
    global user_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r") as f:
                user_data = json.load(f)
            logger.info(f"Loaded {len(user_data)} users")
        else:
            user_data = {}
            save_user_data()
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        user_data = {}

def save_user_data():
    try:
        with open(USER_DATA_FILE, "w") as f:
            json.dump(user_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

load_user_data()

# ==================== HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"Admin Panel\nUsers: {len(user_data)}\n\n"
            f"/broadcast <msg> - Send message\n/stats - View stats"
        )
        return
    
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_member = member.status in ["member", "administrator", "creator"]
    except:
        is_member = False
    
    if is_member:
        if str(user_id) not in user_data:
            user_data[str(user_id)] = {"name": user.first_name, "joined": datetime.now().isoformat()}
            save_user_data()
        await update.message.reply_text(f"✅ Welcome! You have access.")
    else:
        keyboard = [[InlineKeyboardButton("Join Channel", url="https://t.me/abe_army")],
                    [InlineKeyboardButton("Verified", callback_data="verify")]]
        await update.message.reply_text("Please join @abe_army first:", reply_markup=InlineKeyboardMarkup(keyboard))

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    message = " ".join(context.args)
    success = 0
    for uid in user_data.keys():
        try:
            await context.bot.send_message(int(uid), f"Announcement:\n{message}")
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await update.message.reply_text(f"Sent to {success}/{len(user_data)} users")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only")
        return
    await update.message.reply_text(f"Users: {len(user_data)}")

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user.id)
        is_member = member.status in ["member", "administrator", "creator"]
    except:
        is_member = False
    
    if is_member:
        if str(user.id) not in user_data:
            user_data[str(user.id)] = {"name": user.first_name, "joined": datetime.now().isoformat()}
            save_user_data()
        await query.edit_message_text("✅ Verified! Use /start")
    else:
        await query.edit_message_text("❌ Not joined yet. Please join @abe_army")

# ==================== MAIN ====================
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(verify))
    
    logger.info("Bot starting...")
    app.run_polling()
