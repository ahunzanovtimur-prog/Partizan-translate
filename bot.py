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

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-20250514"

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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


SYSTEM_PROMPT = (
    "You are an expert academic translator with PhD-level expertise in Uzbek and Russian linguistics. "
    "Your translations are used in official university publications, dissertations, and academic journals. "
    "Quality must be PERFECT - suitable for official publication without any editing.\n\n"
    "CRITICAL QUALITY RULES:\n\n"
    "FOR UZBEK OUTPUT:\n"
    "- Use ONLY modern Uzbek Latin script. NEVER mix Cyrillic and Latin letters.\n"
    "- Correct alphabet: a, b, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v, x, y, z, "
    "o' (with apostrophe), g' (with apostrophe), sh, ch, ng.\n"
    "- The apostrophe in o' and g' is critical - never omit it.\n"
    "- NEVER use Russian Cyrillic letters inside Uzbek Latin text.\n"
    "- NEVER use Turkish-specific letters - use Uzbek equivalents (sh, ch, g', i, o', u).\n"
    "- Double-check every word for correct Uzbek spelling.\n\n"
    "FOR RUSSIAN OUTPUT:\n"
    "- Use proper Russian Cyrillic. NEVER mix Latin letters.\n"
    "- Follow all Russian grammar rules.\n"
    "- Use correct punctuation.\n\n"
    "OUTPUT RULES:\n"
    "- Output ONLY the translated text. NOTHING else.\n"
    "- Do NOT add notes, comments, explanations, or remarks.\n"
    "- Do NOT add headers, labels, separators, or dashes.\n"
    "- Do NOT write Translator Notes or any similar section.\n"
    "- Just the pure translated text, ready to copy and paste.\n\n"
    "Must score 10/10 on grammar and spelling. Proofread twice."
)


def build_translate_prompt(text, target_lang, source_lang="auto"):
    target_name = LANGUAGES.get(target_lang, target_lang)
    if source_lang and source_lang != "auto":
        source_name = LANGUAGES.get(source_lang, source_lang)
        return "Translate from " + source_name + " into " + target_name + ". Output ONLY the translation.\n\n" + text
    return "Translate into " + target_name + ". Output ONLY the translation.\n\n" + text


async def call_ai(text, target_lang, source_lang="auto"):
    prompt = build_translate_prompt(text, target_lang, source_lang)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        translation = response.content[0].text

        check_prompt = (
            "You are a proofreader for academic texts. Check the following translation and fix ANY errors:\n"
            "- Fix spelling mistakes\n"
            "- Fix grammar errors\n"
            "- If Uzbek Latin text: make sure there are NO Cyrillic letters mixed in, apostrophes in o' and g' are correct\n"
            "- If Russian text: make sure there are NO Latin letters mixed in\n"
            "- Fix punctuation\n\n"
            "Output ONLY the corrected text. If the text is already perfect, output it unchanged. NO comments or notes.\n\n"
            + translation
        )
        check_response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": check_prompt}],
        )
        return check_response.content[0].text
    except Exception as exc:
        logger.error("API error: %s", exc)
        return "Xatolik yuz berdi. Qayta urinib ko'ring. / Oshibka. Poprobuite snova."


async def detect_language(text):
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": "Detect the language. Reply with ONLY the ISO 639-1 two-letter code. For Uzbek reply 'uz'. Nothing else.\n\n" + text[:300],
            }],
        )
        return response.content[0].text.strip().lower()[:2]
    except Exception:
        return "unknown"


def lang_keyboard(prefix="translate"):
    buttons = [
        InlineKeyboardButton(name, callback_data=prefix + ":" + code)
        for code, name in LANGUAGES.items()
    ]
    rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(rows)


def after_translate_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Boshqa tilga / Drugoy yazyk", callback_data="retry")]
    ])


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
        "2. Tugmalar \u2014 tarjimadan keyin boshqa tilni tanlash mumkin.\n"
        "3. /lang \u2014 doimiy maqsad tilni o'rnatish.\n"
        "4. /reset \u2014 avtomatik rejimga qaytish.\n\n"
        "Joriy til: " + lang_str,
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
