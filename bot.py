import asyncio
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging

# Bot configuration
BOT_TOKEN = "7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A"
ADMIN_ID = 894002841
CHANNEL_USERNAME = "@abe_army"  # Channel that users must join

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store user data (in production, use a database)
user_benefits = {}

async def check_user_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is a member of the channel"""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Check if user is admin (bypass channel check for admin)
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"👋 Welcome Admin {user_name}!\n\n"
            "You have full control over this bot.\n"
            "Commands:\n"
            "/broadcast <message> - Send message to all users\n"
            "/stats - Check total users\n"
            "/start - Show this menu"
        )
        return
    
    # Check if user joined the channel
    is_member = await check_user_membership(user_id, context)
    
    if is_member:
        # User joined the channel, provide access
        await update.message.reply_text(
            f"✅ Welcome {user_name}!\n\n"
            "Thank you for joining our channel!\n"
            "You now have full access to the bot's features.\n\n"
            "Enjoy your benefits! 🎉"
        )
        
        # Track user benefit
        if user_id not in user_benefits:
            user_benefits[user_id] = {
                'username': user_name,
                'joined_date': update.message.date,
                'benefits_received': True
            }
    else:
        # User hasn't joined, show join button
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ Access Denied!\n\n"
            f"Dear {user_name},\n\n"
            "To use this bot, you must first join our channel.\n\n"
            "👉 Click the button below to join, then press 'I've Joined' to verify.\n\n"
            "After joining, you will receive exclusive benefits! 🎁",
            reply_markup=reply_markup
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if query.data == "check_join":
        is_member = await check_user_membership(user_id, context)
        
        if is_member:
            # User joined successfully
            await query.edit_message_text(
                f"✅ Verified! Welcome {user_name}!\n\n"
                "Thank you for joining our channel!\n"
                "You now have full access to the bot.\n\n"
                "Enjoy your benefits! 🎉"
            )
            
            # Track user benefit
            if user_id not in user_benefits:
                user_benefits[user_id] = {
                    'username': user_name,
                    'joined_date': update.effective_message.date,
                    'benefits_received': True
                }
        else:
            # User still hasn't joined
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
                [InlineKeyboardButton("✅ Check Again", callback_data="check_join")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ Not Joined Yet!\n\n"
                f"You need to join {CHANNEL_USERNAME} first.\n\n"
                "Please join using the button below, then click 'Check Again'.",
                reply_markup=reply_markup
            )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast message to all users"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    
    # Check if message was provided
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n\n"
            "Example: /broadcast Hello everyone!"
        )
        return
    
    message_text = ' '.join(context.args)
    await update.message.reply_text(f"📢 Broadcasting message to {len(user_benefits)} users...")
    
    # Send message to all users
    success_count = 0
    fail_count = 0
    
    for user_id in user_benefits.keys():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 **Announcement from Admin:**\n\n{message_text}",
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)  # Small delay to avoid rate limiting
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            fail_count += 1
    
    await update.message.reply_text(
        f"✅ Broadcast completed!\n"
        f"📨 Sent: {success_count}\n"
        f"❌ Failed: {fail_count}"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to see bot statistics"""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    
    total_users = len(user_benefits)
    
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"👑 Admin ID: {ADMIN_ID}\n"
        f"📢 Channel: {CHANNEL_USERNAME}\n\n"
        f"Users List:\n" + 
        "\n".join([f"• {data['username']} (ID: {uid})" for uid, data in list(user_benefits.items())[:10]])
        + (f"\n... and {total_users - 10} more" if total_users > 10 else "")
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all other messages"""
    user_id = update.effective_user.id
    
    # Admin bypass
    if user_id == ADMIN_ID:
        await update.message.reply_text("Admin mode active. Use /broadcast or /stats commands.")
        return
    
    # Check if user joined channel
    is_member = await check_user_membership(user_id, context)
    
    if not is_member:
        # User hasn't joined, send join message
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **Access Restricted**\n\n"
            "You need to join our channel first to use this bot.\n\n"
            "Click the button below to join:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # User has access, respond to their message
        await update.message.reply_text(
            f"✅ Your message has been received!\n\n"
            f"You have access to all bot features.\n"
            f"Type /start to see the menu again."
        )

async def main():
    """Main function to run the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start polling
    print("🤖 Bot is starting...")
    print(f"Admin ID: {ADMIN_ID}")
    print(f"Channel: {CHANNEL_USERNAME}")
    
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
