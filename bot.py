#!/usr/bin/env python3
"""
Telegram Bot - Requires users to join @abe_army channel
Admin can broadcast messages to all users
"""

import os
import json
import logging
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
            logger.info(f"✅ Loaded {len(user_data)} users from {USER_DATA_FILE}")
        else:
            user_data = {}
            save_user_data()
            logger.info(f"✅ Created new {USER_DATA_FILE} file")
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
        logger.error(f"Membership check error for {user_id}: {e}")
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
            logger.info(f"✅ New user registered: {user_name} ({user_id})")

        await update.message.reply_text(
            f"✅ **Welcome {user_name}!**\n\n"
            f"Thank you for joining @abe_army!\n"
            f"You now have full access to this bot.\n\n"
            f"📌 **Commands:**\n"
            f"/start - Show this menu\n"
            f"/benefits - View your benefits\n\n"
            f"🎉 Enjoy exclusive content!",
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
            f"You must join our channel to use this bot.\n\n"
            f"👉 **Channel:** @abe_army\n\n"
            f"After joining, click the button below to verify.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin control panel"""
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 User List", callback_data="admin_users")],
        [InlineKeyboardButton("💾 Export Data", callback_data="admin_export")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👑 **Admin Control Panel**\n\n"
        f"✅ Bot is running\n"
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
    user_name = user.first_name

    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👑 **Admin Benefits**\n\n"
            "• Full control panel\n"
            "• Broadcast messages\n"
            "• View all users\n"
            "• Export user data"
        )
        return

    is_member = await check_membership(user_id, context)

    if not is_member:
        await update.message.reply_text(
            "⚠️ Please join @abe_army first to receive benefits!\n"
            "Use /start to join."
        )
        return

    user_info = user_data.get(str(user_id), {})

    await update.message.reply_text(
        f"🎁 **Your Benefits**\n\n"
        f"✅ Verified Member of @abe_army\n"
        f"📅 Joined: {user_info.get('joined_date', 'Today')[:10]}\n\n"
        f"**Active Benefits:**\n"
        f"• Full bot access\n"
        f"• Receive announcements\n"
        f"• Priority updates\n"
        f"• Exclusive content\n\n"
        f"Thank you for being part of our community! 🎉",
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin stats command"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command.")
        return

    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {len(user_data)}\n"
        f"👑 Admin ID: {ADMIN_ID}\n"
        f"📢 Channel: {CHANNEL_USERNAME}\n"
        f"🤖 Status: Online\n"
        f"📁 Data File: {USER_DATA_FILE}",
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
            "📢 **Usage:** `/broadcast <message>`\n\n"
            "Example: `/broadcast Hello everyone!`\n\n"
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
                text=f"📢 **Announcement from Admin**\n\n{message}\n\n---\n🇪🇹 @abe_army",
                parse_mode="Markdown"
            )
            success += 1
            import asyncio
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send to {uid}: {e}")

    await update.message.reply_text(
        f"✅ **Broadcast Complete**\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}\n"
        f"👥 Total: {len(user_data)}"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    user_id = user.id
    user_name = user.first_name

    # ========== ADMIN BUTTONS ==========
    if query.data.startswith("admin_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("⛔ Unauthorized!")
            return

        if query.data == "admin_stats":
            await query.edit_message_text(
                f"📊 **Statistics**\n\n"
                f"👥 Total Users: {len(user_data)}\n"
                f"📢 Channel: {CHANNEL_USERNAME}\n"
                f"👑 Admin ID: {ADMIN_ID}\n"
                f"📁 Data: {USER_DATA_FILE}",
                parse_mode="Markdown"
            )

        elif query.data == "admin_users":
            if not user_data:
                await query.edit_message_text("No users registered yet.")
                return

            user_list = "👥 **User List**\n\n"
            for i, (uid, data) in enumerate(list(user_data.items())[:20], 1):
                user_list += f"{i}. {data.get('username', 'Unknown')} (ID: {uid})\n"

            if len(user_data) > 20:
                user_list += f"\n... and {len(user_data) - 20} more"

            await query.edit_message_text(user_list, parse_mode="Markdown")

        elif query.data == "admin_export":
            export_data = {
                "export_date": datetime.now().isoformat(),
                "total_users": len(user_data),
                "admin_id": ADMIN_ID,
                "users": user_data
            }
            with open("export.json", "w") as f:
                json.dump(export_data, f, indent=2)
            await query.edit_message_text(
                f"✅ Data exported!\n"
                f"File: export.json\n"
                f"Total users: {len(user_data)}"
            )

        elif query.data == "admin_broadcast":
            await query.edit_message_text(
                "📢 **Broadcast Mode**\n\n"
                "Use: `/broadcast <message>`\n\n"
                f"Example: `/broadcast Hello to {len(user_data)} users!`"
            )

        return

    # ========== VERIFY JOIN BUTTON ==========
    if query.data == "verify_join":
        is_member = await check_membership(user_id, context)

        if is_member:
            # Save user
            if str(user_id) not in user_data:
                user_data[str(user_id)] = {
                    "username": user.username or user_name,
                    "full_name": user.full_name or user_name,
                    "joined_date": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat()
                }
                save_user_data()
                logger.info(f"✅ Verified new user: {user_name} ({user_id})")

            await query.edit_message_text(
                f"✅ **Verification Successful!**\n\n"
                f"Welcome {user_name}!\n\n"
                f"Thank you for joining @abe_army!\n\n"
                f"🎉 You now have full access.\n\n"
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
                f"Please join @abe_army first, then click Verify.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

# ==================== FLASK HEALTH CHECK ====================
health_app = Flask(__name__)

@health_app.route("/")
@health_app.route("/health")
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "healthy",
        "service": "abe-army-bot",
        "users": len(user_data),
        "admin_id": ADMIN_ID,
        "channel": CHANNEL_USERNAME
    })

@health_app.route("/ping")
def ping():
    """Simple ping endpoint"""
    return "pong"

def run_health_server():
    """Run Flask health check server on separate port"""
    port = int(os.environ.get("PORT", 5001))
    health_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== MAIN ====================
def main():
    """Start the bot"""
    # Start health server in background
    import threading
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("✅ Health check server started")

    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("benefits", benefits_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Add callback handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start bot
    logger.info("🚀 Bot is starting...")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info(f"📢 Channel: {CHANNEL_USERNAME}")
    logger.info(f"👥 Users loaded: {len(user_data)}")

    # Run bot (this blocks)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
