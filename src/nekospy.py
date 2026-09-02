# requires: telethon

import os
import shutil
import asyncio
from telethon import events
from registry import register_cmd, set_module_meta, register_bg, init_config, get_config, set_config

MODULE_ID = "Nekospy"
CACHE_DIR = "nekospy_cache"

# Кэш сообщений для отслеживания удалений и редактирований в ЛС
# Структура: {message_id: {"text": "текст", "sender_name": "Имя", "has_media": bool, "media_path": str/None}}
pm_cache = {}

# Множество для отслеживания файлов, которые собеседник удалил ПРЯМО ВО ВРЕМЯ нашей фоновой загрузки
deleted_pending_media = set()

# 1. Задаем метаданные для отображения в списке модулей
set_module_meta(
    "Nekospy",
    "Шпионский модуль: перехватывает одноразовые фото/видео и отслеживает удаленные/измененные сообщения (и их медиа) в ЛС."
)

# 2. Инициализируем конфигурацию по умолчанию
init_config(MODULE_ID, {
    "enabled": True,
    "track_pm": True,             # Отслеживание текста ЛС
    "track_pm_media": True,       # Кэширование медиа ЛС для перехвата
    "dump_chat": "me"
})

@register_cmd("onetime", desc="Вкл/выкл перехват одноразовых сообщений")
async def toggle_onetime(client, event, args):
    """Команда для быстрого включения или отключения главного рубильника модуля"""
    current_state = get_config(MODULE_ID, "enabled")
    new_state = not current_state

    set_config(MODULE_ID, "enabled", new_state)

    status = "ВКЛЮЧЕН ✅" if new_state else "ВЫКЛЮЧЕН ❌"
    await event.edit(f"🔥 **Перехват одноразовых медиа:** {status}\n\n"
                     f"ℹ️ *Все сгорающие фото и видео будут сохранены.*")

@register_cmd("pmspy", desc="Вкл/выкл шпиона за текстом в ЛС")
async def toggle_pmspy(client, event, args):
    """Команда для переключения отслеживания удаленных/отредактированных сообщений"""
    current_state = get_config(MODULE_ID, "track_pm")
    new_state = not current_state

    set_config(MODULE_ID, "track_pm", new_state)

    status = "ВКЛЮЧЕН ✅" if new_state else "ВЫКЛЮЧЕН ❌"
    await event.edit(f"🕵️‍♂️ **Шпион за ЛС (текст):** {status}\n\n"
                     f"ℹ️ *Удаленные и измененные собеседниками сообщения будут дублироваться.*")

@register_cmd("pmmedia", desc="Вкл/выкл кэширование медиа в ЛС (для перехвата при удалении)")
async def toggle_pmmedia(client, event, args):
    """Команда для переключения загрузки медиа из ЛС во временную память"""
    current_state = get_config(MODULE_ID, "track_pm_media", default=True)
    new_state = not current_state

    set_config(MODULE_ID, "track_pm_media", new_state)

    status = "ВКЛЮЧЕНО ✅" if new_state else "ВЫКЛЮЧЕНО ❌"
    await event.edit(f"🖼 **Кэширование медиа ЛС:** {status}\n\n"
                     f"ℹ️ *Если включено, бот будет сохранять все фото и видео из ЛС во временную папку, чтобы отправить их при удалении собеседником.*")

@register_cmd("onetimedump", desc="Установить чат для сохранения (по умолчанию me)")
async def set_dump_chat(client, event, args):
    """Команда для смены места, куда отправляются файлы и уведомления"""
    if not args:
        current_dump = get_config(MODULE_ID, "dump_chat")
        return await event.edit(f"❌ **Укажи ID чата или юзернейм.**\n"
                                f"Текущий чат: `{current_dump}`\n"
                                f"Пример: `.onetimedump me`")

    arg = args.strip()
    # Исправление бага Telethon: конвертируем в число, если передан ID, иначе Telethon выдаст ошибку
    if arg.lstrip("-").isdigit():
        arg = int(arg)

    set_config(MODULE_ID, "dump_chat", arg)
    await event.edit(f"✅ **Чат для перехвата успешно установлен на:** `{arg}`")

@register_bg()
async def nekospy_interceptor_bg(client):
    """Фоновая задача для привязки всех шпионских хендлеров"""
    print(f"[Nekospy] Запуск обработчиков... Чат для сохранения: {get_config(MODULE_ID, 'dump_chat')}")

    # Очищаем кэш прошлого сеанса, чтобы не засорять диск
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Асинхронная задача загрузки медиа (чтобы не блокировать хендлер)
    async def background_download(m_id, message, file_size):
        try:
            max_cache_bytes = 500 * 1024 * 1024  # 500 МБ
            current_size = 0
            
            if os.path.exists(CACHE_DIR):
                current_size = sum(
                    os.path.getsize(os.path.join(CACHE_DIR, f)) 
                    for f in os.listdir(CACHE_DIR) 
                    if os.path.isfile(os.path.join(CACHE_DIR, f))
                )
                
                # Если места не хватает, чистим старые файлы
                if current_size + file_size > max_cache_bytes:
                    for k in list(pm_cache.keys()):
                        if current_size + file_size <= max_cache_bytes:
                            break
                        mp = pm_cache[k].get("media_path")
                        if mp and os.path.exists(mp):
                            try:
                                sz = os.path.getsize(mp)
                                os.remove(mp)
                                current_size -= sz
                                pm_cache[k]["media_path"] = None 
                            except:
                                pass

            if current_size + file_size <= max_cache_bytes:
                # Скачиваем файл
                path = await client.download_media(message, file=f"{CACHE_DIR}/")
                if not path:
                    return

                if m_id in pm_cache:
                    pm_cache[m_id]["media_path"] = path
                    pm_cache[m_id]["downloading"] = False
                elif m_id in deleted_pending_media:
                    # СУПЕР-ФИЧА: Если сообщение удалили, пока мы его качали, мы сразу кидаем дамп!
                    dump_chat = get_config(MODULE_ID, "dump_chat")
                    caption = "🗑 **[ДОСКАЧАНО] Медиа было удалено во время загрузки!** 📎"
                    try:
                        await client.send_file(dump_chat, path, caption=caption)
                    except Exception as e:
                        print(f"[Nekospy] Ошибка досыла медиа: {e}")
                    finally:
                        if os.path.exists(path):
                            os.remove(path)
                else:
                    # Вытеснено из кэша по лимиту (2000 шт)
                    if os.path.exists(path):
                        os.remove(path)
        except Exception as e:
            print(f"[Nekospy] ❌ Ошибка фоновой загрузки: {e}")
        finally:
            deleted_pending_media.discard(m_id)


    # ==========================================
    # 1. ОБРАБОТЧИК НОВЫХ СООБЩЕНИЙ
    # ==========================================
    async def incoming_handler(incoming_event):
        if not get_config(MODULE_ID, "enabled"):
            return

        msg = incoming_event.message

        # --- БЛОК ПЕРЕХВАТА ОДНОРАЗОВЫХ МЕДИА ---
        if msg.media:
            ttl = getattr(msg.media, 'ttl_seconds', None)
            if ttl is not None:
                dump_chat = get_config(MODULE_ID, "dump_chat")
                path = None
                try:
                    sender = await incoming_event.get_sender()
                    sender_name = getattr(sender, 'first_name', 'Неизвестный')
                    path = await client.download_media(msg)
                    if path:
                        caption = (f"🔥 **Перехвачено одноразовое медиа!**\n"
                                   f"👤 **От:** {sender_name}")
                        await client.send_file(dump_chat, path, caption=caption)
                except Exception as e:
                    print(f"[Nekospy] ❌ Критическая ошибка при перехвате: {e}")
                finally:
                    if path and os.path.exists(path):
                        os.remove(path)
                return 

        # --- БЛОК КЭШИРОВАНИЯ ЛС (ДЛЯ ШПИОНА) ---
        if get_config(MODULE_ID, "track_pm") and incoming_event.is_private and not incoming_event.out:
            sender = await incoming_event.get_sender()
            sender_name = getattr(sender, 'first_name', 'Неизвестный')
            
            has_med = bool(msg.media)
            
            # ВАЖНО: Сразу пишем в кэш! Это решает проблему удаления во время загрузки.
            pm_cache[msg.id] = {
                "text": msg.text,
                "sender_name": sender_name,
                "has_media": has_med,
                "media_path": None,
                "downloading": has_med
            }

            if has_med and get_config(MODULE_ID, "track_pm_media", default=True):
                file_size = getattr(msg.file, 'size', 0) if (hasattr(msg, 'file') and msg.file) else 0
                if file_size <= 50 * 1024 * 1024:
                    # Запускаем загрузку в фоне, не стопоря основной хендлер
                    asyncio.create_task(background_download(msg.id, msg, file_size))
                else:
                    pm_cache[msg.id]["downloading"] = False
            else:
                pm_cache[msg.id]["downloading"] = False

            # Очистка памяти кэша
            if len(pm_cache) > 2000:
                keys_to_delete = list(pm_cache.keys())[:500]
                for k in keys_to_delete:
                    data = pm_cache.pop(k, None)
                    if data and data.get("media_path") and os.path.exists(data["media_path"]):
                        try:
                            os.remove(data["media_path"])
                        except:
                            pass


    # ==========================================
    # 2. ОБРАБОТЧИК ИЗМЕНЕННЫХ СООБЩЕНИЙ
    # ==========================================
    async def edit_handler(event):
        if not get_config(MODULE_ID, "enabled") or not get_config(MODULE_ID, "track_pm"):
            return

        if event.is_private and not event.out:
            msg_id = event.id
            if msg_id in pm_cache:
                old_data = pm_cache[msg_id]
                old_text = old_data["text"] or "<Без текста>"
                new_text = event.text or "<Без текста>"

                if old_text != new_text:
                    sender_name = old_data["sender_name"]
                    dump_chat = get_config(MODULE_ID, "dump_chat")

                    caption = (f"✏️ **Изменено сообщение в ЛС!**\n"
                               f"👤 **От:** {sender_name}\n\n"
                               f"❌ **Было:**\n`{old_text}`\n\n"
                               f"✅ **Стало:**\n`{new_text}`")
                    try:
                        # Защита от превышения лимитов длины сообщения
                        if len(caption) > 4096:
                            caption = caption[:4090] + "..."
                        await client.send_message(dump_chat, caption)
                    except Exception as e:
                        print(f"[Nekospy] Ошибка отправки уведомления об изменении: {e}")

                pm_cache[msg_id]["text"] = event.text
            else:
                sender = await event.get_sender()
                pm_cache[msg_id] = {
                    "text": event.text,
                    "sender_name": getattr(sender, 'first_name', 'Неизвестный'),
                    "has_media": bool(event.media),
                    "media_path": None,
                    "downloading": False
                }


    # ==========================================
    # 3. ОБРАБОТЧИК УДАЛЕННЫХ СООБЩЕНИЙ
    # ==========================================
    async def delete_handler(event):
        if not get_config(MODULE_ID, "enabled") or not get_config(MODULE_ID, "track_pm"):
            return

        dump_chat = get_config(MODULE_ID, "dump_chat")

        for msg_id in event.deleted_ids:
            if msg_id in pm_cache:
                old_data = pm_cache[msg_id]
                sender_name = old_data["sender_name"]
                old_text = old_data["text"] or "<Без текста>"
                media_path = old_data.get("media_path")
                is_downloading = old_data.get("downloading", False)
                
                media_info = ""
                if old_data.get("has_media"):
                    if media_path and os.path.exists(media_path):
                        media_info = " 📎 [Медиа-файл]"
                    elif is_downloading:
                        media_info = " ⏳ [Загружается... Пришлю как докачается!]"
                        deleted_pending_media.add(msg_id)
                    else:
                        media_info = " 📎 [Медиа-файл не кэшировался]"
                
                if old_text == "<Без текста>" and media_info == "":
                     old_text = "<Только медиа>"

                caption = (f"🗑 **Удалено сообщение в ЛС!**\n"
                           f"👤 **От:** {sender_name}\n\n"
                           f"💬 **Текст:**\n`{old_text}`{media_info}")
                
                try:
                    if media_path and os.path.exists(media_path):
                        # Telegram не позволяет делать подписи к фото длиннее 1024 символов
                        if len(caption) > 1024:
                            await client.send_message(dump_chat, caption[:4090] + "...")
                            await client.send_file(dump_chat, media_path)
                        else:
                            await client.send_file(dump_chat, media_path, caption=caption)
                        os.remove(media_path)
                    else:
                        await client.send_message(dump_chat, caption[:4090] + "...")
                except Exception as e:
                    print(f"[Nekospy] Ошибка отправки уведомления об удалении: {e}")

                del pm_cache[msg_id]


    # Привязываем хендлеры к клиенту
    client.add_event_handler(incoming_handler, events.NewMessage(incoming=True))
    client.add_event_handler(edit_handler, events.MessageEdited(incoming=True))
    client.add_event_handler(delete_handler, events.MessageDeleted())

    print("[Nekospy] Все слушатели (TTL и ЛС-Шпион) успешно привязаны!")

    # Держим таску открытой не блокируя поток
    while True:
        try:
            await asyncio.sleep(86400)
        except asyncio.CancelledError:
            break