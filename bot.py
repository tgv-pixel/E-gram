import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Replace with your NEW token from BotFather
TOKEN = '7294379764:AAHAOQ1OVT2TJ0cRAlWhyyxXQdVB3oS9K_A'
CHANNEL_USERNAME = '@Abe_army' # e.g., @my_cool_channel
CHANNEL_LINK = 'https://t.me/Abe_army'

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # English and Amharic text
    text = (
        "👋 **Welcome!**\n"
        "To use this bot, you must first join our channel.\n\n"
        "👋 **እንኳን ደህና መጡ!**\n"
        "ይህን ቦት ለመጠቀም በመጀመሪያ ቻናላችንን መቀላቀል አለብዎት።"
    )
    
    keyboard = [[InlineKeyboardButton("Join Channel / ቻናሉን ይቀላቀሉ", url=CHANNEL_LINK)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

def main():
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add the start command handler
    application.add_handler(CommandHandler("start", start))

    # Run the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
