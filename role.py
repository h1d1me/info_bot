import sqlite3
from datetime import datetime, timedelta

DB_PATH = "bot_database.db"

def update_users_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'Nowicjusz'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN reputation INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_warning TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def add_reputation(user_id, points, bot=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET reputation = reputation + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()
    update_user_role(user_id)
    # Powiadom użytkownika o przyznaniu punktów
    if bot:
        try:
            import asyncio
            asyncio.create_task(bot.send_message(user_id, f"🎉 Otrzymałeś {points} punkt(ów) reputacji!"))
        except Exception as e:
            print(f"Nie udało się wysłać powiadomienia: {e}")

def update_user_role(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT reputation FROM users WHERE user_id = ?", (user_id,))
    rep = cursor.fetchone()
    if rep:
        rep = rep[0]
        if rep >= 200:
            role = "💎 Poszukiwacz Skarbów"
        elif rep >= 100:
            role = "🌒 Nocny"
        elif rep >= 60:
            role = "🧭 Odkrywca"
        elif rep >= 30:
            role = "🔦 Tropiciel"
        elif rep >= 10:
            role = "🗺 Zwiadowca"
        else:
            role = "🪨 Nowicjusz"
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()
    conn.close()

def set_operator_role(user_id, shop_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Nadaj rolę Operator_<shop_name>
    role = f"Operator_{shop_name}"
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
    # Przypisz operatora do sklepu jeśli sklep istnieje
    cursor.execute("SELECT shop_name FROM shops WHERE shop_name = ?", (shop_name,))
    if cursor.fetchone():
        cursor.execute("UPDATE shops SET operator_link = ? WHERE shop_name = ?", (f"tg://user?id={user_id}", shop_name))
    conn.commit()
    conn.close()
    return role

def add_warning(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT warnings, last_warning FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    warnings = row[0] or 0
    last_warning = row[1]
    now = datetime.now().isoformat()
    # Jeśli ostatnie ostrzeżenie było ponad 7 dni temu, resetuj licznik
    if last_warning:
        last = datetime.fromisoformat(last_warning)
        if datetime.now() - last > timedelta(days=7):
            warnings = 0
    warnings += 1
    cursor.execute("UPDATE users SET warnings = ?, last_warning = ? WHERE user_id = ?", (warnings, now, user_id))
    conn.commit()
    conn.close()
    return warnings

def reset_warnings(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET warnings = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role, reputation, warnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        role, rep, warns = row
        return role, rep, warns
    else:
        return None, None, None

# Wywołaj update_users_table() raz na starcie projektu (np. w main.py)