import os
import logging
import tempfile

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
from groq import Groq

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
MODEL = "claude-sonnet-4-20250514"

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SEPARATOR = "\n\n\u3030\ufe0f\u3030\ufe0f\u3030\ufe0f\n\n"

user_settings = {}


def get_user_lang(user_id):
    return user_settings.get(user_id, {}).get("target_lang")


def set_user_lang(user_id, lang_code):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["target_lang"] = lang_code


SYSTEM_PROMPT = (
    "You are a professional editor and translator for Uzbek, Russian, and English languages, "
    "specializing in university, press-release, and SMM content.\n\n"
    "YOUR TASK:\n"
    "- Translate text between languages\n"
    "- Make Uzbek text native, literary, and natural\n"
    "- Preserve original meaning exactly\n\n"
    "STRICT RULES:\n"
    "1. DO NOT change names: brands, universities, names, surnames - keep them exactly as is\n"
    "2. Russian text: DO NOT rewrite, fix only obvious errors\n"
    "3. Uzbek text: fix grammar, remove Russian-style phrasing, make native formulation\n"
    "4. DO NOT add new information\n"
    "5. DO NOT shorten meaning\n"
    "6. DO NOT write explanations unless asked\n"
    "7. Preserve all emojis exactly\n"
    "8. Preserve HTML formatting tags like <b>, <i>, <blockquote>\n\n"
    "STYLE: official, press-release / SMM / university, clean, literate, confident\n\n"
    "UZBEK-SPECIFIC FIXES:\n"
    "- 'uy' -> 'xonadon' (in congratulations context)\n"
    "- 'doim' -> 'doimo'\n"
    "- 'tabriklaymiz' <-> 'tabriklaydi' (based on subject logic: if org congratulates, use 3rd person)\n"
    "- 'bo\\'lishdi' -> 'o\\'rtoqlashdilar'\n"
    "- Avoid word-for-word translation from Russian\n"
    "- Use proper Uzbek Latin script with o\\' and g\\' apostrophes\n\n"
    "NATIVE UZBEK MARKETING RULES:\n"
    "- 'atmosferadan' -> 'muhitdan' (more native Uzbek)\n"
    "- 'kenglik' -> 'keng va qulay makon' (richer, more premium feel)\n"
    "- 'oshxona' -> 'taomlar' (stronger for marketing)\n"
    "- Always match the rhythm and tone of the Russian version\n"
    "- Use premium, elegant Uzbek phrasing for marketing/SMM texts\n"
    "- Avoid calques from Russian - rephrase naturally in Uzbek\n"
    "- For event/restaurant/hotel texts: use warm, inviting, premium language\n"
    "- Think like a native Uzbek copywriter, not a translator\n"
    "- Numbers with postpositions use hyphen: 31-maygacha, 5-kursga, 10-martdan (NOT 31 maygacha)\n"
    "- 'tejash/ekonomiya' -> 'foyda' in marketing context (sounds more appealing)\n"
    "- 'real' -> 'haqiqiy' or 'amaliy' (avoid anglicisms)\n"
    "- 'keys/kejs' -> 'holat' or 'misol' (use native Uzbek)\n"
    "- 'kontakt' -> 'aloqa', 'format' -> 'shakl', 'prezentatsiya' -> 'taqdimot'\n"
    "- Always prefer native Uzbek words over borrowed Russian/English words\n\n"
    "EXAMPLES:\n\n"
    "Input: TIUE sizni bayram bilan tabriklaymiz\n"
    "Output: TIUE sizni bayram bilan tabriklaydi\n\n"
    "Input: Biz sizga yangi uy sotib olganingiz bilan tabriklaymiz\n"
    "Output: Sizni yangi xonadon sotib olganingiz bilan tabriklaymiz\n\n"
    "Input: Talabalar doim yaxshi natijalar ko\\'rsatishdi\n"
    "Output: Talabalar doimo yaxshi natijalar ko\\'rsatishdi\n\n"
    "Input: Students achieved excellent results in the international olympiad\n"
    "Output (to Russian): Студенты достигли отличных результатов на международной олимпиаде\n\n"
    "OUTPUT FORMAT:\n"
    "- Output ONLY the translated/corrected text\n"
    "- NO notes, NO comments, NO explanations\n"
    "- Just the pure text ready to copy and paste"
)

CHECK_PROMPT = (
    "You are a proofreader for academic and official texts. "
    "Check the following translation and fix ANY errors:\n"
    "- Fix spelling mistakes\n"
    "- Fix grammar errors\n"
    "- If Uzbek Latin: no Cyrillic letters mixed in, apostrophes in o\\' and g\\' correct\n"
    "- If Russian: no Latin letters mixed in\n"
    "- Apply Uzbek-specific fixes: doim->doimo, tabriklaymiz->tabriklaydi (for orgs), uy->xonadon (congrats)\n"
    "- Fix punctuation\n\n"
    "Output ONLY the corrected text. If perfect, output unchanged. NO comments.\n\n"
)

def fix_uzbek_text(text):
    # Fix Turkish characters to Uzbek
    replacements = {
        "\u015f": "sh", "\u015e": "Sh",
        "\u00e7": "ch", "\u00c7": "Ch",
        "\u011f": "g\u02BB", "\u011e": "G\u02BB",
        "\u0131": "i", "\u00f6": "o\u02BB", "\u00d6": "O\u02BB",
        "\u00fc": "u", "\u00dc": "U",
        "o'": "o\u02BB", "O'": "O\u02BB",
        "g'": "g\u02BB", "G'": "G\u02BB",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Check if Uzbek text has Cyrillic mixed in - remove stray Cyrillic
    import re
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        latin_count = len(re.findall(r'[a-zA-Z]', line))
        cyrillic_count = len(re.findall(r'[\u0400-\u04FF]', line))
        # If line is mostly Latin but has some Cyrillic, it is a bug
        if latin_count > 0 and cyrillic_count > 0 and latin_count > cyrillic_count:
            line = re.sub(r'[\u0400-\u04FF]+', '', line)
        cleaned.append(line)
    return "\n".join(cleaned)
def build_translate_prompt(text, target_lang):
    if target_lang == "ru":
        return "Translate into Russian. Output ONLY the translation.\n\n" + text
    elif target_lang == "uz":
        return "Translate into Uzbek Latin. Output ONLY the translation.\n\n" + text
    elif target_lang == "en":
        return "Translate into English. Output ONLY the translation.\n\n" + text
    else:
        return "Translate into Russian. Output ONLY the translation.\n\n" + text


async def call_ai(text, target_lang):
    prompt = build_translate_prompt(text, target_lang)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        translation = response.content[0].text

        check_response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            temperature=0.2,
            messages=[{"role": "user", "content": CHECK_PROMPT + translation}],
        )
        result = check_response.content[0].text
        # Convert Markdown bold to HTML bold
        import re
        translation = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', translation)
        translation = re.sub(r'__(.+?)__', r'<i>\1</i>', translation)
        result = fix_uzbek_text(result)
        return result
    except Exception as exc:
        logger.error("API error: %s", exc)
        return "Tarjima xatosi / Oshibka perevoda"


async def detect_language(text):
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": (
                    "What language is this text written in? Reply with ONLY the ISO 639-1 code.\n"
                    "Rules:\n"
                    "- Uzbek Latin (o'zbek, qilish, bo'ladi) = uz\n"
                    "- Russian Cyrillic = ru\n"
                    "- English = en\n"
                    "- Reply ONLY the 2-letter code, nothing else.\n\n"
                    + text[:500]
                ),
            }],
        )
        return response.content[0].text.strip().lower()[:2]
    except Exception:
        return "unknown"


async def transcribe_voice(file_path):
    try:
        with open(file_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="uz",
            )
        return transcription.text
    except Exception as exc:
        logger.error("Transcription error: %s", exc)
        return None


def extract_text_from_pdf(file_path):
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as exc:
        logger.error("PDF error: %s", exc)
        return None


def extract_text_from_docx(file_path):
    try:
        import docx
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        return text.strip()
    except Exception as exc:
        logger.error("DOCX error: %s", exc)
        return None


def after_translate_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f1fa\U0001f1ff UZB", callback_data="lang:uz"),
            InlineKeyboardButton("\U0001f1f7\U0001f1fa RUS", callback_data="lang:ru"),
            InlineKeyboardButton("\U0001f1ec\U0001f1e7 ENG", callback_data="lang:en"),
        ]
    ])


async def cmd_start(update, ctx):
    await update.message.reply_text(
        "Tarjimon bot \u2014 Akademik tarjimon\n\n"
        "Qanday foydalanish:\n\n"
        "\u2022 Matnga reply qiling va yozing: tr\n"
        "  (avtomatik tilni aniqlaydi)\n\n"
        "\u2022 Hujjat yuboring (PDF, Word)\n"
        "  \u2014 avtomatik tarjima qiladi\n\n"
        "\u2022 Ovozli xabar yuboring\n"
        "  \u2014 matnga o'giradi va tarjima qiladi\n\n"
        "Tillar: O'zbekcha \u2194 Ruscha \u2194 English\n\n"
        "Buyruqlar:\n"
        "/start \u2014 boshlash\n"
        "/reset \u2014 avto-rejim",
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
        and text.lower().strip() in ["tr", "translate", "\u043f\u0435\u0440\u0435\u0432\u043e\u0434", "tarjima"]
    ):
        return

    original_text = message.reply_to_message.text_html

    if not original_text:
        await message.reply_text("Matn topilmadi")
        return

    await message.chat.send_action(ChatAction.TYPING)

    detected = await detect_language(original_text)

    if detected == "ru":
        target_lang = "uz"
    elif detected == "uz":
        target_lang = "ru"
    elif detected == "en":
        target_lang = "ru"
    else:
        target_lang = "ru"

    translation = await call_ai(original_text, target_lang)

    if target_lang == "ru":
        combined = original_text + SEPARATOR + translation
    else:
        combined = translation + SEPARATOR + original_text

    chunks = split_message(combined)

    for i, chunk in enumerate(chunks):
        kwargs = {}
        if i == len(chunks) - 1:
            kwargs["reply_markup"] = after_translate_keyboard()
        await message.reply_text(chunk, parse_mode="HTML", **kwargs)

    ctx.user_data["last_text"] = original_text
    ctx.user_data["last_detected"] = detected


async def handle_voice(update, ctx):
    message = update.message
    voice = message.voice or message.audio

    if not voice:
        return

    await message.chat.send_action(ChatAction.TYPING)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        file = await ctx.bot.get_file(voice.file_id)
        await file.download_to_drive(tmp_path)

        transcription = await transcribe_voice(tmp_path)

        if not transcription:
            await message.reply_text("Ovozni aniqlab bo'lmadi / Ne udalos raspoznat golos")
            return

        detected = await detect_language(transcription)

        if detected == "ru":
            target_lang = "uz"
        elif detected == "uz":
            target_lang = "ru"
        elif detected == "en":
            target_lang = "ru"
        else:
            target_lang = "ru"

        translation = await call_ai(transcription, target_lang)

        if target_lang == "ru":
            combined = transcription + SEPARATOR + translation
        else:
            combined = translation + SEPARATOR + transcription

        chunks = split_message(combined)

        for i, chunk in enumerate(chunks):
            kwargs = {}
            if i == len(chunks) - 1:
                kwargs["reply_markup"] = after_translate_keyboard()
            await message.reply_text(chunk, **kwargs)

        ctx.user_data["last_text"] = transcription

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def handle_document(update, ctx):
    message = update.message
    document = message.document

    if not document:
        return

    file_name = document.file_name or ""
    file_ext = file_name.lower().split(".")[-1] if "." in file_name else ""

    if file_ext not in ("pdf", "docx", "doc", "txt"):
        await message.reply_text(
            "Qo'llab-quvvatlanadigan formatlar: PDF, DOCX, TXT\n"
            "Podderzhivayemye formaty: PDF, DOCX, TXT"
        )
        return

    await message.chat.send_action(ChatAction.TYPING)

    with tempfile.NamedTemporaryFile(suffix="." + file_ext, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        file = await ctx.bot.get_file(document.file_id)
        await file.download_to_drive(tmp_path)

        if file_ext == "pdf":
            text = extract_text_from_pdf(tmp_path)
        elif file_ext in ("docx", "doc"):
            text = extract_text_from_docx(tmp_path)
        elif file_ext == "txt":
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
        else:
            text = None

        if not text:
            await message.reply_text(
                "Matnni ajratib bo'lmadi / Ne udalos izvlech tekst"
            )
            return

        if len(text) > 15000:
            text = text[:15000]
            await message.reply_text("Hujjat juda katta, faqat birinchi qismi tarjima qilinadi.")

        detected = await detect_language(text)

        if detected == "ru":
            target_lang = "uz"
        elif detected == "uz":
            target_lang = "ru"
        elif detected == "en":
            target_lang = "ru"
        else:
            target_lang = "ru"

        translation = await call_ai(text, target_lang)

        header = "\U0001f4c4 " + file_name + "\n\n"
        result = header + translation

        chunks = split_message(result)

        for i, chunk in enumerate(chunks):
            kwargs = {}
            if i == len(chunks) - 1:
                kwargs["reply_markup"] = after_translate_keyboard()
            await message.reply_text(chunk, **kwargs)

        ctx.user_data["last_text"] = text

    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def callback_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("lang:"):
        lang_code = data.split(":")[1]
        last_text = ctx.user_data.get("last_text")

        if not last_text:
            await query.message.reply_text("Matn topilmadi. Qayta yuboring.")
            return

        await query.message.chat.send_action(ChatAction.TYPING)

        translation = await call_ai(last_text, lang_code)

        chunks = split_message(translation)

        for i, chunk in enumerate(chunks):
            kwargs = {}
            if i == len(chunks) - 1:
                kwargs["reply_markup"] = after_translate_keyboard()
            await query.message.reply_text(chunk, **kwargs)


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
        BotCommand("start", "Boshlash / Start"),
        BotCommand("reset", "Avto-rejim / Reset"),
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
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
