# requires: aiohttp pillow telethon
"""
Модуль: Цитатник (Quotes)
Создание стикеров-цитат из сообщений Telegram (Quotly стиль).
Поддерживает мультицитирование (.q <число>), фейк-цитаты (.fq / .fsq),
кастомные цвета/градиенты, аватары, форматирование и ВСЕ виды медиа
(фото, голосовые, музыка, файлы/документы, видео, кружочки, стикеры, гифки, опросы).
"""

import io
import re
import ssl
import base64
import random
import aiohttp
from telethon import errors
from telethon.tl.types import (
    User,
    Channel,
    Chat,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityStrike,
    MessageEntityUnderline,
    MessageEntitySpoiler,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityCustomEmoji,
    MessageEntityBlockquote,
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    DocumentAttributeAnimated
)
from registry import register_cmd, set_module_meta, init_config, get_config, set_config

# 1. Задаем метаданные модуля
set_module_meta(
    name="Цитатник",
    desc="Создание стикеров-цитат (Quotly стиль). Поддерживает фото, голосовые, музыку, файлы, видео, кружочки, мультицитаты (.q [N]) и фейк-цитаты (.fsq <текст>).",
    system=False
)

# 2. Инициализируем конфигурацию
init_config(__name__, {
    "bg_color": "#1b1429",
    "api_url": "https://quote.yuri.ly/generate",
    "max_messages": 15,
    "scale": 2
})

RANDOM_COLORS = [
    "#1b1429",
    "#201b2d",
    "#1e1e24",
    "#2d132c",
    "#0f3460",
    "#1a1a2e",
    "#2b2e4a",
    "#162447",
    "#1f4068",
    "#1b262c",
    "#0f4c75",
    "#3282b8",
    "#2c3e50",
    "#34495e",
    "#232931",
    "#393e46",
    "#1a3636",
    "#40534c",
    "#222831",
    "#31363f",
    "#1b1429/#2a1b3d",
    "#0f2027/#203a43",
    "#232526/#414345"
]

FALLBACK_ENDPOINTS = [
    "https://quote.yuri.ly/generate",
    "https://bot.lyo.su/quote/generate"
]


def is_color_string(s: str) -> bool:
    """Проверяет, является ли строка цветом, градиентом или ключевым словом цвета."""
    if not s:
        return False
    val = s.strip().lower()
    if val in ("random", "r", "transparent", "black", "white", "red", "green", "blue", "purple", "dark", "pink", "yellow", "orange"):
        return True
    parts = val.split("/")
    if all(re.match(r"^#[0-9a-fA-F]{3,8}$", p) for p in parts):
        return True
    return False


def parse_q_args(args: str):
    """
    Парсит аргументы команды .q
    Возвращает кортеж: (count, bg_color, custom_text)
    """
    args = (args or "").strip()
    if not args:
        return 1, None, None

    parts = args.split()
    count = 1
    bg_color = None
    custom_text = None

    # Если первый аргумент — число (кол-во сообщений)
    if parts[0].isdigit():
        count = max(1, min(int(parts[0]), 15))
        rem = args[len(parts[0]):].strip()
        if rem:
            rem_parts = rem.split(maxsplit=1)
            if is_color_string(rem_parts[0]):
                bg_color = rem_parts[0]
                if len(rem_parts) > 1:
                    custom_text = rem_parts[1]
            else:
                custom_text = rem
        return count, bg_color, custom_text

    # Если первый аргумент — цвет
    if is_color_string(parts[0]):
        bg_color = parts[0]
        rem = args[len(parts[0]):].strip()
        if rem:
            custom_text = rem
        return 1, bg_color, custom_text

    # Все аргументы являются кастомным текстом
    return 1, None, args


def get_display_name(entity):
    """Получает отображаемое имя для пользователя или канала/чата."""
    if not entity:
        return "Anonymous"
    if isinstance(entity, User):
        first = entity.first_name or ""
        last = entity.last_name or ""
        full = f"{first} {last}".strip()
        return full or entity.username or "User"
    if isinstance(entity, (Channel, Chat)):
        return entity.title or "Channel"
    return "User"


def convert_entities(entities):
    """Конвертирует сущности форматирования Telethon в формат Telegram Bot API / Quotly."""
    if not entities:
        return []

    res = []
    for ent in entities:
        ent_data = {"offset": ent.offset, "length": ent.length}
        if isinstance(ent, MessageEntityBold):
            ent_data["type"] = "bold"
        elif isinstance(ent, MessageEntityItalic):
            ent_data["type"] = "italic"
        elif isinstance(ent, MessageEntityCode):
            ent_data["type"] = "code"
        elif isinstance(ent, MessageEntityPre):
            ent_data["type"] = "pre"
            ent_data["language"] = getattr(ent, "language", "")
        elif isinstance(ent, MessageEntityStrike):
            ent_data["type"] = "strikethrough"
        elif isinstance(ent, MessageEntityUnderline):
            ent_data["type"] = "underline"
        elif isinstance(ent, MessageEntitySpoiler):
            ent_data["type"] = "spoiler"
        elif isinstance(ent, MessageEntityTextUrl):
            ent_data["type"] = "text_link"
            ent_data["url"] = ent.url
        elif isinstance(ent, MessageEntityUrl):
            ent_data["type"] = "url"
        elif isinstance(ent, MessageEntityMention):
            ent_data["type"] = "mention"
        elif isinstance(ent, MessageEntityMentionName):
            ent_data["type"] = "text_mention"
            ent_data["user"] = {"id": ent.user_id}
        elif isinstance(ent, MessageEntityCustomEmoji):
            ent_data["type"] = "custom_emoji"
            ent_data["custom_emoji_id"] = str(ent.document_id)
        elif isinstance(ent, MessageEntityBlockquote):
            ent_data["type"] = "blockquote"
        else:
            continue
        res.append(ent_data)
    return res


def unpack_waveform(waveform_bytes):
    """Распаковывает 5-битные значения волны голосового сообщения Telegram."""
    if not waveform_bytes:
        return [0, 4, 8, 16, 24, 18, 12, 6, 12, 18, 24, 16, 8, 4, 0]
    try:
        bits = "".join(f"{b:08b}" for b in waveform_bytes)
        res = []
        for i in range(0, len(bits) - 4, 5):
            res.append(int(bits[i:i+5], 2))
        return res or [0, 4, 8, 16, 24, 18, 12, 6, 12, 18, 24, 16, 8, 4, 0]
    except Exception:
        return [0, 4, 8, 16, 24, 18, 12, 6, 12, 18, 24, 16, 8, 4, 0]


async def extract_message_media(client, msg, msg_dict):
    """Извлекает и обрабатывает все виды медиа (фото, голосовые, музыку, видео, файлы, стикеры, опросы)."""
    if not msg.media:
        return

    try:
        # 1. Фотография
        if hasattr(msg, "photo") and msg.photo:
            thumb = await client.download_media(msg, file=bytes, thumb=-1)
            if not thumb:
                thumb = await client.download_media(msg, file=bytes)
            if thumb and len(thumb) <= 8 * 1024 * 1024:
                b64 = base64.b64encode(thumb).decode("utf-8")
                msg_dict["media"] = {"url": f"data:image/jpeg;base64,{b64}"}

        # 2. Документы (Голосовые, Музыка, Видео, Кружочки, Стикеры, Гифки, Файлы)
        elif hasattr(msg, "document") and msg.document:
            doc = msg.document
            attributes = getattr(doc, "attributes", []) or []
            audio_attr = next((a for a in attributes if isinstance(a, DocumentAttributeAudio)), None)
            video_attr = next((a for a in attributes if isinstance(a, DocumentAttributeVideo)), None)
            sticker_attr = next((a for a in attributes if isinstance(a, DocumentAttributeSticker)), None)
            file_attr = next((a for a in attributes if isinstance(a, DocumentAttributeFilename)), None)
            animated_attr = next((a for a in attributes if isinstance(a, DocumentAttributeAnimated)), None)

            # Голосовое сообщение
            if audio_attr and getattr(audio_attr, "voice", False):
                duration = getattr(audio_attr, "duration", 0) or 0
                wf = unpack_waveform(getattr(audio_attr, "waveform", None))
                msg_dict["voice"] = {"duration": duration, "waveform": wf}

            # Аудиозапись / Музыка
            elif audio_attr and not getattr(audio_attr, "voice", False):
                title = getattr(audio_attr, "title", None) or (file_attr.file_name if file_attr else "Audio")
                performer = getattr(audio_attr, "performer", None) or ""
                duration = getattr(audio_attr, "duration", 0) or 0
                file_size = getattr(doc, "size", 0) or (msg.file.size if msg.file else 0)

                cover_thumb = await client.download_media(msg, file=bytes, thumb=-1)
                cover_dict = None
                if cover_thumb and len(cover_thumb) <= 5 * 1024 * 1024:
                    cover_b64 = base64.b64encode(cover_thumb).decode("utf-8")
                    cover_dict = {"url": f"data:image/jpeg;base64,{cover_b64}"}

                audio_obj = {
                    "title": title or "Track",
                    "performer": performer,
                    "duration": duration,
                    "file_size": file_size
                }
                if cover_dict:
                    audio_obj["cover"] = cover_dict
                msg_dict["audio"] = audio_obj

            # Видео или видеосообщение (кружочек)
            elif video_attr:
                is_round = bool(getattr(video_attr, "round_message", False) or getattr(msg, "video_note", False))
                duration = getattr(video_attr, "duration", 0) or 0
                thumb = await client.download_media(msg, file=bytes, thumb=-1)
                if thumb and len(thumb) <= 8 * 1024 * 1024:
                    b64 = base64.b64encode(thumb).decode("utf-8")
                    msg_dict["media"] = {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "type": "video_note" if is_round else "video",
                        "is_round": is_round,
                        "duration": duration
                    }

            # Стикер
            elif sticker_attr or getattr(msg, "sticker", False):
                thumb = await client.download_media(msg, file=bytes, thumb=-1)
                if not thumb:
                    thumb = await client.download_media(msg, file=bytes)
                if thumb and len(thumb) <= 8 * 1024 * 1024:
                    b64 = base64.b64encode(thumb).decode("utf-8")
                    msg_dict["media"] = {
                        "url": f"data:image/webp;base64,{b64}",
                        "type": "sticker"
                    }

            # Анимация / GIF
            elif animated_attr or getattr(msg, "gif", False):
                thumb = await client.download_media(msg, file=bytes, thumb=-1)
                if thumb and len(thumb) <= 8 * 1024 * 1024:
                    b64 = base64.b64encode(thumb).decode("utf-8")
                    msg_dict["media"] = {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "type": "video"
                    }

            # Обычный файл / Документ
            else:
                file_name = (file_attr.file_name if file_attr else None) or (msg.file.name if msg.file else "Document")
                file_size = getattr(doc, "size", 0) or (msg.file.size if msg.file else 0)
                msg_dict["document"] = {
                    "file_name": file_name,
                    "file_size": file_size
                }

        # 3. Опрос
        elif hasattr(msg.media, "poll") and msg.media.poll:
            poll = msg.media.poll
            q_text = getattr(getattr(poll, "question", None), "text", str(getattr(poll, "question", "Опрос")))
            options = []
            for ans in getattr(poll, "answers", []):
                opt_text = getattr(getattr(ans, "text", None), "text", str(getattr(ans, "text", "")))
                options.append(f"▫️ {opt_text}")
            poll_str = f"📊 **{q_text}**\n" + "\n".join(options)
            if not msg_dict["text"]:
                msg_dict["text"] = poll_str
            else:
                msg_dict["text"] += f"\n\n{poll_str}"

        # 4. Контакт
        elif hasattr(msg.media, "phone_number"):
            contact = msg.media
            c_name = f"{getattr(contact, 'first_name', '')} {getattr(contact, 'last_name', '')}".strip()
            c_str = f"👤 **Контакт:** {c_name} (`{getattr(contact, 'phone_number', '')}`)"
            if not msg_dict["text"]:
                msg_dict["text"] = c_str
            else:
                msg_dict["text"] += f"\n\n{c_str}"

        # 5. Геолокация
        elif hasattr(msg.media, "geo") and msg.media.geo:
            geo = msg.media.geo
            g_str = f"📍 **Геолокация:** `{getattr(geo, 'lat', 0)}`, `{getattr(geo, 'long', 0)}`"
            if not msg_dict["text"]:
                msg_dict["text"] = g_str
            else:
                msg_dict["text"] += f"\n\n{g_str}"

    except Exception:
        pass


async def build_message_obj(client, msg, custom_text=None, avatar_cache=None):
    """Строит объект сообщения для payload API Quotly."""
    if avatar_cache is None:
        avatar_cache = {}

    sender = None
    try:
        sender = await msg.get_sender()
    except Exception:
        pass

    # Определение автора сообщения
    sender_id = msg.sender_id or (sender.id if sender else 1)
    first_name = ""
    last_name = ""
    username = ""
    name = "Anonymous"

    if sender:
        if isinstance(sender, User):
            first_name = sender.first_name or ""
            last_name = sender.last_name or ""
            username = sender.username or ""
            name = f"{first_name} {last_name}".strip() or username or "User"
        elif isinstance(sender, (Channel, Chat)):
            name = sender.title or "Channel"
            first_name = name
            username = getattr(sender, "username", "") or ""
    elif msg.fwd_from:
        if msg.fwd_from.from_name:
            name = msg.fwd_from.from_name
            first_name = name
        elif msg.fwd_from.from_id:
            try:
                fwd_entity = await client.get_entity(msg.fwd_from.from_id)
                name = get_display_name(fwd_entity)
                first_name = name
                sender = fwd_entity
            except Exception:
                name = "Forwarded"
                first_name = name

    # Загрузка и кеширование аватара в памяти
    photo_data = None
    if sender_id not in avatar_cache:
        try:
            target_entity = sender or msg.sender_id
            if target_entity:
                photo_bytes = await client.download_profile_photo(target_entity, file=bytes)
                if photo_bytes:
                    b64 = base64.b64encode(photo_bytes).decode("utf-8")
                    avatar_cache[sender_id] = f"data:image/jpeg;base64,{b64}"
                else:
                    avatar_cache[sender_id] = None
            else:
                avatar_cache[sender_id] = None
        except Exception:
            avatar_cache[sender_id] = None

    if avatar_cache.get(sender_id):
        photo_data = {"url": avatar_cache[sender_id]}

    from_dict = {
        "id": sender_id if isinstance(sender_id, int) else 1,
        "first_name": first_name or name,
        "last_name": last_name,
        "username": username,
        "name": name
    }
    if photo_data:
        from_dict["photo"] = photo_data

    # Текст сообщения и форматирование
    if custom_text is not None:
        text = custom_text
        entities = []
    else:
        text = msg.raw_text or msg.message or ""
        entities = convert_entities(msg.entities)

    msg_dict = {
        "entities": entities,
        "avatar": True,
        "from": from_dict,
        "text": text,
        "replyMessage": {}
    }

    # Поддержка реплая внутри цитируемого сообщения
    if msg.is_reply:
        try:
            sub_reply = await msg.get_reply_message()
            if sub_reply:
                sub_sender = await sub_reply.get_sender()
                sub_name = get_display_name(sub_sender)
                sub_text = sub_reply.raw_text or ("[Медиа]" if sub_reply.media else "")
                if len(sub_text) > 80:
                    sub_text = sub_text[:77] + "..."
                msg_dict["replyMessage"] = {
                    "name": sub_name,
                    "text": sub_text,
                    "chatId": sub_reply.sender_id or 0
                }
        except Exception:
            pass

    # Извлечение всех видов медиа, если это не кастомная фейк-текст цитата
    if not custom_text:
        await extract_message_media(client, msg, msg_dict)

    return msg_dict


async def generate_quote_image(messages_data, bg_color=None):
    """Отправляет запрос к Quotly API для генерации стикера в формате WEBP."""
    configured_bg = get_config(__name__, "bg_color", "#1b1429")
    target_bg = bg_color or configured_bg

    if target_bg in ("r", "random"):
        target_bg = random.choice(RANDOM_COLORS)

    primary_url = get_config(__name__, "api_url", "https://quote.yuri.ly/generate")
    endpoints = [primary_url]
    for ep in FALLBACK_ENDPOINTS:
        if ep not in endpoints:
            endpoints.append(ep)

    scale = get_config(__name__, "scale", 2)
    payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": target_bg,
        "scale": scale,
        "messages": messages_data
    }

    ssl_context = ssl._create_unverified_context()
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    timeout = aiohttp.ClientTimeout(total=25)

    last_error = None
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        for endpoint in endpoints:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (UBTG Quotes Module; Linux x86_64)"
                }
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "json" in content_type:
                            data = await resp.json()
                            if data.get("ok") and "result" in data:
                                raw_img = data["result"]["image"]
                                return base64.b64decode(raw_img)
                            elif "image" in data:
                                return base64.b64decode(data["image"])
                            else:
                                last_error = f"Ответ API не содержит изображения: {data}"
                        else:
                            # Прямой бинарный ответ WEBP
                            img_bytes = await resp.read()
                            if len(img_bytes) > 0:
                                return img_bytes
                    else:
                        resp_text = await resp.text()
                        last_error = f"HTTP {resp.status} от {endpoint}: {resp_text[:100]}"
            except Exception as ex:
                last_error = f"Ошибка подключения к {endpoint}: {ex}"

    raise Exception(last_error or "Не удалось сгенерировать цитату через доступные API.")


@register_cmd("q", desc="Создать цитату в виде стикера. Юзай: .q [кол-во] [цвет/текст]")
async def q_cmd(client, event, args):
    """
    Основная команда создания цитат.
    Использование:
      - .q (в ответ на сообщение) — 1 сообщение с медиа/текстом
      - .q 3 (в ответ на сообщение) — 3 сообщения подряд
      - .q #1b1429 (в ответ) — цитата с указанным цветом фона
      - .q 3 #ff0055 (в ответ) — 3 сообщения с указанным цветом
      - .q r / .q random (в ответ) — случайный градиент/цвет фона
      - .q <текст> (без ответа) — фейк-цитата вашего аккаунта
    """
    count, bg_color, custom_text = parse_q_args(args)
    reply_msg = await event.get_reply_message()

    await event.edit("🎨 **Создаю стикер-цитату...**")

    messages_to_quote = []
    reply_to_target_id = None

    if reply_msg:
        reply_to_target_id = reply_msg.id
        if custom_text and count == 1:
            # Кастомный текст от лица автора ответа (фейк-цитата)
            messages_to_quote = [reply_msg]
        elif count == 1:
            messages_to_quote = [reply_msg]
        else:
            # Захват нескольких сообщений начиная с реплая в хронологическом порядке
            try:
                async for m in client.iter_messages(
                    event.chat_id,
                    min_id=reply_msg.id - 1,
                    limit=count + 15,
                    reverse=True
                ):
                    if m.id == event.id:
                        continue
                    if not (m.raw_text or m.media):
                        continue
                    messages_to_quote.append(m)
                    if len(messages_to_quote) >= count:
                        break
            except Exception:
                pass

            if not messages_to_quote:
                messages_to_quote = [reply_msg]
    else:
        # Если команда вызвана без реплая
        if custom_text and not args.strip().isdigit() and not is_color_string(args.strip()):
            # Создаем цитату текущего пользователя с введенным текстом
            me = await client.get_me()
            fake_msg_dict = {
                "entities": [],
                "avatar": True,
                "from": {
                    "id": me.id,
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "username": me.username or "",
                    "name": get_display_name(me)
                },
                "text": custom_text,
                "replyMessage": {}
            }
            # Аватар владельца
            try:
                photo_bytes = await client.download_profile_photo(me, file=bytes)
                if photo_bytes:
                    b64 = base64.b64encode(photo_bytes).decode("utf-8")
                    fake_msg_dict["from"]["photo"] = {"url": f"data:image/jpeg;base64,{b64}"}
            except Exception:
                pass

            try:
                img_bytes = await generate_quote_image([fake_msg_dict], bg_color)
                sticker_file = io.BytesIO(img_bytes)
                sticker_file.name = "quote.webp"

                await client.send_file(
                    event.chat_id,
                    sticker_file,
                    reply_to=event.reply_to_msg_id
                )
                return await event.delete()
            except Exception as e:
                return await event.edit(f"❌ **Ошибка при создании цитаты:**\n`{e}`")
        else:
            # Захват последних сообщений из чата перед вызовом команды
            try:
                msgs = []
                async for m in client.iter_messages(
                    event.chat_id,
                    max_id=event.id,
                    limit=count + 10
                ):
                    if not (m.raw_text or m.media):
                        continue
                    msgs.append(m)
                    if len(msgs) >= count:
                        break
                msgs.reverse()
                messages_to_quote = msgs
            except Exception:
                pass

            if not messages_to_quote:
                return await event.edit("❌ **Ответьте на сообщение, чтобы создать цитату, или введите текст:** `.q Привет мир`")

    # Сборка объектов сообщений
    avatar_cache = {}
    messages_payload = []

    for idx, msg in enumerate(messages_to_quote):
        c_text = custom_text if (custom_text and len(messages_to_quote) == 1) else None
        try:
            msg_obj = await build_message_obj(
                client=client,
                msg=msg,
                custom_text=c_text,
                avatar_cache=avatar_cache
            )
            messages_payload.append(msg_obj)
        except Exception:
            continue

    if not messages_payload:
        return await event.edit("❌ **Не удалось обработать сообщения для цитаты.**")

    # Генерация стикера и отправка
    try:
        img_bytes = await generate_quote_image(messages_payload, bg_color)
        sticker_file = io.BytesIO(img_bytes)
        sticker_file.name = "quote.webp"

        await client.send_file(
            event.chat_id,
            sticker_file,
            reply_to=reply_to_target_id
        )
        await event.delete()
    except Exception as e:
        await event.edit(f"❌ **Ошибка при создании цитаты:**\n`{e}`")


@register_cmd("quote", desc="Алиас для команды .q")
async def quote_cmd(client, event, args):
    """Алиас для .q"""
    await q_cmd(client, event, args)


@register_cmd("fq", desc="Создать фейк-цитату. Юзай: .fq <текст> (в ответ на сообщение или без)")
async def fq_cmd(client, event, args):
    """Создает цитату с поддельным текстом."""
    if not args:
        return await event.edit("❌ **Укажите текст для фейк-цитаты:** `.fq Привет!`")
    reply_msg = await event.get_reply_message()
    if reply_msg:
        # Вызываем .q с кастомным текстом на реплай
        await q_cmd(client, event, args)
    else:
        # Вызываем .q без реплая для текущего пользователя
        await q_cmd(client, event, args)


@register_cmd("fsq", desc="Фейк-стикер от имени пользователя. Юзай: .fsq <текст> (в ответ на сообщение)")
async def fsq_cmd(client, event, args):
    """
    Создает цитату от имени пользователя, на чье сообщение сделан ответ, с заданным текстом.
    Использование: .fsq <текст> или .fsq <цвет> <текст> (в ответ на сообщение).
    """
    text_arg = (args or "").strip()
    if not text_arg:
        return await event.edit("❌ **Укажите текст для фейк-цитаты:** `.fsq <текст>` (в ответ на сообщение)")

    reply_msg = await event.get_reply_message()
    if not reply_msg:
        return await event.edit("❌ **Ответьте на сообщение человека, от чьего имени сделать цитату:** `.fsq <текст>`")

    # Проверяем, передан ли первым аргументом кастомный цвет (например .fsq #ff0055 Привет мир)
    parts = text_arg.split(maxsplit=1)
    bg_color = None
    custom_text = text_arg
    if is_color_string(parts[0]) and len(parts) > 1:
        bg_color = parts[0]
        custom_text = parts[1]

    await event.edit("🎨 **Создаю фейк-стикер...**")

    try:
        avatar_cache = {}
        msg_obj = await build_message_obj(
            client=client,
            msg=reply_msg,
            custom_text=custom_text,
            avatar_cache=avatar_cache
        )

        img_bytes = await generate_quote_image([msg_obj], bg_color=bg_color)
        sticker_file = io.BytesIO(img_bytes)
        sticker_file.name = "quote.webp"

        await client.send_file(
            event.chat_id,
            sticker_file,
            reply_to=reply_msg.id
        )
        await event.delete()
    except Exception as e:
        await event.edit(f"❌ **Ошибка при создании цитаты:**\n`{e}`")


@register_cmd("qcolor", desc="Установить цвет фона цитат по умолчанию. Юзай: .qcolor <#HEX-цвет/градиент>")
async def qcolor_cmd(client, event, args):
    """Позволяет быстро изменить цвет цитат по умолчанию."""
    color = (args or "").strip()
    if not color:
        cur_color = get_config(__name__, "bg_color", "#1b1429")
        return await event.edit(f"🎨 **Текущий цвет фона цитат:** `{cur_color}`\nИзменить: `.qcolor #1b1429` или `.qcolor #1b1429/#2a1b3d`")

    if not is_color_string(color):
        return await event.edit("❌ **Неверный формат цвета!**\nИспользуйте HEX-код (например, `#1b1429` или градиент `#1b1429/#2a1b3d`).")

    set_config(__name__, "bg_color", color)
    await event.edit(f"✅ **Цвет фона цитат по умолчанию изменен на:** `{color}`")
