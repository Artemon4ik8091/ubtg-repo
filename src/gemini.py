# requires: aiohttp aiohttp-socks
# ---------------------------------------------------------------------------------
# Name: Gemini
# Description: Интеграция с Google Gemini AI (поддержка текста, анализа фото, кастомных правил и собственного API-ключа)
#
# ИНСТРУКЦИЯ ПО НАСТРОЙКЕ МОДУЛЯ:
# 1. Получение ключа:
#    - Перейдите на сайт Google AI Studio: https://aistudio.google.com/app/apikey
#    - Войдите в Google-аккаунт и нажмите «Create API key».
#    - Скопируйте полученный ключ.
#
# 2. Установка ключа:
#    - Выполните команду: .gemini_key <ваш_ключ>
#    - Или через интерактивное меню: .cfg -> Пользовательские модули -> gemini -> api_key
#
# 3. Настройка правил (системного промпта):
#    - Выполните: .gemini_rules <ваши правила>
#    - Или сделайте реплай командой .gemini_rules на сообщение с подробным промптом.
#    - Сброс правил: .gemini_rules clear
#
# 4. Выбор модели:
#    - По умолчанию: gemini-2.5-flash
#    - Смена модели: .gemini_model gemini-1.5-pro (или .gemini_model gemini-2.5-flash)
#    - Список доступных моделей: .gemini_models
#
# 5. Настройка прокси (при необходимости):
#    - Установить: .gemini_proxy http://login:pass@ip:port (или socks5://...)
#    - Сбросить: .gemini_proxy clear
#
# 6. Использование:
#    - Обычный запрос: .gemini <текст> или .ai <текст>
#    - Реплай на текст: .gemini [вопрос] (использует сообщение как контекст)
#    - Анализ фото: .gemini [вопрос] в ответ на фото
#    - Пошаговое руководство в Telegram: .gemini_setup
# ---------------------------------------------------------------------------------

import asyncio
import base64
import json
import os
import re
import html as py_html
import aiohttp
from telethon import errors

from registry import (
    register_cmd,
    set_module_meta,
    init_config,
    get_config,
    set_config,
    delete_config,
    get_logger
)

logger = get_logger("Gemini")

set_module_meta(
    name="Gemini",
    desc="Интеграция с Google Gemini AI (поддержка текста, анализа фото, кастомных правил и собственного API-ключа)",
    system=False
)

# Инициализируем конфигурацию модуля
init_config(__name__, {
    "api_key": "",
    "rules": "",
    "model": "gemini-2.5-flash",
    "temperature": 0.7,
    "max_tokens": 4096,
    "history_enabled": True,
    "show_model_footer": True,
    "expandable_threshold": 250,
    "proxy": ""
})

# Локальная история диалогов по ID чата: chat_id -> list of contents
_chat_histories = {}
MAX_HISTORY_ENTRIES = 10  # максимум 10 сообщений (5 раундов) в памяти


def _mask_key(key: str) -> str:
    """Маскирует API-ключ для безопасного отображения."""
    if not key:
        return "Не задан"
    clean = key.strip()
    if len(clean) > 10:
        return f"`{clean[:6]}...{clean[-4:]}`"
    return "`****`"


def _get_active_api_key() -> str:
    """Получает ключ из конфигурации модуля или переменных окружения."""
    key = get_config(__name__, "api_key", default="")
    if isinstance(key, str) and key.strip():
        return key.strip()
    env_key = os.getenv("GEMINI_API_KEY", "")
    return env_key.strip()


def _get_proxy_url() -> str:
    """
    Возвращает URL прокси:
    1. Из конфигурации модуля gemini ("proxy").
    2. Из core_conf.json (если в юзерботе настроен прокси для Telegram).
    3. Из переменных окружения HTTPS_PROXY, HTTP_PROXY, ALL_PROXY.
    """
    mod_proxy = get_config(__name__, "proxy", default="")
    if isinstance(mod_proxy, str) and mod_proxy.strip():
        return mod_proxy.strip()

    # Проверяем переменные окружения
    for env_var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.getenv(env_var, "").strip()
        if val:
            return val

    # Проверяем core_conf.json
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        conf_path = os.path.join(base_dir, "core_conf.json")
        if os.path.exists(conf_path):
            with open(conf_path, "r", encoding="utf-8") as f:
                core_data = json.load(f)
            p = core_data.get("proxy")
            if isinstance(p, dict) and p.get("addr") and p.get("port"):
                ptype = p.get("proxy_type", "http").lower()
                user = p.get("username")
                pwd = p.get("password")
                auth = f"{user}:{pwd}@" if user and pwd else ""
                return f"{ptype}://{auth}{p['addr']}:{p['port']}"
    except Exception as e:
        logger.debug(f"Ошибка проверки proxy в core_conf: {e}")

    return ""


def _normalize_model_name(model_name: str) -> str:
    """Нормализует имя модели для запросов к Google API."""
    clean = (model_name or "gemini-2.5-flash").strip()
    if clean.startswith("models/"):
        return clean
    return f"models/{clean}"


def markdown_to_telegram_html(text: str) -> str:
    """
    Преобразует базовый Markdown в валидный HTML для Telegram.
    Корректно сохраняет блоки кода, инлайн-код, экранирует спецсимволы,
    заменяет заголовки, жирный текст, курсив, зачеркивание и ссылки.
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 1. Защищаем блоки кода ```lang\ncode\n```
    code_blocks = []
    def _save_cb(m):
        lang = (m.group(1) or "").strip()
        code = m.group(2)
        code_esc = py_html.escape(code)
        idx = len(code_blocks)
        if lang:
            code_blocks.append(f'<pre><code class="language-{lang}">{code_esc}</code></pre>')
        else:
            code_blocks.append(f'<pre>{code_esc}</pre>')
        return f'__TG_CB_{idx}__'

    text = re.sub(r'```([a-zA-Z0-9_\-\+\#]*)\n?(.*?)```', _save_cb, text, flags=re.DOTALL)

    # 2. Защищаем инлайн-код `code`
    inline_codes = []
    def _save_ic(m):
        code = m.group(1)
        code_esc = py_html.escape(code)
        idx = len(inline_codes)
        inline_codes.append(f'<code>{code_esc}</code>')
        return f'__TG_IC_{idx}__'

    text = re.sub(r'`([^`\n]+)`', _save_ic, text)

    # 3. Экранируем спецсимволы HTML
    text = py_html.escape(text)

    # 4. Заголовки: # Заголовок -> <b>Заголовок</b>
    text = re.sub(r'^(#{1,6})\s+(.+)$', r'<b>\2</b>', text, flags=re.MULTILINE)

    # 5. Ссылки: [текст](url)
    text = re.sub(r'\[(.*?)\]\((https?://[^\s\)]+)\)', r'<a href="\2">\1</a>', text)

    # 6. Жирный текст: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)

    # 7. Зачеркнутый текст: ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text, flags=re.DOTALL)

    # 8. Курсив: *text* или _text_ (без совпадений внутри слов)
    text = re.sub(r'(?<!\w)\*([^\*\n]+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_\n]+?)_(?!\w)', r'<i>\1</i>', text)

    # 9. Возвращаем инлайн-код и блоки кода
    for i, ic in enumerate(inline_codes):
        text = text.replace(f'__TG_IC_{i}__', ic)
    for i, cb in enumerate(code_blocks):
        text = text.replace(f'__TG_CB_{i}__', cb)

    return text


def _format_gemini_messages(
    prompt: str,
    answer: str,
    model: str,
    threshold: int = 250,
    is_photo: bool = False,
    show_model: bool = True
) -> list:
    """
    Формирует список частей сообщения с HTML-разметкой цитат:
    - Запрос пользователя оборачивается в <blockquote> (или <blockquote expandable>, если сам запрос длинный).
    - Ответ модели оборачивается в цитату. Если ответ длинный (превышает threshold символов
      или содержит >= 4 строк) — цитата делается сворачиваемой (<blockquote expandable>).
    - При необходимости разбивает длинный ответ на несколько сообщений.
    """
    prompt_clean = (prompt or "").strip()
    prompt_html = markdown_to_telegram_html(prompt_clean)
    is_prompt_long = len(prompt_clean) > threshold or prompt_clean.count("\n") >= 4
    prompt_tag = "blockquote expandable" if is_prompt_long else "blockquote"
    q_icon = "🖼 Запрос (к фото):" if is_photo else "💬 Запрос:"
    q_block = f"<b>{q_icon}</b>\n<{prompt_tag}>{prompt_html}</{prompt_tag.split()[0]}>\n\n"

    clean_model = model.replace("models/", "")
    answer_hdr = f"<b>🤖 Gemini ({clean_model}):</b>\n" if show_model else "<b>🤖 Ответ:</b>\n"

    # Лимит символов исходного текста ответа на одну часть
    limit = 3200
    answer_raw = answer.strip()
    chunks = []
    rem = answer_raw
    while rem:
        if len(rem) <= limit:
            chunks.append(rem)
            break
        split_at = rem.rfind("\n\n", 0, limit)
        if split_at == -1 or split_at < limit // 3:
            split_at = rem.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 3:
            split_at = rem.rfind(" ", 0, limit)
        if split_at == -1 or split_at < limit // 4:
            split_at = limit
        chunks.append(rem[:split_at].rstrip())
        rem = rem[split_at:].lstrip()

    html_chunks = []
    for idx, chunk in enumerate(chunks):
        chunk_html = markdown_to_telegram_html(chunk)
        is_ans_long = len(chunk) > threshold or chunk.count("\n") >= 4
        ans_tag = "blockquote expandable" if is_ans_long else "blockquote"

        if idx == 0:
            full_html = f"{q_block}{answer_hdr}<{ans_tag}>{chunk_html}</{ans_tag.split()[0]}>"
        else:
            hdr = f"<b>🤖 Gemini ({clean_model}) [Продолжение]:</b>\n"
            full_html = f"{hdr}<{ans_tag}>{chunk_html}</{ans_tag.split()[0]}>"
        html_chunks.append(full_html)

    return html_chunks


async def _send_html_multimessage(client, event, html_chunks: list, fallback_text: str = ""):
    """
    Отправляет сообщения в чат с parse_mode='html'.
    В случае ошибки парсинга разметки выполняет безопасный fallback.
    """
    if not html_chunks:
        return

    # Редактируем первое сообщение
    try:
        await event.edit(html_chunks[0], parse_mode="html")
    except Exception as e:
        logger.debug(f"Ошибка edit с parse_mode='html': {e}, пробуем fallback")
        try:
            await event.edit(fallback_text or html_chunks[0], parse_mode=None)
        except Exception as e2:
            logger.error(f"Ошибка fallback edit: {e2}")

    # Последующие части отправляем новыми сообщениями в чат
    for chunk in html_chunks[1:]:
        await asyncio.sleep(0.35)
        try:
            await client.send_message(event.chat_id, chunk, reply_to=event.id, parse_mode="html")
        except Exception:
            try:
                await client.send_message(event.chat_id, chunk, reply_to=event.id, parse_mode=None)
            except Exception as e:
                logger.debug(f"Ошибка при отправке продолжения: {e}")


async def _send_multimessage(client, event, full_text: str):
    """
    Редактирует исходное сообщение первой частью и, если текст длинный,
    отправляет оставшиеся части новыми сообщениями.
    """
    limit = 4000
    if len(full_text) <= limit:
        chunks = [full_text]
    else:
        chunks = []
        rem = full_text
        while rem:
            if len(rem) <= limit:
                chunks.append(rem)
                break
            split_at = rem.rfind("\n\n", 0, limit)
            if split_at == -1 or split_at < limit // 3:
                split_at = rem.rfind("\n", 0, limit)
            if split_at == -1 or split_at < limit // 3:
                split_at = rem.rfind(" ", 0, limit)
            if split_at == -1 or split_at < limit // 4:
                split_at = limit
            chunks.append(rem[:split_at].rstrip())
            rem = rem[split_at:].lstrip()

    if not chunks:
        return

    try:
        await event.edit(chunks[0])
    except Exception:
        try:
            await event.edit(chunks[0], parse_mode=None)
        except Exception as e:
            logger.debug(f"Ошибка при edit первой части: {e}")

    for chunk in chunks[1:]:
        await asyncio.sleep(0.35)
        try:
            await client.send_message(event.chat_id, chunk, reply_to=event.id)
        except Exception:
            try:
                await client.send_message(event.chat_id, chunk, reply_to=event.id, parse_mode=None)
            except Exception as e:
                logger.debug(f"Ошибка при отправке продолжения: {e}")


async def _call_gemini_generate(
    api_key: str,
    model: str,
    contents: list,
    system_instruction: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096
) -> str:
    """
    Асинхронный вызов Google Generative Language API (REST v1beta).
    """
    model_path = _normalize_model_name(model)
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent?key={api_key}"

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_tokens)
        }
    }

    if system_instruction and system_instruction.strip():
        payload["system_instruction"] = {
            "parts": [
                {"text": system_instruction.strip()}
            ]
        }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    timeout = aiohttp.ClientTimeout(total=90)
    proxy_url = _get_proxy_url()

    connector = None
    post_kwargs = {}
    if proxy_url:
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(proxy_url)
        except Exception as pe:
            logger.debug(f"Не удалось использовать aiohttp_socks в gemini: {pe}")
            if proxy_url.startswith("http"):
                post_kwargs["proxy"] = proxy_url

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers, **post_kwargs) as resp:
            status = resp.status
            try:
                data = await resp.json()
            except Exception:
                raw_txt = await resp.text()
                data = {"error": {"message": raw_txt}}

            if not isinstance(data, dict):
                data = {"error": {"message": str(data)}}

            if status != 200:
                err_obj = data.get("error", {})
                if isinstance(err_obj, dict):
                    err_msg = str(err_obj.get("message") or err_obj.get("status") or err_obj)
                    err_status = str(err_obj.get("status", ""))
                else:
                    err_msg = str(err_obj)
                    err_status = ""

                if status == 400 and ("API_KEY_INVALID" in err_msg or "not valid" in err_msg.lower()):
                    raise RuntimeError("Неверный API-ключ Google Gemini. Задайте корректный ключ командой: `.gemini_key <ключ>`")
                elif status == 429 or "RESOURCE_EXHAUSTED" in err_status:
                    raise RuntimeError("Превышен лимит запросов Google Gemini API (Rate Limit / Quota). Подождите минуту.")
                elif status == 404:
                    raise RuntimeError(f"Модель `{model}` не найдена в API Google. Проверьте имя модели через `.gemini_models` или выберите `gemini-2.5-flash`.")
                else:
                    raise RuntimeError(f"Ошибка Google Gemini API [{status}]: {err_msg}")

            # Проверяем фильтры блокировки запроса
            prompt_feedback = data.get("promptFeedback", {})
            block_reason = prompt_feedback.get("blockReason")
            if block_reason:
                raise RuntimeError(f"Запрос заблокирован политиками безопасности Google Gemini ({block_reason}).")

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("Модель не вернула ни одного варианта ответа.")

            cand = candidates[0]
            finish_reason = cand.get("finishReason", "")
            content = cand.get("content", {})
            parts = content.get("parts", [])

            result_text = "".join([p.get("text", "") for p in parts if "text" in p]).strip()

            if not result_text:
                if finish_reason == "SAFETY":
                    raise RuntimeError("Ответ был заблокирован фильтрами безопасности Google Gemini (Safety Policy).")
                elif finish_reason == "MAX_TOKENS":
                    raise RuntimeError("Генерация прервана из-за лимита токенов (maxOutputTokens).")
                elif finish_reason:
                    raise RuntimeError(f"Пустой ответ модели (finishReason: {finish_reason}).")
                else:
                    raise RuntimeError("Модель вернула пустой ответ.")

            return result_text


# =================================================================================
# КОМАНДЫ МОДУЛЯ
# =================================================================================

@register_cmd("gemini", desc="Запрос к Gemini AI (текст, реплаи, анализ фото). Юзай: .gemini <запрос>")
@register_cmd("ai", desc="Алиас для .gemini")
async def gemini_cmd(client, event, args):
    """
    Основная команда общения с Gemini AI.
    - Принимает текст запроса.
    - Поддерживает реплай на другое сообщение (использует его как контекст).
    - Поддерживает фото/картинки (как в реплае, так и прикрепленные к сообщению).
    """
    api_key = _get_active_api_key()
    if not api_key:
        return await event.edit(
            "❌ **API-ключ Google Gemini не задан!**\n\n"
            "📖 Для подробной пошаговой инструкции напишите:\n"
            "`.gemini_setup`\n\n"
            "⚡ **Быстрый старт:**\n"
            "1. Получите бесплатный ключ: [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
            "2. Установите его: `.gemini_key ВАШ_КЛЮЧ`\n"
            "3. Задайте правила: `.gemini_rules <ваши правила>`\n\n"
            "💡 *Также доступно через инлайн-меню* `.cfg`"
        )

    # Проверяем реплай
    reply_msg = await event.get_reply_message()

    # Определяем медиафайл (фото/изображение)
    target_media_msg = None
    if event.media and (event.photo or (event.document and getattr(event.document, "mime_type", "").startswith("image/"))):
        target_media_msg = event
    elif reply_msg and reply_msg.media and (reply_msg.photo or (reply_msg.document and getattr(reply_msg.document, "mime_type", "").startswith("image/"))):
        target_media_msg = reply_msg

    # Определяем текст запроса
    user_prompt = (args or "").strip()
    context_text = ""

    if reply_msg and reply_msg.text and not target_media_msg:
        if not user_prompt:
            # Если своего текста нет, берем текст сообщения из реплая как запрос
            user_prompt = reply_msg.text.strip()
        else:
            # Если есть и реплай, и свой вопрос — передаем реплай как контекст
            context_text = reply_msg.text.strip()

    if not user_prompt and not target_media_msg:
        return await event.edit(
            "ℹ️ **Как использовать Gemini:**\n\n"
            "• `.gemini <текст запроса>` — задать вопрос\n"
            "• `.gemini` *(в ответ на сообщение)* — ответить/объяснить сообщение\n"
            "• `.gemini [вопрос]` *(в ответ на фото)* — анализ изображения\n"
            "• `.gemini_help` — подробный список команд"
        )

    # Если это анализ фото без уточняющего вопроса
    if target_media_msg and not user_prompt:
        user_prompt = "Подробно опиши, что изображено на этом изображении, и выдели ключевые детали."

    status_text = "🖼 **Gemini анализирует изображение...**" if target_media_msg else "💭 **Gemini думает...**"
    await event.edit(status_text)

    # Формируем части сообщения пользователя (parts)
    current_parts = []

    # Если есть изображение — скачиваем и кодируем в base64
    if target_media_msg:
        try:
            media_bytes = await client.download_media(target_media_msg, file=bytes)
            if media_bytes:
                # Определяем MIME-тип
                mime_type = "image/jpeg"
                if target_media_msg.document and getattr(target_media_msg.document, "mime_type", ""):
                    mime_type = target_media_msg.document.mime_type

                if len(media_bytes) > 20 * 1024 * 1024:
                    return await event.edit("❌ Изображение слишком большое (лимит Gemini API — 20 МБ).")

                b64_img = base64.b64encode(media_bytes).decode("utf-8")
                current_parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": b64_img
                    }
                })
        except Exception as e:
            logger.error(f"Ошибка скачивания медиа: {e}")
            return await event.edit(f"❌ Не удалось загрузить изображение: `{e}`")

    # Формируем финальный текстовый промпт с учетом контекста
    if context_text:
        final_prompt_text = (
            f"Контекст (сообщение, на которое дан ответ):\n\"\"\"\n{context_text}\n\"\"\"\n\n"
            f"Запрос пользователя:\n{user_prompt}"
        )
    else:
        final_prompt_text = user_prompt

    current_parts.append({"text": final_prompt_text})

    # Считываем конфигурацию
    model = get_config(__name__, "model", default="gemini-2.5-flash")
    rules = get_config(__name__, "rules", default="")
    temperature = get_config(__name__, "temperature", default=0.7)
    max_tokens = get_config(__name__, "max_tokens", default=4096)
    history_enabled = get_config(__name__, "history_enabled", default=True)
    show_footer = get_config(__name__, "show_model_footer", default=True)

    chat_id = event.chat_id

    # Формируем массив contents (с учетом истории диалога)
    contents = []
    if history_enabled and chat_id in _chat_histories and not target_media_msg:
        contents.extend(_chat_histories[chat_id])

    # Добавляем текущее сообщение
    contents.append({
        "role": "user",
        "parts": current_parts
    })

    try:
        answer = await _call_gemini_generate(
            api_key=api_key,
            model=model,
            contents=contents,
            system_instruction=rules,
            temperature=temperature,
            max_tokens=max_tokens
        )
    except Exception as e:
        logger.error(f"Ошибка вызова Gemini: {e}")
        return await event.edit(f"❌ **Ошибка Gemini:**\n`{str(e)}`")

    # Сохраняем в историю (только текстовые реплики, без тяжелых base64 изображений)
    if history_enabled:
        if chat_id not in _chat_histories:
            _chat_histories[chat_id] = []

        _chat_histories[chat_id].append({
            "role": "user",
            "parts": [{"text": final_prompt_text}]
        })
        _chat_histories[chat_id].append({
            "role": "model",
            "parts": [{"text": answer}]
        })
        # Ограничиваем глубину истории
        if len(_chat_histories[chat_id]) > MAX_HISTORY_ENTRIES:
            _chat_histories[chat_id] = _chat_histories[chat_id][-MAX_HISTORY_ENTRIES:]

    # Формируем текст запроса для отображения в цитате
    if target_media_msg and not user_prompt:
        display_prompt = "Анализ изображения (описать детали)"
    elif context_text and user_prompt:
        display_prompt = f"Контекст: {context_text[:120]}...\n{user_prompt}"
    else:
        display_prompt = user_prompt or final_prompt_text

    expand_thresh = get_config(__name__, "expandable_threshold", default=250)
    try:
        expand_thresh = int(expand_thresh)
    except (ValueError, TypeError):
        expand_thresh = 250

    html_chunks = _format_gemini_messages(
        prompt=display_prompt,
        answer=answer,
        model=model,
        threshold=expand_thresh,
        is_photo=bool(target_media_msg),
        show_model=show_footer
    )

    await _send_html_multimessage(client, event, html_chunks, fallback_text=answer)


@register_cmd("gemini_key", desc="Установить или просмотреть API-ключ Gemini (.gemini_key <ключ> | .gemini_key clear)")
async def gemini_key_cmd(client, event, args):
    """Управление API-ключом Gemini."""
    args = (args or "").strip()

    if not args:
        current_key = get_config(__name__, "api_key", default="")
        if current_key:
            return await event.edit(
                f"🔑 **Текущий API-ключ Google Gemini:** {_mask_key(current_key)}\n\n"
                f"• Чтобы обновить: `.gemini_key <новый_ключ>`\n"
                f"• Чтобы удалить: `.gemini_key clear`\n\n"
                f"💡 *Также доступно через* `.cfg`"
            )
        else:
            return await event.edit(
                "❌ **API-ключ Google Gemini не установлен!**\n\n"
                "1. Откройте [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
                "2. Создайте бесплатный API-ключ (Get API key)\n"
                "3. Установите его: `.gemini_key ВАШ_КЛЮЧ`"
            )

    if args.lower() in ("clear", "del", "delete", "reset", "удалить", "сброс"):
        set_config(__name__, "api_key", "")
        return await event.edit("🗑 **API-ключ Google Gemini успешно удален!**")

    # Сохраняем новый ключ
    set_config(__name__, "api_key", args)
    await event.edit(
        f"✅ **API-ключ Google Gemini сохранен!**\n\n"
        f"🔑 **Ключ:** {_mask_key(args)}\n"
        f"🚀 Теперь вы можете пользоваться командами `.gemini <запрос>` и `.ai`."
    )


@register_cmd("gemini_rules", desc="Установить или посмотреть системные правила (промпт) для Gemini. Юзай: .gemini_rules <правила>")
async def gemini_rules_cmd(client, event, args):
    """Управление системной инструкцией / правилами поведения Gemini."""
    args = (args or "").strip()
    reply_msg = await event.get_reply_message()

    # Сброс правил
    if args.lower() in ("clear", "del", "delete", "reset", "удалить", "сброс"):
        set_config(__name__, "rules", "")
        return await event.edit("🗑 **Системные правила Gemini сброшены!**\nМодель будет использовать стандартное поведение.")

    # Если текста в аргументах нет, но есть реплай на сообщение — берем текст реплая
    new_rules = args
    if not new_rules and reply_msg and reply_msg.text:
        new_rules = reply_msg.text.strip()

    if not new_rules:
        current_rules = get_config(__name__, "rules", default="")
        if current_rules:
            return await event.edit(
                f"📜 **Текущие правила (системный промпт) Gemini:**\n\n"
                f"```\n{current_rules}\n```\n\n"
                f"• Изменить: `.gemini_rules <новый текст>` (или ответьте командой на длинное сообщение)\n"
                f"• Сбросить: `.gemini_rules clear`\n"
                f"💡 *Также доступно через* `.cfg`"
            )
        else:
            return await event.edit(
                "ℹ️ **Кастомные правила для Gemini не заданы.**\n"
                "Модель отвечает в стандартном режиме.\n\n"
                "**Как задать правила:**\n"
                "• `.gemini_rules Отвечай кратко, саркастично и только по делу.`\n"
                "• Или отправьте длинный текст правил в чат и сделайте на него реплай с командой `.gemini_rules`"
            )

    # Сохраняем правила в Global_config.json
    set_config(__name__, "rules", new_rules)
    await event.edit(
        f"✅ **Системные правила Gemini успешно сохранены!**\n\n"
        f"📜 **Правила:**\n"
        f"```\n{new_rules}\n```\n\n"
        f"💡 *Все последующие запросы `.gemini` будут следовать этим правилам.*"
    )


@register_cmd("gemini_model", desc="Выбрать или просмотреть текущую модель Gemini. Юзай: .gemini_model [имя]")
async def gemini_model_cmd(client, event, args):
    """Просмотр и переключение активной модели Gemini."""
    args = (args or "").strip()

    if not args:
        current_model = get_config(__name__, "model", default="gemini-2.5-flash")
        return await event.edit(
            f"🧠 **Текущая модель Gemini:** `{current_model}`\n\n"
            f"**Популярные и рекомендуемые модели:**\n"
            f"• `gemini-2.5-flash` — быстрая, новейшая и универсальная (по умолчанию)\n"
            f"• `gemini-2.0-flash` — предыдущая версия Flash\n"
            f"• `gemini-1.5-pro` — максимальное качество для сложных рассуждений и кода\n"
            f"• `gemini-1.5-flash` — быстрая облегченная модель\n\n"
            f"💡 Для смены: `.gemini_model <имя_модели>`\n"
            f"🔍 Посмотреть полный список доступных моделей: `.gemini_models`"
        )

    clean_model = args.replace("models/", "").strip()
    set_config(__name__, "model", clean_model)
    await event.edit(f"✅ **Активная модель Gemini переключена на:** `{clean_model}`")


@register_cmd("gemini_models", desc="Получить список всех доступных моделей из Google Gemini API")
async def gemini_models_cmd(client, event, args):
    """Запрашивает список доступных моделей через Google API."""
    api_key = _get_active_api_key()
    if not api_key:
        return await event.edit("❌ Сначала укажите API-ключ: `.gemini_key <ключ>`")

    await event.edit("🔍 **Запрашиваю список доступных моделей у Google API...**")

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    timeout = aiohttp.ClientTimeout(total=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    err_txt = await resp.text()
                    return await event.edit(f"❌ Ошибка получения моделей [{resp.status}]:\n`{err_txt}`")

                data = await resp.json()
                models_list = data.get("models", [])
                if not models_list:
                    return await event.edit("ℹ️ Google API не вернул моделей.")

                current_model = get_config(__name__, "model", default="gemini-2.5-flash")
                gen_models = []
                for m in models_list:
                    name = m.get("name", "").replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        display = m.get("displayName", name)
                        mark = " 🟢 *(активна)*" if name == current_model else ""
                        gen_models.append(f"• `{name}` — {display}{mark}")

                text = (
                    f"📋 **Доступные модели Google Gemini ({len(gen_models)}):**\n\n"
                    + "\n".join(gen_models[:25])
                    + "\n\n💡 Переключить: `.gemini_model <имя>`"
                )
                await _send_multimessage(client, event, text)
    except Exception as e:
        logger.error(f"Ошибка в gemini_models: {e}")
        await event.edit(f"❌ Ошибка запроса к API: `{e}`")


@register_cmd("gemini_temp", desc="Установить креативность (температуру) от 0.0 до 2.0. Юзай: .gemini_temp [число]")
async def gemini_temp_cmd(client, event, args):
    """Настройка температуры ответов."""
    args = (args or "").strip()

    if not args:
        current_temp = get_config(__name__, "temperature", default=0.7)
        return await event.edit(
            f"🌡 **Текущая температура Gemini:** `{current_temp}`\n\n"
            f"• `0.0` — `0.3`: Точные, фактологические и строгие ответы\n"
            f"• `0.4` — `0.7`: Оптимальный сбалансированный режим (по умолчанию `0.7`)\n"
            f"• `0.8` — `2.0`: Творческий, свободный и креативный режим\n\n"
            f"💡 Для изменения: `.gemini_temp 0.5`"
        )

    try:
        new_temp = float(args.replace(",", "."))
        if not (0.0 <= new_temp <= 2.0):
            return await event.edit("❌ Температура должна быть числом от `0.0` до `2.0`!")

        set_config(__name__, "temperature", round(new_temp, 2))
        await event.edit(f"✅ **Температура Gemini установлена на:** `{round(new_temp, 2)}`")
    except ValueError:
        await event.edit("❌ Неверный формат числа! Пример: `.gemini_temp 0.7`")


@register_cmd("gemini_history", desc="Включить или выключить память контекста диалога (.gemini_history on|off)")
async def gemini_history_cmd(client, event, args):
    """Включение/выключение контекстной памяти диалога."""
    args = (args or "").strip().lower()

    if not args:
        is_enabled = get_config(__name__, "history_enabled", default=True)
        status_str = "🟢 **Включена**" if is_enabled else "🔴 **Отключена**"
        return await event.edit(
            f"🧠 **Память диалога Gemini:** {status_str}\n\n"
            f"• Включить: `.gemini_history on`\n"
            f"• Отключить: `.gemini_history off`\n"
            f"• Очистить текущий диалог: `.gemini_clear`"
        )

    if args in ("on", "1", "true", "вкл", "да"):
        set_config(__name__, "history_enabled", True)
        await event.edit("🟢 **Память диалога Gemini включена!** Бот будет учитывать контекст предыдущих реплик.")
    elif args in ("off", "0", "false", "выкл", "нет"):
        set_config(__name__, "history_enabled", False)
        # Очищаем память текущего чата при выключении
        _chat_histories.pop(event.chat_id, None)
        await event.edit("🔴 **Память диалога Gemini отключена!** Каждый запрос будет обрабатываться независимо.")
    else:
        await event.edit("❌ Укажите `on` или `off`: `.gemini_history on`")


@register_cmd("gemini_clear", desc="Очистить историю диалога Gemini в текущем чате")
@register_cmd("gemini_reset", desc="Алиас для .gemini_clear")
async def gemini_clear_cmd(client, event, args):
    """Сброс истории диалога в текущем чате."""
    chat_id = event.chat_id
    if chat_id in _chat_histories:
        _chat_histories.pop(chat_id, None)
    await event.edit("🧹 **История диалога с Gemini для этого чата очищена!** Следующий запрос начнется с чистого листа.")


@register_cmd("gemini_collapse", desc="Порог длины ответа для сворачивания цитаты (символов). Юзай: .gemini_collapse [число]")
async def gemini_collapse_cmd(client, event, args):
    """Настройка порога длины для автоматического сворачивания цитаты ответа."""
    args = (args or "").strip()
    if not args:
        current_th = get_config(__name__, "expandable_threshold", default=250)
        return await event.edit(
            f"📏 **Порог сворачивания цитаты Gemini:** `{current_th}` символов\n\n"
            f"Если ответ превышает это количество символов (или 4+ строк), "
            f"он автоматически оборачивается в **сворачиваемую цитату** с кнопкой «Показать больше».\n\n"
            f"💡 Изменить: `.gemini_collapse 300`\n"
            f"💡 *Также доступно через* `.cfg`"
        )

    try:
        new_th = int(args)
        if new_th < 50 or new_th > 3000:
            return await event.edit("❌ Порог должен быть числом от `50` до `3000` символов.")

        set_config(__name__, "expandable_threshold", new_th)
        await event.edit(f"✅ **Порог сворачивания цитаты установлен на:** `{new_th}` символов.")
    except ValueError:
        await event.edit("❌ Укажите целое число символов! Пример: `.gemini_collapse 250`")


@register_cmd("gemini_proxy", desc="Установить или просмотреть прокси для Gemini (.gemini_proxy <url> | .gemini_proxy clear)")
async def gemini_proxy_cmd(client, event, args):
    """Настройка прокси для запросов к Google Gemini."""
    args = (args or "").strip()

    if not args:
        current_proxy = get_config(__name__, "proxy", default="")
        active_proxy = _get_proxy_url()
        active_info = f"`{active_proxy}`" if active_proxy else "Не используется (прямое подключение)"
        source = "из настроек модуля" if current_proxy else ("из core_conf / переменных окружения" if active_proxy else "")
        if source:
            active_info += f" *({source})*"

        return await event.edit(
            f"🌐 **Прокси для Google Gemini AI:**\n"
            f"• Активный прокси: {active_info}\n\n"
            f"💡 **Установка собственного прокси:**\n"
            f"• HTTP/HTTPS: `.gemini_proxy http://login:pass@ip:port`\n"
            f"• SOCKS5: `.gemini_proxy socks5://login:pass@ip:port`\n"
            f"• Сброс (прямое подключение): `.gemini_proxy clear`"
        )

    if args.lower() in ("clear", "del", "delete", "reset", "удалить", "сброс"):
        set_config(__name__, "proxy", "")
        return await event.edit("🗑 **Прокси Gemini сброшен!** Запросы будут отправляться напрямую.")

    set_config(__name__, "proxy", args)
    await event.edit(
        f"✅ **Прокси для Gemini успешно сохранен!**\n\n"
        f"🌐 **Прокси:** `{args}`\n"
        f"💡 Все последующие запросы `.gemini` и `.gemini_models` будут проходить через этот прокси."
    )


@register_cmd("gemini_setup", desc="Пошаговая инструкция по настройке модуля Gemini. Юзай: .gemini_setup")
@register_cmd("gemini_guide", desc="Алиас для .gemini_setup")
@register_cmd("gemini_instruction", desc="Алиас для .gemini_setup")
async def gemini_setup_cmd(client, event, args):
    """Пошаговое руководство по полной настройке модуля Gemini."""
    current_key = get_config(__name__, "api_key", default="")
    current_rules = get_config(__name__, "rules", default="")
    current_model = get_config(__name__, "model", default="gemini-2.5-flash")
    current_th = get_config(__name__, "expandable_threshold", default=250)
    current_proxy = _get_proxy_url()

    key_status = f"✅ Установлен ({_mask_key(current_key)})" if current_key else "❌ Не установлен"
    rules_status = f"✅ Заданы (`{len(current_rules)}` симв.)" if current_rules else "⚪ Стандартные (не заданы)"
    proxy_status = f"✅ `{current_proxy}`" if current_proxy else "⚪ Прямое подключение"

    setup_guide = (
        "🛠 **Пошаговая инструкция по настройке модуля Google Gemini AI**\n\n"
        "**Шаг 1: Получение бесплатного API-ключа**\n"
        "1. Перейдите на сайт [Google AI Studio](https://aistudio.google.com/app/apikey).\n"
        "2. Войдите в свой Google-аккаунт.\n"
        "3. Нажмите кнопку **«Create API key»** (или «Get API key»).\n"
        "4. Выберите проект Google Cloud (или создайте новый в один клик) и скопируйте созданный ключ вида `AIzaSy...`.\n"
        "*(Google AI Studio предоставляет бесплатный тариф с высокими лимитами для персонального использования)*.\n\n"
        "**Шаг 2: Установка API-ключа в юзербот**\n"
        "Отправьте команду с вашим ключом в любой чат:\n"
        "`.gemini_key ВАШ_API_КЛЮЧ`\n"
        "• Проверить статус ключа: `.gemini_key`\n"
        "• Удалить ключ: `.gemini_key clear`\n\n"
        "**Шаг 3: Настройка кастомных правил (System Instructions)**\n"
        "Кастомные правила определяют стиль, роль, ограничения и поведение ИИ.\n"
        "• **Быстрая команда:**\n"
        "`.gemini_rules Отвечай кратко, саркастично, пиши чистый код на Python без лишних слов.`\n"
        "• **Установка длинных правил из сообщения:**\n"
        "Отправьте подробный текст правил в чат (или в Избранное) и ответьте на него командой `.gemini_rules`.\n"
        "• Посмотреть активные правила: `.gemini_rules`\n"
        "• Сбросить правила: `.gemini_rules clear`\n\n"
        "**Шаг 4: Выбор активной модели**\n"
        "• Посмотреть текущую модель: `.gemini_model`\n"
        "• Сменить модель: `.gemini_model <имя>`\n"
        "  - `gemini-2.5-flash` — быстрая, новейшая и универсальная (по умолчанию)\n"
        "  - `gemini-1.5-pro` — глубокие рассуждения и сложный кодинг\n"
        "• Проверить доступные модели для вашего ключа: `.gemini_models`\n\n"
        "**Шаг 5: Прокси и дополнительные настройки**\n"
        "• Прокси (при необходимости): `.gemini_proxy http://login:pass@ip:port`\n"
        "• Порог сворачивания цитаты ответа: `.gemini_collapse [символов]` (сейчас `{current_th}`)\n"
        "  *(Запрос и ответ оборачиваются в цитаты; если ответ длинный — цитата сворачивается)*\n"
        "• Креативность (температура): `.gemini_temp 0.7` (от 0.0 до 2.0)\n"
        "• Контекст диалога: `.gemini_history on` или `.gemini_history off`\n"
        "• Очистить память диалога в текущем чате: `.gemini_clear`\n\n"
        "⚙️ **Управление через панель конфигурации:**\n"
        "Все настройки также можно менять в интерактивном меню: `.cfg` -> Пользовательские модули -> `gemini`.\n\n"
        f"📊 **Текущее состояние вашей конфигурации:**\n"
        f"• API-ключ: {key_status}\n"
        f"• Прокси: {proxy_status}\n"
        f"• Модель: `{current_model}`\n"
        f"• Правила: {rules_status}\n"
        f"• Порог сворачивания: `{current_th}` симв."
    )
    await _send_multimessage(client, event, setup_guide)


@register_cmd("gemini_help", desc="Подробная справка по командам и настройке модуля Gemini")
async def gemini_help_cmd(client, event, args):
    """Справка по модулю Gemini."""
    current_key = get_config(__name__, "api_key", default="")
    current_model = get_config(__name__, "model", default="gemini-2.5-flash")
    current_rules = get_config(__name__, "rules", default="")
    current_th = get_config(__name__, "expandable_threshold", default=250)
    current_proxy = _get_proxy_url()
    has_rules = "Установлены ✅" if current_rules else "Не заданы ❌"
    proxy_str = f"`{current_proxy}`" if current_proxy else "Прямое подключение"

    help_text = (
        "✨ **Google Gemini AI — Справка по модулю**\n\n"
        "📖 **Пошаговая инструкция по настройке:** `.gemini_setup`\n\n"
        "**Команды общения:**\n"
        "• `.gemini <запрос>` (или `.ai`) — отправить запрос (запрос и ответ будут в цитатах)\n"
        "• `.gemini` *(реплай на текст)* — объяснить, перевести или дополнить сообщение\n"
        "• `.gemini [вопрос]` *(реплай на фото)* — анализ изображения с помощью Gemini Vision\n\n"
        "**Настройка API-ключа, прокси и правил:**\n"
        "• `.gemini_key <ключ>` — установить собственный API-ключ\n"
        "• `.gemini_key` — проверить статус ключа (`.gemini_key clear` — удалить)\n"
        "• `.gemini_proxy <url>` — установить прокси (`http://...` или `socks5://...`)\n"
        "• `.gemini_proxy clear` — сбросить прокси\n"
        "• `.gemini_rules <правила>` — задать системные правила/поведение для ИИ\n"
        "• `.gemini_rules` *(реплай)* — установить правила из текста сообщения\n"
        "• `.gemini_rules clear` — сбросить системные правила\n\n"
        "**Управление параметрами и цитатами:**\n"
        "• `.gemini_collapse [число]` — настроить порог сворачивания цитаты ответа (символов)\n"
        "• `.gemini_model [имя]` — выбор модели (`gemini-2.5-flash`, `gemini-1.5-pro` и др.)\n"
        "• `.gemini_models` — список доступных моделей из Google API\n"
        "• `.gemini_temp [0.0-2.0]` — настройка креативности/температуры\n"
        "• `.gemini_history [on/off]` — вкл/выкл запоминание контекста диалога\n"
        "• `.gemini_clear` — сбросить контекст диалога в текущем чате\n\n"
        "⚙️ **Интеграция с Global Config:**\n"
        "Все параметры можно также легко настраивать в интерактивном инлайн-меню: `.cfg`\n\n"
        f"📊 **Текущий статус:**\n"
        f"• Ключ: {_mask_key(current_key)}\n"
        f"• Прокси: {proxy_str}\n"
        f"• Модель: `{current_model}`\n"
        f"• Правила: {has_rules}\n"
        f"• Порог сворачивания цитаты: `{current_th}` симв."
    )
    await event.edit(help_text)
