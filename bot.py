"""
Perevod UZ-RUS - Telegram-bot dlya akademicheskikh perevodov
Ispolzuet Anthropic Claude API dlya perevodov universitetskogo kachestva.
"""

import os
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction

import anthropic

# --- Nastroyki ---

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-20250514"

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Yazyki ---

LANGUAGES = {
    "uz": "\U0001f1fa\U0001f1ff O'zbekcha",
    "ru": "\U0001f1f7\U0001f1fa Russkiy",
    "en": "\U0001f1ec\U0001f1e7 English",
    "de": "\U0001f1e9\U0001f1ea Deutsch",
    "fr": "\U0001f1eb\U0001f1f7 Francais",
    "es": "\U0001f1ea\U0001f1f8 Espanol",
    "it": "\U0001f1ee\U0001f1f9 Italiano",
    "pt": "\U0001f1f5\U0001f1f9 Portugues",
    "zh": "\U0001f1e8\U0001f1f3 Zhongwen",
    "ja": "\U0001f1ef\U0001f1f5 Nihongo",
    "ko": "\U0001f1f0\U0001f1f7 Hangugeo",
    "ar": "\U0001f1f8\U0001f1e6 Al-Arabiyyah",
    "tr": "\U0001f1f9\U0001f1f7 Turkce",
    "pl": "\U0001f1f5\U0001f1f1 Polski",
    "uk": "\U0001f1fa\U0001f1e6 Ukrainska",
    "cs": "\U0001f1e8\U0001f1ff Cestina",
    "nl": "\U0001f1f3\U0001f1f1 Nederlands",
}

AUTO_PAIRS = {
    "uz": "ru", "ru": "uz",
    "en": "ru", "de": "ru", "fr": "ru",
    "es": "ru", "ja": "ru", "zh": "ru",
    "ko": "ru", "ar": "ru", "it": "ru",
    "pt": "ru", "tr": "ru", "pl": "ru",
    "uk": "ru",
}

user_settings = {}


def get_user_lang(user_id):
    return user_settings.get(user_id, {}).get("target_lang")


def set_user_lang(user_id, lang_code):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["target_lang"] = lang_code


# --- Prompt ---

SYSTEM_PROMPT = """You are an expert academic translator specializing in Uzbek and Russian translation, with deep expertise in linguistics, terminology, and cross-cultural communication between Central Asian and Russian-speaking academic traditions. You also handle translations to/from other languages with equal precision. Your translations are used in university settings - dissertations, research papers, academic correspondence, and lectures.

STRICT RULES:
1. Provide an accurate, natural-sounding translation that preserves the academic register, tone, and terminology of the original.
2. Keep domain-specific terms precise (legal, medical, technical, philosophical, scientific, etc.).
3. For Uzbek texts: correctly handle both Latin and Cyrillic Uzbek scripts. Always output Uzbek in Latin script unless asked otherwise.
4. Preserve formatting: paragraphs, bullet points, numbered lists.
5. If the source contains citations or references, keep them intact.
6. After the translation, add a section called Tarjimon izohlari / Primechaniya perevodchika (Translator Notes) IN BOTH Uzbek and Russian, where you:
   - Explain non-obvious translation choices.
   - Mention alternative phrasings for key terms.
   - Note cultural or contextual nuances.
   - If a term has an established academic translation, mention it.
7. Respond ONLY in the format below - no extra chatter.

FORMAT:
---
(translated text here)
---

Tarjimon izohlari / Primechaniya perevodchika:
- ...
- ...
"""


def build_translate_prompt(text, target_lang, source_lang="auto"):
    target_name = LANGUAGES.get(target_lang, target_lang)
    if source_lang and source_lang != "auto":
        source_name = LANGUAGES.get(source_lang, source_lang)
        return "Translate the following text from " + source_name + " into " + target_name + ".\n\nText:\n\"\"\"\n" + text + "\n\"\"\""
    return "Detect the source language and translate the following text into " + target_name + ". State the detected language in your translator notes.\n\nText:\n\"\"\"\n" + text + "\n\"\"\""


async def call_ai(text, target_lang, source_lang="auto"):
    prompt = build_translate_prompt(text, target_lang, source_lang)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.error("API error: %s", exc)
        return "Xatolik yuz berdi. Iltimos qayta urinib ko'ring. / Proizoshla oshibka. Poprobuite eshchyo raz."


async def detect_language(text):
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": "Detect the language of the following text. Reply with ONLY the ISO 639-1 two-letter code (e.g. 'uz', 'ru', 'en', 'de'). For Uzbek (both Latin and Cyrillic script) reply 'uz'. Nothing else.\n\n\"" + text[:300] + "\"",
            }],
        )
        return response.content[0].text.strip().lower()[:2]
    except Exception:
        return "unknown"


# --- Klaviatury ---

def lang_keyboard(prefix="translate"):
    buttons = [
        InlineKeyboardButton(name, callback_data=prefix + ":" + code)
        for code, name in LANGUAGES.items()
    ]
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def after_translate_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Boshqa tilga tarjima qilish / Drugoy yazyk", callback_data="retry")]
    ])


# --- Hendlery ---

async def cmd_start(update, ctx):
    await update.message.reply_text(
        "Perevod UZ-RUS \u2014 Akademik tarjimon\n\n"
        "Matnlarni akademik darajada tarjima qilaman.\n"
        "Ixtisoslik: o'zbekcha \u2194 ruscha\n\n"
        "Qanday foydalanish:\n"
        "\u2022 Matn yuboring \u2014 tilni aniqlab tarjima qilaman\n"
        "\u2022 Tugmani bosib boshqa tilni tanlang\n"
        "\u2022 /lang \u2014 doimiy tilni tanlash\n\n"
        "Buyruqlar:\n"
        "/lang \u2014 maqsad tilni tanlash\n"
        "/langs \u2014 tillar ro'yxati\n"
        "/reset \u2014 avto-rejimga qaytish\n"
        "/help \u2014 yordam",
    )


async def cmd_help(update, ctx):
    current = get_user_lang(update.effective_user.id)
    lang_str = LANGUAGES.get(current, "avto (uzb \u2194 rus)") if current else "avto (uzb \u2194 rus)"
    await update.message.reply_text(
        "Yordam / Spravka\n\n"
        "1. Matn yuboring \u2014 bot tilni aniqlaydi va tarjima qiladi.\n"
        "   O'zbekcha \u2192 ruscha, ruscha \u2192 o'zbekcha.\n\n"
        "2. Tugmalar \u2014 tarjimadan keyin boshqa tilni tanlash mumkin.\n\n"
        "3. /lang \u2014 doimiy maqsad tilni o'rnatish.\n\n"
        "4. /reset \u2014 avtomatik rejimga qaytish.\n\n"
        "Joriy til: " + lang_str + "\n\n"
        "Har bir tarjima tarjimon izohlari bilan birga keladi.",
    )


async def cmd_lang(update, ctx):
    await update.message.reply_text(
        "Tilni tanlang / Vyberite yazyk:",
        reply_markup=lang_keyboard(prefix="setlang"),
    )


async def cmd_langs(update, ctx):
    lines = ["  " + v + " (" + k + ")" for k, v in LANGUAGES.items()]
    await update.message.reply_text(
        "Qo'llab-quvvatlanadigan tillar:\n\n" + "\n".join(lines),
    )


async def cmd_reset(update, ctx):
    uid = update.effective_user.id
    if uid in user_settings:
        user_settings[uid].pop("target_lang", None)
    await update.message.reply_text(
        "Til qayta o'rnatildi. Bot avtomatik ravishda tilni aniqlaydi\n"
        "va o'zbekcha \u2194 ruscha tarjima qiladi."
    )


async def handle_message(update, ctx):
    text = update.message.text
    if not text or len(text.strip()) < 2:
        return

    user_id = update.effective_user.id
    await update.message.chat.send_action(ChatAction.TYPING)

    target_lang = get_user_lang(user_id)

    if target_lang:
        result = await call_ai(text, target_lang)
    else:
        detected = await detect_language(text)
        target_lang = AUTO_PAIRS.get(detected, "ru")
        result = await call_ai(text, target_lang, source_lang=detected)

    chunks = split_message(result)
    for i, chunk in enumerate(chunks):
        kwargs = {}
        if i == len(chunks) - 1:
            kwargs["reply_markup"] = after_translate_keyboard()
        await update.message.reply_text(chunk, **kwargs)

    ctx.user_data["last_text"] = text


async def callback_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "retry":
        await query.message.reply_text(
            "Tilni tanlang / Vyberite yazyk:",
            reply_markup=lang_keyboard(prefix="translate"),
        )
        return

    if data.startswith("translate:"):
        lang_code = data.split(":")[1]
        last_text = ctx.user_data.get("last_text")
        if not last_text:
            await query.message.reply_text("Matn topilmadi. Qayta yuboring.")
            return
        await query.message.chat.send_action(ChatAction.TYPING)
        result = await call_ai(last_text, lang_code)
        chunks = split_message(result)
        for i, chunk in enumerate(chunks):
            kwargs = {}
            if i == len(chunks) - 1:
                kwargs["reply_markup"] = after_translate_keyboard()
            await query.message.reply_text(chunk, **kwargs)
        return

    if data.startswith("setlang:"):
        lang_code = data.split(":")[1]
        set_user_lang(query.from_user.id, lang_code)
        lang_name = LANGUAGES.get(lang_code, lang_code)
        await query.message.edit_text(
            "Til o'rnatildi: " + lang_name + "\n\n"
            "Barcha matnlar shu tilga tarjima qilinadi.\n"
            "Qayta o'rnatish: /reset",
        )
        return


# --- Utility ---

def split_message(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = text.rfind(" ", 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


# --- Zapusk ---

async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Boshlash"),
        BotCommand("lang", "Tilni tanlash"),
        BotCommand("langs", "Tillar royxati"),
        BotCommand("reset", "Avto-rejim"),
        BotCommand("help", "Yordam"),
    ])


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("langs", cmd_langs))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
