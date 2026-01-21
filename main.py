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

# ================= CONFIG =================
TOKEN = "PASTE_YOUR_TOKEN_HERE"
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
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, pair) VALUES (?, ?)",
        (user_id, pair)
    )
    conn.commit()
    conn.close()

def get_pair(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT pair FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

# ================= FSM =================
class Form(StatesGroup):
    waiting_for_id = State()
    waiting_for_type = State()
    waiting_for_pair = State()
    ready_for_signals = State()

# ================= DATA =================
otc_pairs = [
    "EUR/USD OTC", "USD/CHF OTC", "AUD/USD OTC", "Gold OTC",
    "AUD/CAD OTC", "AUD/JPY OTC", "CAD/JPY OTC"
]

real_pairs = [
    "EUR/USD", "AUD/USD", "Gold", "AUD/JPY", "CAD/JPY"
]

cryptomonedas = [
    "BNB OTC",
    "Litecoin OTC",
    "Polygon OTC",
    "Ethereum OTC",
    "Bitcoin ETF OTC",
    "Dogecoin OTC",
    "Polkadot OTC",
    "Toncoin OTC",
    "Bitcoin OTC",
    "Avalanche OTC",
    "Chainlink OTC",
    "TRON OTC",
    "Cardano OTC"
]

all_pairs = otc_pairs + real_pairs + cryptomonedas

timeframes = ["10 minutos"] * 5 + ["20 minutos"] * 3 + ["30 minutos"] * 2 + ["50 minutos"]
budget_options = ["20$", "30$", "40$"]
directions = ["📈 Arriba", "📉 Abajo"]

user_cooldowns = {}

# ================= KEYBOARDS =================
def get_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕹 Pares OTC", callback_data="type_otc")],
        [InlineKeyboardButton(text="📈 Pares reales", callback_data="type_real")],
        [InlineKeyboardButton(text="🪙 Criptomonedas", callback_data="type_crypto")]
    ])

def get_pairs_keyboard(pairs):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"pair:{p}")]
            for p in pairs
        ] + [[InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]]
    )

def get_signal_keyboard():
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
async def process_id(message: Message, state: FSMContext):
    await message.answer(
        "✅ ID recibido. Elige el tipo de activo:",
        reply_markup=get_type_keyboard()
    )
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data == "type_otc")
async def show_otc(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Selecciona un par OTC:",
        reply_markup=get_pairs_keyboard(otc_pairs)
    )
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_real")
async def show_real(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Selecciona un par real:",
        reply_markup=get_pairs_keyboard(real_pairs)
    )
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_crypto")
async def show_crypto(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Selecciona una criptomoneda:",
        reply_markup=get_pairs_keyboard(cryptomonedas)
    )
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Elige el tipo de activo:",
        reply_markup=get_type_keyboard()
    )
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    pair = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    save_pair(user_id, pair)

    await callback.message.answer(
        f"✅ Par seleccionado: *{pair}*\nPulsa para recibir la señal 👇",
        reply_markup=get_signal_keyboard()
    )
    await state.set_state(Form.ready_for_signals)

@dp.callback_query(F.data == "get_signal")
async def send_signal(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id
    pair = get_pair(user_id)

    if not pair:
        await callback.message.answer("⚠️ Primero selecciona un par.")
        return

    now = datetime.now()
    cooldown = user_cooldowns.get(user_id)

    if cooldown and cooldown > now:
        remaining = int((cooldown - now).total_seconds())
        await callback.answer(
            f"⏳ Espera {remaining // 60}m {remaining % 60}s",
            show_alert=True
        )
        return

    user_cooldowns[user_id] = now + timedelta(minutes=5)

    loading = await callback.message.answer("⏳ Preparando señal...")
    await asyncio.sleep(3)
    await loading.delete()

    signal = (
        f"Par: *{pair}*\n"
        f"Tiempo: *{random.choice(timeframes)}*\n"
        f"Presupuesto: *{random.choice(budget_options)}*\n"
        f"Dirección: *{random.choice(directions)}*"
    )

    await callback.message.answer(signal, reply_markup=get_signal_keyboard())
    await state.set_state(Form.ready_for_signals)

# ================= AUTO SIGNALS =================
async def scheduled_signals():
    while True:
        now = datetime.utcnow() + timedelta(hours=5)
        hour = now.hour

        if 19 <= hour or hour < 4:
            interval = 3
        elif 4 <= hour < 10:
            interval = 1
        else:
            next_run = now.replace(hour=19, minute=0, second=0, microsecond=0)
            await asyncio.sleep((next_run - now).total_seconds())
            continue

        text = (
            f"📊 *SEÑAL AUTOMÁTICA*\n\n"
            f"Par: *{random.choice(all_pairs)}*\n"
            f"Tiempo: *{random.choice(timeframes)}*\n"
            f"Presupuesto: *{random.choice(budget_options)}*\n"
            f"Dirección: *{random.choice(directions)}*"
        )

        for uid in get_all_users():
            try:
                await bot.send_message(uid, text, reply_markup=get_signal_keyboard())
            except:
                pass

        await asyncio.sleep(interval * 3600)

# ================= MAIN =================
async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    asyncio.create_task(scheduled_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
