"""
Simple Telegram Bot - Works with Python 3.10+
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Your bot token - REPLACE WITH NEW ONE!
BOT_TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"
WEBAPP_URL = "https://e-gram-98zv.onrender.com"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send invite link when /start is issued."""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        logger.info(f"User {user_id} (@{username}) started the bot")
        
        invite_link = f"{WEBAPP_URL}/login?inviter={user_id}"
        keyboard = [[InlineKeyboardButton("➕ Add Account", url=invite_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔗 Your invite link:\n{invite_link}\n\n"
            "Share this link to let others add accounts under your invite.",
            reply_markup=reply_markup
        )
        logger.info(f"Sent invite link to user {user_id}")
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again later.")

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send link to private dashboard."""
    try:
        user_id = update.effective_user.id
        logger.info(f"User {user_id} requested dashboard")
        
        dash_link = f"{WEBAPP_URL}/user-dashboard?inviter={user_id}"
        await update.message.reply_text(f"📊 Your dashboard:\n{dash_link}")
        logger.info(f"Sent dashboard link to user {user_id}")
    except Exception as e:
        logger.error(f"Error in dashboard handler: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again later.")

def main():
    """Start the bot."""
    try:
        logger.info("Starting bot...")
        
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("dashboard", dashboard))
        
        logger.info("Bot is polling...")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

if __name__ == "__main__":
    main()
