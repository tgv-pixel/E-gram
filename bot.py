import asyncio
import os
import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
import json

# Bot configuration
BOT_TOKEN = "7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A"
ADMIN_ID = 894002841
CHANNEL_USERNAME = "@abe_army"

# File to store user data (shared with main system)
USER_DATA_FILE = 'bot_users.json'

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user data
user_data = {}

def load_user_data():
    """Load user data from file"""
    global user_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                content = f.read()
                if content.strip():
                    user_data = json.loads(content)
                else:
                    user_data = {}
        else:
            user_data = {}
            with open(USER_DATA_FILE, 'w') as f:
                json.dump({}, f)
        logger.info(f"Loaded {len(user_data)} users from bot data")
    except Exception as e:
        logger.error(f"Error loading user data: {e}")
        user_data = {}

def save_user_data():
    """Save user data to file"""
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

# Load data on start
load_user_data()

async def check_user_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is a member of the channel"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking membership for {user_id}: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Admin bypass
    if user_id == ADMIN_ID:
        await show_admin_menu(update, context)
        return
    
    # Check if user joined the channel
    is_member = await check_user_membership(user_id, context)
    
    if is_member:
        # Track user benefit
        if str(user_id) not in user_data:
            user_data[str(user_id)] = {
                'username': user_name,
                'full_name': update.effective_user.full_name,
                'joined_date': datetime.now().isoformat(),
                'benefits_received': True,
                'last_active': datetime.now().isoformat()
            }
            save_user_data()
            logger.info(f"New user joined: {user_name} ({user_id})")
        
        await update.message.reply_text(
            f"✅ Welcome {user_name}!\n\n"
            "Thank you for joining @abe_army channel!\n"
            "You now have full access to this bot.\n\n"
            "🎉 Enjoy your exclusive benefits!\n\n"
            "Commands:\n"
            "/start - Show this menu\n"
            "/benefits - View your benefits"
        )
    else:
        # User hasn't joined, show join button
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/abe_army")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ **Access Denied!**\n\n"
            f"Dear {user_name},\n\n"
            f"To use this bot, you must first join our channel:\n"
            f"👉 @abe_army\n\n"
            f"**Why join?**\n"
            f"• Exclusive updates\n"
            f"• Special benefits\n"
            f"• Community access\n\n"
            f"Click the button below to join, then press '✅ I've Joined' to verify.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin menu with controls"""
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 View Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 List Users", callback_data="admin_users")],
        [InlineKeyboardButton("💾 Export Data", callback_data="admin_export")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👑 **Admin Control Panel**\n\n"
        f"Welcome back, Admin!\n\n"
        f"📊 Quick Stats:\n"
        f"• Total Users: {len(user_data)}\n"
        f"• Channel: {CHANNEL_USERNAME}\n\n"
        f"Select an option below:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Handle admin actions
    if query.data.startswith("admin_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("⛔ You are not authorized to use admin controls.")
            return
        
        if query.data == "admin_broadcast":
            context.user_data['awaiting_broadcast'] = True
            await query.edit_message_text(
                "📢 **Broadcast Mode Activated**\n\n"
                "Please send me the message you want to broadcast to all users.\n\n"
                "Type /cancel to cancel.",
                parse_mode='Markdown'
            )
        
        elif query.data == "admin_stats":
            total_users = len(user_data)
            active_today = sum(1 for u in user_data.values() 
                              if u.get('last_active', '').startswith(datetime.now().strftime('%Y-%m-%d')))
            
            stats_text = (
                f"📊 **Bot Statistics**\n\n"
                f"👥 Total Users: {total_users}\n"
                f"📅 Active Today: {active_today}\n"
                f"👑 Admin ID: {ADMIN_ID}\n"
                f"📢 Channel: {CHANNEL_USERNAME}\n"
                f"🤖 Bot Status: Active\n\n"
                f"📈 Total Benefits Distributed: {total_users}"
            )
            await query.edit_message_text(stats_text, parse_mode='Markdown')
        
        elif query.data == "admin_users":
            if not user_data:
                await query.edit_message_text("No users have joined yet.")
                return
            
            users_list = "👥 **User List**\n\n"
            for uid, data in list(user_data.items())[:20]:
                users_list += f"• {data.get('username', 'Unknown')} (ID: {uid})\n"
                users_list += f"  Joined: {data.get('joined_date', 'Unknown')[:10]}\n\n"
            
            if len(user_data) > 20:
                users_list += f"\n... and {len(user_data) - 20} more users"
            
            # Add buttons for pagination
            keyboard = [[InlineKeyboardButton("📥 Export Full List", callback_data="admin_export")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(users_list, parse_mode='Markdown', reply_markup=reply_markup)
        
        elif query.data == "admin_export":
            # Create export data
            export = {
                'export_date': datetime.now().isoformat(),
                'total_users': len(user_data),
                'users': user_data
            }
            
            # Save to file
            with open('user_export.json', 'w') as f:
                json.dump(export, f, indent=2)
            
            # Send file (you'll need to implement file sending)
            await query.edit_message_text(
                f"✅ Data exported!\n"
                f"Total users: {len(user_data)}\n\n"
                f"File saved as: user_export.json"
            )
        
        return
    
    # Handle join verification
    if query.data == "check_join":
        is_member = await check_user_membership(user_id, context)
        
        if is_member:
            # Register user
            if str(user_id) not in user_data:
                user_data[str(user_id)] = {
                    'username': user_name,
                    'full_name': update.effective_user.full_name,
                    'joined_date': datetime.now().isoformat(),
                    'benefits_received': True,
                    'last_active': datetime.now().isoformat()
                }
                save_user_data()
            
            await query.edit_message_text(
                f"✅ **Verification Successful!**\n\n"
                f"Welcome {user_name}!\n\n"
                f"Thank you for joining @abe_army!\n\n"
                f"🎉 **Your Benefits:**\n"
                f"• Full bot access\n"
                f"• Exclusive updates\n"
                f"• Priority support\n\n"
                f"Type /start to continue.",
                parse_mode='Markdown'
            )
        else:
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url="https://t.me/abe_army")],
                [InlineKeyboardButton("✅ Check Again", callback_data="check_join")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ **Not Joined Yet!**\n\n"
                f"You need to join @abe_army first.\n\n"
                f"Please click the button below to join, then click 'Check Again'.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message from admin"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized.")
        return
    
    if not context.user_data.get('awaiting_broadcast'):
        return
    
    message_text = update.message.text
    
    if message_text == "/cancel":
        context.user_data['awaiting_broadcast'] = False
        await update.message.reply_text("❌ Broadcast cancelled.")
        return
    
    context.user_data['awaiting_broadcast'] = False
    
    await update.message.reply_text(f"📢 Broadcasting to {len(user_data)} users...")
    
    success_count = 0
    fail_count = 0
    
    broadcast_message = (
        f"📢 **Announcement from Admin**\n\n"
        f"{message_text}\n\n"
        f"---\n"
        f"🇪🇹 @abe_army"
    )
    
    for uid in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=broadcast_message,
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send to {uid}: {e}")
            fail_count += 1
    
    await update.message.reply_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"📨 Sent: {success_count}\n"
        f"❌ Failed: {fail_count}\n"
        f"👥 Total users: {len(user_data)}"
    )

async def benefits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user benefits"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Admin check
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👑 **Admin Benefits**\n\n"
            "• Full control panel\n"
            "• Broadcast messages\n"
            "• View user statistics\n"
            "• Export user data\n\n"
            "Use the admin menu from /start"
        )
        return
    
    # Check membership
    is_member = await check_user_membership(user_id, context)
    
    if not is_member:
        await update.message.reply_text(
            "⚠️ Please join @abe_army first to receive benefits!\n"
            "Use /start to join."
        )
        return
    
    user_info = user_data.get(str(user_id), {})
    
    await update.message.reply_text(
        f"🎁 **Your Benefits**\n\n"
        f"Dear {user_name},\n\n"
        f"✅ Verified Member of @abe_army\n"
        f"📅 Joined: {user_info.get('joined_date', 'Today')[:10]}\n\n"
        f"**Active Benefits:**\n"
        f"• 🚀 Full bot access\n"
        f"• 📢 Receive announcements\n"
        f"• 🔔 Priority notifications\n"
        f"• ⭐ Exclusive content\n\n"
        f"Thank you for being part of our community! 🎉"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    if context.user_data.get('awaiting_broadcast'):
        context.user_data['awaiting_broadcast'] = False
        await update.message.reply_text("❌ Broadcast cancelled.")
    else:
        await update.message.reply_text("No active operation to cancel.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command for admin"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command.")
        return
    
    total_users = len(user_data)
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📢 Channel: {CHANNEL_USERNAME}\n"
        f"🤖 Status: Online\n\n"
        f"Use the admin menu for more options."
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast command for admin"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only command.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n\n"
            "Example: /broadcast Hello everyone!\n\n"
            "Or use the admin menu for interactive broadcast."
        )
        return
    
    message_text = ' '.join(context.args)
    await update.message.reply_text(f"📢 Broadcasting to {len(user_data)} users...")
    
    success_count = 0
    fail_count = 0
    
    for uid in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 **Announcement:**\n\n{message_text}",
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
    
    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"Sent: {success_count}\n"
        f"Failed: {fail_count}"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An error occurred. Please try again later."
        )

async def main():
    """Main function to run the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("benefits", benefits))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    print("🤖 Bot is starting...")
    print(f"Admin ID: {ADMIN_ID}")
    print(f"Channel: {CHANNEL_USERNAME}")
    print(f"Users loaded: {len(user_data)}")
    
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
