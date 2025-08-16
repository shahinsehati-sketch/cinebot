import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# 🔑 توکن جدید رباتتو اینجا بذار
BOT_TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"

logging.basicConfig(level=logging.INFO)

# کیبورد (منو)
main_menu = [
    ["🎬 فیلم‌های جدید", "📺 سریال‌های جدید"],
    ["📂 آرشیو ۳ روز اخیر", "📩 تماس با سازنده"]
]
reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)

# دستور استارت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام 👋\nبه ربات فیلم و سریال خوش اومدی!",
        reply_markup=reply_markup
    )

# هندل دکمه‌ها
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🎬 فیلم‌های جدید":
        await update.message.reply_text("📌 لیست فیلم‌های جدید:\n- فیلم ۱\n- فیلم ۲\n- فیلم ۳")
    elif text == "📺 سریال‌های جدید":
        await update.message.reply_text("📌 لیست سریال‌های جدید:\n- سریال ۱\n- سریال ۲\n- سریال ۳")
    elif text == "📂 آرشیو ۳ روز اخیر":
        await update.message.reply_text("📂 آرشیو ۳ روز اخیر:\n- مورد A\n- مورد B\n- مورد C")
    elif text == "📩 تماس با سازنده":
        await update.message.reply_text("برای ارتباط با سازنده به آیدی زیر پیام بده:\n👉 @shahin_sehati")
    else:
        await update.message.reply_text("لطفاً از منو انتخاب کن 👇", reply_markup=reply_markup)

# راه‌اندازی
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()     
