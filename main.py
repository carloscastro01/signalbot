import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F
from aiogram.client.default import DefaultBotProperties
import logging

TOKEN = "8535869380:AAHCUGD-I0rXeMbj7VUr22kcuN2c6xSMQAA"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher(storage=MemoryStorage())

# ================= DB =================
DB_FILE = "users.db"

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
    cur.execute("INSERT OR REPLACE INTO users (user_id, pair) VALUES (?, ?)", (user_id, pair))
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
    "AUD/CAD OTC", "AUD/CHF OTC", "AUD/JPY OTC", "AUD/NZD OTC",
    "CAD/CHF OTC", "CAD/JPY OTC", "CHF/JPY OTC"
]
real_pairs = [
    "EUR/USD", "AUD/USD", "Gold", "AUD/CAD", "AUD/JPY", "CAD/JPY"
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
        [InlineKeyboardButton(text="🪙 Cryptomonedas", callback_data="type_crypto")]
    ])

def get_pairs_keyboard(pairs):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=p, callback_data=f"pair:{p}")] for p in pairs] +
                        [[InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]]
    )

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await message.answer("👋 ¡Hola! Por favor envíame tu ID de cuenta.")
    await state.set_state(Form.waiting_for_id)

@dp.message(Form.waiting_for_id)
async def process_id(message: Message, state: FSMContext):
    await message.answer(
        "✅ ID recibido. Ahora elige el tipo de par:", 
        reply_markup=get_type_keyboard()
    )
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data == "type_otc")
async def show_otc_pairs(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Selecciona un par OTC:", reply_markup=get_pairs_keyboard(otc_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_real")
async def show_real_pairs(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Selecciona un par real:", reply_markup=get_pairs_keyboard(real_pairs))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "type_crypto")
async def show_crypto_pairs(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer( "Selecciona una criptomoneda:", reply_markup=get_pairs_keyboard(cryptomonedas))
    await state.set_state(Form.waiting_for_pair)

@dp.callback_query(F.data == "back_to_types")
async def back_to_type_selection(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Elige el tipo de par:", reply_markup=get_type_keyboard())
    await state.set_state(Form.waiting_for_type)

@dp.callback_query(F.data.startswith("pair:"))
async def select_pair(callback: CallbackQuery, state: FSMContext):
    pair = callback.data.split(":", 1)[1]
    uid = callback.from_user.id

    save_pair(uid, pair)
    logging.info(f"✅ Usuario {uid} eligió {pair}")  

    btn = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 OBTENER SEÑAL", callback_data="get_signal")],
            [InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]
        ]
    )
    await callback.message.answer(f"Excelente par: *{pair}*\nListo para enviar la señal 👇", reply_markup=btn)
    await state.set_state(Form.ready_for_signals)

@dp.callback_query(F.data == "get_signal")
async def send_signal(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    pair = get_pair(user_id)

    if not pair:
        await callback.message.answer("⚠️ Primero selecciona un par.")
        return

    now = datetime.now()
    cooldown_until = user_cooldowns.get(user_id)
    if cooldown_until and (cooldown_until - now).total_seconds() > 0:
        remaining = (cooldown_until - now).total_seconds()
        minutes = int(remaining) // 60
        seconds = int(remaining) % 60
        await callback.answer(
            f"⏳ Espera {minutes} min {seconds} seg para la próxima señal",
            show_alert=True
        )
        return

    user_cooldowns[user_id] = now + timedelta(minutes=5)

    msg = await callback.message.answer("⏳ Preparando señal...")
    await asyncio.sleep(5)
    await msg.delete()

    tf = random.choice(timeframes)
    budget = random.choice(budget_options)
    direction = random.choice(directions)

    signal_text = (
        f"Par: *{pair}*\n"
        f"Tiempo de operación: *{tf}*\n"
        f"Presupuesto: *{budget}*\n"
        f"Dirección: *{direction}*"
    )

    btn = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 OBTENER SEÑAL", callback_data="get_signal")],
            [InlineKeyboardButton(text="🔙 Volver", callback_data="back_to_types")]
        ]
    )
    await callback.message.answer(signal_text, reply_markup=btn)
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
            next_time = now.replace(hour=19, minute=0, second=0, microsecond=0)
            if next_time < now:
                next_time += timedelta(days=1)
            await asyncio.sleep((next_time - now).total_seconds())
            continue

        pair = random.choice(all_pairs)
        tf = random.choice(timeframes)
        budget = random.choice(budget_options)
        direction = random.choice(directions)

        text = (
            f"Par: *{pair}*\n"
            f"Tiempo de operación: *{tf}*\n"
            f"Presupuesto: *{budget}*\n"
            f"Dirección: *{direction}*"
        )

        btn = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text="📩 OBTENER SEÑAL",
                callback_data="get_signal"
            )]]
        )

        for uid in get_all_users():
            try:
                await bot.send_message(uid, text, reply_markup=btn)
            except Exception as e:
                logging.warning(f"❌ No se pudo enviar a {uid}: {e}")

        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=interval)
        await asyncio.sleep((next_time - (datetime.utcnow() + timedelta(hours=5))).total_seconds())

# ================= MAIN =================
async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    asyncio.create_task(scheduled_signals())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
