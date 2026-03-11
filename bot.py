import os
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# 1. Internal Web Server (Prevents Render "Port" Deployment Failure)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running professionally.", 200

def run_web_server():
    # Render uses the 'PORT' environment variable automatically
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 2. Your Bot Configuration
# Use your NEW revoked token here
TOKEN = "7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A" 
CHANNEL_LINK = "https://t.me/Abe_army"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Amharic and English combined as requested
    text = (
        "👋 **Welcome!**\n"
        "To use this bot, you must first join our channel.\n\n"
        "👋 **እንኳን ደህና መጡ!**\n"
        "ይህን ቦት ለመጠቀም በመጀመሪያ የኛን ቻናል መቀላቀል አለብዎት።"
    )
    
    # "Join" Button
    keyboard = [[InlineKeyboardButton("Join Channel / ቻናሉን ይቀላቀሉ", url=CHANNEL_LINK)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

def main():
    # Start the web server in a background thread
    Thread(target=run_web_server, daemon=True).start()

    # Start the Telegram Bot
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("Bot is live and server is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
