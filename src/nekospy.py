# requires: telethon

import os
import asyncio
from telethon import events
from registry import register_cmd, set_module_meta, register_bg, init_config, get_config, set_config

# Жестко задаем ID модуля для конфига
MODULE_ID = "Nekospy"

# Кэш сообщений для отслеживания удалений и редактирований в ЛС
# Структура: {message_id: {"text": "текст", "sender_name": "Имя", "has_media": True/False}}
pm_cache = {}

# 1. Задаем метаданные для отображения в списке модулей
set_module_meta(
    "Nekospy",
    "Шпионский модуль: перехватывает одноразовые фото/видео и отслеживает удаленные/измененные сообщения в ЛС."
)

# 2. Инициализируем конфигурацию по умолчанию
init_config(MODULE_ID, {
    "enabled": True,
    "track_pm": True,      # Новый параметр для отслеживания ЛС
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

@register_cmd("pmspy", desc="Вкл/выкл шпиона за сообщениями в ЛС")
async def toggle_pmspy(client, event, args):
    """Команда для переключения отслеживания удаленных/отредактированных сообщений"""
    current_state = get_config(MODULE_ID, "track_pm")
    new_state = not current_state

    set_config(MODULE_ID, "track_pm", new_state)

    status = "ВКЛЮЧЕН ✅" if new_state else "ВЫКЛЮЧЕН ❌"
    await event.edit(f"🕵️‍♂️ **Шпион за ЛС:** {status}\n\n"
                     f"ℹ️ *Удаленные и измененные собеседниками сообщения будут дублироваться.*")

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

        # --- БЛОК КЭШИРОВАНИЯ ЛС (ДЛЯ ШПИОНА) ---
        if get_config(MODULE_ID, "track_pm") and incoming_event.is_private and not incoming_event.out:
            sender = await incoming_event.get_sender()
            sender_name = getattr(sender, 'first_name', 'Неизвестный')

            pm_cache[msg.id] = {
                "text": msg.text,
                "sender_name": sender_name,
                "has_media": bool(msg.media)
            }

            # Простейшая очистка памяти кэша, чтобы он не рос бесконечно
            if len(pm_cache) > 2000:
                keys_to_delete = list(pm_cache.keys())[:500]
                for k in keys_to_delete:
                    pm_cache.pop(k, None)


    # ==========================================
    # 2. ОБРАБОТЧИК ИЗМЕНЕННЫХ СООБЩЕНИЙ
    # ==========================================
    async def edit_handler(event):
        if not get_config(MODULE_ID, "enabled") or not get_config(MODULE_ID, "track_pm"):
            return

        if event.is_private and not event.out:
            msg_id = event.id
            # Проверяем, есть ли старая версия в нашем кэше
            if msg_id in pm_cache:
                old_data = pm_cache[msg_id]
                old_text = old_data["text"] or "<Без текста>"
                new_text = event.text or "<Без текста>"

                # Если текст действительно изменился
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

                # Обновляем кэш на новый текст, на случай если отредактируют снова
                pm_cache[msg_id]["text"] = event.text
            else:
                # Если сообщения нет в кэше, просто добавим его текущую версию
                sender = await event.get_sender()
                pm_cache[msg_id] = {
                    "text": event.text,
                    "sender_name": getattr(sender, 'first_name', 'Неизвестный'),
                    "has_media": bool(event.media)
                }


    # ==========================================
    # 3. ОБРАБОТЧИК УДАЛЕННЫХ СООБЩЕНИЙ
    # ==========================================
    async def delete_handler(event):
        if not get_config(MODULE_ID, "enabled") or not get_config(MODULE_ID, "track_pm"):
            return

        dump_chat = get_config(MODULE_ID, "dump_chat")

        # event.deleted_ids содержит список удаленных ID
        for msg_id in event.deleted_ids:
            # Если удаленный ID есть в нашем кэше ЛС - значит удалили сообщение в личке
            if msg_id in pm_cache:
                old_data = pm_cache[msg_id]
                sender_name = old_data["sender_name"]
                old_text = old_data["text"] or "<Без текста/Только медиа>"
                media_info = " 📎 [Медиа-файл]" if old_data["has_media"] else ""

                caption = (f"🗑 **Удалено сообщение в ЛС!**\n"
                           f"👤 **От:** {sender_name}\n\n"
                           f"💬 **Текст:**\n`{old_text}`{media_info}")
                try:
                    await client.send_message(dump_chat, caption)
                except Exception as e:
                    print(f"[Nekospy] Ошибка отправки уведомления об удалении: {e}")

                # Удаляем из кэша
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
