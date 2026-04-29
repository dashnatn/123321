import os
from dotenv import load_dotenv

load_dotenv()

# --- ТОКЕН И АДМИНЫ ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Список ID админов
ADMIN_IDS = [int(x.strip()) for x in os.environ.get('ADMIN_IDS', '8463616971,7465469653, 8012361844').split(',') if x.strip()]

# --- ID КАНАЛОВ ДЛЯ ЛОГОВ ---
LOG_CHANNEL_ID = int(os.environ.get('LOG_CHANNEL_ID', '1'))

# --- ССЫЛКИ И КОНТАКТЫ ---
REVIEWS_URL = os.environ.get('REVIEWS_URL', '1')
SUPPORT_URL = os.environ.get('SUPPORT_URL', '1') 

# --- РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ ---
CARD_NUMBER = os.environ.get('CARD_NUMBER', '1')
USDT_ADDRESS = os.environ.get('USDT_ADDRESS', '1')

# --- НАСТРОЙКИ БОТА ---
ORDER_COOLDOWN = int(os.environ.get('ORDER_COOLDOWN', 120))

# --- ДАННЫЕ ДЛЯ МАГАЗИНА ---
CITIES = {
    "Луганск": ["Каменобродский", "Артемовский"],
    "Донецк": ["Ворошиловский", "Ленинский", "Буденовский"],
    "Шахтерск": ["Центр"],
    "Ясиноватая": ["Центр"],
    "Макеевка": ["Центр"],
    "Мариуполь": ["Кальмиусский", "Центр"],
    "Авдеевка": ["Центр"],
    "Курск": ["Центр"],
    "Белгород": ["Центр"],
    "Краснодон": ["Центр"],
    "Первомайск": ["Центр"],
    "Ровеньки": ["Центр"]
}

# ТОВАРЫ (С ОБФУСКАЦИЕЙ)
PRODUCTS_DATA = [
    {"name": "❄️ Мeфeдpоn (M-Cát)", "variants": ["2г - 8900 RUB", "5г - 17400 RUB"]},
    {"name": "🍫 Гaшuш (H-Q)", "variants": ["2г - 7800 RUB", "5г - 16300 RUB"]},
    {"name": "💊 Лuρuкa (Pf1zer)", "variants": ["14шт (300мг) - 5600 RUB"]},
    {"name": "🌲 Шuшкu (W-eed)", "variants": ["3г - 12300 RUB"]},
    {"name": "💎 Aльфa-PVР (Sk)", "variants": ["2г - 8700 RUB", "5г - 17100 RUB"]}
]
