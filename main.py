import asyncio
import requests
from aiogram import Bot, Dispatcher

# اطلاعات ربات
TOKEN = "8153319362:AAGgeAOZyP2VgAdqvjyvvIkgGZBsJtTQOTs"
CHAT_ID = 821239377

bot = Bot(token=TOKEN)
dp = Dispatcher()

# گرفتن اطلاعات قیمت
def fetch_crypto_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 15, "page": 1}
    response = requests.get(url, params=params)
    data = response.json()

    message = "💹 قیمت ۱۵ ارز برتر:\n\n"
    for coin in data:
        usd_price = coin['current_price']
        irr_price = usd_price * 60000  # تبدیل تقریبی به تومان
        change = coin['price_change_percentage_24h']
        message += f"🔸 {coin['name']} ({coin['symbol'].upper()})\n"
        message += f"💵 {usd_price:,} دلار | 🇮🇷 {irr_price:,.0f} تومان\n"
        message += f"📉 تغییرات ۲۴ساعت: {change:.2f}%\n\n"

    return message

# ارسال پیام هر 5 دقیقه
async def send_updates():
    while True:
        try:
            text = fetch_crypto_data()
            await bot.send_message(chat_id=CHAT_ID, text=text)
        except Exception as e:
            print("خطا در ارسال:", e)
        await asyncio.sleep(300)  # 5 دقیقه

async def main():
    # اجرای تسک اصلی
    asyncio.create_task(send_updates())
    # ربات فقط باید روشن بمونه
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
