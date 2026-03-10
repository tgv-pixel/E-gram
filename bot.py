import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your bot token - REPLACE WITH NEW ONE!
BOT_TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"
WEBAPP_URL = "https://e-gram-98zv.onrender.com"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    invite_link = f"{WEBAPP_URL}/login?inviter={user_id}"
    
    keyboard = [[InlineKeyboardButton("➕ Add Account", url=invite_link)]]
    await update.message.reply_text(
        f"🔗 Your invite link:\n{invite_link}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logger.info(f"Sent invite link to user {user_id}")

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dash_link = f"{WEBAPP_URL}/user-dashboard?inviter={user_id}"
    await update.message.reply_text(f"📊 Your dashboard:\n{dash_link}")
    logger.info(f"Sent dashboard link to user {user_id}")

def main():
    """Start the bot"""
    logger.info("Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    
    logger.info("Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
