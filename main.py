import asyncio
import json
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

TOKEN = "TOKENINGIZNI_SHU_YERGA_QOYING"
CHANNEL_ID = -1003948451744
ADMIN_ID = 8490510878

bot = Bot(token=TOKEN)
dp = Dispatcher()

users = set()
required_channels = []

MOVIES_FILE = "movies.json"
USERS_FILE = "users.json"

# ===================== FAYL SAQLASH =====================

def load_movies():
    if os.path.exists(MOVIES_FILE):
        with open(MOVIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_movies():
    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(list(users), f)

movies = load_movies()
users = load_users()

# ===================== HTTP SERVER =====================

async def start_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

# ===================== OBUNA TEKSHIRISH =====================

async def check_subscription(user_id: int) -> bool:
    if not required_channels:
        return True
    for channel in required_channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked", "banned"]:
                return False
        except:
            pass
    return True

async def subscription_keyboard():
    buttons = []
    for channel in required_channels:
        try:
            chat = await bot.get_chat(channel)
            invite = await bot.export_chat_invite_link(channel)
            buttons.append([InlineKeyboardButton(text=f"📢 {chat.title}", url=invite)])
        except:
            buttons.append([InlineKeyboardButton(text=f"📢 {channel}", url=f"https://t.me/{channel.replace('@', '')}")])
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim!", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===================== FOYDALANUVCHI =====================

@dp.message(Command("start"))
async def start(message: Message):
    users.add(message.from_user.id)
    save_users()
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer(
            "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>",
            reply_markup=keyboard, parse_mode="HTML"
        )
        return
    await message.answer(
        "🎬 <b>Reevora Cinema Bot</b>ga xush kelibsiz!\n\n"
        "🔍 Kino kodini yuboring — filmni topasiz\n"
        "📝 Kino nomini yuboring — qidiruv amalga oshiriladi\n\n"
        "📚 /katalog — barcha kinolar\n"
        "🔎 /qidirish [nom] — kino qidirish\n"
        "ℹ️ /help — yordam",
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text(
            "✅ <b>Rahmat! Endi botdan foydalanishingiz mumkin!</b>\n\n"
            "🎬 Kino kodini yuboring yoki /katalog ga kiring.",
            parse_mode="HTML"
        )
    else:
        keyboard = await subscription_keyboard()
        await callback.message.edit_text(
            "⚠️ <b>Siz hali ham barcha kanallarga obuna bo'lmagansiz!</b>\n\n"
            "Iltimos, barcha kanallarga obuna bo'ling:",
            reply_markup=keyboard, parse_mode="HTML"
        )
    await callback.answer()

@dp.message(Command("help"))
async def help_cmd(message: Message):
    users.add(message.from_user.id)
    save_users()
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "▫️ Kino <b>kodini</b> yuboring → film keladi\n"
        "▫️ /katalog → barcha kinolar ro'yxati\n"
        "▫️ /qidirish Avatar → kino qidirish\n\n"
        "⭐ Kino kelgandan so'ng unga baho bering!",
        parse_mode="HTML"
    )

@dp.message(Command("katalog"))
async def katalog(message: Message):
    users.add(message.from_user.id)
    save_users()
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    if not movies:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    text = "📚 <b>Mavjud kinolar:</b>\n\n"
    for kod, info in movies.items():
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        text += f"🎬 <b>{info['nomi']}</b>{stars}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("qidirish"))
async def qidirish(message: Message):
    users.add(message.from_user.id)
    save_users()
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Yozing: /qidirish <b>kino nomi</b>", parse_mode="HTML")
        return
    query = args[1].lower()
    results = [(k, v) for k, v in movies.items() if query in v["nomi"].lower()]
    if not results:
        await message.answer(f"🔍 <b>{args[1]}</b> topilmadi!", parse_mode="HTML")
        return
    text = "🔍 <b>Qidiruv natijalari:</b>\n\n"
    for kod, info in results:
        text += f"🎬 <b>{info['nomi']}</b>\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

# ===================== ADMIN =====================

@dp.message(Command("addsub"))
async def add_sub(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        channel = message.text.split()[1]
        if channel not in required_channels:
            required_channels.append(channel)
            await message.answer(f"✅ <b>{channel}</b> majburiy obunaga qo'shildi!", parse_mode="HTML")
        else:
            await message.answer("⚠️ Bu kanal allaqachon qo'shilgan!")
    except:
        await message.answer("❌ Yozing: <code>/addsub @kanal_username</code>", parse_mode="HTML")

@dp.message(Command("delsub"))
async def del_sub(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        channel = message.text.split()[1]
        if channel in required_channels:
            required_channels.remove(channel)
            await message.answer(f"✅ <b>{channel}</b> o'chirildi!", parse_mode="HTML")
        else:
            await message.answer("❌ Bunday kanal yo'q!")
    except:
        await message.answer("❌ Yozing: <code>/delsub @kanal_username</code>", parse_mode="HTML")

@dp.message(Command("subslist"))
async def subs_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    if not required_channels:
        await message.answer("📭 Majburiy obuna kanallari yo'q!")
        return
    text = "📋 <b>Majburiy obuna kanallari:</b>\n\n"
    for i, ch in enumerate(required_channels, 1):
        text += f"{i}. {ch}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("addmovie"))
async def add_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        parts = message.text.split(maxsplit=3)
        kod = parts[1]
        msg_id = int(parts[2])
        nomi = parts[3] if len(parts) > 3 else kod
        movies[kod] = {"nomi": nomi, "msg_id": msg_id, "views": 0, "ratings": []}
        save_movies()
        await message.answer(
            f"✅ <b>Kino qo'shildi!</b>\n\n🎬 Nomi: {nomi}\n🔑 Kod: {kod}",
            parse_mode="HTML"
        )
    except:
        await message.answer(
            "❌ Yozing:\n<code>/addmovie KOD XABAR_ID KINO_NOMI</code>\n\n"
            "Masalan:\n<code>/addmovie 001 26 Avatar</code>",
            parse_mode="HTML"
        )

@dp.message(Command("delmovie"))
async def del_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        kod = message.text.split()[1]
        if kod in movies:
            nomi = movies[kod]["nomi"]
            del movies[kod]
            save_movies()
            await message.answer(f"✅ <b>{nomi}</b> o'chirildi!", parse_mode="HTML")
        else:
            await message.answer("❌ Bunday kod yo'q!")
    except:
        await message.answer("❌ Yozing: <code>/delmovie KOD</code>", parse_mode="HTML")

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    top_movies = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. {v['nomi']} — {v['views']} marta" for i, (k, v) in enumerate(top_movies)])
    yoq = "Hali yoq"
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {len(users)}\n"
        f"🎬 Kinolar soni: {len(movies)}\n"
        f"📢 Majburiy obunalar: {len(required_channels)}\n\n"
        f"🔥 <b>Top kinolar:</b>\n{top_text if top_text else yoq}",
        parse_mode="HTML"
    )

@dp.message(Command("reklama"))
async def reklama(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Yozing: <code>/reklama Xabar matni</code>", parse_mode="HTML")
        return
    text = args[1]
    success = 0
    fail = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 <b>Reklama</b>\n\n{text}", parse_mode="HTML")
            success += 1
        except:
            fail += 1
    await message.answer(f"✅ Reklama yuborildi!\n✔️ Muvaffaqiyatli: {success}\n❌ Xato: {fail}", parse_mode="HTML")

@dp.message(Command("listmovies"))
async def list_movies(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    if not movies:
        await message.answer("📭 Kinolar yo'q!")
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in movies.items():
        text += f"▫️ {info['nomi']} | Kod: <code>{kod}</code> | Ko'rishlar: {info['views']}\n"
    await message.answer(text, parse_mode="HTML")

# ===================== KINO YUBORISH =====================

@dp.message()
async def find_movie(message: Message):
    users.add(message.from_user.id)
    save_users()
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    kod = message.text.strip()
    if kod in movies:
        movie = movies[kod]
        movie["views"] += 1
        save_movies()
        await bot.forward_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=movie["msg_id"]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_{kod}_1"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_{kod}_2"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_{kod}_3"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_{kod}_4"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_{kod}_5"),
        ]])
        await message.answer(
            f"🎬 <b>{movie['nomi']}</b>\n👁 {movie['views']} marta ko'rildi\n\nBaho bering:",
            reply_markup=keyboard, parse_mode="HTML"
        )
    else:
        results = [(k, v) for k, v in movies.items() if kod.lower() in v["nomi"].lower()]
        if results:
            text = "🔍 <b>Siz izlagan kinolar:</b>\n\n"
            for k, v in results:
                text += f"🎬 {v['nomi']}\n🔑 Kod: <code>{k}</code>\n\n"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                "❌ Bunday kino topilmadi!\n\n📚 /katalog — barcha kinolarni ko'rish\n🔎 /qidirish — kino qidirish"
            )

@dp.callback_query(F.data.startswith("rate_"))
async def rate_movie(callback: CallbackQuery):
    parts = callback.data.split("_")
    kod = parts[1]
    ball = int(parts[2])
    if kod in movies:
        movies[kod]["ratings"].append(ball)
        save_movies()
        avg = sum(movies[kod]["ratings"]) / len(movies[kod]["ratings"])
        await callback.message.edit_text(
            f"✅ Bahoyingiz qabul qilindi: {'⭐' * ball}\n📊 O'rtacha reyting: ⭐{avg:.1f}"
        )
    await callback.answer()

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
