async def handle_message(update, ctx):

    message = update.message
    text = message.text

    if not text:
        return

    # работает только если reply + команда
    if not (
        message.reply_to_message
        and text.lower().strip() in ["tr", "translate", "перевод", "tarjima"]
    ):
        return

    # берем текст без html чтобы Claude переводил нормально
    original_text = message.reply_to_message.text

    if not original_text:
        await message.reply_text("Нет текста для перевода")
        return

    user_id = update.effective_user.id

    await message.chat.send_action(ChatAction.TYPING)

    target_lang = get_user_lang(user_id)

    # если пользователь вручную выбрал язык
    if target_lang:

        result = await call_ai(original_text, target_lang)

    else:

        detected = await detect_language(original_text)

        if detected:
            detected = detected.strip().lower()
        else:
            detected = ""

        # строгая логика RU ↔ UZ
        if detected.startswith("ru"):
            target_lang = "uz"

        elif detected.startswith("uz"):
            target_lang = "ru"

        else:
            # если язык неизвестен
            target_lang = "ru"

        result = await call_ai(
            original_text,
            target_lang,
            source_lang=detected
        )

    chunks = split_message(result)

    for i, chunk in enumerate(chunks):

        kwargs = {}

        if i == len(chunks) - 1:
            kwargs["reply_markup"] = after_translate_keyboard()

        await message.reply_text(
            chunk,
            **kwargs
        )

    ctx.user_data["last_text"] = original_text
