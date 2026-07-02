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
SERIAL_KANAL_ID = int(os.environ.get("SERIAL_KANAL_ID", "0"))
ADMIN_ID = 8490510878
KARTA_RAQAM = "5614 6873 0746 5246"
KINO_ZAKAZ_NARXI = 2000
SERIAL_ZAKAZ_NARXI = 5000
ADMIN_USERNAME = "@sdmirv"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
required_channels = []

# ===== FSM =====
class ZakazState(StatesGroup):
    waiting_for_kino = State()
    waiting_for_payment = State()

class ReklamaState(StatesGroup):
    waiting_for_content = State()

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

# ===== SERIALS =====
def load_serials():
    with httpx.Client() as client:
        res = client.get(db_url("serials"), headers=headers())
        return res.json()

def get_serial_names():
    serials = load_serials()
    names = {}
    for row in serials:
        nomi = row["nomi"]
        if nomi not in names:
            names[nomi] = {"vip": row.get("vip", False), "views": 0}
        names[nomi]["views"] += row.get("views", 0)
    return names

def get_serial_fasls(nomi):
    serials = load_serials()
    fasls = set()
    for row in serials:
        if row["nomi"].lower() == nomi.lower():
            fasls.add(row["fasl"])
    return sorted(fasls)

def get_serial_qismlar(nomi, fasl):
    serials = load_serials()
    qismlar = []
    for row in serials:
        if row["nomi"].lower() == nomi.lower() and row["fasl"] == fasl:
            qismlar.append(row)
    return sorted(qismlar, key=lambda x: x["qism"])

def get_serial_qism(nomi, fasl, qism):
    serials = load_serials()
    for row in serials:
        if row["nomi"].lower() == nomi.lower() and row["fasl"] == fasl and row["qism"] == qism:
            return row
    return None

def save_serial(nomi, fasl, qism, msg_id, vip=False):
    with httpx.Client() as client:
        existing = get_serial_qism(nomi, fasl, qism)
        if existing:
            client.patch(
                db_url("serials") + f"?id=eq.{existing['id']}",
                headers=headers(),
                json={"msg_id": msg_id, "vip": vip}
            )
        else:
            client.post(
                db_url("serials"),
                headers=headers(),
                json={"nomi": nomi, "fasl": fasl, "qism": qism, "msg_id": msg_id, "vip": vip, "bought_by": [], "views": 0}
            )

def delete_serial(nomi):
    with httpx.Client() as client:
        serials = load_serials()
        for row in serials:
            if row["nomi"].lower() == nomi.lower():
                client.delete(db_url("serials") + f"?id=eq.{row['id']}", headers=headers())

def update_serial_views(serial_id):
    with httpx.Client() as client:
        res = client.get(db_url("serials") + f"?id=eq.{serial_id}", headers=headers())
        data = res.json()
        if data:
            views = data[0].get("views", 0) + 1
            client.patch(db_url("serials") + f"?id=eq.{serial_id}", headers=headers(), json={"views": views})

def get_serial_bought(nomi):
    serials = load_serials()
    for row in serials:
        if row["nomi"].lower() == nomi.lower():
            return row.get("bought_by") or []
    return []

def add_serial_buyer(nomi, user_id):
    serials = load_serials()
    with httpx.Client() as client:
        for row in serials:
            if row["nomi"].lower() == nomi.lower():
                bought = row.get("bought_by") or []
                if user_id not in bought:
                    bought.append(user_id)
                    client.patch(
                        db_url("serials") + f"?id=eq.{row['id']}",
                        headers=headers(),
                        json={"bought_by": bought}
                    )

# ===== SERIAL FAVORITES =====
def get_favorites(user_id):
    try:
        with httpx.Client() as client:
            res = client.get(db_url("serial_favorites") + f"?user_id=eq.{user_id}", headers=headers())
            return [row["serial_nomi"] for row in res.json()]
    except:
        return []

def add_favorite(user_id, serial_nomi):
    with httpx.Client() as client:
        client.post(
            db_url("serial_favorites"),
            headers={**headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json={"user_id": user_id, "serial_nomi": serial_nomi}
        )

def remove_favorite(user_id, serial_nomi):
    with httpx.Client() as client:
        client.delete(
            db_url("serial_favorites") + f"?user_id=eq.{user_id}&serial_nomi=eq.{serial_nomi}",
            headers=headers()
        )

def get_serial_fans(serial_nomi):
    try:
        with httpx.Client() as client:
            res = client.get(db_url("serial_favorites") + f"?serial_nomi=eq.{serial_nomi}", headers=headers())
            return [row["user_id"] for row in res.json()]
    except:
        return []

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

def get_user_watched(user_id):
    try:
        with httpx.Client() as client:
            res = client.get(db_url("users") + f"?user_id=eq.{user_id}", headers=headers())
            data = res.json()
            return data[0].get("watched") or [] if data else []
    except:
        return []

def add_to_watched(user_id, kod):
    watched = get_user_watched(user_id)
    if kod not in watched:
        watched.append(kod)
        with httpx.Client() as client:
            client.patch(
                db_url("users") + f"?user_id=eq.{user_id}",
                headers=headers(),
                json={"watched": watched}
            )

# ===== ZAKAZ =====
def create_zakaz(user_id, username, kino_nomi, tur="kino"):
    with httpx.Client() as client:
        res = client.post(
            db_url("zakazlar"),
            headers=headers(),
            json={"user_id": user_id, "username": username, "kino_nomi": kino_nomi, "status": "kutilmoqda", "tur": tur}
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
            buttons.append([InlineKeyboardButton(text=f"📢 {channel}", url=f"https://t.me/{channel.replace('@','')}")]  )
    buttons.append([InlineKeyboardButton(text="✅ Obuna bo'ldim!", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== KEYBOARDS =====
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kinolar"), KeyboardButton(text="📺 Seriallar")],
            [KeyboardButton(text="⭐ Top kinolar"), KeyboardButton(text="🎭 Janrlar")],
            [KeyboardButton(text="🎲 Tasodifiy"), KeyboardButton(text="🆕 Yangi kinolar")],
            [KeyboardButton(text="📦 Zakaz"), KeyboardButton(text="❤️ Sevimlilar")],
            [KeyboardButton(text="👁 Ko'rganlarim"), KeyboardButton(text="👤 Profil")],
            [KeyboardButton(text="❓ Yordam")],
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="🎬 Kinolar", callback_data="admin_movies"),
        ],
        [
            InlineKeyboardButton(text="📺 Seriallar", callback_data="admin_serials"),
            InlineKeyboardButton(text="📦 Zakazlar", callback_data="admin_zakazlar"),
        ],
        [
            InlineKeyboardButton(text="📢 Reklama", callback_data="admin_reklama"),
            InlineKeyboardButton(text="👥 Adminlar", callback_data="admin_admins"),
        ],
        [
            InlineKeyboardButton(text="🔔 Obunalar", callback_data="admin_subs"),
        ],
    ])

def zakaz_action_keyboard(zakaz_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"zakaz_confirm_{zakaz_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"zakaz_reject_{zakaz_id}"),
    ]])

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

# ===== KINO YUBORISH =====
async def send_movie_to_user(chat_id, movie, kod):
    if movie.get("vip"):
        await bot.forward_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=movie["msg_id"], protect_content=True)
    else:
        await bot.forward_message(chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=movie["msg_id"])

async def send_serial_to_user(chat_id, qism_data):
    if qism_data.get("vip"):
        await bot.forward_message(chat_id=chat_id, from_chat_id=SERIAL_KANAL_ID, message_id=qism_data["msg_id"], protect_content=True)
    else:
        await bot.forward_message(chat_id=chat_id, from_chat_id=SERIAL_KANAL_ID, message_id=qism_data["msg_id"])

# ===== START =====
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
        "🔍 Kino yoki serial <b>nomini</b> yuboring\n"
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

# ===== ADMIN PANEL =====
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("👑 <b>Admin panel</b>\n\nQuyidagi bo'limlardan birini tanlang:", reply_markup=admin_panel_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    movies = load_movies()
    serials = get_serial_names()
    user_count = get_user_count()
    zakazlar = get_all_zakazlar()
    admins = get_admins()
    vip_movies = sum(1 for v in movies.values() if v.get("vip"))
    vip_serials = sum(1 for v in serials.values() if v.get("vip"))
    top = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. {v['nomi']} — {v['views']} marta" for i, (k, v) in enumerate(top)])
    await callback.message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {user_count}\n"
        f"🎬 Kinolar: {len(movies)} (💎 {vip_movies} pullik)\n"
        f"📺 Seriallar: {len(serials)} (💎 {vip_serials} pullik)\n"
        f"👑 Adminlar: {len(admins) + 1}\n"
        f"📢 Majburiy obunalar: {len(required_channels)}\n"
        f"📦 Kutilayotgan zakazlar: {len(zakazlar)}\n\n"
        f"🔥 <b>Top kinolar:</b>\n{top_text or 'Hali yoq'}",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_movies")
async def admin_movies_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    movies = load_movies()
    if not movies:
        await callback.message.answer("📭 Kinolar yo'q!\n\n➕ /addmovie KOD MSG_ID NOMI")
        await callback.answer()
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in movies.items():
        janr = f" | {info['janr']}" if info.get("janr") else ""
        vip = " 💎" if info.get("vip") else ""
        text += f"▫️ {info['nomi']}{vip}{janr}\nKod: <code>{kod}</code> | Ko'rishlar: {info['views']}\n\n"
    text += "➕ /addmovie KOD MSG_ID NOMI\n🗑 /delmovie KOD"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_serials")
async def admin_serials_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    serials = get_serial_names()
    if not serials:
        await callback.message.answer(
            "📭 Seriallar yo'q!\n\n"
            "➕ /addserial NOMI FASL QISM MSG_ID\n"
            "Misol: <code>/addserial SquidGame 1 1 12345</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    text = "📺 <b>Barcha seriallar:</b>\n\n"
    for nomi, info in serials.items():
        vip = " 💎" if info.get("vip") else ""
        fasls = get_serial_fasls(nomi)
        text += f"▫️ {nomi}{vip} | {len(fasls)} fasl\n\n"
    text += "➕ /addserial NOMI FASL QISM MSG_ID\n🗑 /delserial NOMI"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_zakazlar")
async def admin_zakazlar_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    zakazlar = get_all_zakazlar()
    if not zakazlar:
        await callback.message.answer("📭 Kutilayotgan zakazlar yo'q!")
        await callback.answer()
        return
    for z in zakazlar:
        tur = z.get("tur", "kino")
        tur_emoji = "📺" if tur == "serial" else "🎬"
        text = (
            f"📦 <b>Zakaz #{z['id']}</b>\n\n"
            f"👤 @{z['username']} (ID: {z['user_id']})\n"
            f"{tur_emoji} {'Serial' if tur == 'serial' else 'Kino'}: <b>{z['kino_nomi']}</b>\n\n"
            f"✅ /tasdiqlash {z['id']} [kino_kodi]\n"
            f"❌ /rad {z['id']}"
        )
        await callback.message.answer(text, reply_markup=zakaz_action_keyboard(z['id']), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_admins")
async def admin_admins_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    admins = get_admins()
    text = "👑 <b>Adminlar ro'yxati:</b>\n\n"
    text += f"⭐ Super admin: <code>{ADMIN_ID}</code>\n\n"
    if admins:
        for i, admin_id in enumerate(admins, 1):
            text += f"{i}. <code>{admin_id}</code>\n"
    else:
        text += "Qo'shimcha adminlar yo'q.\n"
    text += "\n➕ /addadmin USER_ID\n🗑 /removeadmin USER_ID"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_subs")
async def admin_subs_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    if not required_channels:
        text = "📭 Majburiy obuna kanallari yo'q.\n\n➕ /addsub @kanal"
    else:
        text = "📋 <b>Majburiy obuna kanallari:</b>\n\n"
        for i, ch in enumerate(required_channels, 1):
            text += f"{i}. {ch}\n"
        text += "\n➕ /addsub @kanal\n🗑 /delsub @kanal"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_reklama")
async def admin_reklama_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(ReklamaState.waiting_for_content)
    await callback.message.answer(
        "📢 <b>Reklama yuborish</b>\n\n"
        "Matn, rasm yoki video yuboring:\n\n"
        "❌ Bekor qilish: /admin",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("zakaz_confirm_"))
async def zakaz_confirm_inline(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    zakaz_id = int(callback.data.split("_")[2])
    await callback.message.answer(
        f"✅ Zakaz #{zakaz_id} tasdiqlash uchun kino kodini yozing:\n"
        f"<code>/tasdiqlash {zakaz_id} KINO_KODI</code>\n\n"
        f"Serial uchun:\n"
        f"<code>/tasdiqlashserial {zakaz_id} SERIAL_NOMI</code>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("zakaz_reject_"))
async def zakaz_reject_inline(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    zakaz_id = int(callback.data.split("_")[2])
    zakaz = get_zakaz(zakaz_id)
    if not zakaz:
        await callback.answer("❌ Zakaz topilmadi!")
        return
    update_zakaz_status(zakaz_id, "rad etilgan")
    await bot.send_message(zakaz["user_id"], f"❌ <b>Zakazingiz rad etildi.</b>\n🎬 {zakaz['kino_nomi']}", parse_mode="HTML")
    await callback.message.answer(f"✅ Zakaz #{zakaz_id} rad etildi.")
    await callback.answer("✅ Rad etildi")

# ===== REKLAMA FSM =====
@dp.message(StateFilter(ReklamaState.waiting_for_content))
async def reklama_content(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    users = get_all_users()
    success = fail = 0
    for user_id in users:
        try:
            if message.photo:
                await bot.send_photo(user_id, photo=message.photo[-1].file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.video:
                await bot.send_video(user_id, video=message.video.file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.text:
                await bot.send_message(user_id, message.text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    await state.clear()
    await message.answer(f"✅ Reklama yuborildi!\n✔️ Muvaffaqiyatli: {success}\n❌ Xato: {fail}")

# ===== SERIAL CALLBACKS =====
@dp.callback_query(F.data.startswith("serial_fasl_"))
async def serial_fasl_cb(callback: CallbackQuery):
    parts = callback.data.split("_")
    nomi = parts[2]
    fasl = int(parts[3])
    qismlar = get_serial_qismlar(nomi, fasl)
    if not qismlar:
        await callback.answer("❌ Qismlar topilmadi!")
        return
    buttons = []
    row = []
    for i, q in enumerate(qismlar):
        row.append(InlineKeyboardButton(
            text=f"{q['qism']}-qism",
            callback_data=f"serial_qism_{nomi}_{fasl}_{q['qism']}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"serial_back_{nomi}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"📺 <b>{nomi}</b> — {fasl}-fasl\n\nQismni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("serial_back_"))
async def serial_back_cb(callback: CallbackQuery):
    nomi = callback.data[12:]
    fasls = get_serial_fasls(nomi)
    serials = load_serials()
    vip = False
    for row in serials:
        if row["nomi"].lower() == nomi.lower():
            vip = row.get("vip", False)
            break
    buttons = []
    for fasl in fasls:
        buttons.append([InlineKeyboardButton(text=f"📁 {fasl}-fasl", callback_data=f"serial_fasl_{nomi}_{fasl}")])
    favs = get_favorites(callback.from_user.id)
    fav_text = "❤️ Sevimlilardan o'chirish" if nomi in favs else "🤍 Sevimlilarga qo'shish"
    fav_cb = f"serial_unfav_{nomi}" if nomi in favs else f"serial_fav_{nomi}"
    buttons.append([InlineKeyboardButton(text=fav_text, callback_data=fav_cb)])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    vip_text = "\n💎 <b>Pullik serial</b>" if vip else ""
    await callback.message.edit_text(
        f"📺 <b>{nomi}</b>{vip_text}\n\nFaslni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("serial_qism_"))
async def serial_qism_cb(callback: CallbackQuery):
    parts = callback.data.split("_")
    nomi = parts[2]
    fasl = int(parts[3])
    qism = int(parts[4])
    user_id = callback.from_user.id

    serials = load_serials()
    qism_data = None
    for row in serials:
        if row["nomi"].lower() == nomi.lower() and row["fasl"] == fasl and row["qism"] == qism:
            qism_data = row
            break

    if not qism_data:
        await callback.answer("❌ Qism topilmadi!")
        return

    if qism_data.get("vip"):
        bought = get_serial_bought(nomi)
        if user_id not in bought:
            await callback.message.answer(
                f"💎 <b>{nomi}</b> — pullik serial!\n\n"
                f"Bu serialni ko'rish uchun zakaz bering:\n"
                f"📦 /zakaz — buyurtma berish\n\n"
                f"💰 Narx: {SERIAL_ZAKAZ_NARXI:,} so'm",
                parse_mode="HTML"
            )
            await callback.answer()
            return

    update_serial_views(qism_data["id"])
    await send_serial_to_user(callback.message.chat.id, qism_data)
    await callback.message.answer(
        f"📺 <b>{nomi}</b>\n"
        f"📁 {fasl}-fasl | 🎬 {qism}-qism\n\n"
        f"Keyingi qismni ko'rish uchun tugmani bosing! 👆"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("serial_fav_"))
async def serial_fav_cb(callback: CallbackQuery):
    nomi = callback.data[11:]
    add_favorite(callback.from_user.id, nomi)
    await callback.answer(f"❤️ {nomi} sevimlilarga qo'shildi!")
    fasls = get_serial_fasls(nomi)
    buttons = []
    for fasl in fasls:
        buttons.append([InlineKeyboardButton(text=f"📁 {fasl}-fasl", callback_data=f"serial_fasl_{nomi}_{fasl}")])
    buttons.append([InlineKeyboardButton(text="❤️ Sevimlilardan o'chirish", callback_data=f"serial_unfav_{nomi}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data.startswith("serial_unfav_"))
async def serial_unfav_cb(callback: CallbackQuery):
    nomi = callback.data[13:]
    remove_favorite(callback.from_user.id, nomi)
    await callback.answer(f"🤍 {nomi} sevimlilardan o'chirildi!")
    fasls = get_serial_fasls(nomi)
    buttons = []
    for fasl in fasls:
        buttons.append([InlineKeyboardButton(text=f"📁 {fasl}-fasl", callback_data=f"serial_fasl_{nomi}_{fasl}")])
    buttons.append([InlineKeyboardButton(text="🤍 Sevimlilarga qo'shish", callback_data=f"serial_fav_{nomi}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_reply_markup(reply_markup=kb)

# ===== MENYU TUGMALARI =====

@dp.message(F.text == "🎬 Kinolar")
async def kinolar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    bepul = {k: v for k, v in movies.items() if not v.get("vip")}
    if not bepul:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    text = "🎬 <b>Barcha kinolar:</b>\n\n"
    for kod, info in bepul.items():
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        janr = f" | {info['janr']}" if info.get("janr") else ""
        text += f"🎬 <b>{info['nomi']}</b>{stars}{janr}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📺 Seriallar")
async def seriallar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    serials = get_serial_names()
    bepul = {k: v for k, v in serials.items() if not v.get("vip")}
    if not bepul:
        await message.answer("📭 Hozircha seriallar yo'q!")
        return
    text = "📺 <b>Barcha seriallar:</b>\n\n"
    for nomi, info in bepul.items():
        fasls = get_serial_fasls(nomi)
        text += f"📺 <b>{nomi}</b>\n📁 {len(fasls)} fasl\n\n"
    text += "🔍 Serial nomini yuboring — qismlarni tanlang"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "⭐ Top kinolar")
async def top_kinolar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    bepul = {k: v for k, v in movies.items() if not v.get("vip")}
    if not bepul:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    top = sorted(bepul.items(), key=lambda x: x[1]["views"], reverse=True)[:10]
    text = "🏆 <b>Top 10 kinolar:</b>\n\n"
    for i, (kod, info) in enumerate(top, 1):
        stars = ""
        if info["ratings"]:
            avg = sum(info["ratings"]) / len(info["ratings"])
            stars = f" ⭐{avg:.1f}"
        text += f"{i}. <b>{info['nomi']}</b>{stars}\n   👁 {info['views']} marta | 🔑 <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🎭 Janrlar")
async def janrlar_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    bepul = {k: v for k, v in movies.items() if not v.get("vip")}
    janrlar = set()
    for info in bepul.values():
        if info.get("janr"):
            for j in info["janr"].split(","):
                janrlar.add(j.strip().lower())
    if not janrlar:
        await message.answer("📭 Hozircha janrlar belgilanmagan!")
        return
    buttons = [[InlineKeyboardButton(text=f"🎭 {j.capitalize()}", callback_data=f"janr_{j}")] for j in sorted(janrlar)]
    await message.answer("🎭 <b>Janrni tanlang:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("janr_"))
async def janr_callback(callback: CallbackQuery):
    janr = callback.data[5:]
    movies = load_movies()
    results = [(k, v) for k, v in movies.items() if not v.get("vip") and janr in [j.strip().lower() for j in v.get("janr", "").split(",")]]
    if not results:
        await callback.message.answer(f"📭 <b>{janr.capitalize()}</b> janrida kino topilmadi!")
        await callback.answer()
        return
    text = f"🎭 <b>{janr.capitalize()} kinolari:</b>\n\n"
    for k, v in results:
        stars = f" ⭐{sum(v['ratings'])/len(v['ratings']):.1f}" if v["ratings"] else ""
        text += f"🎬 <b>{v['nomi']}</b>{stars}\n🔑 Kod: <code>{k}</code>\n\n"
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
    bepul = [(k, v) for k, v in movies.items() if not v.get("vip")]
    if not bepul:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    kod, movie = random.choice(bepul)
    movie["views"] += 1
    save_movie(kod, movie)
    add_to_watched(message.from_user.id, kod)
    await send_movie_to_user(message.chat.id, movie, kod)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⭐{i}", callback_data=f"rate_{kod}_{i}") for i in range(1, 6)
    ]])
    await message.answer(f"🎲 <b>Tasodifiy: {movie['nomi']}</b>\n👁 {movie['views']} marta\n\nBaho bering:", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🆕 Yangi kinolar")
async def yangi_btn(message: Message):
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    movies = load_movies()
    bepul = [(k, v) for k, v in movies.items() if not v.get("vip")]
    if not bepul:
        await message.answer("📭 Hozircha kinolar yo'q!")
        return
    yangi = list(reversed(bepul[-10:]))
    text = "🆕 <b>Yangi kinolar:</b>\n\n"
    for kod, info in yangi:
        stars = f" ⭐{sum(info['ratings'])/len(info['ratings']):.1f}" if info["ratings"] else ""
        text += f"🎬 <b>{info['nomi']}</b>{stars}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "❤️ Sevimlilar")
async def sevimlilar_btn(message: Message):
    save_user(message.from_user.id)
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("📭 Sevimli seriallaringiz yo'q!\n\nSerial ko'rayotganda ❤️ tugmasini bosing.")
        return
    text = "❤️ <b>Sevimli seriallaringiz:</b>\n\n"
    for nomi in favs:
        fasls = get_serial_fasls(nomi)
        text += f"📺 <b>{nomi}</b> | {len(fasls)} fasl\n"
    text += "\nSerial nomini yuboring — davom ettiring!"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👁 Ko'rganlarim")
async def korgan_btn(message: Message):
    save_user(message.from_user.id)
    watched = get_user_watched(message.from_user.id)
    if not watched:
        await message.answer("📭 Siz hali hech qanday kino ko'rmagansiz!")
        return
    movies = load_movies()
    text = "👁 <b>Ko'rgan kinolaringiz:</b>\n\n"
    for kod in watched:
        if kod in movies:
            info = movies[kod]
            stars = f" ⭐{sum(info['ratings'])/len(info['ratings']):.1f}" if info["ratings"] else ""
            text += f"🎬 <b>{info['nomi']}</b>{stars}\n🔑 Kod: <code>{kod}</code>\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "👤 Profil")
async def profil_btn(message: Message):
    save_user(message.from_user.id)
    user = message.from_user
    watched = get_user_watched(user.id)
    favs = get_favorites(user.id)
    admin_text = f"\n👥 Foydalanuvchilar: {get_user_count()}" if is_admin(user.id) else ""
    await message.answer(
        f"👤 <b>Profil</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 Ism: {user.full_name}\n"
        f"🎬 Ko'rgan kinolar: {len(watched)}\n"
        f"❤️ Sevimli seriallar: {len(favs)}"
        f"{admin_text}",
        parse_mode="HTML"
    )

@dp.message(F.text == "❓ Yordam")
async def yordam_btn(message: Message):
    await message.answer(
        "❓ <b>Yordam bo'limi</b>\n\n"
        "🎬 Kino kodini yuboring → film keladi\n"
        "📺 Serial nomini yuboring → fasl/qism tanlang\n"
        "📦 Zakaz → kino yoki serial buyurtma\n\n"
        "📋 <b>Tugmalar:</b>\n"
        "🎬 Kinolar | 📺 Seriallar\n"
        "⭐ Top | 🎭 Janrlar | 🎲 Tasodifiy\n"
        "🆕 Yangilar | ❤️ Sevimlilar\n"
        "👁 Ko'rganlarim | 👤 Profil\n\n"
        "💎 — pullik (zakaz orqali)\n\n"
        f"💬 Muammo bo'lsa: {ADMIN_USERNAME}",
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
        f"🎬 Kino narxi: <b>{KINO_ZAKAZ_NARXI:,} so'm</b>\n"
        f"📺 Serial narxi: <b>{SERIAL_ZAKAZ_NARXI:,} so'm</b>\n\n"
        "Kino/serial <b>nomi</b>, <b>rasmi</b> yoki <b:qisqa videosini</b> yuboring:\n\n"
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

    serials = get_serial_names()
    tur = "serial" if kino_nomi.lower() in [s.lower() for s in serials.keys()] else "kino"
    narx = SERIAL_ZAKAZ_NARXI if tur == "serial" else KINO_ZAKAZ_NARXI

    zakaz_id = create_zakaz(message.from_user.id, username, kino_nomi, tur)
    await state.update_data(zakaz_id=zakaz_id, tur=tur, narx=narx)
    await state.set_state(ZakazState.waiting_for_payment)

    tur_emoji = "📺" if tur == "serial" else "🎬"
    await message.answer(
        f"✅ <b>Zakaz qabul qilindi!</b>\n\n"
        f"{tur_emoji} {'Serial' if tur == 'serial' else 'Kino'}: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 To'lov miqdori: <b>{narx:,} so'm</b>\n\n"
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
        f"{tur_emoji} {'Serial' if tur == 'serial' else 'Kino'}: <b>{kino_nomi}</b>\n"
        f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n"
        f"💰 Narx: {narx:,} so'm\n\n"
        f"⏳ To'lov screenshoti kutilmoqda..."
    )
    if data.get("media_type") == "photo":
        await bot.send_photo(ADMIN_ID, photo=data["file_id"], caption=admin_text, parse_mode="HTML")
    elif data.get("media_type") == "video":
        await bot.send_video(ADMIN_ID, video=data["file_id"], caption=admin_text, parse_mode="HTML")
    else:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")

@dp.message(StateFilter(ZakazState.waiting_for_payment), F.photo)
async def zakaz_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    zakaz_id = data.get("zakaz_id", "?")
    kino_nomi = data.get("kino_nomi", "?")
    username = message.from_user.username or message.from_user.full_name
    await bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"💳 <b>To'lov screenshoti!</b>\n\n"
            f"👤 @{username} (ID: {message.from_user.id})\n"
            f"🎬 {kino_nomi}\n"
            f"🆔 Zakaz ID: <code>{zakaz_id}</code>\n\n"
            f"✅ /tasdiqlash {zakaz_id} [kino_kodi]\n"
            f"❌ /rad {zakaz_id}"
        ),
        reply_markup=zakaz_action_keyboard(zakaz_id),
        parse_mode="HTML"
    )
    await state.clear()
    await message.answer("✅ <b>Screenshot adminga yuborildi!</b>\n\n⏳ Admin tez yuboradi.", reply_markup=main_keyboard(), parse_mode="HTML")

@dp.message(StateFilter(ZakazState.waiting_for_payment))
async def zakaz_payment_wrong(message: Message):
    await message.answer("⚠️ Iltimos, <b>to'lov screenshotini</b> (rasm) yuboring!\n\n❌ Bekor qilish uchun tugmani bosing.", parse_mode="HTML")

@dp.message(F.photo, StateFilter(None))
async def screenshot_handler(message: Message):
    user = message.from_user
    username = user.username or user.full_name
    await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption=f"📸 <b>Rasm!</b>\n\n👤 @{username} (ID: {user.id})\n{message.caption or ''}", parse_mode="HTML")
    await message.answer("✅ Rasm adminga yuborildi!", parse_mode="HTML")

# ===== ADMIN COMMANDS =====

@dp.message(Command("addserial"))
async def add_serial_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer(
            "❌ Format:\n<code>/addserial NOMI FASL QISM MSG_ID</code>\n"
            "Pullik:\n<code>/addserial NOMI FASL QISM MSG_ID vip:ha</code>\n\n"
            "Misol:\n<code>/addserial SquidGame 1 1 12345</code>",
            parse_mode="HTML"
        )
        return
    try:
        parts = command.args.split()
        nomi = parts[0]
        fasl = int(parts[1])
        qism = int(parts[2])
        msg_id = int(parts[3])
        vip = len(parts) > 4 and parts[4] == "vip:ha"

        save_serial(nomi, fasl, qism, msg_id, vip)

        # Yangi qism qo'shilganda sevimlilar xabardor bo'ladi
        fans = get_serial_fans(nomi)
        if fans:
            notif = (
                f"🔔 <b>{nomi}</b> serialida yangi qism!\n\n"
                f"📁 {fasl}-fasl | 🎬 {qism}-qism\n\n"
                f"Serial nomini yuboring va tomosha qiling! 📺"
            )
            for fan_id in fans:
                try:
                    await bot.send_message(fan_id, notif, parse_mode="HTML")
                    await asyncio.sleep(0.05)
                except:
                    pass

        vip_text = " (💎 Pullik)" if vip else " (🆓 Bepul)"
        await message.answer(
            f"✅ Qo'shildi!\n"
            f"📺 {nomi} | {fasl}-fasl | {qism}-qism{vip_text}\n"
            f"🔔 {len(fans)} ta fanga xabar yuborildi.",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Xato: {e}\n\nFormat:\n<code>/addserial NOMI FASL QISM MSG_ID</code>", parse_mode="HTML")

@dp.message(Command("delserial"))
async def del_serial_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/delserial NOMI</code>", parse_mode="HTML")
        return
    nomi = command.args.strip()
    delete_serial(nomi)
    await message.answer(f"✅ <b>{nomi}</b> seriali o'chirildi!", parse_mode="HTML")

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
        if movie.get("vip"):
            bought = movie.get("bought_by") or []
            if zakaz["user_id"] not in bought:
                bought.append(zakaz["user_id"])
                movie["bought_by"] = bought
                save_movie(kino_kod, movie)
        add_to_watched(zakaz["user_id"], kino_kod)
        await send_movie_to_user(zakaz["user_id"], movie, kino_kod)
        await bot.send_message(zakaz["user_id"], f"🎉 <b>{movie['nomi']}</b> yuborildi! Rohatingiz kelsin! 🍿", parse_mode="HTML")
        update_zakaz_status(zakaz_id, "tasdiqlangan")
        await message.answer(f"✅ Zakaz #{zakaz_id} tasdiqlandi!")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("tasdiqlashserial"))
async def tasdiqlash_serial_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/tasdiqlashserial ZAKAZ_ID SERIAL_NOMI</code>", parse_mode="HTML")
        return
    try:
        parts = command.args.split(maxsplit=1)
        zakaz_id = int(parts[0])
        serial_nomi = parts[1]
        zakaz = get_zakaz(zakaz_id)
        if not zakaz:
            await message.answer("❌ Zakaz topilmadi!")
            return
        add_serial_buyer(serial_nomi, zakaz["user_id"])
        await bot.send_message(
            zakaz["user_id"],
            f"🎉 <b>{serial_nomi}</b> serialiga ruxsat berildi!\n\n"
            f"Serial nomini yuboring va tomosha qiling! 📺",
            parse_mode="HTML"
        )
        update_zakaz_status(zakaz_id, "tasdiqlangan")
        await message.answer(f"✅ Zakaz #{zakaz_id} tasdiqlandi! Foydalanuvchi {serial_nomi} serialini ko'ra oladi.")
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
        await bot.send_message(zakaz["user_id"], f"❌ <b>Zakazingiz rad etildi.</b>\n🎬 {zakaz['kino_nomi']}", parse_mode="HTML")
        await message.answer(f"✅ Zakaz #{zakaz_id} rad etildi.")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

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
        await message.answer(f"✅ Admin qo'shildi! ID: <code>{new_admin_id}</code>", parse_mode="HTML")
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
        await message.answer(f"✅ Admin o'chirildi! ID: <code>{admin_id}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}")

@dp.message(Command("addmovie"))
async def add_movie_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer(
            "❌ Format:\n<code>/addmovie KOD MSG_ID NOMI</code>\n"
            "Janr: <code>/addmovie KOD MSG_ID NOMI janr:drama</code>\n"
            "Pullik: <code>/addmovie KOD MSG_ID NOMI vip:ha</code>",
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
        if not vip:
            users = get_all_users()
            janr_text = f"\n🎭 Janr: {janr}" if janr else ""
            notif = f"🆕 <b>Yangi kino!</b>\n\n🎬 <b>{nomi}</b>{janr_text}\n🔑 Kod: <code>{kod}</code>\n\nKodini yuboring! 🍿"
            for user_id in users:
                try:
                    await bot.send_message(user_id, notif, parse_mode="HTML")
                    await asyncio.sleep(0.05)
                except:
                    pass
            await message.answer(f"✅ Bepul kino qo'shildi! {len(users)} ta foydalanuvchiga xabar yuborildi.\n🎬 {nomi} | Kod: <code>{kod}</code>", parse_mode="HTML")
        else:
            await message.answer(f"✅ Pullik kino qo'shildi!\n🎬 {nomi} | Kod: <code>{kod}</code>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xato: {e}", parse_mode="HTML")

@dp.message(Command("delmovie"))
async def del_movie_cmd(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("❌ Format: <code>/delmovie KOD</code>", parse_mode="HTML")
        return
    kod = command.args.strip()
    movies = load_movies()
    if kod in movies:
        delete_movie(kod)
        await message.answer(f"✅ <b>{movies[kod]['nomi']}</b> o'chirildi!", parse_mode="HTML")
    else:
        await message.answer("❌ Bunday kod yo'q!")

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

@dp.message(Command("reklama"))
async def reklama_cmd(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(ReklamaState.waiting_for_content)
    await message.answer("📢 <b>Reklama</b>\n\nMatn, rasm yoki video yuboring:\n\n❌ Bekor qilish: /admin", parse_mode="HTML")

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    movies = load_movies()
    serials = get_serial_names()
    user_count = get_user_count()
    zakazlar = get_all_zakazlar()
    admins = get_admins()
    top = sorted(movies.items(), key=lambda x: x[1]["views"], reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. {v['nomi']} — {v['views']} marta" for i, (k, v) in enumerate(top)])
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {user_count}\n"
        f"🎬 Kinolar: {len(movies)}\n"
        f"📺 Seriallar: {len(serials)}\n"
        f"👑 Adminlar: {len(admins) + 1}\n"
        f"📦 Kutilayotgan zakazlar: {len(zakazlar)}\n\n"
        f"🔥 <b>Top kinolar:</b>\n{top_text or 'Hali yoq'}",
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "❓ <b>Yordam</b>\n\n"
        "▫️ Kino kodini yuboring → film keladi\n"
        "▫️ Serial nomini yuboring → fasl tanlang\n"
        "▫️ /zakaz → buyurtma\n\n"
        f"💬 Muammo bo'lsa: {ADMIN_USERNAME}",
        parse_mode="HTML"
    )

# ===== QIDIRISH =====
@dp.message(StateFilter(None))
async def find_content(message: Message):
    if not message.text or message.text.startswith("/"):
        return
    save_user(message.from_user.id)
    if not await check_subscription(message.from_user.id):
        kb = await subscription_keyboard()
        await message.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=kb, parse_mode="HTML")
        return
    text = message.text.strip()

    # Avval seriallardan qidirish
    serials = get_serial_names()
    serial_match = None
    for nomi in serials:
        if text.lower() == nomi.lower() or text.lower() in nomi.lower():
            serial_match = nomi
            break

    if serial_match:
        nomi = serial_match
        serial_info = serials[nomi]
        if serial_info.get("vip"):
            bought = get_serial_bought(nomi)
            if message.from_user.id not in bought:
                await message.answer(
                    f"💎 <b>{nomi}</b> — pullik serial!\n\n"
                    f"Bu serialni ko'rish uchun zakaz bering:\n"
                    f"📦 /zakaz\n\n"
                    f"💰 Narx: {SERIAL_ZAKAZ_NARXI:,} so'm",
                    parse_mode="HTML"
                )
                return
        fasls = get_serial_fasls(nomi)
        buttons = []
        for fasl in fasls:
            buttons.append([InlineKeyboardButton(text=f"📁 {fasl}-fasl", callback_data=f"serial_fasl_{nomi}_{fasl}")])
        favs = get_favorites(message.from_user.id)
        fav_text = "❤️ Sevimlilardan o'chirish" if nomi in favs else "🤍 Sevimlilarga qo'shish"
        fav_cb = f"serial_unfav_{nomi}" if nomi in favs else f"serial_fav_{nomi}"
        buttons.append([InlineKeyboardButton(text=fav_text, callback_data=fav_cb)])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(f"📺 <b>{nomi}</b>\n\nFaslni tanlang:", reply_markup=kb, parse_mode="HTML")
        return

    # Kinolardan qidirish
    movies = load_movies()
    if text in movies:
        movie = movies[text]
        if movie.get("vip"):
            bought = movie.get("bought_by") or []
            if message.from_user.id not in bought:
                await message.answer(
                    f"💎 <b>{movie['nomi']}</b> — pullik kino!\n\n"
                    f"📦 /zakaz\n\n💰 Narx: {KINO_ZAKAZ_NARXI:,} so'm",
                    parse_mode="HTML"
                )
                return
        movie["views"] += 1
        save_movie(text, movie)
        add_to_watched(message.from_user.id, text)
        await send_movie_to_user(message.chat.id, movie, text)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐{i}", callback_data=f"rate_{text}_{i}") for i in range(1, 6)
        ]])
        await message.answer(f"🎬 <b>{movie['nomi']}</b>\n👁 {movie['views']} marta\n\nBaho bering:", reply_markup=kb, parse_mode="HTML")
    else:
        # Nom bo'yicha qidirish
        kino_results = [(k, v) for k, v in movies.items() if text.lower() in v["nomi"].lower() and not v.get("vip")]
        serial_results = [(n, i) for n, i in serials.items() if text.lower() in n.lower() and not i.get("vip")]

        if kino_results or serial_results:
            result_text = "🔍 <b>Topildi:</b>\n\n"
            for k, v in kino_results:
                result_text += f"🎬 {v['nomi']}\n🔑 Kod: <code>{k}</code>\n\n"
            for n, i in serial_results:
                fasls = get_serial_fasls(n)
                result_text += f"📺 {n} | {len(fasls)} fasl\n\n"
            await message.answer(result_text, parse_mode="HTML")
        else:
            await message.answer(
                f"❌ <b>{text}</b> topilmadi!\n\n"
                f"📚 /katalog — kinolar\n"
                f"📺 Seriallar tugmasini bosing\n"
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
        await callback.message.edit_text(f"✅ Bahoyingiz: {'⭐' * ball}\n📊 O'rtacha reyting: ⭐{avg:.1f}")
    await callback.answer()

# ===== MAIN =====
async def main():
    await start_web()
    asyncio.create_task(send_daily_recommendation())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
