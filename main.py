import os
import json
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity, FSInputFile
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "").split(",")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
ADMIN_LINK = os.getenv("ADMIN_LINK", "")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
ADMIN_PHOTO_URL = "https://i.ibb.co/bjFhm9tT/1abafb14825c44b36d26df4c296eaa14.webp"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

QR_FILE = "qr_data.json"
MAINTENANCE_FILE = "maintenance.json"
QR_IMAGES_DIR = "qr_images"

os.makedirs(QR_IMAGES_DIR, exist_ok=True)

def load_maintenance():
    try:
        with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("enabled", False)
    except:
        return False

def save_maintenance(enabled: bool):
    with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
        json.dump({"enabled": enabled}, f)

class AdminStates(StatesGroup):
    add_title = State()
    add_image = State()
    add_link = State()
    add_preview = State()
    edit_select = State()
    edit_field = State()
    edit_value = State()
    delete_confirm = State()

def load_qr_data():
    try:
        with open(QR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_qr_data(data):
    with open(QR_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def increment_qr_clicks(qr_id):
    qr_data = load_qr_data()
    if qr_id in qr_data:
        qr_data[qr_id]["clicks"] = qr_data[qr_id].get("clicks", 0) + 1
        save_qr_data(qr_data)

async def check_subscription(user_id: int) -> bool:
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def get_subscribe_keyboard():
    buttons = []
    for channel in REQUIRED_CHANNELS:
        buttons.append([InlineKeyboardButton(
            text="Подписаться",
            url=f"https://t.me/{channel.replace('@', '')}",
            icon_custom_emoji_id="5388649450564511668",
            style="primary"
        )])
    buttons.append([InlineKeyboardButton(
        text="Проверить подписку",
        callback_data="check_subscribe",
        icon_custom_emoji_id="5386519125310859863",
        style="success"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_main_menu(user_id=None):
    qr_data = load_qr_data()
    buttons = []
    for qr_id, qr_info in qr_data.items():
        title = qr_info["title"]
        emoji_id = qr_info.get("emoji_id")
        
        btn = InlineKeyboardButton(
            text=title,
            callback_data=f"qr_{qr_id}",
            style="primary"
        )
        
        if emoji_id:
            btn.icon_custom_emoji_id = emoji_id
            
        buttons.append([btn])
        
    buttons.append([InlineKeyboardButton(
        text="Сообщить об ошибке",
        url=ADMIN_LINK,
        icon_custom_emoji_id="5386313314773002654",
        style="danger"
    )])

    buttons.append([InlineKeyboardButton(
        text="Наш канал",
        url=CHANNEL_LINK,
        icon_custom_emoji_id="5386462019425692360",
        style="success"
    )])
    
    if user_id and user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(
            text="Админ-панель",
            callback_data="admin_menu",
            icon_custom_emoji_id="5870982283724328568",
            style="danger"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_menu():
    qr_data = load_qr_data()
    buttons = [
        [InlineKeyboardButton(
            text="Создать QR",
            callback_data="admin_add",
            icon_custom_emoji_id="5870633910337015697",
            style="success"
        )]
    ]
    
    for qr_id, qr_info in qr_data.items():
        title = qr_info["title"]
        emoji_id = qr_info.get("emoji_id")
        
        btn = InlineKeyboardButton(
            text=title,
            callback_data=f"admin_view_{qr_id}",
            style="primary"
        )
        
        if emoji_id:
            btn.icon_custom_emoji_id = emoji_id
            
        buttons.append([btn])
    
    buttons.append([InlineKeyboardButton(
        text="Назад",
        callback_data="main_menu",
        icon_custom_emoji_id="5893057118545646106"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_qr_detail_keyboard(qr_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Удалить",
            callback_data=f"delete_qr_{qr_id}",
            icon_custom_emoji_id="5438565319960442981",
            style="danger"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="admin_menu",
            icon_custom_emoji_id="5893057118545646106"
        )]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Назад",
            callback_data="main_menu",
            icon_custom_emoji_id="5893057118545646106",
            style="primary"
        )]
    ])

def get_qr_keyboard(link):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Активировать по ссылке",
            url=link,
            icon_custom_emoji_id="5386769427414937276",
            style="success"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="main_menu",
            icon_custom_emoji_id="5386670230850267660",
            style="primary"
        )]
    ])

@dp.message(Command("m"))
async def cmd_maintenance(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    current = load_maintenance()
    new_state = not current
    save_maintenance(new_state)
    
    if new_state:
        await message.answer(
            '<b><tg-emoji emoji-id="5870657884844462243">🔒</tg-emoji> Режим технических работ включен</b>',
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            '<b><tg-emoji emoji-id="5870633910337015697">🔓</tg-emoji> Режим технических работ выключен</b>',
            parse_mode=ParseMode.HTML
        )

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    for msg_id in range(message.message_id - 1, max(1, message.message_id - 3), -1):
        try:
            await bot.delete_message(message.chat.id, msg_id)
        except:
            pass
    
    if load_maintenance() and message.from_user.id not in ADMIN_IDS:
        await message.answer(
            '<b><tg-emoji emoji-id="5870657884844462243">⚙️</tg-emoji> Бот на технических работах. Попробуйте позже.</b>',
            parse_mode=ParseMode.HTML
        )
        return
    
    if not await check_subscription(message.from_user.id):
        await message.answer(
            '<b><tg-emoji emoji-id="5386313314773002654">⚠️</tg-emoji> Для доступа к боту подпишитесь на канал:</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    qr_data = load_qr_data()
    if not qr_data:
        text = '<blockquote><tg-emoji emoji-id="5388649450564511668">❤️</tg-emoji> Добро пожаловать!\n\n<tg-emoji emoji-id="5386857409819992573">❕</tg-emoji> Бывает, что разработчики выпускают ограниченные QR-коды, которые быстро заканчиваются. Чтобы вы успели их активировать, бот будет уведомлять о новых кодах и добавлять их в общий список.</blockquote>\n\n<b>Выберите нужный вариант:</b>'
    else:
        text = '<blockquote><tg-emoji emoji-id="5388649450564511668">❤️</tg-emoji> Добро пожаловать!\n\n<tg-emoji emoji-id="5386857409819992573">❕</tg-emoji> Бывает, что разработчики выпускают ограниченные QR-коды, которые быстро заканчиваются. Чтобы вы успели их активировать, бот будет уведомлять о новых кодах и добавлять их в общий список.</blockquote>\n\n<b>Выберите нужный вариант:</b>'
    
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(message.from_user.id))

@dp.callback_query(F.data == "check_subscribe")
async def check_sub_callback(callback: CallbackQuery):
    if load_maintenance() and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Бот на технических работах", show_alert=True)
        return
    
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Вы не подписались на все каналы", show_alert=True)
        return
    
    qr_data = load_qr_data()
    if not qr_data:
        text = '<b><tg-emoji emoji-id="5870528606328852614">🔥</tg-emoji> QR-коды Brawl Stars\n\nПока нет доступных QR-кодов</b>'
    else:
        text = '<blockquote><tg-emoji emoji-id="5388649450564511668">❤️</tg-emoji> Добро пожаловать!\n\n<tg-emoji emoji-id="5386857409819992573">❕</tg-emoji> Бывает, что разработчики выпускают ограниченные QR-коды, которые быстро заканчиваются. Чтобы вы успели их активировать, бот будет уведомлять о новых кодах и добавлять их в общий список.</blockquote>\n\n<b>Выберите нужный вариант:</b>'
    
    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer("Успешно! ✅", show_alert=True)

@dp.callback_query(F.data.startswith("qr_"))
async def show_qr(callback: CallbackQuery):
    if load_maintenance() and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Бот на технических работах", show_alert=True)
        return
    
    if callback.from_user.id not in ADMIN_IDS and not await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(
            '<b><tg-emoji emoji-id="5386313314773002654">⚠️</tg-emoji> Для доступа к боту подпишитесь на канал:</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_subscribe_keyboard()
        )
        await callback.answer("Подписка не найдена", show_alert=True)
        return
    
    qr_id = callback.data.split("_")[1]
    qr_data = load_qr_data()
    
    if qr_id not in qr_data:
        await callback.answer("QR-код не найден", show_alert=True)
        return
    
    increment_qr_clicks(qr_id)
    qr_info = qr_data[qr_id]
    text = f'<b>Ваш QR-код</b>'
    
    await callback.message.delete()
    await bot.send_photo(
        chat_id=callback.message.chat.id,
        photo=FSInputFile(qr_info["image_path"]),
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_qr_keyboard(qr_info["link"])
    )
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    if load_maintenance() and callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Бот на технических работах", show_alert=True)
        return
    
    if callback.from_user.id not in ADMIN_IDS and not await check_subscription(callback.from_user.id):
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            '<b><tg-emoji emoji-id="5386313314773002654">⚠️</tg-emoji> Для доступа к боту подпишитесь на канал:</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_subscribe_keyboard()
        )
        await callback.answer("Подписка не найдена", show_alert=True)
        return
    
    qr_data = load_qr_data()
    if not qr_data:
        text = '<b><tg-emoji emoji-id="5870528606328852614">🔥</tg-emoji> QR-коды Brawl Stars\n\nПока нет доступных QR-кодов</b>'
    else:
        text = '<blockquote><tg-emoji emoji-id="5388649450564511668">❤️</tg-emoji> Добро пожаловать!\n\n<tg-emoji emoji-id="5386857409819992573">❕</tg-emoji> Бывает, что разработчики выпускают ограниченные QR-коды, которые быстро заканчиваются. Чтобы вы успели их активировать, бот будет уведомлять о новых кодах и добавлять их в общий список.</blockquote>\n\n<b>Выберите нужный вариант:</b>'
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu(callback.from_user.id))
    await callback.answer()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.delete()
    await message.answer_photo(
        photo=ADMIN_PHOTO_URL,
        caption='<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Админ-панель</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu()
    )

@dp.callback_query(F.data == "confirm_add_qr")
async def confirm_add_qr(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qr_data = load_qr_data()
    from datetime import datetime
    
    new_id = str(max([int(k) for k in qr_data.keys()], default=0) + 1)
    qr_data[new_id] = {
        "title": data["title"],
        "image_path": data["image_path"],
        "link": data["link"],
        "created": datetime.now().isoformat(),
        "clicks": 0
    }
    
    if data.get("emoji_id"):
        qr_data[new_id]["emoji_id"] = data["emoji_id"]
    
    save_qr_data(qr_data)
    await state.clear()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer_photo(
        photo=ADMIN_PHOTO_URL,
        caption='<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Админ-панель</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu()
    )
    await callback.answer("✅ QR-код успешно создан!", show_alert=True)

@dp.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    await state.clear()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer_photo(
        photo=ADMIN_PHOTO_URL,
        caption='<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Админ-панель</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_view_"))
async def admin_view_qr(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    qr_id = callback.data.split("_")[2]
    qr_data = load_qr_data()
    
    if qr_id not in qr_data:
        await callback.answer("QR-код не найден", show_alert=True)
        return
    
    qr_info = qr_data[qr_id]
    from datetime import datetime
    created = datetime.fromisoformat(qr_info.get("created", datetime.now().isoformat()))
    clicks = qr_info.get("clicks", 0)
    
    text = f'''<b><tg-emoji emoji-id="5870528606328852614">📋</tg-emoji> Информация о QR-коде

<tg-emoji emoji-id="5870801517140775623">📝</tg-emoji> Название: {qr_info["title"]}
<tg-emoji emoji-id="5890937706803894250">📅</tg-emoji> Создан: {created.strftime("%d.%m.%Y %H:%M")}
<tg-emoji emoji-id="5870930636742595124">📊</tg-emoji> Нажатий: {clicks}
<tg-emoji emoji-id="5769289093221454192">🔗</tg-emoji> Ссылка: {qr_info["link"]}</b>'''
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_qr_detail_keyboard(qr_id)
    )
    await callback.answer()



@dp.callback_query(F.data == "admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Назад",
            callback_data="admin_menu",
            icon_custom_emoji_id="5893057118545646106"
        )]
    ])
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        '<b><tg-emoji emoji-id="5870801517140775623">📝</tg-emoji> Введите название кнопки:\n\n<tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji> Можно добавить премиум эмодзи в начале названия</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(AdminStates.add_title)
    await callback.answer()

@dp.message(AdminStates.add_title)
async def admin_add_title(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    try:
        await bot.delete_message(message.chat.id, data.get("last_msg_id"))
    except:
        pass
    
    title_text = message.text
    emoji_id = None
    
    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                emoji_id = entity.custom_emoji_id
                title_text = title_text[:entity.offset] + title_text[entity.offset + entity.length:]
                break
    
    title_text = title_text.strip()
    
    await state.update_data(title=title_text, emoji_id=emoji_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Назад",
            callback_data="admin_menu",
            icon_custom_emoji_id="5893057118545646106"
        )]
    ])
    
    msg = await message.answer(
        '<b><tg-emoji emoji-id="6035128606563241721">🖼</tg-emoji> Отправьте изображение QR-кода:</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(AdminStates.add_image)

@dp.message(AdminStates.add_image, F.photo)
async def admin_add_image(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    try:
        await bot.delete_message(message.chat.id, data.get("last_msg_id"))
    except:
        pass
    
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = file.file_path
    
    import uuid
    filename = f"{uuid.uuid4()}.jpg"
    local_path = os.path.join(QR_IMAGES_DIR, filename)
    
    await bot.download_file(file_path, local_path)
    await state.update_data(image_path=local_path)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Назад",
            callback_data="admin_menu",
            icon_custom_emoji_id="5893057118545646106"
        )]
    ])
    
    msg = await message.answer(
        '<b><tg-emoji emoji-id="5769289093221454192">🔗</tg-emoji> Отправьте ссылку для перехода:</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(AdminStates.add_link)

@dp.message(AdminStates.add_link)
async def admin_add_link(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    try:
        await bot.delete_message(message.chat.id, data.get("last_msg_id"))
    except:
        pass
    
    link = message.text.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Назад",
                callback_data="admin_menu",
                icon_custom_emoji_id="5893057118545646106"
            )]
        ])
        msg = await message.answer(
            '<b><tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Ссылка должна начинаться с http:// или https://</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        await state.update_data(last_msg_id=msg.message_id)
        return
    
    await state.update_data(link=link)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Подтвердить",
            callback_data="confirm_add_qr",
            icon_custom_emoji_id="5870633910337015697",
            style="success"
        )],
        [InlineKeyboardButton(
            text="Отменить",
            callback_data="admin_menu",
            icon_custom_emoji_id="5870657884844462243",
            style="danger"
        )]
    ])
    
    text = f'''<b><tg-emoji emoji-id="6037397706505195857">👁</tg-emoji> Предпросмотр QR-кода:

<tg-emoji emoji-id="5870801517140775623">📝</tg-emoji> Название: {data["title"]}
<tg-emoji emoji-id="5769289093221454192">🔗</tg-emoji> Ссылка: {link}</b>'''
    
    msg = await message.answer_photo(
        photo=FSInputFile(data["image_path"]),
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(AdminStates.add_preview)



@dp.callback_query(F.data.startswith("delete_qr_"))
async def admin_delete_confirm(callback: CallbackQuery, state: FSMContext):
    qr_id = callback.data.split("_")[2]
    qr_data = load_qr_data()
    qr_title = qr_data[qr_id]["title"]
    
    await state.update_data(delete_qr_id=qr_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Да",
            callback_data="confirm_delete_yes",
            icon_custom_emoji_id="5870633910337015697",
            style="danger"
        )],
        [InlineKeyboardButton(
            text="Нет",
            callback_data=f"admin_view_{qr_id}",
            icon_custom_emoji_id="5870657884844462243",
            style="success"
        )]
    ])
    
    await callback.message.edit_text(
        f'<b><tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> Вы уверены, что хотите удалить "{qr_title}"?</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "confirm_delete_yes")
async def admin_delete_execute(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qr_id = data.get("delete_qr_id")
    
    qr_data = load_qr_data()
    
    if os.path.exists(qr_data[qr_id]["image_path"]):
        os.remove(qr_data[qr_id]["image_path"])
    
    del qr_data[qr_id]
    save_qr_data(qr_data)
    
    await state.clear()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.message.answer_photo(
        photo=ADMIN_PHOTO_URL,
        caption='<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Админ-панель</b>',
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu()
    )
    await callback.answer()

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await message.delete()
    await state.clear()
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            '<b><tg-emoji emoji-id="5870982283724328568">⚙</tg-emoji> Админ-панель</b>',
            parse_mode=ParseMode.HTML,
            reply_markup=get_admin_menu()
        )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
