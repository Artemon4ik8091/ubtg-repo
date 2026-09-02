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

    set_config(MODULE_ID, "dump_chat", args)
    await event.edit(f"✅ **Чат для перехвата успешно установлен на:** `{args}`")

@register_bg()
async def nekospy_interceptor_bg(client):
    """Фоновая задача для привязки всех шпионских хендлеров"""
    print(f"[Nekospy] Запуск обработчиков... Чат для сохранения: {get_config(MODULE_ID, 'dump_chat')}")

    # Очищаем кэш прошлого сеанса, чтобы не засорять диск
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # ==========================================
    # 1. ОБРАБОТЧИК НОВЫХ СООБЩЕНИЙ (Перехват TTL + Кэш ЛС)
    # ==========================================
    async def incoming_handler(incoming_event):
        if not get_config(MODULE_ID, "enabled"):
            return

        msg = incoming_event.message

        # --- БЛОК ПЕРЕХВАТА ОДНОРАЗОВЫХ МЕДИА ---
        if msg.media:
            ttl = getattr(msg.media, 'ttl_seconds', None)
            if ttl is not None:
                print(f"[Nekospy] 🔥 Обнаружено сгорающее медиа! (TTL: {ttl} сек). Пытаюсь скачать...")
                dump_chat = get_config(MODULE_ID, "dump_chat")
                path = None

                try:
                    sender = await incoming_event.get_sender()
                    sender_name = getattr(sender, 'first_name', 'Неизвестный')

                    path = await client.download_media(msg)

                    if not path:
                        print("[Nekospy] ❌ Ошибка: Telethon вернул пустой путь (файл не скачан).")
                    else:
                        caption = (f"🔥 **Перехвачено одноразовое медиа!**\n"
                                   f"👤 **От:** {sender_name}")
                        await client.send_file(dump_chat, path, caption=caption)
                        print("[Nekospy] ✅ Файл успешно переслан!")

                except Exception as e:
                    print(f"[Nekospy] ❌ Критическая ошибка при перехвате: {e}")

                finally:
                    if path and os.path.exists(path):
                        os.remove(path)
                return # Одноразовые медиа мы уже обработали, в кэш ЛС их не пишем

        # --- БЛОК КЭШИРОВАНИЯ ЛС (ДЛЯ ШПИОНА) ---
        if get_config(MODULE_ID, "track_pm") and incoming_event.is_private and not incoming_event.out:
            sender = await incoming_event.get_sender()
            sender_name = getattr(sender, 'first_name', 'Неизвестный')
            
            media_path = None
            
            # Если есть медиа и кэширование включено
            if msg.media and get_config(MODULE_ID, "track_pm_media", default=True):
                # Проверяем размер файла (не скачиваем файлы больше 50 МБ)
                if hasattr(msg, 'file') and msg.file and msg.file.size:
                    if msg.file.size <= 50 * 1024 * 1024:
                        max_cache_bytes = 500 * 1024 * 1024  # Жёсткий лимит 500 МБ
                        current_size = 0
                        
                        if os.path.exists(CACHE_DIR):
                            # Считаем текущий размер всех файлов в папке кэша
                            current_size = sum(
                                os.path.getsize(os.path.join(CACHE_DIR, f)) 
                                for f in os.listdir(CACHE_DIR) 
                                if os.path.isfile(os.path.join(CACHE_DIR, f))
                            )
                            
                            # Если новый файл превышает лимит в 500 МБ, очищаем старые медиа
                            if current_size + msg.file.size > max_cache_bytes:
                                print(f"[Nekospy] 🧹 Кэш достигает лимита ({current_size/1024/1024:.1f} МБ). Освобождаем место...")
                                
                                # Словари в Python сохраняют порядок добавления, поэтому первые ключи — самые старые
                                for k in list(pm_cache.keys()):
                                    if current_size + msg.file.size <= max_cache_bytes:
                                        break
                                    
                                    mp = pm_cache[k].get("media_path")
                                    if mp and os.path.exists(mp):
                                        try:
                                            sz = os.path.getsize(mp)
                                            os.remove(mp)
                                            current_size -= sz
                                            pm_cache[k]["media_path"] = None # Отвязываем удаленный файл
                                        except Exception:
                                            pass

                        # Скачиваем файл только если успешно освободили место (или оно изначально было)
                        if current_size + msg.file.size <= max_cache_bytes:
                            try:
                                media_path = await client.download_media(msg, file=f"{CACHE_DIR}/")
                            except Exception as e:
                                print(f"[Nekospy] ❌ Ошибка загрузки медиа в кэш: {e}")
                        else:
                            print(f"[Nekospy] ⚠️ Не удалось освободить место, медиа пропущено.")

            pm_cache[msg.id] = {
                "text": msg.text,
                "sender_name": sender_name,
                "has_media": bool(msg.media),
                "media_path": media_path
            }

            # Очистка памяти кэша, чтобы он не рос бесконечно
            if len(pm_cache) > 2000:
                keys_to_delete = list(pm_cache.keys())[:500]
                for k in keys_to_delete:
                    data = pm_cache.pop(k, None)
                    # Удаляем физический файл, если он кэшировался
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
                    "media_path": None
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
                
                # Если файл не скачался/не кэшировался, но медиа там было, добавляем пометку
                media_info = " 📎 [Медиа-файл]" if old_data.get("has_media") and not (media_path and os.path.exists(media_path)) else ""
                
                if old_text == "<Без текста>" and media_info == "":
                     old_text = "<Только медиа>"

                caption = (f"🗑 **Удалено сообщение в ЛС!**\n"
                           f"👤 **От:** {sender_name}\n\n"
                           f"💬 **Текст:**\n`{old_text}`{media_info}")
                
                try:
                    # Если медиа удалось перехватить - отправляем его
                    if media_path and os.path.exists(media_path):
                        await client.send_file(dump_chat, media_path, caption=caption)
                        os.remove(media_path) # Удаляем после пересылки
                    else:
                        await client.send_message(dump_chat, caption)
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