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

def get_user_lang(user_id):
    return user_settings.get(user_id, {}).get("target_lang")

def set_user_lang(user_id, lang_code):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["target_lang"] = lang_code


SYSTEM_PROMPT = (
    "You are a professional academic translator between Russian and Uzbek.\n"
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

    text_lower = text.lower()

    # простое определение языка
    if any(c in text_lower for c in "қғҳў"):
        return "uz"

    if any(c in text_lower for c in "абвгдеёжзийклмнопрстуфхцчшщыэюя"):
        return "ru"

    return "ru"


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

    # работает только reply + команда
    if not (
        message.reply_to_message
        and text.lower().strip() in ["tr", "translate", "перевод", "tarjima"]
    ):
        return

    original_text = message.reply_to_message.text

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

    result = await call_ai(original_text, target_lang)

    chunks = split_message(result)

    for i, chunk in enumerate(chunks):

        kwargs = {}

        if i == len(chunks) - 1:
            kwargs["reply_markup"] = after_translate_keyboard()

        await message.reply_text(chunk, **kwargs)

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
