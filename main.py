import asyncio
import random
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
import logging

# ================= CONFIG =================
TOKEN = "8535869380:AAHCUGD-I0rXeMbj7VUr22kcuN2c6xSMQAA"
DB_FILE = "users.db"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=MemoryStorage())

# ================= DB =================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            pair TEXT
        )
    """)
    conn.commit()
    conn.close()

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

def get_all_users():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute("SELECT user_id FROM users")
        return [r[0] for r in cur.fetchall()]

# ================= FSM =================
class Form(StatesGroup):
    waiting_for_id = State()
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

cryptomonedas = [
    "Bitcoin OTC", "Ethereum OTC", "BNB OTC", "Litecoin OTC",
    "Dogecoin OTC", "Polygon OTC", "Toncoin OTC",
    "Polkadot OTC", "Avalanche OTC", "Chainlink OTC",
    "TRON OTC", "Cardano OTC"
]

all_pairs = otc_pairs + real_pairs + cryptomonedas

timeframes = ["10 minutos"] * 5 + ["20 minutos"] * 3 + ["30 minutos"] * 2 + ["50 minutos"]
budget_options = ["20$", "30$", "40$"]
directions = ["📈 Arriba", "📉 Abajo"]

user_cooldowns = {}

# ================= KEYBOARDS =================
def kb_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕹 Pares OTC", callback_data="type_otc")],
        [InlineKeyboardButton(text="📈 Pares reales", callback_data="type_real")],
        [InlineKeyboardButton(text="🪙 Cryptomonedas", callback_data="type_crypto")]
    ])

def kb_pairs(pairs):
    keyboard = []

    for p in pairs:
        keyboard.append(
            [InlineKeyboardButton(text=p, callback_data=f"pair:{p}")]
        )

    keyboard.append(
        [InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def kb_signal_only():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 OBTENER SEÑAL", callback_data="get_signal")]
    ])

def kb_after_pair():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 OBTENER SEÑAL", callback_data="get_signal")],
        [InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]
    ])

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await message.answer("👋 ¡Hola! Envíame tu ID de cuenta.")
    await state.set_state(Form.waiting_for_id)

@dp.message(Form.waiting_for_id)
async def get_id(message: Message, state: FSMContext):
    await message.answer("✅ ID recibido. Elige el tipo de activo:", reply_markup=kb_types())
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data == "type_otc")
async def type_otc(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Selecciona un par OTC:", reply_markup=kb_pairs(otc_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_real")
async def type_real(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Selecciona un par real:", reply_markup=kb_pairs(real_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_crypto")
async def type_crypto(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Selecciona una criptomoneda:", reply_markup=kb_pairs(cryptomonedas))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "back_to_types")
async def back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("Elige el tipo de activo:", reply_markup=kb_types())
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    pair = callback.data.split(":", 1)[1]
    save_pair(callback.from_user.id, pair)

    await callback.message.edit_text(
        f"✅ Par seleccionado: *{pair}*\nPulsa para recibir la señal 👇",
        reply_markup=kb_after_pair()
    )
    await state.set_state(Form.ready_for_signals)

@dp.callback_query(F.data == "get_signal")
async def send_signal(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    now = datetime.now()
    cooldown = user_cooldowns.get(user_id)

    if cooldown and cooldown > now:
        remaining = int((cooldown - now).total_seconds())
        await callback.answer(
            f"⏳ Próxima señal en {remaining//60}m {remaining%60}s",
            show_alert=True
        )
        return

    await callback.answer()
    user_cooldowns[user_id] = now + timedelta(minutes=5)

    pair = get_pair(user_id)

    loading = await callback.message.answer("⏳ Preparando señal...")
    await asyncio.sleep(2)
    await loading.delete()

    text = (
        f"Par: *{pair}*\n"
        f"Tiempo: *{random.choice(timeframes)}*\n"
        f"Presupuesto: *{random.choice(budget_options)}*\n"
        f"Dirección: *{random.choice(directions)}*"
    )

    await callback.message.answer(text, reply_markup=kb_signal_only())

# ================= MAIN =================
import os
from aiohttp import web

async def healthcheck():
    return web.Response(text="OK")

async def run_web():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="OK"))

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()

    # 👇 запускаем фейковый сервер
    await run_web()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

