

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = "8786835988:AAEFXWRGRsaSoVy4uldfW277O0ib93m6iF8"

bot = Bot(token=TOKEN)
dp = Dispatcher()

movies = {
    "001": {"nomi": "Inception", "link": "https://t.me/reevora"},
    "002": {"nomi": "Interstellar", "link": "https://t.me/reevora"},
    "003": {"nomi": "Avengers", "link": "https://t.me/reevora"},
}

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🎬 Reevora Botga xush kelibsiz!\n\n"
        "Kino kodini yuboring 🍿\n"
        "Masalan: 001"
    )

@dp.message(Command("katalog"))
async def katalog(message: Message):
    text = "📚 Mavjud kinolar:\n\n"
    for kod, info in movies.items():
        text += f"🎞 {kod} — {info['nomi']}\n"
    await message.answer(text)

@dp.message()
async def find_movie(message: Message):
    kod = message.text.strip()
    if kod in movies:
        movie = movies[kod]
        await message.answer(
            f"🎬 Film: {movie['nomi']}\n"
            f"🔗 Link: {movie['link']}"
        )
    else:
        await message.answer("❌ Bunday kod topilmadi. /katalog yuboring.")

asyncio.run(dp.start_polling(bot))
