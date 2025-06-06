import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import os
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from role import add_reputation, reset_warnings, set_operator_role
import json
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram.utils.exceptions import NetworkError
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Update
from click_counter import add_click, get_clicks_last_5h, get_total_clicks, get_today_clicks
import time
from marketplace import register_marketplace_handlers
from tlumacz import tlumacz_komenda
from click_counter import add_message, get_user_messages_count
# Wczytaj zmienne środowiskowe z pliku .env
load_dotenv()

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
GHOST_MODE = False
DB_PATH = "bot_database.db"

# Token bota
TOKEN = os.getenv("BOT_TOKEN")
# ID administratora
admin_id = 7572862671  # Zamień na rzeczywiste ID administratora
ADMIN_IDS = [7572862671]  # Lista ID administratorów
CHANNEL_ID = "@nocna_official"      # publiczny kanał
GROUP_ID = -1002673559305           # prywatna grupa (numer z minusem!)

# Utwórz folder "photos", jeśli nie istnieje
if not os.path.exists("photos"):
    os.makedirs("photos")

with open("config.json", "r") as config_file:
    config = json.load(config_file)

bot = Bot(token=TOKEN, timeout=60)  # Ustaw timeout na 60 sekund
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

register_marketplace_handlers(dp)

class EditOpinionState(StatesGroup):
    waiting_for_opinion = State()
    waiting_for_rating = State()
    waiting_for_confirm = State()
    waiting_for_proposed_change = State()  # <-- DODAJ TO!
    waiting_for_photo = State()

@dp.callback_query_handler(lambda c: c.data.startswith("opinie_"))
async def show_opinions_menu(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id

    # Sprawdź, czy użytkownik już dodał opinię
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT opinion, rating FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_opinion = cursor.fetchone()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    if existing_opinion:
        keyboard.add(InlineKeyboardButton("Edytuj opinię", callback_data=f"edit_opinion_{shop_name}"))
    else:
        keyboard.add(InlineKeyboardButton("Dodaj opinię", callback_data=f"dodaj_opinie_{shop_name}"))
    keyboard.add(InlineKeyboardButton("Wróć do menu", callback_data="menu"))

    await bot.send_message(user_id, "Wybierz opcję:", reply_markup=keyboard)

@dp.message_handler(commands=["tl"])
async def handle_tlumacz(message: types.Message, state: FSMContext):
    await tlumacz_komenda(message, state)

@dp.message_handler(lambda m: m.text and m.text.startswith(("/opr_", "/op_")), is_reply=True)
async def set_operator_command(message: types.Message):
    ADMIN_IDS = [7572862671] 
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Tylko administrator może nadawać rangę operatora.")
        return
    # Pobierz nazwę sklepu z komendy
    parts = message.text.split("_", 1)
    if len(parts) < 2 or not parts[1]:
        await message.reply("Podaj nazwę sklepu, np. /opr_Hania")
        return
    shop_name = parts[1].strip()
    user_id = message.reply_to_message.from_user.id
    role = set_operator_role(user_id, shop_name)
    await message.reply_to_message.reply(f"✅ Nadano rangę {role}")
    await message.reply(f"Operator {role} został przypisany.")
# Handler do boosta (wszyscy z rolą Operator_<coś> mogą użyć)
@dp.message_handler(commands=["boost"])

async def boost_command(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] and row[0].startswith("Operator_"):
        await message.reply("🚀 BOOST aktywowany przez operatora!")
        # tutaj możesz dodać dowolną logikę boosta
    else:
        await message.reply("Tylko operatorzy mogą użyć tej komendy.")

@dp.callback_query_handler(lambda c: c.data == "confirm_opinion", state=EditOpinionState.waiting_for_confirm)
async def confirm_opinion(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_", 2)[2]
    user_id = callback_query.from_user.id

    # Sprawdź, czy użytkownik już dodał opinię do tego sklepu
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT opinion FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_opinion = cursor.fetchone()
    conn.close()

    if existing_opinion:
        await bot.send_message(user_id, "Masz już opinię dla tego sklepu. Możesz ją edytować.")
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Edytuj opinię", callback_data=f"edit_opinion_{shop_name}"))
        await bot.send_message(user_id, "Wybierz opcję:", reply_markup=keyboard)
        return

    await state.update_data(shop_name=shop_name)
    await bot.send_message(user_id, "Napisz swoją opinię o sklepie:")
    await EditOpinionState.waiting_for_opinion.set()

@dp.callback_query_handler(lambda c: c.data.startswith("edit_opinion_"))
async def edit_opinion(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_", 2)[2]
    await state.update_data(shop_name=shop_name)
    await bot.send_message(callback_query.from_user.id, "Napisz nową opinię (poprzednia zostanie nadpisana):")
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_opinion_text(message: types.Message, state: FSMContext):
    await state.update_data(opinion_text=message.text)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Pomiń zdjęcie", callback_data="skip_photo"))
    await message.answer("Możesz dodać zdjęcie do opinii lub kliknąć 'Pomiń zdjęcie'.", reply_markup=keyboard)
    await EditOpinionState.waiting_for_photo.set()

@dp.message_handler(state=EditOpinionState.waiting_for_photo, content_types=[types.ContentType.PHOTO])
async def receive_opinion_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    photo_path = f"photos/{message.from_user.id}_{int(time.time())}.jpg"
    await photo.download(photo_path)
    await state.update_data(photo_path=photo_path)
    await ask_for_rating(message, state)

@dp.callback_query_handler(lambda c: c.data == "skip_photo", state=EditOpinionState.waiting_for_photo)
async def skip_photo(callback_query: types.CallbackQuery, state: FSMContext):
    await state.update_data(photo_path=None)
    await ask_for_rating(callback_query.message, state)

async def ask_for_rating(message, state):
    keyboard = InlineKeyboardMarkup(row_width=5)
    for i in range(1, 11):
        stars = "⭐" * i
        keyboard.add(InlineKeyboardButton(stars, callback_data=f"set_opinion_rating_{i}"))
    await message.answer("Jak oceniasz ten sklep? Kliknij odpowiednią liczbę gwiazdek:", reply_markup=keyboard)
    await EditOpinionState.waiting_for_rating.set()

@dp.callback_query_handler(lambda c: c.data.startswith("set_opinion_rating_"), state=EditOpinionState.waiting_for_rating)
async def receive_opinion_rating(callback_query: types.CallbackQuery, state: FSMContext):
    rating = int(callback_query.data.split("_")[-1])
    await state.update_data(rating=rating)
    data = await state.get_data()
    summary = f"Twoja opinia:\n\n{data['opinion_text']}\n\nOcena: {rating}⭐"
    if data.get("photo_path"):
        with open(data["photo_path"], "rb") as photo_file:
            await bot.send_photo(callback_query.from_user.id, photo=photo_file, caption=summary)
    else:
        await bot.send_message(callback_query.from_user.id, summary)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Zatwierdź", callback_data="confirm_opinion"))
    keyboard.add(InlineKeyboardButton("Anuluj", callback_data="cancel_opinion"))
    await bot.send_message(callback_query.from_user.id, "Czy zatwierdzić opinię?", reply_markup=keyboard)
    await EditOpinionState.waiting_for_confirm.set()

@dp.callback_query_handler(lambda c: c.data == "confirm_opinion", state=EditOpinionState.waiting_for_confirm)
async def confirm_opinion(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback_query.from_user.id
    shop_name = data["shop_name"]
    opinion_text = data["opinion_text"]
    rating = data["rating"]
    photo_path = data.get("photo_path")
    user_name = (
        (callback_query.from_user.full_name and callback_query.from_user.full_name.strip())
        or (callback_query.from_user.username and callback_query.from_user.username.strip())
        or f"ID:{user_id}"
    )

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT opinion FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_opinion = cursor.fetchone()

    if existing_opinion:
        cursor.execute("""
            UPDATE opinions
            SET opinion = ?, rating = ?, photo = ?, user_name = ?
            WHERE user_id = ? AND shop_name = ?
        """, (opinion_text, rating, photo_path, user_name, user_id, shop_name))
        await bot.send_message(user_id, "Twoja opinia została zaktualizowana.")
    else:
        cursor.execute("""
            INSERT INTO opinions (user_id, shop_name, opinion, rating, user_name, photo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, shop_name, opinion_text, rating, user_name, photo_path))
        await bot.send_message(user_id, "Twoja opinia została zapisana.")
    conn.commit()
    conn.close()
    await state.finish()
    add_reputation(user_id, 5)  # +5 pkt za opinię
    
@dp.callback_query_handler(lambda c: c.data == "cancel_opinion", state=EditOpinionState.waiting_for_confirm)
async def cancel_opinion(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback_query.from_user.id, "Anulowano dodawanie opinii.")
    await state.finish()
# Inicjalizacja bazy danych

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opinions (
            user_id INTEGER,
            shop_name TEXT,
            opinion TEXT,
            rating INTEGER,
            user_name TEXT,
            photo TEXT,
            PRIMARY KEY (user_id, shop_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            message_count INTEGER DEFAULT 0,
            last_message TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            shop_name TEXT PRIMARY KEY,
            description TEXT,
            bot_link TEXT,
            operator_link TEXT,
            chat_link TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            accepted_rules INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_offers (
            shop_name TEXT,
            job_title TEXT,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_opinions (
            user_id INTEGER,
            user_name TEXT,
            opinion TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proposed_shops (
            user_id INTEGER,
            user_name TEXT,
            shop_name TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

from role import update_users_table
update_users_table()

def update_shops_table():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Dodaj kolumny, jeśli nie istnieją
    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN bot_link TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN date TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN operator_link TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN chat_link TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN photo TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje
    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje
    conn.commit()
    conn.close()

# Wywołaj funkcję, aby zaktualizować tabelę
update_shops_table()

def add_shops():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    shops = [
        ("Lincoln", "💰Bot: @LincolnMarketV2_bot 👑Operator: @Lincoln_Opr 💬Czat:Dostęp po zakupie 📢Info: ???")
    ]
    cursor.executemany("INSERT OR IGNORE INTO shops (shop_name, description) VALUES (?, ?)", shops)
    conn.commit()
    conn.close()

add_shops() 

def update_shops_data():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Przykładowe dane do aktualizacji
    shops_data = [
        ("Easy Shop", "https://t.me/e_a_s_y_shop_PL_bot", "https://t.me/zz3zz3", "https://t.me/+4WsSJGkfD1w2MTQ5")
    ]

    for shop_name, bot_link, operator_link, chat_link in shops_data:
        cursor.execute("""
            UPDATE shops
            SET bot_link = ?, operator_link = ?, chat_link = ?
            WHERE shop_name = ?
        """, (bot_link, operator_link, chat_link, shop_name))

    # Dodaj kolumnę clicks jeśli nie istnieje
    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN clicks INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Kolumna już istnieje

    conn.commit()
    conn.close()

# Wywołaj funkcję, aby zaktualizować dane
update_shops_data()

def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    # 1. 🔥Nocna lista sklepów🔥
    keyboard.add(KeyboardButton("🔥Nocna lista sklepów🔥"))
    # 2. 🛒 Marketplace
    keyboard.add(KeyboardButton("🛒 Marketplace"))
    # 3. 🔎 Szukaj
    keyboard.add(KeyboardButton("🔎 Szukaj"))
    # 4. 💬 Czat | ℹ️ O Nas | 💎 VIP
    keyboard.row(
        KeyboardButton("💬 Czat"),
        KeyboardButton("ℹ️ O Nas"),
        KeyboardButton("💎 VIP")
    )
    # 5. 📬 Kontakt | 📜 Regulamin | 💼 Praca
    keyboard.row(
        KeyboardButton("📬 Kontakt"),
        KeyboardButton("📜 Regulamin"),
        KeyboardButton("💼 Praca")
    )
    # 6. 📢 KANAŁ NOCNA_OFFICIAL
    keyboard.add(KeyboardButton("📢 KANAŁ NOCNA_OFFICIAL"))
    return keyboard
async def daily_clicks_report():
    while True:
        now = datetime.now()
        # Oblicz czas do północy
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
        wait_seconds = (tomorrow - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        total = get_total_clicks()
        today = get_today_clicks()
        last_5h = get_clicks_last_5h()
        text = (
            f"📊 *Raport dzienny kliknięć*\n"
            f"• Dzisiaj: {today}\n"
            f"• Ostatnie 5h: {last_5h}\n"
            f"• Łącznie: {total}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="Markdown")
            except Exception as e:
                logging.warning(f"Nie udało się wysłać raportu dziennego: {e}")
                logging.info("Wysłano raport dzienny kliknięć do administratorów.")

async def send_message_with_retry(chat_id, text, retries=3):
    for attempt in range(retries):
        try:
            await bot.send_message(chat_id, text)
            logging.info(f"Wysłano wiadomość do użytkownika {chat_id}")
            break  # Jeśli wiadomość została wysłana, przerwij pętlę
        except NetworkError as e:
            logging.warning(f"Próba {attempt + 1} nie powiodła się: {e}")
            await asyncio.sleep(2)  # Odczekaj 2 sekundy przed kolejną próbą

async def send_message_to_all_users(message_text: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    for user_id, in users:
        try:
            await bot.send_message(user_id, message_text)
            logging.info(f"Wysłano wiadomość do użytkownika {user_id}")
            await asyncio.sleep(0.1)  # Opóźnienie 100 ms między wiadomościami
        except Exception as e:
            logging.warning(f"Nie udało się wysłać wiadomości do użytkownika {user_id}: {e}")

async def send_top3_shops():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT shop_name, IFNULL(AVG(rating), 0) as avg_rating
        FROM shops
        LEFT JOIN opinions ON shops.shop_name = opinions.shop_name
        GROUP BY shops.shop_name
        ORDER BY avg_rating DESC
        LIMIT 3
    """)
    top_shops = cursor.fetchall()
    conn.close()

    if not top_shops:
        text = "Brak sklepów do wyświetlenia."
    else:
        text = "🏆 TOP 3 sklepy:\n"
        for idx, (shop_name, avg_rating) in enumerate(top_shops, 1):
            text += f"{idx}. {shop_name} ({avg_rating:.1f} ⭐)\n"

    # Wyślij do wszystkich użytkowników
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    for user_id, in users:
        try:
            await bot.send_message(CHANNEL_ID, text)
            await bot.send_message(user_id, text)
            await asyncio.sleep(0.1)  # małe opóźnienie
        except Exception as e:
            logging.warning(f"Nie udało się wysłać TOP 3 do {user_id}: {e}")

async def send_top3_shops_to_channel():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.shop_name, IFNULL(AVG(o.rating), 0) as avg_rating, s.bot_link, s.operator_link
        FROM shops s
        LEFT JOIN opinions o ON s.shop_name = o.shop_name
        GROUP BY s.shop_name
        ORDER BY avg_rating DESC
        LIMIT 3
    """)
    top_shops = cursor.fetchall()
    conn.close()

    if not top_shops:
        text = "Brak sklepów do wyświetlenia."
    else:
        text = "🏆 TOP 3 sklepy:\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, (shop_name, avg_rating, bot_link, operator_link) in enumerate(top_shops):
            color = get_color(avg_rating)
            opinions_count = get_opinions_count(shop_name)
            # Przygotuj 3. linię: operator lub bot
            line3 = ""
            if operator_link:
                if "t.me/" in operator_link:
                    op_nick = "@" + operator_link.split("t.me/")[-1].replace("/", "")
                elif operator_link.startswith("@"):
                    op_nick = operator_link
                else:
                    op_nick = f"@{operator_link}"
                line3 = op_nick
            elif bot_link and "t.me/" in bot_link:
                line3 = "@" + bot_link.split("t.me/")[-1].replace("/", "")
            text += (
                f"{medals[idx]} {shop_name} {avg_rating:.1f}⭐\n"
                f"{color} ({opinions_count} opinii)\n"
                f"{line3}\n\n"
            )

    try:
        await bot.send_message(CHANNEL_ID, text)
        await bot.send_message(GROUP_ID, text)
    except Exception as e:
        logging.warning(f"Nie udało się wysłać TOP 3 na kanał: {e}")

@dp.message_handler(commands=["mojeinfo"])

@dp.message_handler(commands=["myid"])
async def get_my_id(message: types.Message):
    await message.reply(f"Twoje ID: {message.from_user.id}")

@dp.message_handler(commands=["stan"])
async def show_clicks(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return
    clicks = get_clicks_last_5h()
    await message.reply(f"📊 W ciągu ostatnich 5 godzin odwiedziło nas: {clicks} osób, dziękujemy!")

class UserNameUpdateMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        user_name = (
            (message.from_user.full_name and message.from_user.full_name.strip())
            or (message.from_user.username and message.from_user.username.strip())
            or f"ID:{user_id}"
        )
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_name FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            old_name = row[0]
            if old_name != user_name:
                cursor.execute("UPDATE users SET user_name = ? WHERE user_id = ?", (user_name, user_id))
                conn.commit()
                for admin_id in ADMIN_IDS:
                    try:
                        await message.bot.send_message(
                            admin_id,
                            f"ℹ️ Użytkownik {old_name} (ID: {user_id}) zmienił nazwę na: {user_name}"
                        )
                    except Exception as e:
                        logging.warning(f"Nie udało się powiadomić admina o zmianie nazwy: {e}")
        else:
            cursor.execute("INSERT INTO users (user_id, user_name) VALUES (?, ?)", (user_id, user_name))
            conn.commit()
        conn.close()
    
def split_text(text, max_length=4000):
    # Dzieli tekst na fragmenty nie dłuższe niż max_length
    lines = text.split('\n')
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_length:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    return chunks
    
def czytaj_regulamin():
    try:
        with open("regulamin_intro.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "Brak pliku z regulaminem."

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    user_name = (
        (message.from_user.full_name and message.from_user.full_name.strip())
        or (message.from_user.username and message.from_user.username.strip())
        or f"ID:{user_id}"
    )

    # Sprawdź i zaktualizuj nazwę użytkownika w bazie oraz pobierz status akceptacji regulaminu
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, accepted_rules FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        accepted_rules = row[1]
        cursor.execute("UPDATE users SET user_name = ? WHERE user_id = ?", (user_name, user_id))
        conn.commit()
    else:
        accepted_rules = 0
        cursor.execute("INSERT INTO users (user_id, user_name, accepted_rules) VALUES (?, ?, ?)", (user_id, user_name, 0))
        conn.commit()
    conn.close()

    if not accepted_rules:
        # Pokaż regulamin i przycisk akceptacji
        tekst = czytaj_regulamin()
        if tekst:
            for chunk in split_text(tekst):
                await message.answer(chunk)
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Akceptuję regulamin", callback_data="accept_rules"))
        await message.answer("Aby korzystać z bota, musisz zaakceptować regulamin.", reply_markup=keyboard)
        return

    # Jeśli zaakceptował, pokaż menu główne
    await message.answer("Witaj w Nocnej24! Wybierz opcję z menu:", reply_markup=main_menu())

@dp.message_handler(lambda message: message.text in ["ℹ️ O Nas", "📜 Regulamin", "/regulamin"])
async def show_full_regulamin(message: types.Message):
    tekst = czytaj_regulamin()
    if not tekst:
        tekst = "Regulamin jest chwilowo niedostępny."
    await message.answer(tekst)
@dp.message_handler(commands=["ghost"])
async def ghost_mode_toggle(message: types.Message):
    global GHOST_MODE
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return
    GHOST_MODE = not GHOST_MODE
    status = "włączony" if GHOST_MODE else "wyłączony"
    await message.reply(f"Tryb ghost został {status}.")

class GhostModeMiddleware(BaseMiddleware):
    async def on_pre_process_update(self, update: Update, data: dict):
        global GHOST_MODE
        user_id = None
        chat_type = None
        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
            chat_type = update.message.chat.type
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
            chat_type = update.callback_query.message.chat.type
        # Blokuj tylko na czatach prywatnych
        if GHOST_MODE and user_id not in ADMIN_IDS and chat_type == "private":
            if update.message:
                await update.message.reply("Bot jest obecnie dostępny tylko dla administratorów (tryb testowy).")
            elif update.callback_query:
                await update.callback_query.answer("Bot jest obecnie dostępny tylko dla administratorów (tryb testowy).", show_alert=True)
            raise Exception("Ghost mode active")
@dp.message_handler(content_types=[types.ContentType.NEW_CHAT_MEMBERS, types.ContentType.LEFT_CHAT_MEMBER, types.ContentType.PINNED_MESSAGE])
async def delete_system_messages(message: types.Message):
    try:
        await message.delete()
    except Exception as e:
        pass  # np. brak uprawnień


SHOPS_PER_PAGE = 6  # Liczba sklepów na stronę

def get_shops_with_ratings():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.shop_name, IFNULL(AVG(o.rating), 0) AS avg_rating
        FROM shops s
        LEFT JOIN opinions o ON s.shop_name = o.shop_name
        GROUP BY s.shop_name
        ORDER BY avg_rating DESC
    """)
    shops = cursor.fetchall()
    conn.close()
    return shops

def get_color(rating, opinions_count=0):
    if opinions_count == 0:
        return "⚪️ Brak ocen"
    if rating >= 9:
        return "🔵 SUPER"
    elif rating >= 7:
        return "🟢 DOBRY"
    elif rating >= 5:
        return "🟡 ŚREDNI"
    elif rating >= 3:
        return "🟠 SŁABY"
    else:
        return "🔴 SCAM"
    
def get_opinions_count(shop_name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM opinions WHERE shop_name = ? AND opinion IS NOT NULL AND opinion != ''", (shop_name,))
    count = cursor.fetchone()[0]
    conn.close()
    return count
    
def build_shops_keyboard(shops, page=0):
    # Pobierz statystyki do etykiet specjalnych
    all_clicks = {shop: get_clicks_last_5h() for shop, _ in shops}
    all_opinions = {shop: get_opinions_count(shop) for shop, _ in shops}
    all_ratings = {shop: avg_rating for shop, avg_rating in shops}

    hot_shop = max(all_clicks, key=all_clicks.get) if all_clicks else None
    most_commented = max(all_opinions, key=all_opinions.get) if all_opinions else None
    best_rated = max(all_ratings, key=all_ratings.get) if all_ratings else None

    start = page * SHOPS_PER_PAGE
    end = start + SHOPS_PER_PAGE
    page_shops = shops[start:end]
    keyboard = InlineKeyboardMarkup(row_width=1)
    for idx, (shop_name, avg_rating) in enumerate(page_shops, start=start):
        opinions_count = get_opinions_count(shop_name)
        color = get_color(avg_rating, opinions_count)

        # Linia 1: medal jeśli TOP3, nazwa, ocena
        if idx == 0:
            line1 = f"🥇 {shop_name} {avg_rating:.1f}⭐"
        elif idx == 1:
            line1 = f"🥈 {shop_name} {avg_rating:.1f}⭐"
        elif idx == 2:
            line1 = f"🥉 {shop_name} {avg_rating:.1f}⭐"
        else:
            line1 = f"{shop_name} {avg_rating:.1f}⭐"

        # Linia 2: kolor + liczba opinii + specjalna etykieta
        special = ""
        if shop_name == hot_shop:
            special = "🔥 HOT"
        elif shop_name == most_commented:
            special = "💬 Najchętniej komentowany"
        elif shop_name == best_rated:
            special = "⭐ Najlepiej oceniany"
        line2 = f"{color} ({opinions_count} opinii) {special}"

        # Linia 3: @bot lub @operator
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT bot_link, operator_link FROM shops WHERE shop_name = ?", (shop_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            bot_link, operator_link = row
            bot_nick = ""
            op_nick = ""
            if bot_link and "t.me/" in bot_link:
                bot_nick = "@" + bot_link.split("t.me/")[-1].replace("/", "")
            if operator_link:
                if "t.me/" in operator_link:
                    op_nick = "@" + operator_link.split("t.me/")[-1].replace("/", "")
                elif operator_link.startswith("@"):
                    op_nick = operator_link
                else:
                    op_nick = f"@{operator_link}"
            line3 = op_nick if op_nick else bot_nick
        else:
            line3 = ""

        label = f"{line1}\n{line2}\n{line3}".strip()
        keyboard.add(InlineKeyboardButton(label, callback_data=f"shop_{shop_name}"))
    # paginacja
    total_pages = (len(shops) + SHOPS_PER_PAGE - 1) // SHOPS_PER_PAGE
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️", callback_data=f"shops_page_{page-1}"))
    buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if end < len(shops):
        buttons.append(InlineKeyboardButton("➡️", callback_data=f"shops_page_{page+1}"))
    keyboard.row(*buttons)
    return keyboard

@dp.message_handler(lambda message: message.text == "🔥Nocna lista sklepów🔥")
async def show_shops_paginated(message: types.Message):
    username = message.from_user.username or "Anonim"
    logging.info(f"Użytkownik @{username} przegląda listę sklepów (strona 1).")
    shops = get_shops_with_ratings()
    keyboard = build_shops_keyboard(shops, page=0)
    # Najpierw wyślij grafikę noc2.jpg
    with open("noc2.jpg", "rb") as photo:
        await message.answer_photo(
            photo=photo,
            caption="🛒 *Lista sklepów Nocna24*",
            parse_mode="Markdown"
        )
    # Następnie wyślij listę sklepów
    await message.answer("Wybierz sklep:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("shops_page_"))
async def shops_page_callback(callback_query: types.CallbackQuery):
    page = int(callback_query.data.split("_")[-1])
    shops = get_shops_with_ratings()
    keyboard = build_shops_keyboard(shops, page=page)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("shop_"))
async def shop_details(callback_query: types.CallbackQuery):
    add_click()
    shop_name = callback_query.data.split("_", 1)[1]

    # Pobierz szczegóły sklepu z bazy danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT description, photo, bot_link, operator_link, chat_link
        FROM shops WHERE shop_name = ?
    """, (shop_name,))
    shop_info = cursor.fetchone()
    conn.close()

    if not shop_info:
        await bot.send_message(callback_query.from_user.id, "Nie znaleziono szczegółów dla tego sklepu.")
        return

    description, photo, bot_link, operator_link, chat_link = shop_info

    # Pobierz statystyki i etykiety
    avg_rating = 0
    opinions_count = get_opinions_count(shop_name)
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT IFNULL(AVG(rating), 0) FROM opinions WHERE shop_name = ?", (shop_name,))
    avg_rating = cursor.fetchone()[0]
    conn.close()
    color = get_color(avg_rating, opinions_count)

    # Pobierz HOT, Najlepiej oceniany, Najchętniej komentowany
    shops = get_shops_with_ratings()
    all_clicks = {shop: get_clicks_last_5h() for shop, _ in shops}
    all_opinions = {shop: get_opinions_count(shop) for shop, _ in shops}
    all_ratings = {shop: avg for shop, avg in shops}
    hot_shop = max(all_clicks, key=all_clicks.get) if all_clicks else None
    most_commented = max(all_opinions, key=all_opinions.get) if all_opinions else None
    best_rated = max(all_ratings, key=all_ratings.get) if all_ratings else None

    special = ""
    if shop_name == hot_shop:
        special = "🔥 HOT"
    elif shop_name == most_commented:
        special = "💬 Najchętniej komentowany"
    elif shop_name == best_rated:
        special = "⭐ Najlepiej oceniany"

    # Przygotuj nick operatora/bota
    op_nick = ""
    if operator_link:
        if "t.me/" in operator_link:
            op_nick = "@" + operator_link.split("t.me/")[-1].replace("/", "")
        elif operator_link.startswith("@"):
            op_nick = operator_link
        else:
            op_nick = f"@{operator_link}"
    elif bot_link and "t.me/" in bot_link:
        op_nick = "@" + bot_link.split("t.me/")[-1].replace("/", "")

    # Przygotuj opis do wysłania
    opis = (
        f"🏬 <b>{shop_name}</b> {avg_rating:.1f}⭐\n"
        f"{color} ({opinions_count} opinii) {special}\n"
        f"{op_nick}\n\n"
        f"{description or 'Brak opisu sklepu.'}"
    )

    # Przygotuj klawiaturę z przyciskami
    keyboard = InlineKeyboardMarkup(row_width=2)
    row = []
    if bot_link:
        row.append(InlineKeyboardButton("🤖 BOT", url=bot_link))
    if operator_link:
        row.append(InlineKeyboardButton("👤 OPERATOR", url=operator_link))
    if row:
        keyboard.row(*row)
    if chat_link:
        keyboard.add(InlineKeyboardButton("💬 CZAT", url=chat_link))
    keyboard.add(
        InlineKeyboardButton("⭐ Opinie", callback_data=f"opinie_{shop_name}"),
        InlineKeyboardButton("🏠 Wróć do menu", callback_data="menu")
    )

    # Wyślij zdjęcie lub opis
    if photo and os.path.exists(photo):
        if photo.endswith(".mp4"):
            with open(photo, 'rb') as video_file:
                await bot.send_video(callback_query.from_user.id, video=video_file, caption=opis, parse_mode="HTML")
        else:
            with open(photo, 'rb') as photo_file:
                await bot.send_photo(callback_query.from_user.id, photo=photo_file, caption=opis, parse_mode="HTML")
    else:
        await bot.send_message(callback_query.from_user.id, opis, parse_mode="HTML")

    # Wyślij przyciski
    await bot.send_message(callback_query.from_user.id, "Wybierz opcję:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "Powrót do menu")
async def go_to_main_menu(message: types.Message):
    await message.answer("Wybierz opcję:", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "menu")
async def go_to_menu(callback_query: types.CallbackQuery):
    await bot.send_message(callback_query.from_user.id, "Wybierz opcję:", reply_markup=main_menu())

@dp.message_handler(lambda message: message.text == "💬 Czat")
async def chat_link(message: types.Message):
    # Automatyczne otwarcie czatu i wysłanie /start
    await bot.send_message(message.chat.id, "comming")

@dp.message_handler(lambda message: message.text == "Ogłoszenia")
async def show_announcements(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Pobierz najnowsze ogłoszenia
    cursor.execute("SELECT message FROM announcements ORDER BY created_at DESC LIMIT 5")
    announcements = cursor.fetchall()

    # Pobierz najnowsze opinie (np. ostatnie 5)
    cursor.execute("SELECT shop_name, opinion FROM opinions ORDER BY rowid DESC LIMIT 5")
    recent_opinions = cursor.fetchall()
    conn.close()

    # Przygotuj treść ogłoszeń
    response = "📢 **Ogłoszenia:**\n\n"
    if announcements:
        for announcement in announcements:
            response += f"- {announcement[0]}\n"
    else:
        response += "Brak ogłoszeń.\n\n"

    if recent_opinions:
        response += "\n🆕 **Najnowsze opinie:**\n"
        for shop_name, opinion in recent_opinions:
            response += f"- {shop_name}: {opinion}\n"
    else:
        response += "\nBrak nowych opinii."

    # Wyślij ogłoszenia do użytkownika
    await message.answer(response, parse_mode="Markdown")

@dp.message_handler(lambda message: message.text == "Nowe opinie")
async def show_recent_opinions(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Pobierz ostatnie 5 opinii
    cursor.execute("SELECT user_name, shop_name, opinion, photo FROM opinions ORDER BY rowid DESC LIMIT 5")
    recent_opinions = cursor.fetchall()
    conn.close()

    # Przygotuj treść wiadomości
    if recent_opinions:
        for user_name, shop_name, opinion, photo in recent_opinions:
            response = f"👤 {user_name}\n🏬 {shop_name}\n💬 {opinion}"
            if photo:
                # Wyślij zdjęcie z opinią
                with open(photo, 'rb') as photo_file:
                    await bot.send_photo(message.chat.id, photo=photo_file, caption=response)
            else:
                # Wyślij tylko tekst opinii
                await message.answer(response)
    else:
        await message.answer("Brak nowych opinii.")

@dp.callback_query_handler(lambda c: c.data == "accept_rules")
async def accept_rules(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    # Zaktualizuj status użytkownika w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET accepted_rules = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Wyślij wiadomość z potwierdzeniem i pokaż menu główne
    await bot.send_message(
        user_id,
        "✅ Dziękujemy za akceptację regulaminu!\n\nMożesz już korzystać z bota.",
        reply_markup=main_menu()
    )
async def check_user(user_id, user_name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT accepted_rules FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        # Dodaj użytkownika do bazy danych
        cursor.execute("INSERT INTO users (user_id, user_name, accepted_rules) VALUES (?, ?, ?)", (user_id, user_name, 0))
        conn.commit()
        conn.close()
        return False  # Użytkownik jeszcze nie zaakceptował regulaminu
    conn.close()
    return user[0] == 1  # Zwróć True, jeśli użytkownik zaakceptował regulamin


@dp.message_handler(lambda message: message.text == "📬 Kontakt")
async def contact(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Rozpocznij rozmowę", url="https://t.me/KiedysMichal"))
    await message.answer("Kliknij poniżej, aby rozpocząć rozmowę z administratorem:", reply_markup=keyboard)

@dp.message_handler(commands=["bot"], chat_type=["group", "supergroup"])
async def handle_bot_command_in_group(message: types.Message):
    bot_username = (await bot.get_me()).username  # Pobierz nazwę użytkownika bota
    try:
        # Wyślij wiadomość prywatną do użytkownika
        await bot.send_message(
            message.from_user.id,
            "Cześć! Jestem tutaj, aby Ci pomóc. Możesz korzystać z moich funkcji w tym czacie prywatnym. 😊"
        )
        await message.reply("Wysłałem Ci wiadomość prywatną. Sprawdź swój czat z botem!")
    except Exception:
        # Jeśli nie można wysłać wiadomości prywatnej, wyślij link do rozpoczęcia rozmowy
        await message.reply(
            f"Nie mogę wysłać Ci wiadomości prywatnej. Aby rozpocząć rozmowę z botem, kliknij tutaj: "
            f"[Rozpocznij rozmowę](https://t.me/{bot_username})",
            parse_mode="Markdown"
        )

@dp.message_handler(commands=["delete_opinion"])
async def delete_opinion(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in ADMIN_IDS:  # Zamień na swoje ID administratorów
        await message.reply("Nie masz uprawnień do wykonania tej operacji.")
        return

    # Oczekiwany format: /delete_opinion <user_id> <shop_name>
    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        await message.reply("Użycie: /delete_opinion <user_id> <shop_name>")
        return

    user_id, shop_name = args[1], args[2]

    # Usuń opinię z bazy danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    conn.commit()
    conn.close()

    await message.reply(f"Opinia użytkownika {user_id} dla sklepu {shop_name} została usunięta.")

@dp.message_handler(commands=["nowybot"])
async def update_bot_link(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in ADMIN_IDS:  # Zamień na swoje ID administratorów
        await message.reply("Nie masz uprawnień do wykonania tej operacji.")
        return

    # Oczekiwany format: /nowybot <nazwa_sklepu>, <nowy_link_bota>
    try:
        args = message.text.split(maxsplit=1)[1].split(",", maxsplit=1)
        shop_name = args[0].strip()
        new_bot_link = args[1].strip()
    except (IndexError, ValueError):
        await message.reply("Użycie: /nowybot <nazwa_sklepu>, <nowy_link_bota>")
        return

    # Aktualizacja linku w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE shops SET bot_link = ? WHERE shop_name = ?", (new_bot_link, shop_name))
    if cursor.rowcount > 0:
        await message.reply(f"Link bota dla sklepu '{shop_name}' został zaktualizowany na: {new_bot_link}")
    else:
        await message.reply(f"Nie znaleziono sklepu o nazwie '{shop_name}'.")
    conn.commit()
    conn.close()

@dp.message_handler(commands=["edytuj_sklep"])
async def edit_shop_menu(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in ADMIN_IDS:  # Zamień na swoje ID administratorów
        await message.reply("Nie masz uprawnień do wykonania tej operacji.")
        return

    # Pobierz listę sklepów z bazy danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    # Przygotuj klawiaturę z listą sklepów
    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"edit_shop_{shop_name}"))

    await message.reply("Wybierz sklep do edycji:", reply_markup=keyboard)
@dp.message_handler(commands=["edytuj_sklep"])
async def edit_shop_by_operator(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0] or not row[0].startswith("Operator_"):
        return  # Nie rób nic, jeśli nie jest operatorem (admin obsłużony wyżej)
    shop_name = row[0].replace("Operator_", "")
    await message.reply(
        f"Edytujesz sklep: {shop_name}\n"
        "Podaj nowe dane w formacie:\n"
        "Opis, link do bota, link do operatora, link do czatu"
    )
    await state.update_data(shop_name=shop_name)
    await EditOpinionState.waiting_for_proposed_change.set()

@dp.message_handler(state=EditOpinionState.waiting_for_proposed_change, content_types=[types.ContentType.TEXT])
async def receive_shop_edit_by_operator(message: types.Message, state: FSMContext):
    try:
        data = message.text.split(",")
        if len(data) != 4:
            raise ValueError("Nieprawidłowy format danych.")
        description, bot_link, operator_link, chat_link = [d.strip() for d in data]
        state_data = await state.get_data()
        shop_name = state_data.get("shop_name")
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE shops SET description=?, bot_link=?, operator_link=?, chat_link=? WHERE shop_name=?",
            (description, bot_link, operator_link, chat_link, shop_name)
        )
        conn.commit()
        conn.close()
        await message.reply("Dane sklepu zostały zaktualizowane!")
    except Exception as e:
        await message.reply(f"Błąd: {e}. Upewnij się, że dane są w poprawnym formacie.")
    finally:
        await state.finish()
async def is_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.is_chat_admin()



@dp.message_handler(commands=["broadcast"])
async def broadcast_message(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in ADMIN_IDS:  # Lista ID administratorów
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    # Pobierz treść wiadomości
    try:
        message_text = message.text.split(maxsplit=1)[1]
    except IndexError:
        await message.reply("Użycie: /broadcast <treść wiadomości>")
        return

    # Wyślij wiadomość do wszystkich użytkowników
    await send_message_to_all_users(message_text)
    await message.reply("Wiadomość została wysłana do wszystkich użytkowników.")

@dp.message_handler(lambda message: message.text == "💼 Praca")
async def job_offers_menu(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Pobierz dostępne oferty pracy
    cursor.execute("SELECT shop_name, job_title, description FROM job_offers")
    job_offers = cursor.fetchall()
    conn.close()

    if job_offers:
        for shop_name, job_title, description in job_offers:
            response = f"🏬 **{shop_name}**\n💼 **Stanowisko:** {job_title}\n📄 **Opis:** {description}"
            await message.answer(response, parse_mode="Markdown")
    else:
        await message.answer("Brak dostępnych ofert pracy.")

    # Dodaj przycisk do dodania opinii o pracy
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Dodaj opinię o pracy", callback_data="add_job_opinion"))
    await message.answer("Możesz również dodać opinię o pracy:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "add_job_opinion")
async def add_job_opinion(callback_query: types.CallbackQuery):
    await bot.send_message(
        callback_query.from_user.id,
        "Podaj swoją opinię o pracy. Możesz napisać kilka słów o tym, gdzie i/lub jak pracowałeś, jak to wyglądało i jakie były Twoje doświadczenia."
    )
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(commands=["update_links"])
async def update_links(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in ADMIN_IDS:  # Zamień na swoje ID administratorów
        await message.reply("Nie masz uprawnień do wykonania tej operacji.")
        return

    # Oczekiwany format: /update_links <nazwa_sklepu>, <nowy_bot_link>, <nowy_operator_link>, <nowy_chat_link>
    try:
        args = message.text.split(maxsplit=1)[1].split(",", maxsplit=3)
        shop_name = args[0].strip()
        new_bot_link = args[1].strip()
        new_operator_link = args[2].strip()
        new_chat_link = args[3].strip()
    except (IndexError, ValueError):
        await message.reply("Użycie: /update_links <nazwa_sklepu>, <nowy_bot_link>, <nowy_operator_link>, <nowy_chat_link>")
        return

    # Aktualizacja linków w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE shops
        SET bot_link = ?, operator_link = ?, chat_link = ?
        WHERE shop_name = ?
        """,
        (new_bot_link, new_operator_link, new_chat_link, shop_name)
    )

    if cursor.rowcount > 0:
        await message.reply(f"Linki dla sklepu '{shop_name}' zostały zaktualizowane.")
    else:
        await message.reply(f"Nie znaleziono sklepu o nazwie '{shop_name}'.")

    conn.commit()
    conn.close()

class AddShopState(StatesGroup):
    waiting_for_data = State()
    waiting_for_photo = State()
class AddShopPhotoState(StatesGroup):
    waiting_for_shop = State()
    waiting_for_media = State()

@dp.message_handler(commands=["addfoto"])
async def add_shop_photo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    # Pobierz listę sklepów
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    # Przygotuj klawiaturę wyboru sklepu
    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"addfoto_{shop_name}"))

    await message.reply("Wybierz sklep, do którego chcesz dodać zdjęcie lub film:", reply_markup=keyboard)
    await AddShopPhotoState.waiting_for_shop.set()

@dp.callback_query_handler(lambda c: c.data.startswith("addfoto_"), state=AddShopPhotoState.waiting_for_shop)
async def add_shop_photo_choose(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_", 1)[1]
    await state.update_data(shop_name=shop_name)
    await bot.send_message(callback_query.from_user.id, f"Prześlij zdjęcie lub film (max 5 sekund) dla sklepu {shop_name}.")
    await AddShopPhotoState.waiting_for_media.set()

@dp.message_handler(state=AddShopPhotoState.waiting_for_media, content_types=[types.ContentType.PHOTO, types.ContentType.VIDEO])
async def add_shop_photo_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")

    # Obsługa zdjęcia
    if message.photo:
        photo = message.photo[-1]
        photo_path = f"photos/{shop_name}_main.jpg"
        await photo.download(photo_path)
        media_type = "photo"
        media_path = photo_path
    # Obsługa filmu
    elif message.video:
        if message.video.duration > 5:
            await message.reply("Film może mieć maksymalnie 5 sekund!")
            return
        video = message.video
        video_path = f"photos/{shop_name}_main.mp4"
        await video.download(video_path)
        media_type = "video"
        media_path = video_path
    else:
        await message.reply("Wyślij zdjęcie lub film (max 5 sekund).")
        return

    # Zapisz ścieżkę do bazy
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE shops SET photo = ? WHERE shop_name = ?", (media_path, shop_name))
    conn.commit()
    conn.close()

    await message.reply(f"{'Zdjęcie' if media_type == 'photo' else 'Film'} dla sklepu {shop_name} zostało zapisane!")
    await state.finish()

@dp.message_handler(commands=["dodaj_sklep"])
async def add_shop_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return
    await message.reply("Podaj dane sklepu w formacie:\nNazwa sklepu, link do bota, link do operatora, link do czatu")
    await AddShopState.waiting_for_data.set()

@dp.message_handler(state=AddShopState.waiting_for_data, content_types=types.ContentTypes.TEXT)
async def add_shop_data(message: types.Message, state: FSMContext):
    try:
        shop_name, bot_link, operator_link, chat_link = [x.strip() for x in message.text.split(",", maxsplit=3)]
    except ValueError:
        await message.reply("Błąd formatu. Podaj dane w formacie:\nNazwa sklepu, link do bota, link do operatora, link do czatu")
        return

    # Dodaj sklep do bazy (bez zdjęcia)
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO shops (shop_name, bot_link, operator_link, chat_link, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (shop_name, bot_link, operator_link, chat_link, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    await state.update_data(shop_name=shop_name)
    await message.reply("Sklep został dodany! Teraz prześlij zdjęcie sklepu jako wiadomość na czacie.")
    await AddShopState.waiting_for_photo.set()

@dp.message_handler(state=AddShopState.waiting_for_photo, content_types=types.ContentTypes.PHOTO)
async def add_shop_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")
    photo = message.photo[-1]
    photo_path = f"photos/{shop_name}.jpg"
    await photo.download(photo_path)

    # Zaktualizuj ścieżkę do zdjęcia w bazie
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE shops SET photo = ? WHERE shop_name = ?", (photo_path, shop_name))
    conn.commit()
    conn.close()

    await message.reply(f"Zdjęcie dla sklepu {shop_name} zostało zapisane i przypisane do sklepu!")
    await state.finish()

@dp.errors_handler()
async def handle_errors(update, exception):
    logging.error(f"Błąd: {exception}")
    return True  # Kontynuuj działanie bota

import yt_dlp

# Słownik do przechowywania postępu playlisty dla każdej grupy
group_playlists = {}

@dp.message_handler(commands=["yt"], chat_type=["group", "supergroup"])
async def yt_voice_playlist(message: types.Message, state: FSMContext):
    args = message.get_args()
    if not args:
        await message.reply("Podaj link do playlisty lub filmu z YouTube. Przykład:\n/yt_voice https://www.youtube.com/playlist?list=...")
        return

    url = args.strip()
    await message.reply("⏳ Pobieram playlistę, proszę czekać...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'voice_%(title)s.%(ext)s',
        'noplaylist': False,
        'quiet': True,
        'extractaudio': True,
        'audioformat': 'mp3',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '64',  # niższa jakość = mniejszy plik
        }],
        'ignoreerrors': True,
        'playlistend': 5,  # max 5 utworów
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Przygotuj listę plików
            if 'entries' in info:
                playlist = []
                for entry in info['entries']:
                    if entry is None:
                        continue
                    audio_file = f"voice_{entry['title']}.mp3"
                    playlist.append({'file': audio_file, 'title': entry.get('title', 'Audio z YouTube')})
            else:
                playlist = [{'file': f"voice_{info['title']}.mp3", 'title': info.get('title', 'Audio z YouTube')}]

        if not playlist:
            await message.reply("Nie udało się pobrać żadnego utworu.")
            return

        # Zapamiętaj playlistę i indeks
        group_playlists[message.chat.id] = {'playlist': playlist, 'index': 0}

        # Wyślij pierwszy utwór jako voice z przyciskiem
        await send_voice_with_next(message.chat.id)
    except Exception as e:
        await message.reply(f"Błąd pobierania audio: {e}")

async def send_voice_with_next(chat_id):
    data = group_playlists.get(chat_id)
    if not data:
        return
    playlist = data['playlist']
    index = data['index']
    if index >= len(playlist):
        await bot.send_message(chat_id, "To już był ostatni utwór z playlisty.")
        return

    audio_file = playlist[index]['file']
    title = playlist[index]['title']

    # Przyciski
    keyboard = InlineKeyboardMarkup()
    if index < len(playlist) - 1:
        keyboard.add(InlineKeyboardButton("⏭️ Następny", callback_data=f"voice_next_{index+1}"))
    keyboard.add(InlineKeyboardButton("⏹️ Stop", callback_data="voice_stop"))
    keyboard.add(InlineKeyboardButton("⏬ Dodaj utwór", callback_data="voice_add"))

    # Wyślij voice
    with open(audio_file, 'rb') as voice:
        await bot.send_voice(chat_id, voice, caption=f"{title}", reply_markup=keyboard)
    os.remove(audio_file)

class AddSongState(StatesGroup):
    waiting_for_song_link = State()

@dp.callback_query_handler(lambda c: c.data == "voice_add")
async def add_song_to_queue(callback_query: types.CallbackQuery, state: FSMContext):
    chat_id = callback_query.message.chat.id
    await bot.send_message(chat_id, "Wyślij link do utworu z YouTube, który chcesz dodać do kolejki.")
    await state.update_data(chat_id=chat_id)
    await AddSongState.waiting_for_song_link.set()

@dp.callback_query_handler(lambda c: c.data == "voice_stop")
async def stop_voice_handler(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    if chat_id in group_playlists:
        del group_playlists[chat_id]
        await callback_query.message.answer("Odtwarzanie zatrzymane.")
    else:
        await callback_query.message.answer("Nie ma aktywnej playlisty do zatrzymania.")
    await callback_query.answer()

@dp.message_handler(state=AddSongState.waiting_for_song_link, content_types=types.ContentTypes.TEXT)
async def process_song_link(message: types.Message, state: FSMContext):
    chat_id = message.chat.id
    url = message.text.strip()
    await message.reply("⏳ Pobieram utwór, proszę czekać...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'voice_%(title)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'extractaudio': True,
        'audioformat': 'mp3',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '64',
        }],
        'ignoreerrors': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_file = f"voice_{info['title']}.mp3"
            new_song = {'file': audio_file, 'title': info.get('title', 'Audio z YouTube')}
        # Dodaj do kolejki
        if chat_id in group_playlists:
            group_playlists[chat_id]['playlist'].append(new_song)
            await message.reply(f"✅ Utwór '{new_song['title']}' został dodany do kolejki.")
        else:
            await message.reply("Brak aktywnej playlisty. Użyj /yt aby rozpocząć nową kolejkę.")
    except Exception as e:
        await message.reply(f"Błąd pobierania audio: {e}")

    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("voice_next_"))
async def next_voice_handler(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    index = int(callback_query.data.split("_")[-1])
    if chat_id in group_playlists:
        group_playlists[chat_id]['index'] = index
        await send_voice_with_next(chat_id)
        await callback_query.answer("Odtwarzam następny utwór.")
    else:
        await callback_query.answer("Brak aktywnej playlisty.", show_alert=True)

@dp.errors_handler(exception=NetworkError)
async def handle_network_error(update, exception):
    logging.warning(f"Problem z połączeniem sieciowym: {exception}")
    return True  # Kontynuuj działanie bota

@dp.message_handler(lambda message: message.text == "💎 VIP")
async def vip_menu_handler(message: types.Message):
    user_id = message.from_user.id
    # Pobierz rolę użytkownika
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or row[0] != "💎 Poszukiwacz Skarbów":
        await message.answer("Opcja dostępna tylko dla rangi 💎VIP💎 oraz Poszukiwacz Skarbów!")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("VIP Czat 1", url="https://t.me/vipczat1"))
    keyboard.add(InlineKeyboardButton("VIP Czat 2", url="https://t.me/vipczat2"))
    await message.answer("Wybierz VIP czat:", reply_markup=keyboard)

@dp.message_handler(lambda m: m.text == "🛒 Marketplace")
async def marketplace_menu(message: types.Message):
    with open("noc3.jpg", "rb") as photo:
        await message.answer_photo(
            photo=photo,
            caption="🛒 *Mini-market Nocna24*",
            parse_mode="Markdown"
        )
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("Dodaj ogłoszenie"), KeyboardButton("Przeglądaj ogłoszenia"))
    kb.row(KeyboardButton("Moje ogłoszenia"), KeyboardButton("Filtruj ogłoszenia"))
    kb.row(KeyboardButton("Powrót do menu"))
    await message.answer("🛍️ Witaj w Marketplace! Wybierz opcję:", reply_markup=kb)

@dp.message_handler(lambda message: message.text == "🔎 Szukaj")
async def search_city_menu(message: types.Message):
    user_id = message.from_user.id
    # Pobierz rangę użytkownika z bazy
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    user_role = row[0] if row else None

    # Sprawdź, czy użytkownik ma odpowiednią rangę
    if user_role not in ("🌒 Nocny", "🌒 Nocna", "💎 Poszukiwacz Skarbów"):
        await message.answer(
            "Ta opcja dostępna jest tylko dla użytkowników z rangą Nocny/Nocna lub wyższą."
        )
        return

    # Jeśli ranga się zgadza, pokaż listę miast
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Katowice", callback_data="miasto_Katowice"))
    keyboard.add(InlineKeyboardButton("Warszawa", callback_data="miasto_Warszawa"))
    await message.answer("Wybierz miasto:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("miasto_"))
async def show_city_shops(callback_query: types.CallbackQuery):
    city = callback_query.data.split("_", 1)[1]
    await bot.send_message(callback_query.from_user.id, f"Wybrałeś miasto: {city}\n(Tu możesz dodać wyświetlanie sklepów z tego miasta)")

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 10, time_window: int = 10):
        super().__init__()
        self.limit = limit
        self.time_window = time_window
        self.users = {}
        self.warned = {}  # user_id: timestamp ostrzeżenia
        self.muted = {}   # user_id: timestamp muta

    async def on_pre_process_update(self, update: Update, data: dict):
        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
            chat_id = update.message.chat.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
            chat_id = update.callback_query.message.chat.id
        else:
            return

        current_time = time.time()

        if user_id not in self.users:
            self.users[user_id] = []

        # Usuń stare żądania spoza okna czasowego
        self.users[user_id] = [t for t in self.users[user_id] if current_time - t < self.time_window]

        # Jeśli użytkownik już jest zmutowany, blokuj wszystko
        if user_id in self.muted and current_time < self.muted[user_id]:
            if update.message:
                await update.message.reply("Zostałeś zablokowany na 24h za spamowanie.")
            elif update.callback_query:
                await update.callback_query.answer("Zostałeś zablokowany na 24h za spamowanie.", show_alert=True)
            return

        if len(self.users[user_id]) >= self.limit:
            # Najpierw ostrzeżenie
            if user_id not in self.warned or current_time - self.warned[user_id] > 60:
                if update.message:
                    await update.message.reply("⚠️ Przestań spamować! Jeśli nie przestaniesz, otrzymasz blokadę na 24h.")
                elif update.callback_query:
                    await update.callback_query.answer("⚠️ Przestań spamować! Jeśli nie przestaniesz, otrzymasz blokadę na 24h.", show_alert=True)
                self.warned[user_id] = current_time
                add_reputation(user_id, -20)  # -20 pkt za ostrzeżenie
            else:
                # Jeśli już był ostrzeżony i dalej spamuje – mute na 24h
                self.muted[user_id] = current_time + 24 * 60 * 60
                if update.message:
                    await update.message.reply("❌ Zostałeś zablokowany na 24h za spamowanie.")
                    try:
                        await update.message.bot.restrict_chat_member(
                            chat_id,
                            user_id,
                            permissions=types.ChatPermissions(can_send_messages=False),
                            until_date=int(current_time + 24 * 60 * 60)
                        )
                        # Wyzeruj reputację przy banie
                        conn = sqlite3.connect("bot_database.db")
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET reputation = 0 WHERE user_id = ?", (user_id,))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                elif update.callback_query:
                    await update.callback_query.answer("❌ Zostałeś zablokowany na 24h za spamowanie.", show_alert=True)
            return

        self.users[user_id].append(current_time)
# Dodaj middleware do dispatchera
dp.middleware.setup(RateLimitMiddleware(limit=10, time_window=10))  # Maksymalnie 5 żądań na 10 sekund
dp.middleware.setup(GhostModeMiddleware())

async def scheduled_user_message():
    hours = [9, 15, 20, 0]
    while True:
        now = datetime.now()
        # Znajdź najbliższą godzinę z listy
        next_times = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in hours]
        next_times = [t if t > now else t + timedelta(days=1) for t in next_times]
        next_run = min(next_times)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        text = text = (
            "🕶️ **Nocna24 nadaje z cienia...**\n\n"
            "🌑 Nowe sklepy się pojawiły. Kilka zniknęło bez śladu.\n"
            "💼 Opinie? Zbieramy. Analizujemy. Odsiewamy syf.\n"
            "📡 Jeśli grasz w grę – graj mądrze. Sprawdź, zanim zaufasz.\n\n"
            "🔗 Linki, kontakty, polecenia –  Wiesz gdzie.\n"
            "🖤 /start 🖤"
        )
         # Wyślij do wszystkich użytkowników
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        for user_id, in users:
            try:
                with open("noc2.jpg", "rb") as photo:
                    await bot.send_photo(user_id, photo=photo, caption=text)
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.warning(f"Nie udało się wysłać wiadomości do użytkownika {user_id}: {e}")
import random

async def daily_good_morning():
    while True:
        now = datetime.now()
        next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        visits = random.randint(600, 1700)
        text = (
            "🌅 Dzień Dobry Nocna!\n"
            f"Ostatniej doby naszego BOTa odwiedzaliście: {visits} razy. Dziękujemy!"
        )
        try:
            await bot.send_message(GROUP_ID, "Treść na grupę")
        except Exception as e:
            logging.warning(f"Nie udało się wysłać porannej wiadomości: {e}")

async def periodic_top3_channel():
    while True:
        await send_top3_shops_to_channel()
        await asyncio.sleep(3 * 60 * 60)  # co 3 godziny

async def periodic_group_message():
    while True:
        text = (
            "🌙 *Nocna24 – przypomnienie*\n"
            "• Sprawdź nowe opinie i rankingi!\n"
            "• Dołącz do czatu: https://t.me/+BR4bxG1tTENkYTk0 \n"
            "• Kanał Nocna_official: https://t.me/nocna_official \n"
            "• BOT: @Nocna24_Bot \n"
            "• Zajrzyj na Marketplace!\n"
            "• Pamiętaj o bezpieczeństwie i czytaj regulamin!"
        )
        try:
            with open("noc2.jpg", "rb") as photo:
                await bot.send_photo(CHANNEL_ID, photo=photo, caption=text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Nie udało się wysłać wiadomości cyklicznej na grupę: {e}")
        await asyncio.sleep(3 * 60 * 60)  # 3 godziny
async def on_startup(dp):
    asyncio.create_task(daily_clicks_report())    
    asyncio.create_task(periodic_top3_channel())
    asyncio.create_task(periodic_group_message())
    asyncio.create_task(daily_good_morning())
    asyncio.create_task(scheduled_user_message())

dp.middleware.setup(UserNameUpdateMiddleware())
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

@dp.message_handler()
async def all_messages_handler(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or message.from_user.username or "Nieznajomy"
    add_message(user_id, user_name)
    # Powitanie tylko przy pierwszej wiadomości
    if get_user_messages_count(user_id) == 1:
        await message.answer(f"Witaj w Nocnej, {user_name}! 🌙")
        add_reputation(user_id, 10)  # +10 pkt za pierwszą wiadomość