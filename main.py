import asyncio
import logging
import random
import time
import sqlite3
from datetime import datetime
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    InlineKeyboardButton,
    KeyboardButton,
    BufferedInputFile,
)

from captcha.image import ImageCaptcha
import config

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
image_captcha = ImageCaptcha(width=280, height=90)

# --- БАЗА ДАННЫХ ---
DB_FILE = "users_orders.db"

@contextmanager
def get_db():
    """Контекстный менеджер для безопасной работы с БД"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"DB Error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    """Инициализация БД и создание таблиц"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                join_date TEXT,
                captcha_passed BOOLEAN DEFAULT FALSE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                city TEXT,
                district TEXT,
                product TEXT,
                price TEXT,
                klad_type TEXT,
                payment_method TEXT,
                status TEXT DEFAULT 'Новый',
                order_time TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS captcha_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                captcha_time TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

def add_or_update_user(user: types.User) -> tuple[bool, bool]:
    """Добавляет пользователя в БД или обновляет. Возвращает (is_new, captcha_passed)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT captcha_passed FROM users WHERE user_id = ?", (user.id,))
        result = cursor.fetchone()

        if result is None:
            cursor.execute(
                "INSERT INTO users (user_id, username, full_name, join_date, captcha_passed) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.username or "", user.full_name or "", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False),
            )
            return True, False
        else:
            cursor.execute(
                "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                (user.username or "", user.full_name or "", user.id),
            )
            return False, bool(result['captcha_passed'])

def set_captcha_passed(user_id: int, username: str, full_name: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET captcha_passed = 1 WHERE user_id = ?", (user_id,))
        cursor.execute(
            "INSERT INTO captcha_log (user_id, username, full_name, captcha_time) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )

def add_order_to_db(user_id, username, full_name, city, district, product, price, klad_type, payment_method):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO orders 
            (user_id, username, full_name, city, district, product, price, klad_type, payment_method, status, order_time) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, full_name, city, district, product, price, klad_type, payment_method, "Ожидает оплаты", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        return cursor.lastrowid

def update_order_status(order_id: int, status: str):
     with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))

def get_all_users_ids():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

def get_bot_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders_count = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        
        cursor.execute("SELECT price FROM orders WHERE status = 'Оплачен'")
        total_money = 0
        for row in cursor.fetchall():
            price_str = row[0]
            if price_str and price_str != "Уточняйте":
                try:
                    import re
                    numbers = re.findall(r'\d+', price_str)
                    if numbers:
                        total_money += int(numbers[0])
                except:
                    pass
        
        return users_count, orders_count, total_money

def get_pinned_message_id():
    with get_db() as conn:
        cursor = conn.cursor()
        result = cursor.execute("SELECT value FROM bot_settings WHERE key = 'pinned_stats_msg'").fetchone()
        return int(result[0]) if result else None

def set_pinned_message_id(msg_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('pinned_stats_msg', ?)", (str(msg_id),))

async def update_pinned_stats():
    users_count, orders_count, total_money = get_bot_stats()
    
    stats_text = (
        f'<tg-emoji emoji-id="5870921681735781843">📊</tg-emoji> <b>СТАТИСТИКА БОТА</b>\n\n'
        f'<blockquote>'
        f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Пользователей: <b>{users_count}</b>\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Заказов: <b>{orders_count}</b>\n'
        f'<tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> Нахасслили: <b>{total_money:,} RUB</b>'
        f'</blockquote>'
    )
    
    try:
        pinned_msg_id = get_pinned_message_id()
        
        if pinned_msg_id:
            try:
                await bot.edit_message_text(
                    stats_text,
                    config.LOG_CHANNEL_ID,
                    pinned_msg_id,
                    parse_mode="HTML"
                )
            except Exception:
                pinned_msg_id = None
        
        if not pinned_msg_id:
            msg = await bot.send_message(
                config.LOG_CHANNEL_ID,
                stats_text,
                parse_mode="HTML"
            )
            await bot.pin_chat_message(config.LOG_CHANNEL_ID, msg.message_id, disable_notification=True)
            set_pinned_message_id(msg.message_id)
    except Exception as e:
        logging.error(f"Update pinned stats error: {e}")

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ---
last_order_time: dict[int, float] = {}
banned_users: set[int] = set()
maintenance_mode = False

BANNER_URL = "https://i.postimg.cc/3w8w8nQw/photo-2026-02-22-12-15-45.jpg"

init_db()

# --- FSM STATES ---
class ShopStates(StatesGroup):
    captcha = State()
    main_menu = State()
    choosing_city = State()
    choosing_district = State()
    choosing_product = State()
    choosing_klad_type = State()
    confirm_order = State()
    payment_method = State()

# --- УТИЛИТЫ И ПРОВЕРКИ ---
def format_user_info(user: types.User) -> str:
    parts = []
    if user.full_name: parts.append(f"Имя: <b>{user.full_name}</b>")
    if user.username: parts.append(f"User: @{user.username}")
    parts.append(f"ID: <code>{user.id}</code>")
    return " | ".join(parts)

async def log_action(text: str, reply_markup=None):
    try:
        timestamp = datetime.now().strftime("%d.%m %H:%M")
        await bot.send_message(
            config.LOG_CHANNEL_ID,
            f'<tg-emoji emoji-id="5983150113483134607">⏰</tg-emoji> <code>{timestamp}</code>\n{text}',
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Log error: {e}")

async def check_access(user: types.User, message: types.Message = None) -> bool:
    if user.id in config.ADMIN_IDS: return False
    if user.id in banned_users:
        if message and message.chat.type == "private":
            await message.answer("⛔️ <b>ВЫ ЗАБАНЕНЫ!</b>", parse_mode="HTML")
        return True
    if maintenance_mode:
        if message and message.chat.type == "private":
            await message.answer("🛠 <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\nБот временно недоступен.", parse_mode="HTML")
        return True
    return False

async def safe_delete_message(message: types.Message):
    try: await message.delete()
    except Exception: pass

async def send_captcha(chat_id: int, state: FSMContext):
    captcha_text = "".join(random.choices("0123456789", k=5))
    await state.update_data(captcha_correct_text=captcha_text)
    data = image_captcha.generate(captcha_text)
    captcha_file = BufferedInputFile(data.read(), filename="captcha.png")

    kb = {
        "inline_keyboard": [[{
            "text": "Обновить капчу",
            "callback_data": "refresh_captcha",
            "style": "primary",
            "icon_custom_emoji_id": "5345906554510012647"
        }]]
    }

    await bot.send_photo(
        chat_id=chat_id,
        photo=captcha_file,
        caption='<tg-emoji emoji-id="6037249452824072506">🔐</tg-emoji> <b>Анти-Спам проверка!</b>\nВведите код с картинки (5 цифр):',
        reply_markup=kb,
        parse_mode="HTML",
    )

async def send_welcome_message(chat_id: int):
    welcome_text = (
        '💎 <b>DANZELL SHOP</b> ✨\n\n'
        '<blockquote>'
        '✨ <b>ЧИСТЫЙ КАЙФ</b>\n'
        '📍 <b>ХОРОШИЕ ТОЧКИ</b>\n'
        '⚡️ <b>БЫСТРАЯ ДОСТАВКА</b>\n\n'
        '🚗 <b>Доставка обговаривается лично</b>\n'
        '⏱ <b>СРОКИ ВЫПОЛНЕНИЯ:</b> НЕ БОЛЕЕ 2-3 ЧАСОВ\n\n'
        f'👉 <b>Поддержка:</b> {config.SUPPORT_URL}'
        '</blockquote>\n\n'
        '🌟 <b>DANZELL SHOP</b>\n'
        '<i>Ты знаешь, к кому обратиться!</i>'
    )
    kb = {
        "inline_keyboard": [
            [{"text": "🚀 ДОСТАВКА (ДО ДВЕРИ)", "callback_data": "menu_delivery", "style": "primary", "icon_custom_emoji_id": "5963103826075456248"}],
            [{"text": "🏙 ЗАКАЗАТЬ (ГОРОДА)", "callback_data": "menu_order", "style": "success", "icon_custom_emoji_id": "5890937706803894250"}],
            [{"text": "💎 ОТЗЫВЫ / ГАРАНТИИ", "callback_data": "menu_reviews", "icon_custom_emoji_id": "5870633910337015697"}]
        ]
    }
    await bot.send_photo(
        chat_id=chat_id,
        photo=BANNER_URL,
        caption=welcome_text,
        reply_markup=kb,
        parse_mode="HTML",
    )

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("m", "maintenance"))
async def cmd_maintenance(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    global maintenance_mode
    maintenance_mode = not maintenance_mode
    await message.answer(f"🛠 Тех. работы: <b>{'ВКЛЮЧЕНЫ 🔴' if maintenance_mode else 'ВЫКЛЮЧЕНЫ 🟢'}</b>", parse_mode="HTML")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS: return
    if not command.args:
        return await message.answer("⚠️ Введите текст: /broadcast <текст>")
    
    users_list = get_all_users_ids()
    sent, failed = 0, 0
    status_msg = await message.answer(f"📤 Рассылка начата...")

    for uid in users_list:
        try:
            await bot.send_message(uid, command.args, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await status_msg.edit_text(f"✅ Рассылка завершена!\n📤 Отправлено: {sent}\n❌ Ошибок: {failed}")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    with get_db() as conn:
        cursor = conn.cursor()
        users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders_count = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        new_orders = cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Ожидает оплаты'").fetchone()[0]

    text = (
        f"📊 <b>СТАТИСТИКА БОТА</b>\n\n"
        f"👥 Пользователей: <b>{users_count}</b>\n"
        f"📦 Всего заказов: <b>{orders_count}</b>\n"
        f"🆕 Ожидают оплаты: <b>{new_orders}</b>\n"
        f"⛔️ Забанено: <b>{len(banned_users)}</b>\n"
        f"🛠 Тех. работы: <b>{'Вкл 🔴' if maintenance_mode else 'Выкл 🟢'}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    if not command.args:
        return await message.answer("⚠️ Использование: /ban <user_id>")
    
    try:
        target_id = int(command.args.strip())
    except ValueError:
        return await message.answer("❌ Неверный ID пользователя. Введите число.")
    
    if target_id in config.ADMIN_IDS:
        return await message.answer("⛔️ Нельзя забанить администратора!")
    
    if target_id in banned_users:
        banned_users.remove(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> разбанен.", parse_mode="HTML")
        await log_action(f'<tg-emoji emoji-id="6037496202990194718">🔓</tg-emoji> <b>РАЗБАН</b>\n<blockquote><code>{target_id}</code> | Админ: {format_user_info(message.from_user)}</blockquote>')
    else:
        banned_users.add(target_id)
        await message.answer(f"🔨 Пользователь <code>{target_id}</code> забанен.", parse_mode="HTML")
        await log_action(f'<tg-emoji emoji-id="5870657884844462243">🔨</tg-emoji> <b>БАН</b>\n<blockquote><code>{target_id}</code> | Админ: {format_user_info(message.from_user)}</blockquote>')
        try:
            await bot.send_message(target_id, "⛔️ <b>ВЫ БЫЛИ ЗАБЛОКИРОВАНЫ АДМИНИСТРАТОРОМ</b>", parse_mode="HTML")
        except Exception:
            pass

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    if not command.args:
        return await message.answer("⚠️ Использование: /unban <user_id>")
    
    try:
        target_id = int(command.args.strip())
    except ValueError:
        return await message.answer("❌ Неверный ID пользователя. Введите число.")
    
    if target_id in banned_users:
        banned_users.remove(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> разбанен.", parse_mode="HTML")
        await log_action(f'<tg-emoji emoji-id="6037496202990194718">🔓</tg-emoji> <b>РАЗБАН</b>\n<blockquote><code>{target_id}</code> | Админ: {format_user_info(message.from_user)}</blockquote>')
    else:
        await message.answer(f"ℹ️ Пользователь <code>{target_id}</code> не был забанен.", parse_mode="HTML")
# --- БАЗОВЫЕ ХЕНДЛЕРЫ ---
@dp.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: types.Message, state: FSMContext):
    if await check_access(message.from_user, message): return

    is_new, captcha_passed = add_or_update_user(message.from_user)
    
    if is_new:
        await log_action(
            f'<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> <b>НОВЫЙ</b>\n'
            f'<blockquote><code>{message.from_user.id}</code> | <b>{message.from_user.full_name or "—"}</b> | @{message.from_user.username or "—"}</blockquote>'
        )
        await update_pinned_stats()
    
    await state.clear()

    if is_new and not captcha_passed:
        await state.set_state(ShopStates.captcha)
        await send_captcha(message.chat.id, state)
    else:
        await state.set_state(ShopStates.main_menu)
        await send_welcome_message(message.chat.id)

@dp.callback_query(ShopStates.captcha, F.data == "refresh_captcha")
async def process_refresh_captcha(callback: types.CallbackQuery, state: FSMContext):
    await safe_delete_message(callback.message)
    await send_captcha(callback.from_user.id, state)
    await callback.answer()

@dp.message(ShopStates.captcha, F.chat.type == "private")
async def process_captcha_input(message: types.Message, state: FSMContext):
    if await check_access(message.from_user, message): return
    await safe_delete_message(message)
    
    user_input = message.text.strip() if message.text else ""
    if not user_input.isdigit() or len(user_input) != 5:
        return await message.answer("⚠️ Введите ровно 5 цифр!")

    data = await state.get_data()
    if user_input == data.get("captcha_correct_text", ""):
        set_captcha_passed(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        await state.set_state(ShopStates.main_menu)
        await log_action(
            f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>КАПЧА</b>\n'
            f'<blockquote><code>{message.from_user.id}</code> | <b>{message.from_user.full_name or "—"}</b> | @{message.from_user.username or "—"}</blockquote>'
        )
        await send_welcome_message(message.chat.id)
    else:
        await message.answer("❌ <b>Неверный код! Попробуйте снова.</b>", parse_mode="HTML")
        await send_captcha(message.chat.id, state)

# --- ГЛАВНОЕ МЕНЮ ---
@dp.callback_query(F.data == "back_to_menu")
async def go_back(callback: types.CallbackQuery, state: FSMContext):
    if await check_access(callback.from_user): return
    await state.set_state(ShopStates.main_menu)
    await callback.message.delete()
    await send_welcome_message(callback.message.chat.id)
    await callback.answer()


@dp.callback_query(F.data == "menu_delivery")
async def menu_delivery(callback: types.CallbackQuery, state: FSMContext):
    if await check_access(callback.from_user): return
    text = f'<tg-emoji emoji-id="6039422865189638057">🆘</tg-emoji> <b>ЗАКАЗАТЬ ДОСТАВКУ (ДО ДВЕРИ):</b>\n\n<tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> Связь с оператором: {config.SUPPORT_URL}\n\n<i><tg-emoji emoji-id="5904462880941545555">💸</tg-emoji> Полная анонимность. Любой каприз за ваши деньги.</i>'
    kb = {
        "inline_keyboard": [
            [{"text": "◁ Назад в меню", "callback_data": "back_to_menu", "icon_custom_emoji_id": "5893057118545646106"}]
        ]
    }
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "menu_reviews")
async def menu_reviews(callback: types.CallbackQuery, state: FSMContext):
    if await check_access(callback.from_user): return
    text = f'<tg-emoji emoji-id="5870633910337015697">💎</tg-emoji> <b><a href="{config.REVIEWS_URL}">ЧИТАТЬ ОТЗЫВЫ КЛИЕНТОВ</a></b>\n\n<tg-emoji emoji-id="6028435952299413210">❗️</tg-emoji> <i>ОТКРЫВАТЬ ТОЛЬКО ЧЕРЕЗ ONION БРАУЗЕР!</i>'
    kb = {
        "inline_keyboard": [
            [{"text": "◁ Назад в меню", "callback_data": "back_to_menu", "icon_custom_emoji_id": "5893057118545646106"}]
        ]
    }
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

# --- ОФОРМЛЕНИЕ ЗАКАЗА ---
@dp.callback_query(F.data == "menu_order")
async def start_order(callback: types.CallbackQuery, state: FSMContext):
    if await check_access(callback.from_user): return
    await state.set_state(ShopStates.choosing_city)

    kb = {"inline_keyboard": [
        *[[{
            "text": city,
            "callback_data": f"city_{city}",
            "icon_custom_emoji_id": "5873147866364514353"
        } for city in list(config.CITIES.keys())[i:i+2]] for i in range(0, len(config.CITIES), 2)],
        [{"text": "◁ Назад в меню", "callback_data": "back_to_menu", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}

    text = '<tg-emoji emoji-id="5884479287171485878">🛒</tg-emoji> <b>Режим оформления заказа</b>\n\n<tg-emoji emoji-id="6042011682497106307">📍</tg-emoji> <b>ВЫБЕРИТЕ ГОРОД:</b>\n\n<i>Мы работаем по всем районам.</i>'
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(ShopStates.choosing_city, F.data.startswith("city_"))
async def choose_city(callback: types.CallbackQuery, state: FSMContext):
    city_name = callback.data.removeprefix("city_")
    await state.update_data(city=city_name)
    await state.set_state(ShopStates.choosing_district)

    districts = config.CITIES.get(city_name, [])
    if not districts:
        await callback.message.edit_text("❌ В этом городе пока нет доступных районов.", reply_markup=None)
        await state.set_state(ShopStates.main_menu)
        return

    kb = {"inline_keyboard": [
        *[[{"text": dist, "callback_data": f"dist_{dist}", "icon_custom_emoji_id": "6042011682497106307"} for dist in districts[i:i+2]] for i in range(0, len(districts), 2)],
        [{"text": "◁ К выбору города", "callback_data": "back_to_city", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}

    data = await state.get_data()
    if data.get("prev_bot_msg"):
        try: await bot.delete_message(callback.message.chat.id, data["prev_bot_msg"])
        except: pass

    await callback.message.edit_text(f'<tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> Город: <b>{city_name}</b>\n\n<tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> <b>ВЫБЕРИТЕ РАЙОН:</b>', reply_markup=kb, parse_mode="HTML")
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()

@dp.callback_query(ShopStates.choosing_district, F.data == "back_to_city")
async def back_to_city(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopStates.choosing_city)
    kb = {"inline_keyboard": [[{
        "text": city,
        "callback_data": f"city_{city}",
        "icon_custom_emoji_id": "5873147866364514353"
    } for city in list(config.CITIES.keys())[i:i+2]] for i in range(0, len(config.CITIES), 2)]}
    await callback.message.edit_text('<tg-emoji emoji-id="6042011682497106307">📍</tg-emoji> <b>ВЫБЕРИТЕ ГОРОД:</b>', reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(ShopStates.choosing_district, F.data.startswith("dist_"))
async def choose_district(callback: types.CallbackQuery, state: FSMContext):
    district_name = callback.data.removeprefix("dist_")
    await state.update_data(district=district_name)
    await state.set_state(ShopStates.choosing_product)
    
    data = await state.get_data()
    products_list = [f"{p['name']} ({v})" for p in config.PRODUCTS_DATA for v in p["variants"]]
    random.shuffle(products_list)
    await state.update_data(shuffled_products=products_list)

    kb = {"inline_keyboard": [
        *[[{"text": p_text, "callback_data": f"prod_{idx}", "icon_custom_emoji_id": "5884479287171485878"}] for idx, p_text in enumerate(products_list)],
        [{"text": "◁ К выбору района", "callback_data": "back_to_district", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}

    await callback.message.edit_text(
        f'<tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> {data.get("city")} ➡ <tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> {district_name}\n\n<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>ВЫБЕРИТЕ ТОВАР:</b>', 
        reply_markup=kb, 
        parse_mode="HTML"
    )
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()
@dp.callback_query(ShopStates.choosing_product, F.data == "back_to_district")
async def back_to_district(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    city_name = data.get("city")
    await state.set_state(ShopStates.choosing_district)
    
    districts = config.CITIES.get(city_name, [])
    kb = {"inline_keyboard": [
        *[[{"text": dist, "callback_data": f"dist_{dist}", "icon_custom_emoji_id": "6042011682497106307"} for dist in districts[i:i+2]] for i in range(0, len(districts), 2)],
        [{"text": "◁ К выбору города", "callback_data": "back_to_city", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}
    await callback.message.edit_text(f'<tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> Город: <b>{city_name}</b>\n\n<tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> <b>ВЫБЕРИТЕ РАЙОН:</b>', reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(ShopStates.choosing_product, F.data.startswith("prod_"))
async def product_selected(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.removeprefix("prod_"))
    data = await state.get_data()
    shuffled = data.get("shuffled_products", [])

    if idx >= len(shuffled): return await callback.answer("⚠️ Ошибка.", show_alert=True)
    product_full_name = shuffled[idx]

    price = "Уточняйте"
    if " - " in product_full_name: price = product_full_name.split(" - ")[-1].strip().rstrip(")")
    elif "-" in product_full_name: price = product_full_name.split("-")[-1].strip().rstrip(")")

    await state.update_data(product=product_full_name, price=price)
    await state.set_state(ShopStates.choosing_klad_type)
    
    kb = {"inline_keyboard": [
        [
            {"text": "Прикоп", "callback_data": "type_prikop", "style": "primary", "icon_custom_emoji_id": "6042011682497106307"},
            {"text": "Магнит", "callback_data": "type_magnet", "style": "primary", "icon_custom_emoji_id": "5870875489362513438"}
        ],
        [{"text": "◁ К выбору товара", "callback_data": "back_to_product", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}

    await callback.message.edit_text(
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Товар: <b>{product_full_name}</b>\n<tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> Цена: <b>{price}</b>\n\n<tg-emoji emoji-id="5870982283724328568">🛠</tg-emoji> <b>ВЫБЕРИТЕ ТИП КЛАДА:</b>',
        reply_markup=kb, parse_mode="HTML"
    )
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()

@dp.callback_query(ShopStates.choosing_klad_type, F.data == "back_to_product")
async def back_to_product(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(ShopStates.choosing_product)
    
    kb = {"inline_keyboard": [
        *[[{"text": p_text, "callback_data": f"prod_{idx}", "icon_custom_emoji_id": "5884479287171485878"}] for idx, p_text in enumerate(data.get("shuffled_products", []))],
        [{"text": "◁ К выбору района", "callback_data": "back_to_district", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}
    await callback.message.edit_text(f'<tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> {data.get("city")} ➡ <tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> {data.get("district")}\n\n<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> <b>ВЫБЕРИТЕ ТОВАР:</b>', reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(ShopStates.choosing_klad_type, F.data.startswith("type_"))
async def klad_type_selected(callback: types.CallbackQuery, state: FSMContext):
    klad_type = "Прикоп" if callback.data == "type_prikop" else "Магнит"
    await state.update_data(klad_type=klad_type)
    await state.set_state(ShopStates.confirm_order)
    
    data = await state.get_data()
    summary = (
        f'<tg-emoji emoji-id="5870676941614354370">📝</tg-emoji> <b>ПРОВЕРКА ДАННЫХ ЗАКАЗА</b>\n\n'
        f'<tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> Город: <b>{data.get("city")}</b>\n'
        f'<tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> Район: <b>{data.get("district")}</b>\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Товар: <b>{data.get("product")}</b>\n'
        f'<tg-emoji emoji-id="5870982283724328568">🛠</tg-emoji> Тип клада: <b>{klad_type}</b>\n'
        f'<tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> Цена: <b>{data.get("price")}</b>\n\n'
        f'<tg-emoji emoji-id="6028435952299413210">❓</tg-emoji> <i>Всё верно?</i>'
    )
    kb = {"inline_keyboard": [
        [
            {"text": "ДА, всё верно", "callback_data": "order_confirm_yes", "style": "success", "icon_custom_emoji_id": "5870633910337015697"},
            {"text": "Отменить", "callback_data": "order_confirm_cancel", "style": "danger", "icon_custom_emoji_id": "5870657884844462243"}
        ],
        [{"text": "◁ К типу клада", "callback_data": "back_to_klad_type", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}

    await callback.message.edit_text(summary, reply_markup=kb, parse_mode="HTML")
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()
@dp.callback_query(ShopStates.confirm_order, F.data == "back_to_klad_type")
async def back_to_klad_type(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(ShopStates.choosing_klad_type)
    kb = {"inline_keyboard": [
        [
            {"text": "Прикоп", "callback_data": "type_prikop", "style": "primary", "icon_custom_emoji_id": "6042011682497106307"},
            {"text": "Магнит", "callback_data": "type_magnet", "style": "primary", "icon_custom_emoji_id": "5870875489362513438"}
        ],
        [{"text": "◁ К выбору товара", "callback_data": "back_to_product", "icon_custom_emoji_id": "5893057118545646106"}]
    ]}
    await callback.message.edit_text(f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Товар: <b>{data.get("product")}</b>\n<tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> Цена: <b>{data.get("price")}</b>\n\n<tg-emoji emoji-id="5870982283724328568">🛠</tg-emoji> <b>ВЫБЕРИТЕ ТИП КЛАДА:</b>', reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(ShopStates.confirm_order, F.data == "order_confirm_cancel")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopStates.main_menu)
    await callback.message.edit_text("❌ <b>Заказ отменён.</b>", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(ShopStates.confirm_order, F.data == "order_confirm_yes")
async def select_payment_method(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    now = time.time()
    
    if now - last_order_time.get(user_id, 0) < config.ORDER_COOLDOWN:
        rem = int(config.ORDER_COOLDOWN - (now - last_order_time.get(user_id, 0)))
        return await callback.answer(f"⏳ Анти-спам: Подождите {rem} сек.", show_alert=True)

    await state.set_state(ShopStates.payment_method)
    kb = {"inline_keyboard": [
        [
            {"text": "Карта RU", "callback_data": "pay_card", "style": "primary", "icon_custom_emoji_id": "5769126056262898415"},
            {"text": "USDT (TRC20)", "callback_data": "pay_crypto", "style": "primary", "icon_custom_emoji_id": "5904462880941545555"}
        ],
        [{"text": "Отменить", "callback_data": "order_confirm_cancel", "style": "danger", "icon_custom_emoji_id": "5870657884844462243"}]
    ]}

    await callback.message.edit_text('<tg-emoji emoji-id="5769126056262898415">💳</tg-emoji> <b>ВЫБЕРИТЕ СПОСОБ ОПЛАТЫ:</b>', reply_markup=kb, parse_mode="HTML")
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()

@dp.callback_query(ShopStates.payment_method, F.data.in_({"pay_card", "pay_crypto"}))
async def show_requisites(callback: types.CallbackQuery, state: FSMContext):
    is_card = callback.data == "pay_card"
    method = "Банковская карта" if is_card else "USDT TRC20"
    reqs = config.CARD_NUMBER if is_card else config.USDT_ADDRESS
    await state.update_data(payment_method=method)

    data = await state.get_data()
    text = (
        f'<tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> <b>ОПЛАТА ЗАКАЗА</b>\n\n'
        f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Товар: <b>{data.get("product")}</b>\n'
        f'<tg-emoji emoji-id="5904462880941545555">💵</tg-emoji> Сумма: <b>{data.get("price")}</b>\n'
        f'<tg-emoji emoji-id="5769126056262898415">💳</tg-emoji> Способ: <b>{method}</b>\n\n'
        f'<tg-emoji emoji-id="5870528606328852614">📋</tg-emoji> <b>Реквизиты для перевода:</b>\n<code>{reqs}</code>\n\n'
        '<tg-emoji emoji-id="6028435952299413210">⚠️</tg-emoji> <i>После оплаты обязательно нажмите кнопку «Я ОПЛАТИЛ».</i>'
    )
    
    kb = {"inline_keyboard": [
        [{"text": "Я ОПЛАТИЛ", "callback_data": "i_paid", "style": "success", "icon_custom_emoji_id": "5870633910337015697"}],
        [{"text": "Отмена", "callback_data": "order_confirm_cancel", "style": "danger", "icon_custom_emoji_id": "5870657884844462243"}]
    ]}

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.update_data(last_bot_msg=callback.message.message_id)
    await callback.answer()
@dp.callback_query(ShopStates.payment_method, F.data == "i_paid")
async def process_payment_claim(callback: types.CallbackQuery, state: FSMContext):
    user = callback.from_user
    user_id = user.id
    now = time.time()
    
    if now - last_order_time.get(user_id, 0) < config.ORDER_COOLDOWN:
        return await callback.answer("⏳ Заявка уже в обработке.", show_alert=True)

    last_order_time[user_id] = now
    data = await state.get_data()

    order_id = add_order_to_db(
        user_id, user.username or "", user.full_name or "", 
        data.get("city"), data.get("district"), data.get("product"), 
        data.get("price"), data.get("klad_type"), data.get("payment_method")
    )

    log_text = (
        f'<tg-emoji emoji-id="5904462880941545555">💸</tg-emoji> <b>НОВЫЙ ЗАКАЗ #{order_id}</b>\n\n'
        f'<blockquote expandable>'
        f'<b><tg-emoji emoji-id="5870994129244131212">👤</tg-emoji> КЛИЕНТ</b>\n'
        f'├ ID: <code>{user.id}</code>\n'
        f'├ Имя: <b>{user.full_name or "—"}</b>\n'
        f'└ User: @{user.username or "—"}\n\n'
        f'<b><tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> ЗАКАЗ</b>\n'
        f'├ <tg-emoji emoji-id="5873147866364514353">🏙</tg-emoji> Город: <b>{data.get("city")}</b>\n'
        f'├ <tg-emoji emoji-id="6042011682497106307">🗺</tg-emoji> Район: <b>{data.get("district")}</b>\n'
        f'├ <tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Товар: <b>{data.get("product")}</b>\n'
        f'├ <tg-emoji emoji-id="5870982283724328568">🛠</tg-emoji> Тип: <b>{data.get("klad_type")}</b>\n'
        f'├ <tg-emoji emoji-id="5904462880941545555">💰</tg-emoji> Сумма: <b>{data.get("price")}</b>\n'
        f'└ <tg-emoji emoji-id="5769126056262898415">💳</tg-emoji> Оплата: <b>{data.get("payment_method")}</b>'
        f'</blockquote>'
    )

    admin_kb = {"inline_keyboard": [[
        {"text": "Подтвердить", "callback_data": f"adm_accept_{user_id}_{order_id}", "style": "success", "icon_custom_emoji_id": "5870633910337015697"},
        {"text": "Отклонить", "callback_data": f"adm_reject_{user_id}_{order_id}", "style": "danger", "icon_custom_emoji_id": "5870657884844462243"}
    ]]}

    await log_action(log_text, reply_markup=admin_kb)
    await update_pinned_stats()

    await state.set_state(ShopStates.main_menu)
    
    if data.get("prev_bot_msg"):
        try: await bot.delete_message(callback.message.chat.id, data["prev_bot_msg"])
        except: pass
    
    await callback.message.edit_text(
        f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Заявка №{order_id} принята!</b>\n\n'
        '<tg-emoji emoji-id="5983150113483134607">⏳</tg-emoji> Ожидайте подтверждения оплаты от оператора (обычно 5-10 минут).\n'
        f'<tg-emoji emoji-id="6039486778597970865">📞</tg-emoji> Поддержка: {config.SUPPORT_URL}',
        parse_mode="HTML",
        reply_markup=None
    )
    await callback.answer()

# --- КНОПКИ В КАНАЛЕ ЛОГОВ ---
@dp.callback_query(F.data.startswith("adm_accept_") | F.data.startswith("adm_reject_"))
async def admin_decision(callback: types.CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        return await callback.answer("⛔️ Нет прав!", show_alert=True)

    parts = callback.data.split("_")
    action, target_user_id, order_id = parts[1], int(parts[2]), parts[3]

    if action == "accept":
        try:
            await bot.send_message(
                target_user_id,
                f'<tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>Ваша оплата (Заказ #{order_id}) успешно подтверждена!</b>\n\n'
                '<tg-emoji emoji-id="6042011682497106307">📍</tg-emoji> Координаты клада скоро будут отправлены. Ожидайте.\n'
                f'<tg-emoji emoji-id="6039486778597970865">📞</tg-emoji> Связь: {config.SUPPORT_URL}',
                parse_mode="HTML"
            )
        except Exception: pass
        update_order_status(order_id, "Оплачен")
        await update_pinned_stats()
        new_text = f'{callback.message.text}\n\n<blockquote><tg-emoji emoji-id="5870633910337015697">✅</tg-emoji> <b>ПОДТВЕРЖДЕНО</b> | <b>{callback.from_user.full_name or "—"}</b> (<code>{callback.from_user.id}</code>)</blockquote>'
        
    elif action == "reject":
        try:
            await bot.send_message(
                target_user_id,
                f'<tg-emoji emoji-id="5870657884844462243">🚫</tg-emoji> <b>Оплата по заказу #{order_id} не найдена.</b>\nОбратитесь в поддержку: {config.SUPPORT_URL}',
                parse_mode="HTML"
            )
        except Exception: pass
        update_order_status(order_id, "Отклонен")
        new_text = f'{callback.message.text}\n\n<blockquote><tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> <b>ОТКЛОНЕНО</b> | <b>{callback.from_user.full_name or "—"}</b> (<code>{callback.from_user.id}</code>)</blockquote>'

    try: await callback.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")
    except Exception: pass
    await callback.answer("Обработано ✅")

@dp.message(F.chat.type == "private")
async def fallback_handler(message: types.Message, state: FSMContext):
    if await check_access(message.from_user, message): return
    await safe_delete_message(message)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started!")
    
    await log_action('<tg-emoji emoji-id="5870633910337015697">🟢</tg-emoji> <b>БОТ ЗАПУЩЕН</b>')
    await update_pinned_stats()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
