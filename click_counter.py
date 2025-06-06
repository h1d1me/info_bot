import json
import time
from datetime import datetime
import sqlite3

CLICKS_FILE = "clicks.json"
DB_PATH = "bot_database.db"

def add_click():
    """Dodaje kliknięcie z aktualnym timestampem do pliku, zlicza total i dzienne."""
    now = int(time.time())
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(CLICKS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"total": 0, "clicks": [], "daily": {}}
    if isinstance(data, list):
        # migracja ze starego formatu
        data = {"total": len(data), "clicks": data, "daily": {}}
    data["clicks"].append(now)
    data["total"] += 1
    # Dzienne kliknięcia
    data["daily"][today] = data["daily"].get(today, 0) + 1
    # Zostaw tylko kliknięcia z ostatnich 5h (18000 sekund)
    data["clicks"] = [t for t in data["clicks"] if now - t <= 18000]
    with open(CLICKS_FILE, "w") as f:
        json.dump(data, f)

def get_clicks_last_5h():
    """Zwraca liczbę kliknięć z ostatnich 5 godzin."""
    now = int(time.time())
    try:
        with open(CLICKS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        return len([t for t in data if now - t <= 18000])
    return len([t for t in data.get("clicks", []) if now - t <= 18000])

def get_total_clicks():
    """Zwraca łączną liczbę kliknięć od początku."""
    try:
        with open(CLICKS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        return len(data)
    return data.get("total", 0)

def get_today_clicks():
    """Zwraca liczbę kliknięć z dzisiaj."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(CLICKS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        return 0
    return data.get("daily", {}).get(today, 0)

def add_message(user_id, user_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count FROM messages WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE messages SET message_count = message_count + 1, user_name = ?, last_message = ? WHERE user_id = ?",
            (user_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )
    else:
        cursor.execute(
            "INSERT INTO messages (user_id, user_name, message_count, last_message) VALUES (?, ?, ?, ?)",
            (user_id, user_name, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    conn.commit()
    conn.close()

def get_user_messages_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count FROM messages WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def get_all_messages_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(message_count) FROM messages")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else 0