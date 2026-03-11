import os
import threading
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import BadRequest

# 1. WEB SERVER (Required for Render)
app = Flask(__name__)
@app.route('/')
def health(): return "Bot is Online", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. CONFIGURATION
TOKEN = "7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A"
CHANNEL_ID = "@Abe_army"  # The bot uses this to check membership
CHANNEL_LINK = "https://t.me/Abe_army"

logging.basicConfig(level=logging.INFO)

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 **Welcome!**\n"
        "To use this bot, you must first join our channel.\n\n"
        "👋 **እንኳን ደህና መጡ!**\n"
        "ይህን ቦት ለመጠቀም በመጀመሪያ የኛን ቻናል መቀላቀል አለብዎት።"
    )
    
    keyboard = [
        [InlineKeyboardButton("Join Channel / ቻናሉን ይቀላቀሉ", url=CHANNEL_LINK)],
        [InlineKeyboardButton("Verify / አረጋግጥ ✅", callback_data="check_join")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        # Check if user is in the channel
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        
        if member.status in ['member', 'administrator', 'creator']:
            # Success Message
            success_text = (
                "✅ **Verification Successful!**\n"
                "You can now use the bot.\n\n"
                "✅ **ማረጋገጫው ተሳክቷል!**\n"
                "አሁን ቦቱን መጠቀም ይችላሉ።"
            )
            await query.message.edit_text(success_text, parse_mode='Markdown')
        else:
            # Still not joined
            fail_text = (
                "❌ **You haven't joined yet!**\n"
                "Please join the channel and click Verify again.\n\n"
                "❌ **ገና አልተቀላቀሉም!**\n"
                "እባክዎ ቻናሉን ይቀላቀሉ እና እንደገና 'አረጋግጥ' የሚለውን ይጫኑ።"
            )
            await query.answer("Please join @Abe_army first!", show_alert=True)
            
    except BadRequest:
        await query.answer("Error: Make sure the bot is an ADMIN in your channel!", show_alert=True)

def main():
    # Start Flask thread for Render
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_membership, pattern="check_join"))
    
    print("Professional Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
