#!/usr/bin/env python3
"""
Telegram bot for invite link generation.
Run this script separately or as part of your deployment.
Environment variables:
- BOT_TOKEN: your bot token (from @BotFather)
- WEBAPP_URL: base URL of your Flask app (e.g., https://your-app.onrender.com)
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Read environment variables
BOT_TOKEN = os.environ.get('8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM')
WEBAPP_URL = os.environ.get('https://e-gram-98zv.onrender.com/')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set")
if not WEBAPP_URL:
    raise ValueError("WEBAPP_URL environment variable not set")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send invite link when /start is issued."""
    user_id = update.effective_user.id
    invite_link = f"{WEBAPP_URL}/login?inviter={user_id}"
    
    keyboard = [[InlineKeyboardButton("➕ Add Account", url=invite_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔗 **Your invite link:**\n{invite_link}\n\n"
        "Share this link with others. When they add an account via this link, "
        "you'll see it in your private dashboard.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send link to private dashboard."""
    user_id = update.effective_user.id
    dash_link = f"{WEBAPP_URL}/user-dashboard?inviter={user_id}"
    
    await update.message.reply_text(
        f"📊 **Your private dashboard:**\n{dash_link}\n\n"
        "Here you can see all accounts added via your invite links.",
        parse_mode="Markdown"
    )

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("dashboard", dashboard))

    # Start polling
    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()
