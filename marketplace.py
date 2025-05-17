import os
import sqlite3
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime, timedelta

MARKETPLACE_PHOTOS = "marketplace_photos"
if not os.path.exists(MARKETPLACE_PHOTOS):
    os.makedirs(MARKETPLACE_PHOTOS)

ADMIN_IDS = [7572862671, 7743599256]  # Uzupełnij swoimi ID

class MarketplaceState(StatesGroup):
    choosing_type = State()
    entering_title = State()
    entering_description = State()
    entering_price = State()
    entering_location = State()
    choosing_transaction = State()
    uploading_photos = State()
    choosing_safe_deal = State()
    confirming = State()

# --- 1. Filtrowanie i wyszukiwanie ogłoszeń ---
class FilterState(StatesGroup):
    choosing_type = State()
    entering_location = State()
    entering_phrase = State()

    # Możesz dodać kolejne stany jeśli chcesz rozbudować filtr

def init_marketplace_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marketplace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            offer_type TEXT,
            title TEXT,
            description TEXT,
            price TEXT,
            location TEXT,
            transaction_type TEXT,
            photo1 TEXT,
            photo2 TEXT,
            photo3 TEXT,
            safe_deal INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_marketplace_db()

def register_marketplace_handlers(dp: Dispatcher):

    @dp.message_handler(lambda m: m.text == "Marketplace")
    async def marketplace_menu(message: types.Message):
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row(KeyboardButton("Dodaj ogłoszenie"), KeyboardButton("Przeglądaj ogłoszenia"))
        kb.row(KeyboardButton("Moje ogłoszenia"), KeyboardButton("Filtruj ogłoszenia"))  # Dodany przycisk
        kb.row(KeyboardButton("Powrót do menu"))
        await message.answer("🛍️ Witaj w Marketplace! Wybierz opcję:", reply_markup=kb)

    @dp.message_handler(lambda m: m.text == "Dodaj ogłoszenie")
    async def add_offer_start(message: types.Message, state: FSMContext):
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Sprzedam", callback_data="offer_type_sprzedam"),
            InlineKeyboardButton("Kupię", callback_data="offer_type_kupie"),
            InlineKeyboardButton("Zamienię", callback_data="offer_type_zamienie")
        )
        await message.answer("Wybierz typ ogłoszenia:", reply_markup=kb)
        await MarketplaceState.choosing_type.set()

    @dp.callback_query_handler(lambda c: c.data.startswith("offer_type_"), state=MarketplaceState.choosing_type)
    async def offer_type_chosen(callback_query: types.CallbackQuery, state: FSMContext):
        offer_type = callback_query.data.split("_")[2]
        await state.update_data(offer_type=offer_type)
        await callback_query.message.answer("Podaj tytuł ogłoszenia (np. 'iPhone 12 128GB'):")
        await MarketplaceState.entering_title.set()
        await callback_query.answer()

    @dp.message_handler(state=MarketplaceState.entering_title, content_types=types.ContentTypes.TEXT)
    async def enter_title(message: types.Message, state: FSMContext):
        await state.update_data(title=message.text)
        await message.answer("Opisz przedmiot lub czego szukasz:")
        await MarketplaceState.entering_description.set()

    @dp.message_handler(state=MarketplaceState.entering_description, content_types=types.ContentTypes.TEXT)
    async def enter_description(message: types.Message, state: FSMContext):
        await state.update_data(description=message.text)
        await message.answer("Podaj cenę (lub wpisz 'do negocjacji', 'wymiana na...', itp.):")
        await MarketplaceState.entering_price.set()

    @dp.message_handler(state=MarketplaceState.entering_price, content_types=types.ContentTypes.TEXT)
    async def enter_price(message: types.Message, state: FSMContext):
        await state.update_data(price=message.text)
        await message.answer("Podaj miejscowość:")
        await MarketplaceState.entering_location.set()

    @dp.message_handler(state=MarketplaceState.entering_location, content_types=types.ContentTypes.TEXT)
    async def enter_location(message: types.Message, state: FSMContext):
        await state.update_data(location=message.text)
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Face 2 Face", callback_data="trans_face2face"),
            InlineKeyboardButton("Drop/Kopanie", callback_data="trans_drop"),
            InlineKeyboardButton("Wysyłka", callback_data="trans_wysylka"),
            InlineKeyboardButton("Dostawa pod adres", callback_data="trans_dostawa")
        )
        await message.answer("Wybierz sposób realizacji transakcji:", reply_markup=kb)
        await MarketplaceState.choosing_transaction.set()

    @dp.callback_query_handler(lambda c: c.data.startswith("trans_"), state=MarketplaceState.choosing_transaction)
    async def transaction_chosen(callback_query: types.CallbackQuery, state: FSMContext):
        transaction_type = callback_query.data.split("_")[1]
        await state.update_data(transaction_type=transaction_type)
        await callback_query.message.answer("Prześlij do 3 zdjęć (jedno po drugim, zakończ 'Dalej'):")
        await MarketplaceState.uploading_photos.set()
        await state.update_data(photos=[])
        await callback_query.answer()

    @dp.message_handler(state=MarketplaceState.uploading_photos, content_types=types.ContentTypes.PHOTO)
    async def upload_photos(message: types.Message, state: FSMContext):
        data = await state.get_data()
        photos = data.get("photos", [])
        if len(photos) >= 3:
            await message.answer("Możesz dodać maksymalnie 3 zdjęcia. Jeśli chcesz przejść dalej, napisz 'Dalej'.")
            return
        photo = message.photo[-1]
        photo_path = os.path.join(MARKETPLACE_PHOTOS, f"{message.from_user.id}_{photo.file_id}.jpg")
        await photo.download(photo_path)
        photos.append(photo_path)
        await state.update_data(photos=photos)
        if len(photos) < 3:
            await message.answer(f"Zdjęcie zapisane ({len(photos)}/3). Prześlij kolejne lub napisz 'Dalej'.")

    @dp.message_handler(state=MarketplaceState.uploading_photos, content_types=types.ContentTypes.TEXT)
    async def finish_photos(message: types.Message, state: FSMContext):
        if message.text.lower() == "dalej":
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("Tak, chcę bezpieczny zakup 🛡️", callback_data="safe_deal_yes"),
                InlineKeyboardButton("Nie", callback_data="safe_deal_no")
            )
            await message.answer("Czy chcesz dodać opcję bezpiecznego zakupu (pieniądze trafiają najpierw na konto nocnej)?", reply_markup=kb)
            await MarketplaceState.choosing_safe_deal.set()
        else:
            await message.answer("Prześlij zdjęcie lub napisz 'Dalej'.")

    @dp.callback_query_handler(lambda c: c.data.startswith("safe_deal_"), state=MarketplaceState.choosing_safe_deal)
    async def safe_deal_chosen(callback_query: types.CallbackQuery, state: FSMContext):
        safe_deal = 1 if callback_query.data.endswith("yes") else 0
        await state.update_data(safe_deal=safe_deal)
        data = await state.get_data()
        # Podsumowanie
        summary = (
            f"Typ: {data['offer_type']}\n"
            f"Tytuł: {data['title']}\n"
            f"Opis: {data['description']}\n"
            f"Cena: {data['price']}\n"
            f"Miejscowość: {data['location']}\n"
            f"Transakcja: {data['transaction_type']}\n"
            f"Bezpieczny zakup: {'🛡️ TAK' if safe_deal else 'NIE'}\n"
            f"Zdjęć: {len(data.get('photos', []))}"
        )
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Zatwierdź ogłoszenie", callback_data="confirm_offer"))
        kb.add(InlineKeyboardButton("Anuluj", callback_data="cancel_offer"))
        await callback_query.message.answer(f"Podsumowanie ogłoszenia:\n\n{summary}", reply_markup=kb)
        await MarketplaceState.confirming.set()
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data == "confirm_offer", state=MarketplaceState.confirming)
    async def confirm_offer(callback_query: types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        photos = data.get("photos", [])
        cursor.execute("""
            INSERT INTO marketplace (user_id, user_name, offer_type, title, description, price, location, transaction_type, photo1, photo2, photo3, safe_deal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            callback_query.from_user.id,
            callback_query.from_user.full_name or callback_query.from_user.username or "Anonim",
            data['offer_type'],
            data['title'],
            data['description'],
            data['price'],
            data['location'],
            data['transaction_type'],
            photos[0] if len(photos) > 0 else None,
            photos[1] if len(photos) > 1 else None,
            photos[2] if len(photos) > 2 else None,
            data.get('safe_deal', 0)
        ))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Twoje ogłoszenie zostało dodane do Marketplace!")
        await state.finish()
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data == "cancel_offer", state=MarketplaceState.confirming)
    async def cancel_offer(callback_query: types.CallbackQuery, state: FSMContext):
        await callback_query.message.answer("Anulowano dodawanie ogłoszenia.")
        await state.finish()
        await callback_query.answer()

    @dp.message_handler(lambda m: m.text == "Przeglądaj ogłoszenia")
    async def browse_offers(message: types.Message):
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, offer_type, title, price, location, safe_deal FROM marketplace
            WHERE status='active'
            ORDER BY created_at DESC LIMIT 10
        """)
        offers = cursor.fetchall()
        conn.close()
        if not offers:
            await message.answer("Brak aktywnych ogłoszeń.")
            return
        kb = InlineKeyboardMarkup()
        for offer in offers:
            offer_id, offer_type, title, price, location, safe_deal = offer
            label = f"{'🛡️' if safe_deal else ''}{offer_type.capitalize()}: {title} ({price}) [{location}]"
            kb.add(InlineKeyboardButton(label, callback_data=f"offer_{offer_id}"))
        await message.answer("Dostępne ogłoszenia:", reply_markup=kb)

    @dp.callback_query_handler(lambda c: c.data.startswith("offer_"))
    async def show_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[1])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, user_name, offer_type, title, description, price, location, transaction_type, photo1, photo2, photo3, safe_deal, status
            FROM marketplace WHERE id=?
        """, (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        if not offer:
            await callback_query.message.answer("Ogłoszenie nie istnieje lub zostało usunięte.")
            return
        user_id, user_name, offer_type, title, description, price, location, transaction_type, photo1, photo2, photo3, safe_deal, status = offer
        text = (
            f"{'🛡️ ' if safe_deal else ''}<b>{offer_type.capitalize()}</b>: <b>{title}</b>\n"
            f"<i>{description}</i>\n"
            f"<b>Cena:</b> {price}\n"
            f"<b>Miejscowość:</b> {location}\n"
            f"<b>Transakcja:</b> {transaction_type}\n"
            f"<b>Sprzedający:</b> {user_name}\n"
            f"<b>Status:</b> {status}"
        )
        media = []
        for photo_path in [photo1, photo2, photo3]:
            if photo_path and os.path.exists(photo_path):
                media.append(types.InputMediaPhoto(open(photo_path, "rb")))
        if media:
            await callback_query.message.answer_media_group(media)
        # Dodaj przyciski kontaktu i zgłoszenia
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✉️ Napisz do sprzedającego", url=f"tg://user?id={user_id}"))
        kb.add(InlineKeyboardButton("🚩 Zgłoś ogłoszenie", callback_data=f"report_offer_{offer_id}"))
        await callback_query.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback_query.answer()

    @dp.message_handler(lambda m: m.text == "Moje ogłoszenia")
    async def my_offers(message: types.Message):
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, offer_type, title, price, status FROM marketplace
            WHERE user_id=?
            ORDER BY created_at DESC
        """, (message.from_user.id,))
        offers = cursor.fetchall()
        conn.close()
        if not offers:
            await message.answer("Nie masz żadnych ogłoszeń.")
            return
        kb = InlineKeyboardMarkup()
        for offer in offers:
            offer_id, offer_type, title, price, status = offer
            label = f"{offer_type.capitalize()}: {title} ({price}) [{status}]"
            kb.add(InlineKeyboardButton(label, callback_data=f"myoffer_{offer_id}"))
        await message.answer("Twoje ogłoszenia:", reply_markup=kb)

    @dp.callback_query_handler(lambda c: c.data.startswith("myoffer_"))
    async def show_my_offer(callback_query: types.CallbackQuery, state: FSMContext):
        offer_id = int(callback_query.data.split("_")[1])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT title, status FROM marketplace WHERE id=? AND user_id=?
        """, (offer_id, callback_query.from_user.id))
        offer = cursor.fetchone()
        conn.close()
        if not offer:
            await callback_query.message.answer("Nie znaleziono ogłoszenia.")
            return
        title, status = offer
        kb = InlineKeyboardMarkup()
        if status == "active":
            kb.add(InlineKeyboardButton("Usuń ogłoszenie", callback_data=f"delete_myoffer_{offer_id}"))
            kb.add(InlineKeyboardButton("Edytuj ogłoszenie", callback_data=f"edit_myoffer_{offer_id}"))
        await callback_query.message.answer(f"Ogłoszenie: {title}\nStatus: {status}", reply_markup=kb)
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("delete_myoffer_"))
    async def delete_my_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace SET status='removed' WHERE id=? AND user_id=?", (offer_id, callback_query.from_user.id))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Ogłoszenie zostało usunięte.")
        await callback_query.answer()

    # ADMIN: przeglądanie i moderacja ogłoszeń
    @dp.message_handler(commands=["moderuj_ogloszenia"])
    async def admin_moderate(message: types.Message):
        if message.from_user.id not in ADMIN_IDS:
            await message.reply("Brak uprawnień.")
            return
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, status FROM marketplace ORDER BY created_at DESC LIMIT 20")
        offers = cursor.fetchall()
        conn.close()
        kb = InlineKeyboardMarkup()
        for offer_id, title, status in offers:
            kb.add(InlineKeyboardButton(f"{title} [{status}]", callback_data=f"admin_offer_{offer_id}"))
        await message.answer("Moderacja ogłoszeń:", reply_markup=kb)

    @dp.callback_query_handler(lambda c: c.data.startswith("admin_offer_"))
    async def admin_offer_action(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Usuń", callback_data=f"admin_remove_{offer_id}"),
            InlineKeyboardButton("Wstrzymaj i poproś o poprawę", callback_data=f"admin_pending_{offer_id}")
        )
        await callback_query.message.answer("Co zrobić z tym ogłoszeniem?", reply_markup=kb)
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("admin_remove_"))
    async def admin_remove_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace SET status='removed' WHERE id=?", (offer_id,))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Ogłoszenie usunięte.")
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("admin_pending_"))
    async def admin_pending_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace SET status='pending' WHERE id=?", (offer_id,))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Ogłoszenie wstrzymane. Powiadom użytkownika o poprawkach.")
        await callback_query.answer()

    # --- 2. Kontakt do sprzedającego ---
    @dp.callback_query_handler(lambda c: c.data.startswith("offer_"))
    async def show_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[1])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, user_name, offer_type, title, description, price, location, transaction_type, photo1, photo2, photo3, safe_deal, status
            FROM marketplace WHERE id=?
        """, (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        if not offer:
            await callback_query.message.answer("Ogłoszenie nie istnieje lub zostało usunięte.")
            return
        user_id, user_name, offer_type, title, description, price, location, transaction_type, photo1, photo2, photo3, safe_deal, status = offer
        text = (
            f"{'🛡️ ' if safe_deal else ''}<b>{offer_type.capitalize()}</b>: <b>{title}</b>\n"
            f"<i>{description}</i>\n"
            f"<b>Cena:</b> {price}\n"
            f"<b>Miejscowość:</b> {location}\n"
            f"<b>Transakcja:</b> {transaction_type}\n"
            f"<b>Sprzedający:</b> {user_name}\n"
            f"<b>Status:</b> {status}"
        )
        media = []
        for photo_path in [photo1, photo2, photo3]:
            if photo_path and os.path.exists(photo_path):
                media.append(types.InputMediaPhoto(open(photo_path, "rb")))
        if media:
            await callback_query.message.answer_media_group(media)
        # Dodaj przyciski kontaktu i zgłoszenia
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✉️ Napisz do sprzedającego", url=f"tg://user?id={user_id}"))
        kb.add(InlineKeyboardButton("🚩 Zgłoś ogłoszenie", callback_data=f"report_offer_{offer_id}"))
        await callback_query.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback_query.answer()

    # --- 3. Zgłaszanie nadużyć ---
    @dp.callback_query_handler(lambda c: c.data.startswith("report_offer_"))
    async def report_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        admin_text = (
            f"🚩 <b>Zgłoszono ogłoszenie!</b>\n"
            f"ID ogłoszenia: {offer_id}\n"
            f"Zgłaszający: <a href='tg://user?id={callback_query.from_user.id}'>{callback_query.from_user.full_name}</a>"
        )
        # Wyślij do wszystkich adminów
        for admin_id in ADMIN_IDS:
            try:
                await callback_query.bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception:
                pass
        await callback_query.message.answer("Dziękujemy za zgłoszenie. Admini przyjrzą się ogłoszeniu.")
        await callback_query.answer()

    # --- 4. Data ważności ogłoszenia (automatyczne wygaszanie) ---
    def expire_old_offers():
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        expire_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE marketplace SET status='expired' WHERE status='active' AND created_at < ?", (expire_date,))
        conn.commit()
        conn.close()

    # Wywołuj automatycznie co uruchomienie handlerów (możesz też dodać do on_startup)
    expire_old_offers()

    # --- 5. Powiadomienia o usunięciu/wstrzymaniu ogłoszenia ---
    async def notify_user_about_offer_status(offer_id, status):
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, title FROM marketplace WHERE id=?", (offer_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            user_id, title = result
            status_text = {
                "removed": "Twoje ogłoszenie zostało usunięte przez administratora.",
                "pending": "Twoje ogłoszenie zostało wstrzymane przez administratora. Prosimy o poprawki.",
                "expired": "Twoje ogłoszenie wygasło (minęło 30 dni od dodania)."
            }
            text = f"ℹ️ {status_text.get(status, 'Status ogłoszenia został zmieniony.')} (\"{title}\")"
            try:
                await dp.bot.send_message(user_id, text)
            except Exception:
                pass

    # Zmodyfikuj admin_remove_offer i admin_pending_offer:
    @dp.callback_query_handler(lambda c: c.data.startswith("admin_remove_"))
    async def admin_remove_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace SET status='removed' WHERE id=?", (offer_id,))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Ogłoszenie usunięte.")
        await notify_user_about_offer_status(offer_id, "removed")
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("admin_pending_"))
    async def admin_pending_offer(callback_query: types.CallbackQuery):
        offer_id = int(callback_query.data.split("_")[2])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE marketplace SET status='pending' WHERE id=?", (offer_id,))
        conn.commit()
        conn.close()
        await callback_query.message.answer("Ogłoszenie wstrzymane. Powiadom użytkownika o poprawkach.")
        await notify_user_about_offer_status(offer_id, "pending")
        await callback_query.answer()

    # --- 6. Edycja ogłoszenia ---
    class EditOfferState(StatesGroup):
        choosing_field = State()
        editing_value = State()

    @dp.callback_query_handler(lambda c: c.data.startswith("myoffer_"))
    async def show_my_offer(callback_query: types.CallbackQuery, state: FSMContext):
        offer_id = int(callback_query.data.split("_")[1])
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT title, status FROM marketplace WHERE id=? AND user_id=?
        """, (offer_id, callback_query.from_user.id))
        offer = cursor.fetchone()
        conn.close()
        if not offer:
            await callback_query.message.answer("Nie znaleziono ogłoszenia.")
            return
        title, status = offer
        kb = InlineKeyboardMarkup()
        if status == "active":
            kb.add(InlineKeyboardButton("Usuń ogłoszenie", callback_data=f"delete_myoffer_{offer_id}"))
            kb.add(InlineKeyboardButton("Edytuj ogłoszenie", callback_data=f"edit_myoffer_{offer_id}"))
        await callback_query.message.answer(f"Ogłoszenie: {title}\nStatus: {status}", reply_markup=kb)
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("edit_myoffer_"))
    async def edit_my_offer(callback_query: types.CallbackQuery, state: FSMContext):
        offer_id = int(callback_query.data.split("_")[2])
        await state.update_data(offer_id=offer_id)
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Tytuł", callback_data="edit_field_title"),
            InlineKeyboardButton("Opis", callback_data="edit_field_description"),
            InlineKeyboardButton("Cena", callback_data="edit_field_price"),
            InlineKeyboardButton("Miejscowość", callback_data="edit_field_location")
        )
        await callback_query.message.answer("Co chcesz edytować?", reply_markup=kb)
        await EditOfferState.choosing_field.set()
        await callback_query.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith("edit_field_"), state=EditOfferState.choosing_field)
    async def edit_field_chosen(callback_query: types.CallbackQuery, state: FSMContext):
        field = callback_query.data.split("_")[2]
        await state.update_data(field=field)
        await callback_query.message.answer(f"Podaj nową wartość dla pola: {field}")
        await EditOfferState.editing_value.set()
        await callback_query.answer()

    @dp.message_handler(state=EditOfferState.editing_value, content_types=types.ContentTypes.TEXT)
    async def edit_value(message: types.Message, state: FSMContext):
        data = await state.get_data()
        offer_id = data.get("offer_id")
        field = data.get("field")
        value = message.text
        if field not in ["title", "description", "price", "location"]:
            await message.answer("Nieprawidłowe pole.")
            await state.finish()
            return
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute(f"UPDATE marketplace SET {field}=? WHERE id=?", (value, offer_id))
        conn.commit()
        conn.close()
        await message.answer("Zaktualizowano ogłoszenie!")
        await state.finish()

    @dp.message_handler(lambda m: m.text == "Filtruj ogłoszenia")
    async def filter_start(message: types.Message, state: FSMContext):
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Sprzedam", callback_data="filter_type_sprzedam"),
            InlineKeyboardButton("Kupię", callback_data="filter_type_kupie"),
            InlineKeyboardButton("Zamienię", callback_data="filter_type_zamienie"),
            InlineKeyboardButton("Dowolny", callback_data="filter_type_any")
        )
        await message.answer("Wybierz typ ogłoszenia do filtrowania:", reply_markup=kb)
        await FilterState.choosing_type.set()

    @dp.callback_query_handler(lambda c: c.data.startswith("filter_type_"), state=FilterState.choosing_type)
    async def filter_type_chosen(callback_query: types.CallbackQuery, state: FSMContext):
        offer_type = callback_query.data.split("_")[2]
        await state.update_data(offer_type=offer_type)
        await callback_query.message.answer("Podaj miejscowość (lub napisz 'Dowolna'):")
        await FilterState.entering_location.set()
        await callback_query.answer()

    @dp.message_handler(state=FilterState.entering_location, content_types=types.ContentTypes.TEXT)
    async def filter_location(message: types.Message, state: FSMContext):
        await state.update_data(location=message.text)
        await message.answer("Podaj frazę do wyszukania w tytule (lub napisz 'Dowolna'):");
        await FilterState.entering_phrase.set()

    @dp.message_handler(state=FilterState.entering_phrase, content_types=types.ContentTypes.TEXT)
    async def filter_phrase(message: types.Message, state: FSMContext):
        data = await state.get_data()
        offer_type = data.get("offer_type")
        location = message.text
        await state.update_data(phrase=location)
        # Pobierz dane do filtra
        filter_data = await state.get_data()
        offer_type = filter_data.get("offer_type")
        location = filter_data.get("location")
        phrase = message.text

        query = "SELECT id, offer_type, title, price, location, safe_deal FROM marketplace WHERE status='active'"
        params = []
        if offer_type != "any":
            query += " AND offer_type=?"
            params.append(offer_type)
        if location.lower() != "dowolna":
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
        if phrase.lower() != "dowolna":
            query += " AND title LIKE ?"
            params.append(f"%{phrase}%")
        query += " ORDER BY created_at DESC LIMIT 10"

        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        offers = cursor.fetchall()
        conn.close()
        if not offers:
            await message.answer("Brak ogłoszeń spełniających kryteria.")
            await state.finish()
            return
        kb = InlineKeyboardMarkup()
        for offer in offers:
            offer_id, offer_type, title, price, location, safe_deal = offer
            label = f"{'🛡️' if safe_deal else ''}{offer_type.capitalize()}: {title} ({price}) [{location}]"
            kb.add(InlineKeyboardButton(label, callback_data=f"offer_{offer_id}"))
        await message.answer("Wyniki filtrowania:", reply_markup=kb)
        await state.finish()
