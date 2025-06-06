import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext

API_URL = "https://translate.astian.org/translate"
LANGS = {
    "pl": "🇵🇱 Polski",
    "en": "🇬🇧 English",
    "uk": "🇺🇦 Ukraiński",
    "ru": "🇷🇺 Rosyjski",
}

async def translate(text, target_lang="en", source_lang="auto"):
    async with aiohttp.ClientSession() as session:
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text"
        }
        async with session.post(API_URL, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("translatedText")
            else:
                return None

async def tlumacz_komenda(message: types.Message, state: FSMContext):
    print("Wywołano tlumacz_komenda")  # Dodaj to na początek funkcji
    args = message.get_args().strip().split(" ", 1)
    if len(args) != 2:
        lang_list = "\n".join([f"`{code}` – {flag}" for code, flag in LANGS.items()])
        await message.reply(
            "❗ Użycie: `/tl [kod języka] [tekst]`\n"
            "Np: `/tl uk Dziękuję za pomoc!`\n\n"
            "📘 Dostępne języki:\n" + lang_list,
            parse_mode="Markdown"
        )
        return

    target_lang, text = args
    if target_lang not in LANGS:
        await message.reply("Nieobsługiwany język docelowy. Dostępne: " + ", ".join(LANGS.keys()))
        return

    translated = await translate(text, target_lang)
    if translated:
        await message.reply(f"**Tłumaczenie ({LANGS[target_lang]}):**\n{translated}", parse_mode="Markdown")
    else:
        await message.reply("❌ Nie udało się przetłumaczyć tekstu.")