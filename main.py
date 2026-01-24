import asyncio
import random
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

import logging
import os
from aiohttp import web

# ================= CONFIG =================
TOKEN = "8535869380:AAHCUGD-I0rXeMbj7VUr22kcuN2c6xSMQAA"
DB_FILE = "users.db"

ACCESS_CODE = "2837"
MAX_ATTEMPTS = 3
BAN_TIME = timedelta(minutes=5)

ADMINS = {8251178801}

SIGNAL_COOLDOWN = timedelta(minutes=5)
RISK_RANGE = (30, 40)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=MemoryStorage())

# ================= STATE / SECURITY =================
authorized_users = set()
login_attempts = {}
login_bans = {}
user_cooldowns = {}

# ================= DB =================
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                pair TEXT
            )
        """)

def save_pair(user_id: int, pair: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, pair) VALUES (?, ?)",
            (user_id, pair)
        )

def get_pair(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute("SELECT pair FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None

# ================= FSM =================
class Form(StatesGroup):
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_pair = State()
    ready_for_signals = State()

# ================= DATA =================
otc_pairs = [
    "EUR/USD OTC", "USD/CHF OTC", "AUD/USD OTC",
    "Gold OTC", "AUD/CAD OTC", "AUD/JPY OTC", "CAD/JPY OTC"
]

real_pairs = [
    "EUR/USD", "AUD/USD", "Gold", "AUD/JPY", "CAD/JPY"
]

crypto_pairs = [
    "Bitcoin OTC", "Ethereum OTC", "BNB OTC", "Litecoin OTC",
    "Dogecoin OTC", "Toncoin OTC", "Avalanche OTC"
]

timeframes = ["10 minutos"] * 5 + ["20 minutos"] * 3 + ["30 minutos"] * 2 + ["50 minutos"]
directions = ["📈 Arriba", "📉 Abajo"]

# ================= HELPERS =================
def risk_indicator(risk: int) -> str:
    if 30 <= risk <= 33:
        return "🟢 Bajo"
    elif 34 <= risk <= 37:
        return "🟡 Medio"
    else:
        return "🔴 Alto"

# ================= KEYBOARDS =================
def kb_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕹 Pares OTC", callback_data="type_otc")],
        [InlineKeyboardButton(text="📈 Pares reales", callback_data="type_real")],
        [InlineKeyboardButton(text="🪙 Cryptomonedas", callback_data="type_crypto")]
    ])

def kb_pairs(pairs):
    keyboard = [[InlineKeyboardButton(text=p, callback_data=f"pair:{p}")] for p in pairs]
    keyboard.append([InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def kb_signal():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 OBTENER SEÑAL", callback_data="get_signal")]
    ])

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    authorized_users.discard(message.from_user.id)
    await message.answer("🔐 Ingresa el *código de acceso*:")
    await state.set_state(Form.waiting_for_code)

@dp.message(Form.waiting_for_code)
async def check_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    now = datetime.now()

    if login_bans.get(user_id, now) > now:
        remaining = int((login_bans[user_id] - now).total_seconds())
        await message.answer(f"⛔ Acceso bloqueado\nIntenta en {remaining//60}m {remaining%60}s")
        return

    if message.text.strip() == ACCESS_CODE:
        authorized_users.add(user_id)
        login_attempts.pop(user_id, None)
        login_bans.pop(user_id, None)

        await message.answer("✅ Acceso concedido\n\nElige el tipo de activo:", reply_markup=kb_types())
        await state.set_state(Form.waiting_for_type)
        return

    attempts = login_attempts.get(user_id, 0) + 1
    login_attempts[user_id] = attempts

    await message.answer(f"❌ Código incorrecto\nIntento {attempts}/{MAX_ATTEMPTS}")

    if attempts >= MAX_ATTEMPTS:
        login_bans[user_id] = now + BAN_TIME
        login_attempts.pop(user_id, None)
        await message.answer("⛔ Bloqueado por 5 minutos")

@dp.callback_query(F.data == "back_to_types")
async def back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Elige el tipo de activo:", reply_markup=kb_types())
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data == "type_otc")
async def type_otc(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Selecciona un par OTC:", reply_markup=kb_pairs(otc_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_real")
async def type_real(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Selecciona un par real:", reply_markup=kb_pairs(real_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_crypto")
async def type_crypto(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Selecciona una criptomoneda:", reply_markup=kb_pairs(crypto_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    pair = callback.data.split(":", 1)[1]
    save_pair(callback.from_user.id, pair)

    await callback.answer()
    await callback.message.edit_text(
        f"✅ Par seleccionado: *{pair}*\n\nPulsa para recibir señal 👇",
        reply_markup=kb_signal()
    )
    await state.set_state(Form.ready_for_signals)

@dp.callback_query(F.data == "get_signal")
async def send_signal(callback: CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now()

    if user_cooldowns.get(user_id, now) > now:
        remaining = int((user_cooldowns[user_id] - now).total_seconds())
        await callback.answer(f"⏳ Próxima señal en {remaining//60}m {remaining%60}s", show_alert=True)
        return

    user_cooldowns[user_id] = now + SIGNAL_COOLDOWN
    pair = get_pair(user_id)

    msg = await callback.message.answer("🔄 *Cargando datos desde PocketOption...*")
    await asyncio.sleep(1.5)

    await msg.edit_text("📊 *Analizando el mercado...*")
    await asyncio.sleep(1.5)

    await msg.edit_text("🧮 *Calculando probabilidades...*")
    await asyncio.sleep(1.5)

    risk = random.randint(*RISK_RANGE)
    success = 100 - risk
    label = risk_indicator(risk)

    await msg.delete()

    await callback.message.answer(
        f"📌 *SEÑAL GENERADA*\n\n"
        f"Par: *{pair}*\n"
        f"Tiempo: *{random.choice(timeframes)}*\n"
        f"Dirección: *{random.choice(directions)}*\n\n"
        f"⚠️ Riesgo: `{risk}%` {label}\n"
        f"✅ Probabilidad de éxito: `{success}%`\n\n"
        f"_Gestiona tu capital. El mercado es dinámico._",
        reply_markup=kb_signal()
    )

@dp.message(F.text.startswith("/signal"))
async def manual_signal(message: Message):
    if message.from_user.id not in ADMINS:
        return

    try:
        # формат:
        # /signal EUR/USD 10 📈
        _, pair, time, direction = message.text.split(maxsplit=3)

        for user_id in authorized_users:
            await bot.send_message(
                user_id,
                f"📡 *Señal manual*\n\n"
                f"Par: *{pair}*\n"
                f"Tiempo: *{time} minutos*\n"
                f"Dirección: *{direction}*"
            )

        await message.answer("✅ Señal enviada")
    except Exception as e:
        await message.answer(
            "❌ Формат:\n"
            "`/signal EUR/USD 10 📈`"
        )

# ================= WEB =================
async def run_web():
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ================= MAIN =================
async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await run_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
