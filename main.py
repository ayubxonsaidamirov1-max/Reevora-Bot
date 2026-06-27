import asyncio
import os
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web

TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003948451744
ADMIN_ID = 8490510878
KARTA_RAQAM = "5614 6873 0746 5246"  # O'z karta raqamingizni yozing
ZAKAZ_NARXI = 10000

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
required_channels = []

# ===================== HTTPX SUPABASE =====================

def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def db_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def load_movies():
    with httpx.Client() as client:
        res = client.get(db_url("movies"), headers=headers())
        movies = {}
        for row in res.json():
            ratings = row.get("ratings") or []
            movies[row["kod"]] = {
                "nomi": row["nomi"],
                "msg_id": row["msg_id"],
                "views": row["views"],
                "ratings": ratings
            }
        return movies

def save_movie(kod, data):
    with httpx.Client() as client:
        payload = {
            "kod": kod,
            "nomi": data["nomi"],
            "msg_id": data["msg_id"],
            "views": data["views"],
            "ratings": data["ratings"]
        }
        client.post(
            db_url("movies") + "?on_conflict=kod",
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json=payload
        )

def delete_movie(kod):
    with httpx.Client() as client:
        client.delete(db_url("movies") + f"?kod=eq.{kod}", headers=headers())

def save_user(user_id):
    with httpx.Client() as client:
        client.post(
            db_url("users") + "?on_conflict=user_id",
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json={"user_id": user_id}
        )

def get_user_count():
    with httpx.Client() as client:
        res = client.get(
            db_url("users"),
            headers={**headers(), "Prefer": "count=exact"},
            params={"select": "user_id"}
        )
        count = res.headers.get("content-range", "0/0").split("/")[-1]
        return int(count) if count.isdigit() else 0

def get_all_users():
    with httpx.Client() as client:
        res = client.get(db_url("users"), headers=headers(), params={"select": "user_id"})
        return [row["user_id"] for row in res.json()]

def create_zakaz(user_id, username, kino_nomi):
    with httpx.Client() as client:
        res = client.post(
            db_url("zakazlar"),
            headers=headers(),
            json={"user_id": user_id, "username": username, "kino_nomi": kino_nomi, "status": "kutilmoqda"}
        )
        return res.json()[0]["id"]

def get_zakaz(zakaz_id):
    with httpx.Client() as client:
        res = client.get(db_url("zakazlar") + f"?id=eq.{zakaz_id}", headers=headers())
        data = res.json()
        return data[0] if data else None

def update_zakaz_status(zakaz_id, status):
    with httpx.Client() as client:
        client.patch(
            db_url("zakazlar") + f"?id=eq.{zakaz_id}",
            headers=headers(),
            json={"status": status}
        )

def get_all_zakazlar():
    with httpx.Client() as client:
        res = client.get(db_url("zakazlar") + "?status=eq.kutilmoqda", headers=headers())
        return res.json()

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

# ===================== PASTKI MENYU =====================

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Film qidirish"), KeyboardButton(text="📚 Katalog")],
            [KeyboardButton(text="📦 Zakaz berish"), KeyboardButton(text="ℹ️ Yordam")],
        ],
        resize_keyboard=True
    )

# ===================== FOYDALANUVCHI =====================

@dp.message(Command("start"))
async def start(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>", reply_markup=keyboard, parse_mode="HTML")
        return
    await message.answer(
        "🎬 <b>Reevora Cinema Bot</b>ga xush kelibsiz!\n\n"
        "🔍 Kino kodini yuboring — filmni topasiz\n"
        "📝 Kino nomini yuboring — qidiruv amalga oshiriladi\n\n"
        "📚 /katalog — barcha kinolar\n"
        "🔎 /qidirish [nom] — kino qidirish\n"
        "📦 /zakaz [nom] — kino zakaz berish\n"
        "ℹ️ /help — yordam",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text("✅ <b>Rahmat! Endi botdan foydalanishingiz mumkin!</b>\n\n🎬 Kino kodini yuboring yoki /katalog ga kiring.", parse_mode="HTML")
        await bot.send_message(callback.from_user.id, "Asosiy menyu:", reply_markup=main_keyboard())
    else:
        keyboard = await subscription_keyboard()
        await callback.message.edit_text("⚠️ <b>Siz hali ham barcha kanallarga obuna bo'lmagansiz!</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.message(Command("help"))
async def help_cmd(message: Message):
    save_user(message.from_user.id)
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "▫️ Kino <b>kodini</b> yuboring → film keladi\n"
        "▫️ /katalog → barcha kinolar ro'yxati\n"
        "▫️ /qidirish Avatar → kino qidirish\n"
        "▫️ /zakaz Avatar → botda yo'q kinoni zakaz qilish\n\n"
        "⭐ Kino kelgandan so'ng unga baho bering!",
        parse_mode="HTML"
    )

@dp.message(Command("katalog"))
async def katalog(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    movies = load_movies()
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
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Yozing: /qidirish <b>kino nomi</b>", parse_mode="HTML")
        return
    query = args[1].lower()
    movies = load_movies()
    results = [(k, v) for k, v in movies.items() if query in v["nomi"].lower()]
    if not results:
        await message.answer(f"🔍 <b>{args[1]}</b> topilmadi!", parse_mode="HTML")
        return
    text = "🔍 <b>Qidiruv natijalari:</b>\n\n"
    for kod, info in results:
        text += f"🎬 <b>{info['nomi']}</b>\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

# ===================== ZAKAZ =====================

@dp.message(Command("zakaz"))
async def zakaz_cmd(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Yozing: /zakaz <b>kino nomi</b>\n\nMasalan: <code>/zakaz Avatar 3</code>", parse_mode="HTML")
        return
    kino_nomi = args[1]
    username = message.from_user.username or message.from_user.full_name
    zakaz_id = create_zakaz(message.from_user.id, username, kino_nomi)
    await message.answer(
        f"📦 <b>Zakazingiz qabul qilindi!</b>\n\n"
        f"🎬 Kino: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 To'lov miqdori: <b>{ZAKAZ_NARXI:,} so'm</b>\n\n"
        f"💳 Karta raqami:\n<code>{KARTA_RAQAM}</code>\n\n"
        f"✅ To'lovni amalga oshirib, <b>screenshot</b>ni shu yerga yuboring!\n"
        f"⏳ Admin tekshirib, kinoni yuboradi.",
        parse_mode="HTML"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>Yangi zakaz!</b>\n\n"
        f"👤 Foydalanuvchi: @{username} (ID: {message.from_user.id})\n"
        f"🎬 Kino: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 Narx: {ZAKAZ_NARXI:,} so'm\n\n"
        f"⏳ To'lov kutilmoqda...",
        parse_mode="HTML"
    )

@dp.message(F.photo)
async def screenshot_handler(message: Message):
    user = message.from_user
    username = user.username or user.full_name
    caption = message.caption or ""
    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"💳 <b>To'lov screenshoti!</b>\n\n"
            f"👤 Foydalanuvchi: @{username} (ID: {user.id})\n"
            f"{caption}\n\n"
            f"✅ Tasdiqlash: /tasdiqlash [zakaz_id] [kino_kodi]\n"
            f"❌ Rad etish: /rad [zakaz_id]"
        ),
        parse_mode="HTML"
    )
    await message.answer("✅ <b>Screenshotingiz adminga yuborildi!</b>\n\n⏳ Admin tekshirib, tez orada kinoni yuboradi.", parse_mode="HTML")

# ===================== ADMIN ZAKAZ =====================

@dp.message(Command("tasdiqlash"))
async def tasdiqlash_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        parts = message.text.split()
        zakaz_id = int(parts[1])
        kino_kod = parts[2]
        zakaz = get_zakaz(zakaz_id)
        if not zakaz:
            await message.answer("❌ Bunday zakaz topilmadi!")
            return
        movies = load_movies()
        if kino_kod not in movies:
            await message.answer(f"❌ <code>{kino_kod}</code> kodli kino topilmadi!\n\nKinolar: /listmovies", parse_mode="HTML")
            return
        movie = movies[kino_kod]
        await bot.forward_message(chat_id=zakaz["user_id"], from_chat_id=CHANNEL_ID, message_id=movie["msg_id"])
        await bot.send_message(zakaz["user_id"], f"🎉 <b>Zakazingiz tasdiqlandi!</b>\n\n🎬 <b>{movie['nomi']}</b> kinosi yuborildi!\n\nRohatingiz kelsin! 🍿", parse_mode="HTML")
        update_zakaz_status(zakaz_id, "tasdiqlangan")
        await message.answer(f"✅ Zakaz #{zakaz_id} tasdiqlandi va kino yuborildi!")
    except IndexError:
        await message.answer("❌ Yozing: <code>/tasdiqlash ZAKAZ_ID KINO_KODI</code>\n\nMasalan: <code>/tasdiqlash 5 001</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("rad"))
async def rad_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        zakaz_id = int(message.text.split()[1])
        zakaz = get_zakaz(zakaz_id)
        if not zakaz:
            await message.answer("❌ Bunday zakaz topilmadi!")
            return
        update_zakaz_status(zakaz_id, "rad etilgan")
        await bot.send_message(zakaz["user_id"], f"❌ <b>Zakazingiz rad etildi!</b>\n\n🆔 Zakaz ID: {zakaz_id}\n🎬 Kino: {zakaz['kino_nomi']}\n\nMuammo bo'lsa admin bilan bog'laning.", parse_mode="HTML")
        await message.answer(f"✅ Zakaz #{zakaz_id} rad etildi.")
    except IndexError:
        await message.answer("❌ Yozing: <code>/rad ZAKAZ_ID</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("zakazlar"))
async def zakazlar_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    zakazlar = get_all_zakazlar()
    if not zakazlar:
        await message.answer("📭 Kutilayotgan zakazlar yo'q!")
        return
    text = "📋 <b>Kutilayotgan zakazlar:</b>\n\n"
    for z in zakazlar:
        text += f"🆔 ID: {z['id']} | 🎬 {z['kino_nomi']} | 👤 @{z['username']}\n"
    text += "\n✅ /tasdiqlash [id] [kino_kodi]\n❌ /rad [id]"
    await message.answer(text, parse_mode="HTML")

# ===================== ADMIN BOSHQA =====================

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
        save_movie(kod, {"nomi": nomi, "msg_id": msg_id, "views": 0, "ratings": []})
        await message.answer(f"✅ <b>Kino qo'shildi!</b>\n\n🎬 Nomi: {nomi}\n🔑 Kod: {kod}", parse_mode="HTML")
    except:
        await message.answer("❌ Yozing:\n<code>/addmovie KOD XABAR_ID KINO_NOMI</code>\n\nMasalan:\n<code>/addmovie 001 26 Avatar</code>", parse_mode="HTML")

@dp.message(Command("delmovie"))
async def del_movie(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Sizda ruxsat yo'q!")
        return
    try:
        kod = message.text.split()[1]
        movies = load_movies()
        if kod in movies:
            nomi = movies[kod]["nomi"]
            delete_movie(kod)
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
    movies = load_movies()
    user_count = get_user_count()
    zakazlar = get_all_zakazlar()
    top_movies = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. {v['nomi']} — {v['views']} marta" for i, (k, v) in enumerate(top_movies)])
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {user_count}\n"
        f"🎬 Kinolar soni: {len(movies)}\n"
        f"📢 Majburiy obunalar: {len(required_channels)}\n"
        f"📦 Kutilayotgan zakazlar: {len(zakazlar)}\n\n"
        f"🔥 <b>Top kinolar:</b>\n{top_text if top_text else 'Hali yoq'}",
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
    users = get_all_users()
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
    movies = load_movies()
    if not movies:
        await message.answer("📭 Kinolar yo'q!")
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in movies.items():
        text += f"▫️ {info['nomi']} | Kod: <code>{kod}</code> | Ko'rishlar: {info['views']}\n"
    await message.answer(text, parse_mode="HTML")

# ===================== TUGMALAR =====================

@dp.message(F.text == "🔍 Film qidirish")
async def film_qidirish_btn(message: Message):
    await message.answer("🔍 Kino nomini yoki kodini yuboring:")

@dp.message(F.text == "📚 Katalog")
async def katalog_btn(message: Message):
    await katalog(message)

@dp.message(F.text == "📦 Zakaz berish")
async def zakaz_btn(message: Message):
    await message.answer("📦 <b>Kino zakaz berish</b>\n\nQuyidagi formatda yozing:\n<code>/zakaz Kino nomi</code>\n\nMasalan: <code>/zakaz Avatar 3</code>", parse_mode="HTML")

@dp.message(F.text == "ℹ️ Yordam")
async def yordam_btn(message: Message):
    await help_cmd(message)

# ===================== KINO TOPISH =====================

@dp.message()
async def find_movie(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        keyboard = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=keyboard, parse_mode="HTML")
        return
    kod = message.text.strip()
    movies = load_movies()
    if kod in movies:
        movie = movies[kod]
        movie["views"] += 1
        save_movie(kod, movie)
        await bot.forward_message(chat_id=message.chat.id, from_chat_id=CHANNEL_ID, message_id=movie["msg_id"])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_{kod}_1"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_{kod}_2"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_{kod}_3"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_{kod}_4"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_{kod}_5"),
        ]])
        await message.answer(f"🎬 <b>{movie['nomi']}</b>\n👁 {movie['views']} marta ko'rildi\n\nBaho bering:", reply_markup=keyboard, parse_mode="HTML")
    else:
        results = [(k, v) for k, v in movies.items() if kod.lower() in v["nomi"].lower()]
        if results:
            text = "🔍 <b>Siz izlagan kinolar:</b>\n\n"
            for k, v in results:
                text += f"🎬 {v['nomi']}\n🔑 Kod: <code>{k}</code>\n\n"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ Bunday kino topilmadi!\n\n📚 /katalog — barcha kinolarni ko'rish\n🔎 /qidirish — kino qidirish\n📦 /zakaz — kino zakaz berish")

@dp.callback_query(F.data.startswith("rate_"))
async def rate_movie(callback: CallbackQuery):
    parts = callback.data.split("_")
    kod = parts[1]
    ball = int(parts[2])
    movies = load_movies()
    if kod in movies:
        movie = movies[kod]
        movie["ratings"].append(ball)
        save_movie(kod, movie)
        avg = sum(movie["ratings"]) / len(movie["ratings"])
        await callback.message.edit_text(f"✅ Bahoyingiz qabul qilindi: {'⭐' * ball}\n📊 O'rtacha reyting: ⭐{avg:.1f}")
    await callback.answer()

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
