import asyncio
from telethon import Button, errors
from registry import (
    register_cmd, 
    set_module_meta, 
    init_config, 
    get_config, 
    send_inline, 
    register_callback
)

# 1. Устанавливаем метаданные для красивого отображения в .help
set_module_meta(
    name="TagAll", 
    desc="Отмечает всех участников чата с возможностью отмены.", 
    system=False
)

# 2. Инициализируем конфигурацию в Global_config.json
init_config(__name__, {
    "default_message": "@all",
    "delete_after": False,
    "timeout": 2.0, # Задержка увеличена до 2 сек, чтобы избежать FloodWait
    "silent": False
})

# Глобальный словарь для отслеживания статуса работы модуля в разных чатах (chat_id -> bool)
active_tags = {}

@register_cmd("tagall", desc="[текст] - Отметить всех участников чата")
async def tagall_cmd(client, event, args):
    chat_id = event.chat_id

    # Защита от двойного запуска в одном чате
    if active_tags.get(chat_id, False):
        return await event.edit("⚠️ **В этом чате уже идет сбор участников!** Сначала остановите текущий.")

    active_tags[chat_id] = True
    
    # Удаляем исходное сообщение с командой
    await event.delete()

    # Получаем настройки из конфига
    text = args if args else get_config(__name__, "default_message")
    delete_after = get_config(__name__, "delete_after")
    timeout = get_config(__name__, "timeout")
    silent = get_config(__name__, "silent")

    # Отправляем инлайн-сообщение с кнопкой отмены, если не включен тихий режим
    if not silent:
        # ID чата передаем в callback_data без внутренних подчеркиваний (по правилам док-ции)
        buttons = [[Button.inline("🚫 Отмена", f"tagallstop_{chat_id}".encode())]]
        await send_inline(
            client,
            chat_id,
            "🧚‍♀️ **Отмечаю участников чата...**",
            buttons=buttons,
            reply_to=event.reply_to_msg_id
        )

    chunk = []
    
    try:
        # Итерируемся по участникам чата
        async for user in client.iter_participants(chat_id):
            # Проверяем, не нажал ли пользователь кнопку "Отмена"
            if not active_tags.get(chat_id, False):
                break

            # Пропускаем ботов и удаленные аккаунты
            if not user.bot and not user.deleted:
                # Используем невидимый символ для тега (Markdown Telethon)
                chunk.append(f'[\xad](tg://user?id={user.id})')

            # Отправляем пачками по 5 человек
            if len(chunk) >= 5:
                msg_text = f"{text}\n" + "".join(chunk)
                msg = await client.send_message(chat_id, msg_text)

                if delete_after:
                    # Небольшая пауза перед удалением, чтобы людям успело прийти уведомление
                    await asyncio.sleep(0.5) 
                    await msg.delete()

                chunk = []
                # Обязательный сон (как требует документация), чтобы не поймать спамбан
                await asyncio.sleep(timeout)

        # Отправляем остатки, если цикл завершился и не был отменен
        if chunk and active_tags.get(chat_id, False):
            msg_text = f"{text}\n" + "".join(chunk)
            msg = await client.send_message(chat_id, msg_text)
            if delete_after:
                await asyncio.sleep(0.5)
                await msg.delete()

    except errors.ChatAdminRequiredError:
        # Если пытаемся тегать в канале/чате, где скрыты участники
        await client.send_message(chat_id, "🚫 **Недостаточно прав для просмотра участников чата.**")
    except Exception as e:
        print(f"[TagAll] Ошибка: {e}")
    finally:
        # Обязательно сбрасываем статус при завершении
        active_tags[chat_id] = False


# Обработчик инлайн-кнопки "Отмена"
@register_callback("tagallstop_")
async def stop_tagall_callback(event, data):
    # Парсим ID чата из callback_data (например, "tagallstop_123456789")
    payload = data.replace("tagallstop_", "")
    
    try:
        chat_id = int(payload)
    except ValueError:
        return await event.answer("⚠️ Ошибка ID чата!", alert=True)

    # Проверяем, кто нажал на кнопку (разрешаем только владельцу)
    # По желанию можно убрать эту проверку, чтобы любой админ мог остановить
    sender = await event.get_sender()
    # event.client - это бот, поэтому владельца достаем косвенно, но для простоты 
    # просто разрешаем отмену, так как кнопка создана владельцем.

    if active_tags.get(chat_id, False):
        # Останавливаем процесс
        active_tags[chat_id] = False
        try:
            await event.edit("🧚‍♀️ **Сбор участников отменен!**", buttons=None)
        except errors.MessageNotModifiedError:
            await event.answer()
    else:
        # Если уже остановили или завершился сам
        await event.answer("Сбор уже завершен или остановлен.", alert=True)
        try:
            await event.edit("🧚‍♀️ **Сбор участников завершен.**", buttons=None)
        except errors.MessageNotModifiedError:
            await event.answer()