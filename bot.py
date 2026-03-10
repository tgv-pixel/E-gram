import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8210146562:AAHvM54C4KvHsf-YfAjOC9VLe6o1l-gEtBM"
WEBAPP_URL = "https://e-gram-98zv.onrender.com"  # Change to your actual domain

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Create invite link with inviter ID
    link = f"{WEBAPP_URL}/login?inviter={user_id}"
    
    # Create a button that opens the link
    keyboard = [[InlineKeyboardButton("➕ Add Account", url=link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔗 Your invite link:\n{link}\n\nShare this link with others. When they add an account via this link, you'll see it in your private dashboard.",
        reply_markup=reply_markup
    )

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dash_link = f"{WEBAPP_URL}/user-dashboard?inviter={user_id}"
    await update.message.reply_text(f"📊 Your private dashboard:\n{dash_link}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.run_polling()

if __name__ == "__main__":
    main()
