import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import os
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import json
import asyncio
import logging
from dotenv import load_dotenv
from aiogram.utils.exceptions import NetworkError
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import Update
import time

# Wczytaj zmienne środowiskowe z pliku .env
load_dotenv()

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)

# Token bota
TOKEN = os.getenv("BOT_TOKEN")
# ID administratora
admin_id = 7572862671  # Zamień na rzeczywiste ID administratora
ADMIN_IDS = [7572862671, 7743599256]  # Lista ID administratorów
CHANNEL_ID = "@nocna_official"  # lub np. -1001234567890
# Inicjalizacja bota i dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Utwórz folder "photos", jeśli nie istnieje
if not os.path.exists("photos"):
    os.makedirs("photos")

with open("config.json", "r") as config_file:
    config = json.load(config_file)

bot = Bot(token=TOKEN, timeout=60)  # Ustaw timeout na 60 sekund
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class EditOpinionState(StatesGroup):
    waiting_for_opinion = State()
    waiting_for_proposed_change = State()
    waiting_for_broken_link = State()  # Nowy stan dla zgłaszania niedziałających linków
    waiting_for_photo = State()  # Nowy stan dla dodawania zdjęć

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

def update_shops_table():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Dodaj kolumny, jeśli nie istnieją
    try:
        cursor.execute("ALTER TABLE shops ADD COLUMN bot_link TEXT")
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

    # Przykładowe dane do aktualizacji         ("Lincoln", "https://t.me/LincolnMarketV2_bot", "https://t.me/Lincoln_Opr", "https://t.me/LincolnChat"),
    shops_data = [
        ("Easy Shop", "https://t.me/e_a_s_y_shop_PL_bot", "https://t.me/zz3zz3", "https://t.me/+4WsSJGkfD1w2MTQ5")
    ]

    # Aktualizacja danych w tabeli
    for shop_name, bot_link, operator_link, chat_link in shops_data:
        cursor.execute("""
            UPDATE shops
            SET bot_link = ?, operator_link = ?, chat_link = ?
            WHERE shop_name = ?
        """, (shop_name, bot_link, operator_link, chat_link))

    conn.commit()
    conn.close()

# Wywołaj funkcję, aby zaktualizować dane
update_shops_data()

# Tworzenie klawiatury menu
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("🔥NOCna lista sklepów🔥"))
    keyboard.row(KeyboardButton("Marketplace"))
    keyboard.row(KeyboardButton("Kontakt"), KeyboardButton("Czat"), KeyboardButton("Regulamin"))
    keyboard.row(KeyboardButton("Nowe opinie"), KeyboardButton("Oferty Pracy"))
    return keyboard

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
        SELECT shops.shop_name, IFNULL(AVG(opinions.rating), 0) as avg_rating
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

    try:
        await bot.send_message(CHANNEL_ID, text)
    except Exception as e:
        logging.warning(f"Nie udało się wysłać TOP 3 na kanał: {e}")
@dp.message_handler(commands=["myid"])
async def get_my_id(message: types.Message):
    await message.reply(f"Twoje ID: {message.from_user.id}")

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.full_name or "Anonim"
    
    # Zapisz użytkownika w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, user_name)
        VALUES (?, ?)
    """, (user_id, user_name))
    conn.commit()
    conn.close()

    await message.answer(
        "📜 **Regulamin korzystania z Bota**\n\n"
        "1. **Postanowienia ogólne**\n"
        "1.1. Bot służy do przeglądania listy sklepów oraz dodawania opinii i ocen na temat wybranych sklepów.\n"
        "1.2. Korzystanie z bota oznacza akceptację niniejszego regulaminu.\n"
        "1.3. Administrator zastrzega sobie prawo do modyfikacji regulaminu w dowolnym momencie.\n\n"
        "2. **Dodawanie opinii i zdjęć**\n"
        "2.1. Opinie powinny być kulturalne, rzetelne i oparte na rzeczywistych doświadczeniach.\n"
        "2.2. Zabronione jest dodawanie treści obraźliwych, wulgarnych, dyskryminujących lub naruszających prawo.\n"
        "2.3. Fałszywe opinie, SPAM oraz reklama innych usług/sklepów są zakazane.\n"
        "2.4. Użytkownik może dodać zdjęcie do opinii, pod warunkiem że ma do niego prawa i nie narusza ono zasad społeczności.\n\n"
        "3. **Odpowiedzialność**\n"
        "3.1. Administrator bota nie ponosi odpowiedzialności za treści publikowane przez użytkowników.\n"
        "3.2. Opinie wyrażone w bocie są prywatnymi opiniami użytkowników i nie są stanowiskiem administratora bota.\n"
        "3.3. W przypadku naruszenia regulaminu, administrator ma prawo do usunięcia opinii oraz zablokowania użytkownika.\n\n"
        "Kliknij 'Akceptuję', aby przejść dalej.",
        parse_mode="Markdown"
    )
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Akceptuję >>>", callback_data="accept_rules"))
    await message.answer("Kliknij poniżej, aby zaakceptować regulamin:", reply_markup=keyboard)

from aiogram import types

@dp.message_handler(content_types=[types.ContentType.NEW_CHAT_MEMBERS, types.ContentType.LEFT_CHAT_MEMBER, types.ContentType.PINNED_MESSAGE])
async def delete_system_messages(message: types.Message):
    try:
        await message.delete()
    except Exception as e:
        pass  # np. brak uprawnień

@dp.message_handler(lambda message: message.text == "🔥NOCna lista sklepów🔥")
async def show_shops(message: types.Message):
    username = message.from_user.username or "Anonim"  # Pobierz nazwę użytkownika lub ustaw "Anonim", jeśli brak
    logging.info(f"Użytkownik @{username} aktualnie przegląda listę sklepów.")  # Zapisz log w konsoli

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.shop_name, 
               IFNULL(AVG(o.rating), 0) AS avg_rating
        FROM shops s
        LEFT JOIN opinions o ON s.shop_name = o.shop_name
        GROUP BY s.shop_name
        ORDER BY avg_rating DESC
    """)
    shops = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    for i in range(0, len(shops), 2):
        row = []
        for shop in shops[i:i+2]:
            shop_name, avg_rating = shop
            row.append(InlineKeyboardButton(f"{shop_name} ({avg_rating:.1f} ⭐)", callback_data=f"shop_{shop_name}"))
        keyboard.row(*row)

    await message.answer("Wybierz sklep:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
async def rate_shop(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_", 1)[1]  # Pobierz nazwę sklepu
    keyboard = InlineKeyboardMarkup()
    for i in range(1, 11):
        keyboard.add(InlineKeyboardButton(f"{i} ⭐", callback_data=f"set_rating|{shop_name}|{i}"))
    await bot.send_message(callback_query.from_user.id, f"Wybierz ocenę dla sklepu {shop_name}:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("set_rating|"))
async def set_rating(callback_query: types.CallbackQuery):
    data_parts = callback_query.data.split("|")
    if len(data_parts) != 3:
        await bot.send_message(callback_query.from_user.id, "Wystąpił błąd podczas przetwarzania oceny.")
        return

    _, shop_name, rating = data_parts
    user_id = callback_query.from_user.id

    try:
        rating = int(rating)
        if rating < 1 or rating > 10:
            await callback_query.message.answer("Ocena musi być w zakresie od 1 do 10.")
            return
    except ValueError:
        await bot.send_message(callback_query.from_user.id, "Podano nieprawidłową ocenę. Wybierz liczbę od 1 do 10.")
        return

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()

    # Sprawdź, czy użytkownik już ocenił sklep
    cursor.execute("SELECT rating FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_rating = cursor.fetchone()

    if existing_rating:
        # Jeśli istnieje, zaktualizuj ocenę
        cursor.execute("""
            UPDATE opinions SET rating = ? WHERE user_id = ? AND shop_name = ?
        """, (rating, user_id, shop_name))
        message = f"Twoja ocena została zaktualizowana na {rating} ⭐ dla sklepu {shop_name}."
    else:
        # Jeśli nie istnieje, wstaw nową ocenę
        cursor.execute("""
            INSERT INTO opinions (user_id, shop_name, rating)
            VALUES (?, ?, ?)
        """, (user_id, shop_name, rating))
        message = f"Twoja ocena {rating} ⭐ została zapisana dla sklepu {shop_name}."

    conn.commit()
    conn.close()

    await bot.send_message(callback_query.from_user.id, message)

@dp.callback_query_handler(lambda c: c.data.startswith("shop_"))
async def shop_details(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_")[1]

    # Pobierz szczegóły sklepu z bazy danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT photo, bot_link, operator_link, chat_link FROM shops WHERE shop_name = ?", (shop_name,))
    shop_info = cursor.fetchone()
    conn.close()

    if shop_info:
        photo, bot_link, operator_link, chat_link = shop_info
    else:
        await bot.send_message(callback_query.from_user.id, "Nie znaleziono szczegółów dla tego sklepu.")
        return

    # Wyślij zdjęcie, jeśli istnieje
    if photo and os.path.exists(photo):
        with open(photo, 'rb') as photo_file:
            await bot.send_photo(callback_query.from_user.id, photo=photo_file, caption=f"🏬 {shop_name}")
    else:
        await bot.send_message(callback_query.from_user.id, f"🏬 {shop_name}\n\nBrak zdjęcia dla tego sklepu.")

    # Przygotowanie klawiatury z przyciskami
    keyboard = InlineKeyboardMarkup()
    if bot_link:
        keyboard.add(InlineKeyboardButton("BOT", url=bot_link))
    if operator_link:
        keyboard.add(InlineKeyboardButton("OPERATOR", url=operator_link))
    if chat_link:
        keyboard.add(InlineKeyboardButton("CZAT", url=chat_link))
    keyboard.add(InlineKeyboardButton("Opinie", callback_data=f"opinie_{shop_name}"))
    keyboard.add(InlineKeyboardButton("Wróć do menu", callback_data="menu"))

    await bot.send_message(callback_query.from_user.id, "Wybierz opcję:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("edit_photo_"))
async def edit_photo(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_")[2]
    await bot.send_message(callback_query.from_user.id, f"Prześlij nowe zdjęcie dla sklepu {shop_name}.")
    
    # Zapisz nazwę sklepu w stanie użytkownika
    state = dp.current_state(user=callback_query.from_user.id)
    await state.update_data(shop_name=shop_name)
    await EditOpinionState.waiting_for_opinion.set()

@dp.callback_query_handler(lambda c: c.data.startswith("dodaj_opinie_"))
async def add_opinion(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_")[2]
    await bot.send_message(
        callback_query.from_user.id,
        f"Podaj swoją opinię o sklepie {shop_name}. Możesz również przesłać zdjęcie z opisem."
    )

    # Zapisz nazwę sklepu w stanie użytkownika
    state = dp.current_state(user=callback_query.from_user.id)
    await state.update_data(shop_name=shop_name)

    # Ustaw stan oczekiwania na opinię
    await EditOpinionState.waiting_for_opinion.set()

@dp.callback_query_handler(lambda c: c.data.startswith("opinie_"))
async def show_opinions(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_")[1]
    
    # Pobierz opinie o sklepie
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, opinion, photo FROM opinions WHERE shop_name = ?", (shop_name,))
    opinions = cursor.fetchall()
    conn.close()

    # Przygotowanie treści opinii
    if opinions:
        for user_name, opinion, photo in opinions:
            response = f"👤 {user_name}\n💬 {opinion}"
            if photo:
                # Wyślij zdjęcie z opinią
                try:
                    with open(photo, 'rb') as photo_file:
                        await bot.send_photo(callback_query.from_user.id, photo=photo_file, caption=response)
                except FileNotFoundError:
                    await bot.send_message(callback_query.from_user.id, f"{response}\n\n⚠️ Zdjęcie nie zostało znalezione.")
            else:
                # Wyślij tylko tekst opinii
                await bot.send_message(callback_query.from_user.id, response)
    else:
        await bot.send_message(callback_query.from_user.id, "Brak opinii o tym sklepie.")

    # Przygotowanie klawiatury
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Dodaj opinię", callback_data=f"dodaj_opinie_{shop_name}"))
    #keyboard.add(InlineKeyboardButton("Edytuj opinię", callback_data=f"edit_opinion_{shop_name}"))
    keyboard.add(InlineKeyboardButton("Oceń sklep", callback_data=f"rate_{shop_name}"))
    keyboard.add(InlineKeyboardButton("Wróć do menu", callback_data="menu"))

    # Wyślij klawiaturę
    await bot.send_message(callback_query.from_user.id, "Wybierz opcję:", reply_markup=keyboard)

async def save_opinion(message: types.Message, shop_name):
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username or "Anonim"
    text = message.caption if message.caption else message.text if message.text else "Brak tekstu"
    photo_path = None

    # Jeśli użytkownik przesłał zdjęcie, zapisz je na dysku
    if message.photo:
        photo = message.photo[-1]  # Pobierz zdjęcie w najwyższej rozdzielczości
        photo_path = f"photos/{user_id}_{shop_name}.jpg"
        await photo.download(photo_path)

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT opinion FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_opinion = cursor.fetchone()

    if existing_opinion:
        # Zaktualizuj istniejącą opinię
        cursor.execute("""
            UPDATE opinions
            SET opinion = ?, photo = ?
            WHERE user_id = ? AND shop_name = ?
        """, (text, photo_path, user_id, shop_name))
        await message.answer("Twoja opinia została zaktualizowana.")
    else:
        # Dodaj nową opinię
        cursor.execute("""
            INSERT INTO opinions (user_id, shop_name, opinion, user_name, photo)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, shop_name, text, user_name, photo_path))
        await message.answer("Twoja opinia została zapisana.")
    
    conn.commit()
    conn.close()

#@dp.callback_query_handler(lambda c: c.data.startswith("edit_opinion_"))
#async def edit_opinion(callback_query: types.CallbackQuery, state: FSMContext):
#    shop_name = callback_query.data.split("_")[2]
#    await state.update_data(shop_name=shop_name)  # Zapisz nazwę sklepu w stanie
 #   await bot.send_message(callback_query.from_user.id, f"Podaj nową opinię dla sklepu {shop_name}:")
  #  await EditOpinionState.waiting_for_opinion.set()  # Ustaw stan oczekiwania na nową opinię

@dp.callback_query_handler(lambda c: c.data.startswith("edit_"))
async def edit_link(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    # Sprawdź, czy użytkownik jest administratorem
    if user_id not in ADMIN_IDS:  # Lista ID administratorów
        await bot.send_message(callback_query.from_user.id, "Nie masz uprawnień do edycji linków.")
        return

    #action, shop_name = callback_query.data.split("_", 2)[1:]
    #await state.update_data(shop_name=shop_name, action=action)  # Zapisz nazwę sklepu i akcję w stanie
    #await bot.send_message(callback_query.from_user.id, f"Podaj nowy link dla {action.upper()} sklepu {shop_name}:")
    #await EditOpinionState.waiting_for_opinion.set()  # Ustaw stan oczekiwania na nowy link

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT, types.ContentType.PHOTO])
async def receive_opinion(message: types.Message, state: FSMContext):
    # Pobierz dane ze stanu
    data = await state.get_data()
    shop_name = data.get("shop_name")
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username or "Anonim"
    text = message.caption if message.caption else message.text if message.text else "Brak tekstu"
    photo_path = None

    # Jeśli użytkownik przesłał zdjęcie, zapisz je na dysku
    if message.photo:
        photo = message.photo[-1]  # Pobierz zdjęcie w najwyższej rozdzielczości
        photo_path = f"photos/{user_id}_{shop_name}.jpg"
        await photo.download(photo_path)

    # Zapisz opinię w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT opinion FROM opinions WHERE user_id = ? AND shop_name = ?", (user_id, shop_name))
    existing_opinion = cursor.fetchone()

    if existing_opinion:
        # Zaktualizuj istniejącą opinię
        cursor.execute("""
            UPDATE opinions
            SET opinion = ?, photo = ?
            WHERE user_id = ? AND shop_name = ?
        """, (text, photo_path, user_id, shop_name))
        await message.answer("Twoja opinia została zaktualizowana.")
    else:
        # Dodaj nową opinię
        cursor.execute("""
            INSERT INTO opinions (user_id, shop_name, opinion, user_name, photo)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, shop_name, text, user_name, photo_path))
        await message.answer("Twoja opinia została zapisana.")

    conn.commit()
    conn.close()

    # Zakończ stan
    await state.finish()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def save_new_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")
    action = data.get("action")  # Może być "bot", "operator" lub "chat"
    new_link = message.text.strip()

    # Sprawdź, czy link jest poprawny
    if not new_link.startswith("http"):
        await message.answer("Podano nieprawidłowy link. Upewnij się, że zaczyna się od 'http' lub 'https'.")
        return

    # Zapisz nowy link w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    column_name = f"{action}_link"  # Wybierz odpowiednią kolumnę (bot_link, operator_link, chat_link)
    cursor.execute(f"UPDATE shops SET {column_name} = ? WHERE shop_name = ?", (new_link, shop_name))
    conn.commit()
    conn.close()

    await message.answer(f"Link dla {action.upper()} sklepu {shop_name} został zaktualizowany na:\n{new_link}")
    await state.finish()  # Zakończ stan

@dp.message_handler(state=EditOpinionState.waiting_for_photo, content_types=[types.ContentType.PHOTO])
async def save_shop_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")

    # Pobierz zdjęcie i zapisz je na dysku
    photo = message.photo[-1]  # Najwyższa rozdzielczość
    photo_path = f"photos/{shop_name}.jpg"
    await photo.download(photo_path)

    # Zapisz ścieżkę do zdjęcia w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE shops
        SET photo = ?
        WHERE shop_name = ?
    """, (photo_path, shop_name))
    conn.commit()
    conn.close()

    await message.reply(f"Zdjęcie dla sklepu {shop_name} zostało zapisane.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "Zaproponuj sklep")
async def propose_shop(message: types.Message):
    await message.answer("Podaj nazwę sklepu, który chciałbyś zaproponować:")
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_proposed_shop(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username or "Anonim"
    proposed_shop = message.text

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO proposed_shops (user_id, user_name, shop_name) VALUES (?, ?, ?)", (user_id, user_name, proposed_shop))
    conn.commit()
    conn.close()

    # Wyślij powiadomienie do admina
    admin_id = 7572862671  # Zamień na ID admina
    await bot.send_message(admin_id, f"📢 Nowa propozycja sklepu od @{user_name}:\n\n{proposed_shop}")

    await message.answer("Dziękujemy za Twoją propozycję sklepu! Zostanie ona rozpatrzona przez administratora.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "Zaproponuj zmiany")
async def propose_changes(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"propose_change_{shop_name}"))

    await message.answer("Wybierz sklep, dla którego chcesz zaproponować zmiany:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("propose_change_"))
async def handle_propose_change(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_", 2)[2]
    await state.update_data(shop_name=shop_name)

    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Bot", callback_data="change_bot"))
    keyboard.add(InlineKeyboardButton("Operator", callback_data="change_operator"))
    keyboard.add(InlineKeyboardButton("Czat", callback_data="change_chat"))

    await bot.send_message(callback_query.from_user.id, f"Czego zmianę chcesz zaproponować dla sklepu {shop_name}?", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("approve_change") or c.data.startswith("reject_change"))
async def handle_change_decision(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split("|")[0]  # "approve_change" lub "reject_change"
    data = await state.get_data()
    shop_name = data.get("shop_name")
    change_type = data.get("change_type")
    new_link = data.get("new_link")

    logging.info(f"Odczytano dane ze stanu FSM: {data}")  # Loguj wszystkie dane

    if not change_type:
        logging.error("change_type jest None!")
        await callback_query.message.edit_text("❌ Wystąpił błąd: brak typu zmiany.")
        return

    valid_columns = {
        "bot": "bot_link",
        "operator": "operator_link",
        "chat": "chat_link"
    }
    column_name = valid_columns.get(change_type)

    if not column_name:
        await callback_query.message.edit_text("❌ Nieprawidłowy typ zmiany.")
        return

    if action == "approve_change":
        # Zatwierdź zmianę i zaktualizuj bazę danych
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE shops SET {column_name} = ? WHERE shop_name = ?", (new_link, shop_name))
            conn.commit()
            await callback_query.message.edit_text(
                f"✅ Zmiana dla sklepu {shop_name} została zatwierdzona.\n"
                f"🔹 Typ zmiany: {change_type.capitalize()}\n"
                f"🔗 Nowy link: {new_link}"
            )
        except sqlite3.OperationalError as e:
            logging.error(f"Błąd SQL: {e}")
            await callback_query.message.edit_text("❌ Wystąpił błąd podczas aktualizacji bazy danych.")
        finally:
            conn.close()
    elif action == "reject_change":
        # Odrzuć zmianę
        await callback_query.message.edit_text(
            f"❌ Zmiana dla sklepu {shop_name} została odrzucona.\n"
            f"🔹 Typ zmiany: {change_type.capitalize()}\n"
            f"🔗 Proponowany link: {new_link}"
        )

@dp.callback_query_handler(lambda c: c.data.startswith("change_"))
async def handle_change_request(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_")[1]
    await callback_query.message.answer(f"Podaj nowe dane dla sklepu {shop_name} w formacie:\nLink do bota, Link do operatora, Link do czatu")
    await state.update_data(shop_name=shop_name)
    await EditOpinionState.waiting_for_proposed_change.set()  # Ustaw nowy stan
    
@dp.message_handler(state=EditOpinionState.waiting_for_proposed_change, content_types=[types.ContentType.TEXT])
async def receive_proposed_change(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")
    change_type = data.get("change_type")
    new_link = message.text.strip()

    # Sprawdź, czy link jest poprawny
    if not new_link.startswith("http"):
        await message.answer("Podano nieprawidłowy link. Upewnij się, że zaczyna się od 'http' lub 'https'.")
        return

    # Zapisz dane w stanie FSM
    await state.update_data(shop_name=shop_name, change_type=change_type, new_link=new_link)

    # Przygotuj klawiaturę dla administratora
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Tak", callback_data=f"approve_change|{change_type}"),
        InlineKeyboardButton("❌ Nie", callback_data=f"reject_change|{change_type}")
    )

    # Wyślij zgłoszenie do wszystkich administratorów
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📢 Propozycja zmiany dla sklepu {shop_name}:\n"
                f"🔹 Typ zmiany: {change_type.capitalize()}\n"
                f"🔗 Nowy link: {new_link}\n\n"
                f"Czy zatwierdzić tę zmianę?",
                reply_markup=keyboard
            )
            logging.info(f"Zgłoszenie zostało wysłane do administratora (ID: {admin_id}).")
        except Exception as e:
            logging.error(f"Nie udało się wysłać zgłoszenia do administratora (ID: {admin_id}): {e}")

    # Potwierdzenie dla użytkownika
    await message.answer("Dziękujemy za zgłoszenie! Zostanie ono rozpatrzone przez administratora.")
    await state.finish()

async def process_shop_change(state):
    data = await state.get_data()
    shop_name = data.get("shop_name", "Nieznany sklep")
    admin_id = 7572862671  # Replace with the actual admin ID
    logging.info(f"Zgłoszenie zmiany dla sklepu {shop_name} zostało wysłane do administratora (ID: {admin_id}).")
# Call this function where necessary
# await process_shop_change(state)

@dp.message_handler(lambda message: message.text == "Zgłoś niedziałający link")
async def report_broken_link(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"report_link_{shop_name}"))

    await message.answer("Wybierz sklep, dla którego chcesz zgłosić niedziałający link:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("report_link_"))
async def handle_report_link(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_", 2)[2]
    await bot.send_message(callback_query.from_user.id, f"Podaj szczegóły dotyczące niedziałającego linku dla sklepu {shop_name}:")
    await EditOpinionState.waiting_for_broken_link.set()

@dp.message_handler(state=EditOpinionState.waiting_for_broken_link, content_types=[types.ContentType.TEXT])
async def receive_broken_link_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name", "Nieznany sklep")
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username or "Anonim"
    report_details = message.text

    # Wyślij powiadomienie do admina
    admin_id = 7572862671  # Zamień na ID admina
    await bot.send_message(admin_id, f"📢 Zgłoszenie niedziałającego linku dla sklepu {shop_name} od @{user_name}:\n\n{report_details}")

    await message.answer("Dziękujemy za zgłoszenie! Zostanie ono rozpatrzone przez administratora.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "Dołącz do Nas!")
async def join_us_menu(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("Zaproponuj zmiany"), KeyboardButton("Zaproponuj sklep"))
    keyboard.row(KeyboardButton("Zgłoś niedziałający link"))
    keyboard.row(KeyboardButton("Powrót do menu"))
    await message.answer("Wybierz opcję:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "Powrót do menu")
async def go_to_main_menu(message: types.Message):
    await message.answer("Wybierz opcję:", reply_markup=main_menu())

@dp.callback_query_handler(lambda c: c.data == "menu")
async def go_to_menu(callback_query: types.CallbackQuery):
    await bot.send_message(callback_query.from_user.id, "Wybierz opcję:", reply_markup=main_menu())

@dp.message_handler(lambda message: message.text == "Czat")
async def chat_link(message: types.Message):
    # Automatyczne otwarcie czatu i wysłanie /start
    await bot.send_message(message.chat.id, "https://t.me/+xOnw-BVT1U42NGNk")

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

@dp.callback_query_handler(lambda c: c.data == "show_rules")
async def show_rules(callback_query: types.CallbackQuery):
    # Wyświetl regulamin
    await bot.send_message(
        callback_query.from_user.id,
        "📜 **Regulamin korzystania z Bota**\n\n"
        "1. **Postanowienia ogólne**\n"
        "1.1. Bot służy do przeglądania listy sklepów oraz dodawania opinii i ocen na temat wybranych sklepów.\n"
        "1.2. Korzystanie z bota oznacza akceptację niniejszego regulaminu.\n"
        "1.3. Administrator zastrzega sobie prawo do modyfikacji regulaminu w dowolnym momencie.\n\n"
        "2. **Dodawanie opinii i zdjęć**\n"
        "2.1. Opinie powinny być kulturalne, rzetelne i oparte na rzeczywistych doświadczeniach.\n"
        "2.2. Zabronione jest dodawanie treści obraźliwych, wulgarnych, dyskryminujących lub naruszających prawo.\n"
        "2.3. Fałszywe opinie, SPAM oraz reklama innych usług/sklepów są zakazane.\n"
        "2.4. Użytkownik może dodać zdjęcie do opinii, pod warunkiem że ma do niego prawa i nie narusza ono zasad społeczności.\n\n"
        "3. **Odpowiedzialność**\n"
        "3.1. Administrator bota nie ponosi odpowiedzialności za treści publikowane przez użytkowników.\n"
        "3.2. Opinie wyrażone w bocie są prywatnymi opiniami użytkowników i nie są stanowiskiem administratora bota.\n"
        "3.3. W przypadku naruszenia regulaminu, administrator ma prawo do usunięcia opinii oraz zablokowania użytkownika.\n\n"
        "4. **Uczciwość ocen i zakaz manipulacji**\n"
        "4.1. Bot jest neutralny i nie zachęca do zakupów w żadnym sklepie.\n"
        "4.2. Wszystkie informacje o sklepach mają charakter informacyjny i nie są ofertą handlową.\n"
        "4.3. Zakazane jest manipulowanie ocenami – zarówno sztuczne podbijanie ocen sklepu, jak i celowe ich zaniżanie (np. w celu zaszkodzenia konkurencji).\n"
        "4.4. Używanie wielu kont do poprawy lub pogorszenia ocen jest surowo zabronione.\n"
        "4.5. Administrator zastrzega sobie prawo do blokowania użytkowników podejrzewanych o nieuczciwe działania oraz usuwania podejrzanych ocen bez podania przyczyny.\n\n"
        "5. **Kontakt i zgłaszanie naruszeń**\n"
        "5.1. Jeśli zauważysz treści naruszające regulamin, skontaktuj się z administratorem bota.\n"
        "5.2. Administrator ma prawo do moderacji i usuwania opinii według własnego uznania.\n\n"
        "6. **Ograniczenia zgłoszeń**\n"
        "6.1. Możesz zgłaszać propozycje sklepów, zmiany lub niedziałające linki tylko raz na 3 godziny.\n"
        "6.2. Administrator zastrzega sobie prawo do odrzucenia zgłoszeń niezgodnych z zasadami.\n\n"
        "Kliknij 'Akceptuję', aby przejść dalej."
    )
    # Dodaj przycisk "Akceptuję"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Akceptuję >>>", callback_data="accept_rules"))
    await bot.send_message(callback_query.from_user.id, "Kliknij poniżej, aby zaakceptować regulamin:", reply_markup=keyboard)

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
        callback_query.from_user.id,
        "Dziękujemy za zaakceptowanie regulaminu! Możesz teraz korzystać z bota.",
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


@dp.message_handler(lambda message: message.text == "Kontakt")
async def contact(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Rozpocznij rozmowę", url="https://t.me/N0cna"))
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
    if message.from_user.id not in [7572862671, 7743599256]:  # Zamień na swoje ID administratorów
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
    if message.from_user.id not in [7572862671, 7743599256]:  # Zamień na swoje ID administratorów
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
    if message.from_user.id not in [7572862671, 7743599256]:  # Zamień na swoje ID administratorów
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

async def is_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.is_chat_admin()

@dp.message_handler(commands=["broadcast"])
async def broadcast_message(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in [7572862671, 7743599256]:  # Lista ID administratorów
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

@dp.message_handler(lambda message: message.text == "Oferty Pracy")
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

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_job_opinion(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username or "Anonim"
    opinion = message.text

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO job_opinions (user_id, user_name, opinion) VALUES (?, ?, ?)", (user_id, user_name, opinion))
    conn.commit()
    conn.close()

    await message.answer("Dziękujemy za podzielenie się swoją opinią o pracy!")
    await state.finish()

@dp.message_handler(commands=["update_links"])
async def update_links(message: types.Message):
    # Sprawdź, czy użytkownik jest administratorem
    if message.from_user.id not in [7572862671, 7743599256]:  # Zamień na swoje ID administratorów
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

from aiogram.dispatcher.filters.state import State, StatesGroup

class AddShopState(StatesGroup):
    waiting_for_data = State()
    waiting_for_photo = State()

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
        INSERT OR IGNORE INTO shops (shop_name, bot_link, operator_link, chat_link)
        VALUES (?, ?, ?, ?)
    """, (shop_name, bot_link, operator_link, chat_link))
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

@dp.message_handler(state=EditOpinionState.waiting_for_photo, content_types=[types.ContentType.PHOTO])
async def save_shop_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    shop_name = data.get("shop_name")

    # Pobierz zdjęcie i zapisz je na dysku
    photo = message.photo[-1]  # Najwyższa rozdzielczość
    photo_path = f"photos/{shop_name}.jpg"
    await photo.download(photo_path)

    # Zapisz ścieżkę do zdjęcia w bazie danych
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE shops
        SET photo = ?
        WHERE shop_name = ?
    """, (photo_path, shop_name))
    conn.commit()
    conn.close()

    await message.reply(f"Zdjęcie dla sklepu {shop_name} zostało zapisane.")
    await state.finish()

@dp.errors_handler()
async def handle_errors(update, exception):
    logging.error(f"Błąd: {exception}")
    return True  # Kontynuuj działanie bota

import yt_dlp

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Słownik do przechowywania postępu playlisty dla każdej grupy
group_playlists = {}

@dp.message_handler(commands=["yt_voice"], chat_type=["group", "supergroup"])
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

    # Wyślij voice
    with open(audio_file, 'rb') as voice:
        await bot.send_voice(chat_id, voice, caption=f"{title}", reply_markup=keyboard)
    os.remove(audio_file)

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

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: int = 10, time_window: int = 10):
        super().__init__()
        self.limit = limit
        self.time_window = time_window
        self.users = {}

    async def on_pre_process_update(self, update: Update, data: dict):
        # Sprawdź, czy update zawiera message lub callback_query
        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id
        else:
            # Jeśli brak message i callback_query, pomiń update
            return

        current_time = time.time()

        if user_id not in self.users:
            self.users[user_id] = []

        # Usuń stare żądania spoza okna czasowego
        self.users[user_id] = [t for t in self.users[user_id] if current_time - t < self.time_window]

        if len(self.users[user_id]) >= self.limit:
            # Wyślij wiadomość o przekroczeniu limitu
            if update.message:
                await update.message.reply("Zbyt wiele żądań. Spróbuj ponownie później.")
            elif update.callback_query:
                await update.callback_query.answer("Zbyt wiele żądań. Spróbuj ponownie później.", show_alert=True)
            return

        self.users[user_id].append(current_time)

# Dodaj middleware do dispatchera
dp.middleware.setup(RateLimitMiddleware(limit=10, time_window=10))  # Maksymalnie 5 żądań na 10 sekund

async def periodic_top3_channel():
    while True:
        await send_top3_shops_to_channel()
        await asyncio.sleep(3 * 60 * 60)  # 3 godziny

async def on_startup(dp):
    asyncio.create_task(periodic_top3_channel())

from marketplace import register_marketplace_handlers
register_marketplace_handlers(dp)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
