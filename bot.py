#!/usr/bin/env python3
"""
Telegram Bot - Requires users to join @abe_army channel
Admin can broadcast messages to all users
"""

import os
import json
import logging
import threading
from datetime import datetime
from flask import Flask, jsonify

# Telegram imports
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

# ==================== USER DATA MANAGEMENT ====================
user_data = {}

def load_user_data():
    """Load user data from JSON file"""
    global user_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r") as f:
                content = f.read()
                if content.strip():
                    user_data = json.loads(content)
                else:
                    user_data = {}
            logger.info(f"✅ Loaded {len(user_data)} users")
        else:
            user_data = {}
            save_user_data()
            logger.info(f"✅ Created new {USER_DATA_FILE}")
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        user_data = {}

def save_user_data():
    """Save user data to JSON file"""
    try:
        with open(USER_DATA_FILE, "w") as f:
            json.dump(user_data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user data: {e}")
        return False

# Load existing data
load_user_data()

# ==================== TELEGRAM BOT HANDLERS ====================

async def check_membership(user_id, context):
    """Check if user is a member of the channel"""
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME, 
            user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name or "User"

    # Admin check
    if user_id == ADMIN_ID:
        await show_admin_panel(update, context)
        return

    # Check channel membership
    is_member = await check_membership(user_id, context)

    if is_member:
        # Save user data
        if str(user_id) not in user_data:
            user_data[str(user_id)] = {
                "username": user.username or user_name,
                "full_name": user.full_name or user_name,
                "joined_date": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat()
            }
            save_user_data()
            logger.info(f"✅ New user: {user_name} ({user_id})")

        await update.message.reply_text(
            f"✅ **Welcome {user_name}!**\n\n"
            f"Thank you for joining @abe_army!\n"
            f"You now have full access to this bot.\n\n"
            f"📌 **Commands:**\n"
            f"/start - Show menu\n"
            f"/benefits - View benefits\n\n"
            f"🎉 Enjoy!",
            parse_mode="Markdown"
        )
    else:
        # Need to join channel
        keyboard = [
            [InlineKeyboardButton("📢 Join @abe_army", url="https://t.me/abe_army")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="verify_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ **Access Denied!**\n\n"
            f"Dear {user_name},\n\n"
            f"You must join @abe_army to use this bot.\n\n"
            f"After joining, click the button below to verify.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin control panel"""
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👑 **Admin Panel**\n\n"
        f"👥 Total Users: {len(user_data)}\n"
        f"📢 Channel: {CHANNEL_USERNAME}\n\n"
        f"Select an option:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def benefits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user benefits"""
    user = update.effective_user
    user_id = user.id

    if user_id == ADMIN_ID:
        await update.message.reply_text("👑 Admin benefits: Full control, broadcast, user management")
        return

    is_member = await check_membership(user_id, context)

    if not is_member:
        await update.message.reply_text("⚠️ Please join @abe_army first! Use /start")
        return

    user_info = user_data.get(str(user_id), {})

    await update.message.reply_text(
        f"🎁 **Your Benefits**\n\n"
        f"✅ Verified Member of @abe_army\n"
        f"📅 Joined: {user_info.get('joined_date', 'Today')[:10]}\n\n"
        f"**Benefits:**\n"
        f"• Full bot access\n"
        f"• Receive announcements\n"
        f"• Priority updates\n\n"
        f"Thank you! 🎉",
        parse_mode="Markdown"
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin broadcast command"""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command.")
        return

    if not context.args:
        await update.message.reply_text(
            f"📢 **Usage:** `/broadcast <message>`\n\n"
            f"Example: `/broadcast Hello everyone!`\n\n"
            f"Will send to {len(user_data)} users.",
            parse_mode="Markdown"
        )
        return

    message = " ".join(context.args)
    await update.message.reply_text(f"📢 Broadcasting to {len(user_data)} users...")

    success = 0
    failed = 0

    for uid in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 **Announcement**\n\n{message}\n\n---\n🇪🇹 @abe_army",
                parse_mode="Markdown"
            )
            success += 1
            import asyncio
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1

    await update.message.reply_text(
        f"✅ **Broadcast Complete**\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"👥 Total: {len(user_data)}"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return

    await update.message.reply_text(
        f"📊 **Bot Stats**\n\n"
        f"👥 Users: {len(user_data)}\n"
        f"👑 Admin: {ADMIN_ID}\n"
        f"📢 Channel: {CHANNEL_USERNAME}\n"
        f"🤖 Status: Online",
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    user_id = user.id
    user_name = user.first_name

    # Admin buttons
    if query.data.startswith("admin_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("⛔ Unauthorized!")
            return

        if query.data == "admin_stats":
            await query.edit_message_text(
                f"📊 **Statistics**\n\n"
                f"👥 Total Users: {len(user_data)}\n"
                f"📢 Channel: {CHANNEL_USERNAME}\n"
                f"👑 Admin ID: {ADMIN_ID}",
                parse_mode="Markdown"
            )

        elif query.data == "admin_users":
            if not user_data:
                await query.edit_message_text("No users yet.")
                return

            user_list = "👥 **Users**\n\n"
            for i, (uid, data) in enumerate(list(user_data.items())[:20], 1):
                user_list += f"{i}. {data.get('username', 'Unknown')} (ID: {uid})\n"

            if len(user_data) > 20:
                user_list += f"\n... and {len(user_data) - 20} more"

            await query.edit_message_text(user_list, parse_mode="Markdown")

        elif query.data == "admin_broadcast":
            await query.edit_message_text(
                f"📢 **Broadcast**\n\n"
                f"Use: `/broadcast <message>`\n\n"
                f"Example: `/broadcast Hello to {len(user_data)} users!`"
            )
        return

    # Verify join button
    if query.data == "verify_join":
        is_member = await check_membership(user_id, context)

        if is_member:
            if str(user_id) not in user_data:
                user_data[str(user_id)] = {
                    "username": user.username or user_name,
                    "full_name": user.full_name or user_name,
                    "joined_date": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat()
                }
                save_user_data()
                logger.info(f"✅ New verified user: {user_name}")

            await query.edit_message_text(
                f"✅ **Verified!**\n\n"
                f"Welcome {user_name}!\n\n"
                f"Thank you for joining @abe_army!\n\n"
                f"Use /start to continue.",
                parse_mode="Markdown"
            )
        else:
            keyboard = [
                [InlineKeyboardButton("📢 Join @abe_army", url="https://t.me/abe_army")],
                [InlineKeyboardButton("✅ Check Again", callback_data="verify_join")]
            ]
            await query.edit_message_text(
                f"❌ **Not Joined Yet!**\n\n"
                f"Please join @abe_army first.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

# ==================== FLASK HEALTH CHECK ====================
health_app = Flask(__name__)

@health_app.route("/")
@health_app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "abe-army-bot",
        "users": len(user_data),
        "admin_id": ADMIN_ID
    })

@health_app.route("/ping")
def ping():
    return "pong"

def run_health_server():
    """Run health check server"""
    port = int(os.environ.get("PORT", 5001))
    health_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== MAIN ====================
def main():
    """Start the bot"""
    # Start health server in background
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health server started on port 5001")

    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("benefits", benefits_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start bot
    logger.info("🚀 Bot is starting...")
    logger.info(f"👑 Admin: {ADMIN_ID}")
    logger.info(f"📢 Channel: {CHANNEL_USERNAME}")
    logger.info(f"👥 Users loaded: {len(user_data)}")

    # Run bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
