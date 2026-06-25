import asyncio
import json
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = "8786835988:AAEFXWRGRsaSoVy4uldfW277O0ib93m6iF8"
CHANNEL_ID = -1003948451744
ADMIN_ID = 8490510878

bot = Bot(token=TOKEN)
dp = Dispatcher()

movies = {"69": 26}

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🎬 Reevora Botga xush kelibsiz!\n\n"
        "Kino kodini yuboring 🍿"
    )

@dp.message(Command("addmovie"))
async def add_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        parts = message.text.split()
        kod = parts[1]
        msg_id = int(parts[2])
        movies[kod] = msg_id
        await message.answer(f"✅ Kino qo'shildi!\nKod: {kod}\nID: {msg_id}")
    except:
        await message.answer("❌ To'g'ri yozing: /addmovie KOD XABAR_ID")

@dp.message(Command("delmovie"))
async def del_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        kod = message.text.split()[1]
        if kod in movies:
            del movies[kod]
            await message.answer(f"✅ {kod} o'chirildi!")
        else:
            await message.answer("❌ Bunday kod yo'q!")
    except:
        await message.answer("❌ To'g'ri yozing: /delmovie KOD")

@dp.message(Command("katalog"))
async def katalog(message: Message):
    if not movies:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    text = "📚 Mavjud kinolar:\n\n"
    for kod in movies:
        text += f"🔑 Kod: {kod}\n"
    await message.answer(text)

@dp.message()
async def find_movie(message: Message):
    kod = message.text.strip()
    if kod in movies:
        msg_id = movies[kod]
        await bot.forward_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=msg_id
        )
    else:
        await message.answer("❌ Bunday kod topilmadi. /katalog yuboring.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
