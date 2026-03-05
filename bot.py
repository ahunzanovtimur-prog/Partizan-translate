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
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Russkiy",
}

user_settings = {}

SEPARATOR = "\n\n〰️〰️〰️\n\n"


def get_user_lang(user_id):
    return user_settings.get(user_id, {}).get("target_lang")


def set_user_lang(user_id, lang_code):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["target_lang"] = lang_code


SYSTEM_PROMPT = (
    "You are a professional academic translator between Russian and Uzbek.\n"
    "Preserve all emojis exactly.\n"
    "Preserve HTML formatting tags like <b>, <i>, <blockquote>.\n"
    "Output ONLY the translated text."
)


def build_translate_prompt(text, target_lang):
    if target_lang == "ru":
        return "Translate into Russian.\n\n" + text
    if target_lang == "uz":
        return "Translate into Uzbek Latin.\n\n" + text


async def call_ai(text, target_lang):

    prompt = build_translate_prompt(text, target_lang)

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
        return "Tarjima xatosi / Ошибка перевода"


async def detect_language(text):
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": "What language is this text written in? Reply with ONLY the ISO 639-1 code.\nRules:\n- Uzbek Latin (o'zbek, qilish, bo'ladi) = uz\n- Russian Cyrillic = ru\n- English = en\n- Reply ONLY the 2-letter code, nothing else.\n\n" + text[:500],
            }],
        )
        return response.content[0].text.strip().lower()[:2]
    except Exception:
        return "unknown"


def after_translate_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Boshqa tilga / Drugoy yazyk", callback_data="retry")]
    ])


async def cmd_start(update, ctx):

    await update.message.reply_text(
        "Tarjimon bot\n\n"
        "Matnga reply qiling va yozing:\n"
        "tr / перевод / translate / tarjima"
    )


async def cmd_reset(update, ctx):

    uid = update.effective_user.id

    if uid in user_settings:
        user_settings[uid].pop("target_lang", None)

    await update.message.reply_text("Avto tarjima qayta yoqildi.")


async def handle_message(update, ctx):

    message = update.message
    text = message.text

    if not text:
        return

    if not (
        message.reply_to_message
        and text.lower().strip() in ["tr", "translate", "перевод", "tarjima"]
    ):
        return

    original_text = message.reply_to_message.text_html

    if not original_text:
        await message.reply_text("Matn topilmadi")
        return

    await message.chat.send_action(ChatAction.TYPING)

    user_id = update.effective_user.id

    target_lang = get_user_lang(user_id)

    if not target_lang:

        detected = await detect_language(original_text)

        if detected == "ru":
            target_lang = "uz"
        else:
            target_lang = "ru"

    translation = await call_ai(original_text, target_lang)

    # Всегда: сначала узб, потом рус
    if target_lang == "ru":
        # оригинал = узб, перевод = рус
        combined = original_text + SEPARATOR + translation
    else:
        # оригинал = рус, перевод = узб → переворачиваем
        combined = translation + SEPARATOR + original_text

    chunks = split_message(combined)

    for i, chunk in enumerate(chunks):

        kwargs = {}

        if i == len(chunks) - 1:
            kwargs["reply_markup"] = after_translate_keyboard()

        await message.reply_text(chunk, parse_mode="HTML", **kwargs)

    ctx.user_data["last_text"] = original_text


async def callback_handler(update, ctx):

    query = update.callback_query
    await query.answer()

    if query.data == "retry":

        await query.message.reply_text(
            "Reply qiling va yozing: tr"
        )


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
        BotCommand("start", "Start"),
        BotCommand("reset", "Reset"),
    ])


def main():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
