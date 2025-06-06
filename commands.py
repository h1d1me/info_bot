from aiogram import Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
from aiogram.exceptions import ChatAdminRequired, UserAdminInvalid
from info_bot import dp, bot
from aiogram.fsm.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
import sqlite3
from datetime import datetime, timedelta
import asyncio  # Dodano do obsługi opóźnień
import logging  # Import logging module
from click_counter import get_user_messages_count, get_all_messages_count

# Define admin user IDs here
ADMIN_IDS = {7572862671}  # Replace with actual Telegram user IDs of admins

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
        CREATE TABLE IF NOT EXISTS warns (
            user_id INTEGER,
            warn_time INTEGER
        )
    """)
    conn.commit()
    conn.close()

async def help_command(message: types.Message):
    await message.answer("Dostępne komendy:\n/start - Rozpocznij\n/help - Pomoc\n/lista - Lista sklepów")

@dp.message_handler(commands=["ban"])
async def ban_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        try:
            user_id = int(message.get_args())
        except:
            await message.reply("Użycie: /ban <user_id> lub odpowiedz na wiadomość użytkownika.")
            return

    try:
        await message.bot.kick_chat_member(message.chat.id, user_id)
        await message.reply(f"Użytkownik {user_id} został zbanowany.")
    except ChatAdminRequired:
        await message.reply("Bot nie ma uprawnień administratora.")
    except UserAdminInvalid:
        await message.reply("Nie można zbanować administratora.")
    except Exception as e:
        await message.reply(f"Błąd: {e}")

@dp.message_handler(commands=["mute"])
async def mute_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        try:
            user_id = int(message.get_args())
        except:
            await message.reply("Użycie: /mute <user_id> lub odpowiedz na wiadomość użytkownika.")
            return

    until_date = datetime.now() + timedelta(hours=1)
    try:
        await message.bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await message.reply(f"Użytkownik {user_id} został wyciszony na 1 godzinę.")
    except ChatAdminRequired:
        await message.reply("Bot nie ma uprawnień administratora.")
    except UserAdminInvalid:
        await message.reply("Nie można wyciszyć administratora.")
    except Exception as e:
        await message.reply(f"Błąd: {e}")

@dp.message_handler(commands=["warn"])
async def warn_user(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    if not message.reply_to_message:
        await message.reply("Użyj /warn odpowiadając na wiadomość użytkownika.")
        return

    user_id = message.reply_to_message.from_user.id

    # Sprawdź, czy użytkownik miał już warn w ciągu ostatnich 7 dni
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    cursor.execute("DELETE FROM warns WHERE warn_time < ?", (week_ago,))
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (user_id,))
    warn_count = cursor.fetchone()[0]

    if warn_count >= 1:
        # Ban za drugi warn w ciągu 7 dni
        try:
            await message.bot.kick_chat_member(message.chat.id, user_id)
            await message.reply(f"Użytkownik {user_id} otrzymał 2 ostrzeżenie w ciągu 7 dni i został zbanowany.")
        except Exception as e:
            await message.reply(f"Błąd przy banowaniu: {e}")
        # Usuń warny po banie
        cursor.execute("DELETE FROM warns WHERE user_id = ?", (user_id,))
        conn.commit()
    else:
        # Dodaj warn
        now = int(datetime.now().timestamp())
        cursor.execute("INSERT INTO warns (user_id, warn_time) VALUES (?, ?)", (user_id, now))
        conn.commit()
        await message.reply(f"Użytkownik {user_id} otrzymał ostrzeżenie! (ważne 7 dni)")
        try:
            await message.bot.send_message(user_id, "Otrzymałeś ostrzeżenie od administratora! Po drugim ostrzeżeniu w 7 dni zostaniesz zbanowany.")
        except Exception:
            pass

    conn.close()

@dp.message_handler(commands=["warns"])
async def check_warns(message: types.Message):
    if not message.reply_to_message:
        await message.reply("Użyj /warns odpowiadając na wiadomość użytkownika.")
        return
    user_id = message.reply_to_message.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
    cursor.execute("DELETE FROM warns WHERE warn_time < ?", (week_ago,))
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (user_id,))
    warn_count = cursor.fetchone()[0]
    conn.close()
    await message.reply(f"Użytkownik {user_id} ma {warn_count} ostrzeżenie(a) z ostatnich 7 dni.")
    
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

@dp.message_handler(commands=["tematid"])
async def show_thread_id(message: types.Message):
    thread_id = getattr(message, "message_thread_id", None)
    if thread_id:
        await message.reply(f"ID tego tematu (thread_id): <code>{thread_id}</code>", parse_mode="HTML")
    else:
        await message.reply("Ta wiadomość nie jest w temacie (wątku) lub Twoja wersja Telegrama nie obsługuje tematów.")

@dp.message_handler(commands=["del"])
async def delete_last_messages(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("Nie masz uprawnień do tej komendy.")
        return

    try:
        count = int(message.get_args())
        if count < 1 or count > 100:
            await message.reply("Podaj liczbę od 1 do 100.")
            return
    except:
        await message.reply("Użycie: /del <liczba>")
        return

    chat_id = message.chat.id
    deleted = 0
    async for msg in message.bot.iter_history(chat_id, limit=count+1):  # +1 żeby usunąć też komendę
        try:
            await msg.delete()
            deleted += 1
        except Exception:
            pass
    await message.reply(f"Usunięto {deleted} wiadomości.")
    
@dp.callback_query_handler(lambda c: c.data.startswith("change_"))
async def handle_change_request(callback_query: types.CallbackQuery, state: FSMContext):
    shop_name = callback_query.data.split("_")[1]
    change_type = "change"  # Przykładowa wartość
    logging.info(f"Ustawiam shop_name: {shop_name}, change_type: {change_type}")
    await state.update_data(shop_name=shop_name, change_type=change_type)
    await callback_query.message.answer(f"Podaj nowe dane dla sklepu {shop_name} w formacie:\nLink do bota, Link do operatora, Link do czatu")
    await EditOpinionState.waiting_for_opinion.set()

@dp.message_handler(commands=["ranking"])
async def ranking_command(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, role, reputation FROM users ORDER BY reputation DESC LIMIT 10")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.reply("Brak użytkowników w rankingu.")
        return

    text = "🏆 *Ranking aktywnych użytkowników:*\n\n"
    for idx, (user_name, role, reputation) in enumerate(users, 1):
        text += f"{idx}. {user_name or 'Anonim'}\n   {role or ''} | {reputation} pkt\n"
    await message.reply(text, parse_mode="Markdown")

@dp.message_handler(commands=["top"])
async def top_shops_command(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.shop_name, IFNULL(AVG(o.rating), 0) AS avg_rating, COUNT(o.rating) as opinie
        FROM shops s
        LEFT JOIN opinions o ON s.shop_name = o.shop_name
        GROUP BY s.shop_name
        HAVING opinie > 0
        ORDER BY avg_rating DESC
        LIMIT 10
    """)
    shops = cursor.fetchall()
    conn.close()

    if not shops:
        await message.reply("Brak ocenionych sklepów.")
        return

    text = "🏆 *Najlepsze sklepy (średnia ocen):*\n\n"
    for idx, (shop_name, avg_rating, opinie) in enumerate(shops, 1):
        text += f"{idx}. {shop_name} – {avg_rating:.2f}⭐ ({opinie} opinii)\n"
    await message.reply(text, parse_mode="Markdown")

@dp.message_handler(commands=["/mojeinfo"])
async def me_command(message: types.Message):
    user_id = message.from_user.id
    user_msgs = get_user_messages_count(user_id)
    all_msgs = get_all_messages_count()
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, role, reputation FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        username, role, reputation = row
        username = username or message.from_user.first_name or "Nieznany"
        # Przykładowe liczenie wiadomości (jeśli masz taką kolumnę)
        try:
            conn = sqlite3.connect("bot_database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,))
            user_msgs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM messages")
            all_msgs = cursor.fetchone()[0]
            conn.close()
        except Exception:
            user_msgs = "—"
            all_msgs = "—"
        text = (
            f"👤 Użytkownik: {username}\n"
            f"🏅 Ranga: {role}\n"
            f"📊 Punkty: {reputation}\n"
            f"Twoje Wiadomości: {user_msgs}\n"
            f"Wiadomości ogólnie: {all_msgs}\n\n"
            f"LINKI:\n"
            f"Zaproś kogoś na czat: https://t.me/+aUofaQMoWFs4Yzdk \n"
            f"Nocna Kanał: https://t.me/nocna_official \n"
            f"Nocna Bot: https://t.me/Nocna24_bot \n"
            f"Kontakt: https://t.me/KiedysMichal"
        )
    else:
        text = "Nie znaleziono Twojego profilu w bazie."
    
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

async def lista_command(message: types.Message):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name FROM shops")
    shops = cursor.fetchall()
    conn.close()

    if shops:
        shop_list = "\n".join([shop[0] for shop in shops])
        await message.answer(f"Lista sklepów:\n{shop_list}")
    else:
        await message.answer("Brak sklepów w bazie danych.")

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
