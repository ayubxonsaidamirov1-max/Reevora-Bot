import asyncio
import os
import random
from datetime import datetime, timedelta
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters.command import CommandObject
from aiohttp import web

TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = -1003948451744
ADMIN_ID = 8490510878
KARTA_RAQAM = "5614 6873 0746 5246"
ZAKAZ_NARXI = 2000
ADMIN_USERNAME = "@sdmirv"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
required_channels = []

# ===== FSM STATES =====
class ZakazState(StatesGroup):
    waiting_for_kino = State()
    waiting_for_payment = State()

# ===== SUPABASE =====
def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def db_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

# ===== ADMIN =====
def get_admins():
    try:
        with httpx.Client() as client:
            res = client.get(db_url("admins"), headers=headers())
            return [row["user_id"] for row in res.json()]
    except:
        return []

def add_admin_db(user_id):
    with httpx.Client() as client:
        client.post(
            db_url("admins") + "?on_conflict=user_id",
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json={"user_id": user_id}
        )

def remove_admin_db(user_id):
    with httpx.Client() as client:
        client.delete(db_url("admins") + f"?user_id=eq.{user_id}", headers=headers())

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    return user_id in get_admins()

# ===== MOVIES =====
def load_movies():
    with httpx.Client() as client:
        res = client.get(db_url("movies"), headers=headers())
        movies = {}
        for row in res.json():
            movies[row["kod"]] = {
                "nomi": row["nomi"],
                "msg_id": row["msg_id"],
                "views": row["views"],
                "ratings": row.get("ratings") or [],
                "janr": row.get("janr") or "",
                "vip": row.get("vip") or False,
                "bought_by": row.get("bought_by") or []
            }
        return movies

def save_movie(kod, data):
    with httpx.Client() as client:
        client.post(
            db_url("movies") + "?on_conflict=kod",
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json={
                "kod": kod,
                "nomi": data["nomi"],
                "msg_id": data["msg_id"],
                "views": data["views"],
                "ratings": data["ratings"],
                "janr": data.get("janr", ""),
                "vip": data.get("vip", False),
                "bought_by": data.get("bought_by", [])
            }
        )

def delete_movie(kod):
    with httpx.Client() as client:
        client.delete(db_url("movies") + f"?kod=eq.{kod}", headers=headers())

# ===== USERS =====
def save_user(user_id):
    with httpx.Client() as client:
        client.post(
            db_url("users") + "?on_conflict=user_id",
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json={"user_id": user_id}
        )

def get_user_count():
    with httpx.Client() as client:
        res = client.get(db_url("users"), headers={**headers(), "Prefer": "count=exact"}, params={"select": "user_id"})
        count = res.headers.get("content-range", "0/0").split("/")[-1]
        return int(count) if count.isdigit() else 0

def get_all_users():
    with httpx.Client() as client:
        res = client.get(db_url("users"), headers=headers(), params={"select": "user_id"})
        return [row["user_id"] for row in res.json()]

# ===== ZAKAZ =====
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
        client.patch(db_url("zakazlar") + f"?id=eq.{zakaz_id}", headers=headers(), json={"status": status})

def get_all_zakazlar():
    with httpx.Client() as client:
        res = client.get(db_url("zakazlar") + "?status=eq.kutilmoqda", headers=headers())
        return res.json()

# ===== WEB SERVER =====
async def start_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

# ===== SUBSCRIPTION =====
async def check_subscription(user_id):
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
            buttons.append([InlineKeyboardButton(text=f"📢 {channel}", url=f"https://t.me/{channel.replace('@','')}")])
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim!", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== KEYBOARDS =====
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kinolar"), KeyboardButton(text="⭐ Top kinolar")],
            [KeyboardButton(text="🎭 Janrlar"), KeyboardButton(text="🎲 Tasodifiy")],
            [KeyboardButton(text="🆕 Yangi kinolar"), KeyboardButton(text="📦 Zakaz")],
            [KeyboardButton(text="👤 Profil"), KeyboardButton(text="❓ Yordam")],
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

# ===== KUNLIK TAVSIYA =====
async def send_daily_recommendation():
    while True:
        now = datetime.now()
        target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            movies = load_movies()
            # Faqat bepul kinolardan tavsiya
            bepul = [(k, v) for k, v in movies.items() if not v.get("vip")]
            if not bepul:
                continue
            kod, movie = random.choice(bepul)
            users = get_all_users()
            text = (
                f"🌟 <b>Kunlik tavsiya!</b>\n\n"
                f"🎬 <b>{movie['nomi']}</b>\n"
                f"🔑 Kod: <code>{kod}</code>\n\n"
                f"Shu kinoni ko'rish uchun kodni yuboring! 🍿"
            )
            for user_id in users:
                try:
                    await bot.send_message(user_id, text, parse_mode="HTML")
                    await asyncio.sleep(0.05)
                except:
                    pass
        except Exception as e:
            print(f"Kunlik tavsiya xatosi: {e}")

# ===== KINO YUBORISH FUNKSIYASI =====
async def send_movie_to_user(chat_id, movie, kod):
    """Kinoni foydalanuvchiga yuborish — VIP bo'lsa himoyalangan"""
    if movie.get("vip"):
        # Pullik kino — himoyalangan (forward/ulashish bloklangan)
        await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=CHANNEL_ID,
            message_id=movie["msg_id"],
            protect_content=True
        )
    else:
        # Bepul kino — oddiy forward
        await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=CHANNEL_ID,
            message_id=movie["msg_id"]
        )

# ===== HANDLERS =====

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ <b>Botdan foydalanish uchun kanallarga obuna bo'ling:</b>", reply_markup=kb, parse_mode="HTML")
        return
    await message.answer(
        "🎬 <b>Reevora Cinema</b>ga xush kelibsiz!\n\n"
        "🔍 Kino <b>kodini</b> yuboring — film keladi\n"
        "📝 Kino <b>nomini</b> yuboring — qidiruv\n"
        "👇 Menyu tugmalaridan foydalaning",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text("✅ <b>Rahmat! Endi botdan foydalanishingiz mumkin!</b>", parse_mode="HTML")
        await bot.send_message(callback.from_user.id, "Asosiy menyu 👇", reply_markup=main_keyboard())
    else:
        kb = await subscription_keyboard()
        await callback.message.edit_text("⚠️ <b>Hali barcha kanallarga obuna bo'lmadingiz!</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ===== MENYU TUGMALARI =====

@dp.message(F.text == "🎬 Kinolar")
async def kinolar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    if not movies:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in movies.items():
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        janr = f" | {info['janr']}" if info.get("janr") else ""
        vip = " 💎" if info.get("vip") else ""
        text += f"🎬 <b>{info['nomi']}</b>{vip}{stars}{janr}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "⭐ Top kinolar")
async def top_kinolar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    if not movies:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    top = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:10]
    text = "🏆 <b>Top 10 kinolar:</b>\n\n"
    for i, (kod, info) in enumerate(top, 1):
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        vip = " 💎" if info.get("vip") else ""
        text += f"{i}. <b>{info['nomi']}</b>{vip}{stars}\n   👁 {info['views']} marta | 🔑 <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🎭 Janrlar")
async def janrlar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    janrlar = set()
    for info in movies.values():
        if info.get("janr"):
            for j in info["janr"].split(","):
                janrlar.add(j.strip().lower())
    if not janrlar:
        await message.answer(
            "📭 Hozircha janrlar belgilanmagan!\n\n"
            "Admin kino qo'shayotganda janr ham kiriting:\n"
            "<code>/addmovie KOD MSG_ID NOMI janr:komediya</code>",
            parse_mode="HTML"
        )
        return
    buttons = []
    for janr in sorted(janrlar):
        buttons.append([InlineKeyboardButton(text=f"🎭 {janr.capitalize()}", callback_data=f"janr_{janr}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🎭 <b>Janrni tanlang:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("janr_"))
async def janr_callback(callback: CallbackQuery):
    janr = callback.data[5:]
    movies = load_movies()
    results = []
    for k, v in movies.items():
        movie_janrlar = [j.strip().lower() for j in v.get("janr", "").split(",")]
        if janr in movie_janrlar:
            results.append((k, v))
    if not results:
        await callback.message.answer(f"📭 <b>{janr.capitalize()}</b> janrida kino topilmadi!")
        await callback.answer()
        return
    text = f"🎭 <b>{janr.capitalize()} kinolari:</b>\n\n"
    for k, v in results:
        stars = ""
        if v["ratings"]:
            avg = sum(v["ratings"]) / len(v["ratings"])
            stars = f" ⭐{avg:.1f}"
        vip = " 💎" if v.get("vip") else ""
        text += f"🎬 <b>{v['nomi']}</b>{vip}{stars}\n🔑 Kod: <code>{k}</code>\n\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.message(F.text == "🎲 Tasodifiy")
async def tasodifiy_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    # Faqat bepul kinolardan tasodifiy
    bepul = [(k, v) for k, v in movies.items() if not v.get("vip")]
    if not bepul:
        await message.answer("📭 Hozircha bepul kinolar yo'q!")
        return
    kod, movie = random.choice(bepul)
    movie["views"] += 1
    save_movie(kod, movie)
    await send_movie_to_user(message.chat.id, movie, kod)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⭐1", callback_data=f"rate_{kod}_1"),
        InlineKeyboardButton(text="⭐2", callback_data=f"rate_{kod}_2"),
        InlineKeyboardButton(text="⭐3", callback_data=f"rate_{kod}_3"),
        InlineKeyboardButton(text="⭐4", callback_data=f"rate_{kod}_4"),
        InlineKeyboardButton(text="⭐5", callback_data=f"rate_{kod}_5"),
    ]])
    await message.answer(
        f"🎲 <b>Tasodifiy kino: {movie['nomi']}</b>\n"
        f"👁 {movie['views']} marta ko'rildi\n\nBaho bering:",
        reply_markup=kb, parse_mode="HTML"
    )

@dp.message(F.text == "🆕 Yangi kinolar")
async def yangi_kinolar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    if not movies:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    yangi = list(movies.items())[-10:]
    yangi.reverse()
    text = "🆕 <b>Yangi qo'shilgan kinolar:</b>\n\n"
    for kod, info in yangi:
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        vip = " 💎" if info.get("vip") else ""
        text += f"🎬 <b>{info['nomi']}</b>{vip}{stars}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👤 Profil")
async def profil_btn(message: Message):
    save_user(message.from_user.id)
    user = message.from_user
    user_count = get_user_count()
    await message.answer(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Ism: {user.full_name}\n"
        f"👥 Botdagi foydalanuvchilar: {user_count}",
        parse_mode="HTML"
    )

@dp.message(F.text == "❓ Yordam")
async def yordam_btn(message: Message):
    await message.answer(
        "❓ <b>Yordam bo'limi</b>\n\n"
        "🔍 <b>Kino qidirish:</b>\n"
        "Kino kodini yoki nomini yuboring\n\n"
        "📋 <b>Menyu tugmalari:</b>\n"
        "🎬 Kinolar — barcha kinolar\n"
        "⭐ Top kinolar — eng ko'p ko'rilganlar\n"
        "🎭 Janrlar — janr bo'yicha qidiruv\n"
        "🎲 Tasodifiy — tasodifiy kino\n"
        "🆕 Yangi kinolar — oxirgi qo'shilganlar\n"
        "📦 Zakaz — kino buyurtma qilish\n"
        "👤 Profil — shaxsiy ma'lumotlar\n\n"
        "💎 — pullik kino (zakaz orqali)\n\n"
        f"💬 <b>Muammo bo'lsa?</b>\n"
        f"Admin: {ADMIN_USERNAME}",
        parse_mode="HTML"
    )

# ===== ZAKAZ FSM =====

@dp.message(F.text == "📦 Zakaz")
@dp.message(Command("zakaz"))
async def zakaz_start(message: Message, state: FSMContext):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    await state.set_state(ZakazState.waiting_for_kino)
    await message.answer(
        "📦 <b>Zakaz berish</b>\n\n"
        "🎬 Kino <b>nomi</b>, <b>rasmi</b> yoki <b>qisqa videosini</b> yuboring:\n\n"
        "❌ Bekor qilish uchun tugmani bosing",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text == "❌ Bekor qilish", StateFilter(ZakazState))
async def zakaz_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Zakaz bekor qilindi.", reply_markup=main_keyboard())

@dp.message(StateFilter(ZakazState.waiting_for_kino))
async def zakaz_kino_received(message: Message, state: FSMContext):
    username = message.from_user.username or message.from_user.full_name

    if message.text:
        kino_nomi = message.text
        await state.update_data(kino_nomi=kino_nomi, media_type="text", file_id=None)
    elif message.photo:
        kino_nomi = message.caption or "Rasm orqali zakaz"
        await state.update_data(kino_nomi=kino_nomi, media_type="photo", file_id=message.photo[-1].file_id)
    elif message.video:
        kino_nomi = message.caption or "Video orqali zakaz"
        await state.update_data(kino_nomi=kino_nomi, media_type="video", file_id=message.video.file_id)
    else:
        await message.answer("⚠️ Faqat matn, rasm yoki video yuboring!")
        return

    zakaz_id = create_zakaz(message.from_user.id, username, kino_nomi)
    await state.update_data(zakaz_id=zakaz_id)
    await state.set_state(ZakazState.waiting_for_payment)

    await message.answer(
        f"✅ <b>Zakaz qabul qilindi!</b>\n\n"
        f"🎬 Kino: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 To'lov miqdori: <b>{ZAKAZ_NARXI:,} so'm</b>\n\n"
        f"💳 Karta raqami:\n<code>{KARTA_RAQAM}</code>\n\n"
        f"✅ To'lovni amalga oshirib, <b>screenshot</b>ni yuboring!\n"
        f"⏳ Admin tekshirib, kinoni yuboradi.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )

    data = await state.get_data()
    admin_text = (
        f"🆕 <b>Yangi zakaz!</b>\n\n"
        f"👤 @{username} (ID: {message.from_user.id})\n"
        f"🎬 Kino: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 Narx: {ZAKAZ_NARXI:,} so'm\n\n"
        f"⏳ To'lov screenshoti kutilmoqda..."
    )

    if data.get("media_type") == "photo":
        await bot.send_photo(ADMIN_ID, photo=data["file_id"], caption=admin_text, parse_mode="HTML")
    elif data.get("media_type") == "video":
        await bot.send_video(ADMIN_ID, video=data["file_id"], caption=admin_text, parse_mode="HTML")
    else:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")

@dp.message(StateFilter(ZakazState.waiting_for_payment), F.photo)
async def zakaz_payment_received(message: Message, state: FSMContext):
    data = await state.get_data()
    zakaz_id = data.get("zakaz_id", "?")
    kino_nomi = data.get("kino_nomi", "?")
    username = message.from_user.username or message.from_user.full_name
    caption = message.caption or ""

    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"💳 <b>To'lov screenshoti!</b>\n\n"
            f"👤 @{username} (ID: {message.from_user.id})\n"
            f"🎬 Kino: <b>{kino_nomi}</b>\n"
            f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
            f"{caption}\n\n"
            f"✅ /tasdiqlash {zakaz_id} [kino_kodi]\n"
            f"❌ /rad {zakaz_id}"
        ),
        parse_mode="HTML"
    )
    await state.clear()
    await message.answer(
        "✅ <b>To'lov screenshoti adminga yuborildi!</b>\n\n"
        "⏳ Admin tekshirib, kinoni tez yuboradi.",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@dp.message(StateFilter(ZakazState.waiting_for_payment))
async def zakaz_payment_wrong(message: Message):
    await message.answer(
        "⚠️ Iltimos, <b>to'lov screenshotini</b> (rasm) yuboring!\n\n"
        "❌ Bekor qilish uchun tugmani bosing.",
        parse_mode="HTML"
    )

@dp.message(F.photo, StateFilter(None))
async def screenshot_handler(message: Message):
    user = message.from_user
    username = user.username or user.full_name
    caption = message.caption or ""
    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"📸 <b>Rasm!</b>\n\n"
            f"👤 @{username} (ID: {user.id})\n"
            f"{caption}"
        ),
        parse_mode="HTML"
    )
    await message.answer("✅ Rasm adminga yuborildi!", parse_mode="HTML")

# ===== ADMIN COMMANDS =====

@dp.message(Command("addadmin"))
async def add_admin_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/addadmin USER_ID</code>", parse_mode="HTML")
        return
    try:
        new_admin_id = int(command.args.strip())
        add_admin_db(new_admin_id)
        await message.answer(f"✅ Yangi admin qo'shildi!\nID: <code>{new_admin_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("removeadmin"))
async def remove_admin_cmd(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    if not command.args:
        await message.answer("❌ Format: <code>/removeadmin USER_ID</code>", parse_mode="HTML")
        return
    try:
        admin_id = int(command.args.strip())
        remove_admin_db(admin_id)
        await message.answer(f"✅ Admin o'chirildi!\nID: <code>{admin_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("admins"))
async def admins_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    admins = get_admins()
    text = "👑 <b>Adminlar ro'yxati:</b>\n\n"
    text += f"⭐ Super admin: <code>{ADMIN_ID}</code>\n\n"
    if admins:
        for i, admin_id in enumerate(admins, 1):
            text += f"{i}. <code>{admin_id}</code>\n"
    else:
        text += "Qo'shimcha adminlar yo'q."
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("tasdiqlash"))
async def tasdiqlash_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/tasdiqlash ZAKAZ_ID KINO_KODI</code>", parse_mode="HTML")
        return
    try:
        parts = command.args.split()
        zakaz_id = int(parts[0])
        kino_kod = parts[1]
        zakaz = get_zakaz(zakaz_id)
        if not zakaz:
            await message.answer("❌ Zakaz topilmadi!")
            return
        movies = load_movies()
        if kino_kod not in movies:
            await message.answer(f"❌ <code>{kino_kod}</code> kodli kino yo'q!", parse_mode="HTML")
            return
        movie = movies[kino_kod]

        # VIP kinoni faqat o'sha foydalanuvchiga belgilash
        if movie.get("vip"):
            bought = movie.get("bought_by") or []
            if zakaz["user_id"] not in bought:
                bought.append(zakaz["user_id"])
                movie["bought_by"] = bought
                save_movie(kino_kod, movie)

        await send_movie_to_user(zakaz["user_id"], movie, kino_kod)
        await bot.send_message(
            zakaz["user_id"],
            f"🎉 <b>{movie['nomi']}</b> yuborildi! Rohatingiz kelsin! 🍿",
            parse_mode="HTML"
        )
        update_zakaz_status(zakaz_id, "tasdiqlangan")
        await message.answer(f"✅ Zakaz #{zakaz_id} tasdiqlandi!")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("rad"))
async def rad_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/rad ZAKAZ_ID</code>", parse_mode="HTML")
        return
    try:
        zakaz_id = int(command.args.strip())
        zakaz = get_zakaz(zakaz_id)
        if not zakaz:
            await message.answer("❌ Zakaz topilmadi!")
            return
        update_zakaz_status(zakaz_id, "rad etilgan")
        await bot.send_message(
            zakaz["user_id"],
            f"❌ <b>Zakazingiz rad etildi.</b>\n🎬 {zakaz['kino_nomi']}",
            parse_mode="HTML"
        )
        await message.answer(f"✅ Zakaz #{zakaz_id} rad etildi.")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("zakazlar"))
async def zakazlar_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    zakazlar = get_all_zakazlar()
    if not zakazlar:
        await message.answer("📭 Kutilayotgan zakazlar yo'q!")
        return
    text = "📋 <b>Kutilayotgan zakazlar:</b>\n\n"
    for z in zakazlar:
        text += f"🆔 {z['id']} | 🎬 {z['kino_nomi']} | 👤 @{z['username']}\n"
    text += "\n✅ /tasdiqlash [id] [kod]\n❌ /rad [id]"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("addmovie"))
async def add_movie(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer(
            "❌ Format:\n"
            "<code>/addmovie KOD MSG_ID NOMI</code>\n"
            "Janr bilan:\n"
            "<code>/addmovie KOD MSG_ID NOMI janr:komediya</code>\n"
            "Pullik kino:\n"
            "<code>/addmovie KOD MSG_ID NOMI janr:drama vip:ha</code>",
            parse_mode="HTML"
        )
        return
    try:
        parts = command.args.split(maxsplit=2)
        kod = parts[0]
        msg_id = int(parts[1])
        nomi_janr = parts[2] if len(parts) > 2 else kod

        janr = ""
        vip = False
        nomi = nomi_janr

        if "vip:ha" in nomi_janr:
            vip = True
            nomi_janr = nomi_janr.replace("vip:ha", "").strip()

        if "janr:" in nomi_janr:
            nomi_part, janr_part = nomi_janr.split("janr:", 1)
            nomi = nomi_part.strip()
            janr = janr_part.strip()
        else:
            nomi = nomi_janr.strip()

        save_movie(kod, {"nomi": nomi, "msg_id": msg_id, "views": 0, "ratings": [], "janr": janr, "vip": vip, "bought_by": []})

        # Faqat bepul kinolar uchun xabar yuboriladi
        if not vip:
            users = get_all_users()
            janr_text = f"\n🎭 Janr: {janr}" if janr else ""
            notif = (
                f"🆕 <b>Yangi kino qo'shildi!</b>\n\n"
                f"🎬 <b>{nomi}</b>{janr_text}\n"
                f"🔑 Kod: <code>{kod}</code>\n\n"
                f"Kodini yuboring va tomosha qiling! 🍿"
            )
            for user_id in users:
                try:
                    await bot.send_message(user_id, notif, parse_mode="HTML")
                    await asyncio.sleep(0.05)
                except:
                    pass
            xabar = f"✅ Bepul kino qo'shildi! {len(users)} ta foydalanuvchiga xabar yuborildi."
        else:
            xabar = "✅ Pullik (VIP) kino qo'shildi! Foydalanuvchilarga xabar yuborilmadi."

        janr_text = f"\n🎭 Janr: {janr}" if janr else ""
        vip_text = "\n💎 Tur: Pullik" if vip else "\n🆓 Tur: Bepul"
        await message.answer(
            f"{xabar}\n"
            f"🎬 {nomi}\n"
            f"🔑 Kod: <code>{kod}</code>"
            f"{janr_text}{vip_text}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"❌ Xato: {e}\n\nFormat:\n<code>/addmovie KOD MSG_ID NOMI</code>",
            parse_mode="HTML"
        )

@dp.message(Command("delmovie"))
async def del_movie(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/delmovie KOD</code>", parse_mode="HTML")
        return
    kod = command.args.strip()
    movies = load_movies()
    if kod in movies:
        nomi = movies[kod]["nomi"]
        delete_movie(kod)
        await message.answer(f"✅ <b>{nomi}</b> o'chirildi!", parse_mode="HTML")
    else:
        await message.answer("❌ Bunday kod yo'q!")

@dp.message(Command("listmovies"))
async def list_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    movies = load_movies()
    if not movies:
        await message.answer("📭 Kinolar yo'q!")
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in movies.items():
        janr = f" | {info['janr']}" if info.get("janr") else ""
        vip = " 💎" if info.get("vip") else ""
        text += f"▫️ {info['nomi']}{vip}{janr} | Kod: <code>{kod}</code> | Ko'rishlar: {info['views']}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("addsub"))
async def add_sub(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/addsub @kanal</code>", parse_mode="HTML")
        return
    channel = command.args.strip()
    if channel not in required_channels:
        required_channels.append(channel)
        await message.answer(f"✅ <b>{channel}</b> qo'shildi!", parse_mode="HTML")
    else:
        await message.answer("⚠️ Bu kanal allaqachon bor!")

@dp.message(Command("delsub"))
async def del_sub(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/delsub @kanal</code>", parse_mode="HTML")
        return
    channel = command.args.strip()
    if channel in required_channels:
        required_channels.remove(channel)
        await message.answer(f"✅ <b>{channel}</b> o'chirildi!")
    else:
        await message.answer("❌ Bunday kanal yo'q!")

@dp.message(Command("subslist"))
async def subs_list(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not required_channels:
        await message.answer("📭 Majburiy obuna kanallari yo'q!")
        return
    text = "📋 <b>Majburiy obuna kanallari:</b>\n\n"
    for i, ch in enumerate(required_channels, 1):
        text += f"{i}. {ch}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    movies = load_movies()
    user_count = get_user_count()
    zakazlar = get_all_zakazlar()
    admins = get_admins()
    vip_count = sum(1 for v in movies.values() if v.get("vip"))
    top = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. {v['nomi']} — {v['views']} marta" for i, (k, v) in enumerate(top)])
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {user_count}\n"
        f"🎬 Kinolar: {len(movies)} (💎 {vip_count} pullik)\n"
        f"👑 Adminlar: {len(admins) + 1}\n"
        f"📢 Majburiy obunalar: {len(required_channels)}\n"
        f"📦 Kutilayotgan zakazlar: {len(zakazlar)}\n\n"
        f"🔥 <b>Top kinolar:</b>\n{top_text or 'Hali yoq'}",
        parse_mode="HTML"
    )

@dp.message(Command("reklama"))
async def reklama(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/reklama Xabar matni</code>", parse_mode="HTML")
        return
    users = get_all_users()
    success = fail = 0
    for user_id in users:
        try:
            await bot.send_message(user_id, f"📢 <b>Reklama</b>\n\n{command.args}", parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    await message.answer(f"✅ Yuborildi!\n✔️ Muvaffaqiyatli: {success}\n❌ Xato: {fail}")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "❓ <b>Yordam</b>\n\n"
        "▫️ Kino <b>kodini</b> yuboring → film keladi\n"
        "▫️ Kino <b>nomini</b> yuboring → qidiruv\n"
        "▫️ /zakaz → kino buyurtma\n\n"
        f"💬 Muammo bo'lsa: {ADMIN_USERNAME}",
        parse_mode="HTML"
    )

@dp.message(Command("katalog"))
async def katalog(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
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
        vip = " 💎" if info.get("vip") else ""
        text += f"🎬 <b>{info['nomi']}</b>{vip}{stars}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

# ===== KINO QIDIRISH =====
@dp.message(StateFilter(None))
async def find_movie(message: Message):
    if not message.text or message.text.startswith("/"):
        return
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    kod = message.text.strip()
    movies = load_movies()
    if kod in movies:
        movie = movies[kod]

        # VIP kino tekshiruvi
        if movie.get("vip"):
            bought = movie.get("bought_by") or []
            if message.from_user.id not in bought:
                await message.answer(
                    f"💎 <b>{movie['nomi']}</b> — pullik kino!\n\n"
                    f"Bu kinoni ko'rish uchun zakaz bering:\n"
                    f"📦 /zakaz — buyurtma berish\n\n"
                    f"💰 Narx: {ZAKAZ_NARXI:,} so'm",
                    parse_mode="HTML"
                )
                return

        movie["views"] += 1
        save_movie(kod, movie)
        await send_movie_to_user(message.chat.id, movie, kod)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⭐1", callback_data=f"rate_{kod}_1"),
            InlineKeyboardButton(text="⭐2", callback_data=f"rate_{kod}_2"),
            InlineKeyboardButton(text="⭐3", callback_data=f"rate_{kod}_3"),
            InlineKeyboardButton(text="⭐4", callback_data=f"rate_{kod}_4"),
            InlineKeyboardButton(text="⭐5", callback_data=f"rate_{kod}_5"),
        ]])
        vip_text = " 💎" if movie.get("vip") else ""
        await message.answer(
            f"🎬 <b>{movie['nomi']}</b>{vip_text}\n"
            f"👁 {movie['views']} marta ko'rildi\n\nBaho bering:",
            reply_markup=kb, parse_mode="HTML"
        )
    else:
        results = [(k, v) for k, v in movies.items() if kod.lower() in v["nomi"].lower()]
        if results:
            text = "🔍 <b>Topilgan kinolar:</b>\n\n"
            for k, v in results:
                vip = " 💎" if v.get("vip") else ""
                text += f"🎬 {v['nomi']}{vip}\n🔑 Kod: <code>{k}</code>\n\n"
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(
                f"❌ <b>{kod}</b> topilmadi!\n\n"
                f"📚 /katalog — barcha kinolar\n"
                f"📦 /zakaz — zakaz berish",
                parse_mode="HTML"
            )

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
        await callback.message.edit_text(
            f"✅ Bahoyingiz: {'⭐' * ball}\n"
            f"📊 O'rtacha reyting: ⭐{avg:.1f}"
        )
    await callback.answer()

# ===== MAIN =====
async def main():
    await start_web()
    asyncio.create_task(send_daily_recommendation())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
