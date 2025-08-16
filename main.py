import requests
import telegram
from telegram.ext import Updater, Job
import logging

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# اطلاعات بات
TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
CHAT_ID = "821239377"

# ساخت بات
bot = telegram.Bot(token=TOKEN)

# گرفتن اطلاعات قیمت
def fetch_crypto_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 15, "page": 1}
    response = requests.get(url, params=params)
    data = response.json()

    message = "💹 قیمت ۱۵ ارز برتر:\n\n"
    for coin in data:
        usd_price = coin['current_price']
        try:
            irr_price = usd_price * 60000  # تبدیل به تومان (تقریبی)
        except:
            irr_price = 0
        change = coin['price_change_percentage_24h']
        message += f"🔸 {coin['name']} ({coin['symbol'].upper()})\n"
        message += f"💵 {usd_price:,} دلار | 🇮🇷 {irr_price:,.0f} تومان\n"
        message += f"📉 تغییرات ۲۴ساعت: {change:.2f}%\n\n"

    return message

# تابع ارسال پیام
def send_update(bot, job):
    try:
        text = fetch_crypto_data()
        bot.send_message(chat_id=CHAT_ID, text=text)
    except Exception as e:
        print("خطا در ارسال:", e)

def main():
    updater = Updater(TOKEN)
    job_queue = updater.job_queue

    # هر 5 دقیقه یک بار ارسال کند
    job_queue.run_repeating(send_update, interval=300, first=5)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
