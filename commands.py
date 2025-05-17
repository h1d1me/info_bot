from aiogram import Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot

bot = Bot(token="7584466647:AAH-g23V2MY-QtKxWdEqRfQ5VCh-lEKS-04")  # Replace "YOUR_BOT_TOKEN" with your actual bot token
dp = Dispatcher(bot)
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
import sqlite3
from datetime import datetime, timedelta
import asyncio  # Dodano do obsługi opóźnień
import logging  # Import logging module

# Słowniki do przechowywania czasu ostatnich zgłoszeń dla "Zaproponuj Sklep" i "Zaproponuj Zmiany"
last_propose_shop_time = {}
last_propose_changes_time = {}

# Słownik do przechowywania czasu ostatniego zgłoszenia przez użytkownika
last_report_time = {}

class EditOpinionState(StatesGroup):
    waiting_for_opinion = State()
    waiting_for_proposed_change = State()
    waiting_for_broken_link = State()  # Nowy stan dla zgłaszania niedziałających linków
    waiting_for_photo = State()  # Nowy stan dla dodawania zdjęć

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proposed_changes (
            shop_name TEXT,
            bot_link TEXT,
            operator_link TEXT,
            chat_link TEXT
        )
    """)
    conn.commit()
    conn.close()

@dp.message_handler(commands=["start"])
async def start_command(message: types.Message):
    await main_menu(message)

async def help_command(message: types.Message):
    await message.answer("Dostępne komendy:\n/start - Rozpocznij\n/help - Pomoc\n/lista - Lista sklepów")

#async def lista_command(message: types.Message):
 #   keyboard = InlineKeyboardMarkup()
  #  keyboard.add(InlineKeyboardButton("Sklep 1", callback_data="shop_1"))
   # keyboard.add(InlineKeyboardButton("Sklep 2", callback_data="shop_2"))
    #await message.answer("Wybierz sklep:", reply_markup=keyboard)

async def join_us_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup()
 #   keyboard.add(InlineKeyboardButton("Zaproponuj sklep", callback_data="propose_shop"))
    keyboard.add(InlineKeyboardButton("Zaproponuj zmiany", callback_data="propose_changes"))
#    keyboard.add(InlineKeyboardButton("Zgłoś niedziałający link", callback_data="report_broken_link"))
    keyboard.add(InlineKeyboardButton("Powrót do menu", callback_data="back_to_menu"))

    await message.answer(
        "🌟 *Dołącz do Nas!* 🌟\n\n"
        "Dziękujemy za Twoje zaangażowanie! Aby nasz bot mógł się rozwijać i pomagać większej liczbie osób, prosimy o minimum zaangażowania.\n\n"
        "W celu weryfikacji, wystaw opinię w co najmniej jednym ze sklepów, w którym ostatnio robiłeś zakupy.\n\n"
        "Tutaj znajdziesz skarbiec możliwości, w którym możesz zaproponować nowe sklepy, zgłosić zmiany lub problemy. Wybierz jedną z opcji poniżej:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

#async def propose_shop(callback_query: types.CallbackQuery):
 #   await callback_query.message.answer("Podaj nazwę sklepu, opis, link do bota, operatora i czatu w formacie:\nNazwa, Opis, Link do bota, Link do operatora, Link do czatu")
 #   await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_proposed_shop(message: types.Message, state: FSMContext):
    try:
        shop_data = message.text.split(",")
        if len(shop_data) != 5:
            raise ValueError("Nieprawidłowy format danych.")

        shop_name, description, bot_link, operator_link, chat_link = [data.strip() for data in shop_data]

        # Zapisz propozycję do tabeli propozycji zamiast bezpośrednio do głównej listy
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposed_shops (shop_name, description, bot_link, operator_link, chat_link) VALUES (?, ?, ?, ?, ?)",
                       (shop_name, description, bot_link, operator_link, chat_link))
        conn.commit()
        conn.close()

        await message.answer("Dziękujemy za propozycję sklepu! Zostanie ona zweryfikowana przez administratora.")
    except Exception as e:
        await message.answer(f"Wystąpił błąd: {str(e)}. Upewnij się, że dane są w poprawnym formacie.")
    finally:
        await state.finish()

#async def add_new_shop(shop_name, description, bot_link, operator_link, chat_link):
 #   conn = sqlite3.connect("bot_database.db")
  #  cursor = conn.cursor()
   # cursor.execute("INSERT INTO shops (shop_name, description, bot_link, operator_link, chat_link, rating) VALUES (?, ?, ?, ?, ?, ?)",
 #                  (shop_name, description, bot_link, operator_link, chat_link, 5))  # Domyślna ocena 5
  #  conn.commit()
   # conn.close()

async def propose_changes(callback_query: types.CallbackQuery):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"change_{shop_name}"))

    await callback_query.message.answer("Wybierz sklep, dla którego chcesz zaproponować zmiany:", reply_markup=keyboard)

def register_join_us_handlers(dp: Dispatcher):
    @dp.message_handler(lambda message: message.text == "Dołącz do Nas!")
    async def join_us_menu(message: types.Message):
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row(KeyboardButton("Zaproponuj zmiany"))
        keyboard.row(KeyboardButton("Powrót do menu"))
        await message.answer("Wybierz opcję:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("change_"))
async def handle_change_request(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_")[1]
    change_type = "change"  # Przykładowa wartość
    logging.info(f"Ustawiam shop_name: {shop_name}, change_type: {change_type}")
    await state.update_data(shop_name=shop_name, change_type=change_type)
    await callback_query.message.answer(f"Podaj nowe dane dla sklepu {shop_name} w formacie:\nLink do bota, Link do operatora, Link do czatu")
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_change_request(message: types.Message, state: FSMContext):
    try:
        change_data = message.text.split(",")
        if len(change_data) != 3:
            raise ValueError("Nieprawidłowy format danych.")

        bot_link, operator_link, chat_link = [data.strip() for data in change_data]

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        state_data = await state.get_data()
        shop_name = state_data.get("shop_name")

        # Zapisz zmiany do tabeli propozycji zmian zamiast bezpośrednio do głównej listy
        cursor.execute("INSERT INTO proposed_changes (shop_name, bot_link, operator_link, chat_link) VALUES (?, ?, ?, ?)",
                       (shop_name, bot_link, operator_link, chat_link))
        conn.commit()
        conn.close()

        await message.answer("Dziękujemy za zgłoszenie zmian! Zostaną one zweryfikowane przez administratora.")
    except Exception as e:
        await message.answer(f"Wystąpił błąd: {str(e)}. Upewnij się, że dane są w poprawnym formacie.")
    finally:
        await state.finish()

async def report_broken_link(callback_query: types.CallbackQuery):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup()
    for shop_name, in shops:
        keyboard.add(InlineKeyboardButton(shop_name, callback_data=f"report_{shop_name}"))

    await callback_query.message.answer("Wybierz sklep, dla którego chcesz zgłosić niedziałający link:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("report_"))
async def handle_broken_link_report(callback_query: types.CallbackQuery):
    shop_name = callback_query.data.split("_")[1]
    await callback_query.message.answer(f"Podaj szczegóły dotyczące niedziałającego linku dla sklepu {shop_name}.")
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(state=EditOpinionState.waiting_for_opinion, content_types=[types.ContentType.TEXT])
async def receive_broken_link_report(message: types.Message, state: FSMContext):
    try:
        report_details = message.text

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        state_data = await state.get_data()
        shop_name = state_data.get("shop_name")
        cursor.execute("INSERT INTO broken_links (shop_name, details) VALUES (?, ?)", (shop_name, report_details))
        conn.commit()
        conn.close()

        await message.answer("Dziękujemy za zgłoszenie! Administrator zajmie się problemem.")
    except Exception as e:
        await message.answer(f"Wystąpił błąd: {str(e)}. Spróbuj ponownie.")
    finally:
        await state.finish()

async def back_to_main_menu(callback_query: types.CallbackQuery):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("Lista sklepów"))
    keyboard.add(KeyboardButton("🔥 NOCna 🔥"))
    keyboard.add(KeyboardButton("Dołącz do Nas!"))
    keyboard.add(KeyboardButton("Kontakt"))

    await callback_query.message.answer("Powrót do menu głównego:", reply_markup=keyboard)

async def main_menu(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("1. Lista sklepów"))
    keyboard.add(KeyboardButton("2. NOCna i dołącz do nas"))
    keyboard.add(KeyboardButton("3. Opinie, czat i oferty pracy"))
    keyboard.add(KeyboardButton("4. Kontakty"))
    await message.answer("Wybierz opcję z menu głównego:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "1. Lista sklepów")
async def lista_sklepow_handler(message: types.Message):
    # Obsługa opcji Lista sklepów
    await lista_command(message)

@dp.message_handler(lambda message: message.text == "2. NOCna i dołącz do nas")
async def nocna_dolacz_handler(message: types.Message):
    # Obsługa opcji NOCna i dołącz do nas
    await join_us_menu(message)

@dp.message_handler(lambda message: message.text == "3. Opinie, czat i oferty pracy")
async def opinie_czat_praca_handler(message: types.Message):
    # Obsługa opcji Opinie, czat i oferty pracy
    await message.answer("Wybierz jedną z opcji: Opinie, czat lub oferty pracy.")

@dp.message_handler(lambda message: message.text == "4. Kontakty")
async def kontakty_handler(message: types.Message):
    # Obsługa opcji Kontakty
    await message.answer("Skontaktuj się z nami pod adresem: kontakt@example.com")

async def send_message_to_all_users(message_text: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    for user_id, in users:
        try:
            await bot.send_message(user_id, message_text)
            await asyncio.sleep(1)  # Opóźnienie 1 sekundy między wiadomościami
        except Exception as e:
            print(f"Nie udało się wysłać wiadomości do użytkownika {user_id}: {e}")
