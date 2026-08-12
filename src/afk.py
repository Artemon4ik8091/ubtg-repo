import asyncio
from telethon import events
from registry import register_cmd, register_bg, set_module_meta, init_config, get_config, set_config

set_module_meta(
    name="AFK",
    desc="Автоответчик для ЛС. Снимается сам, когда ты начинаешь писать, или по команде.",
    system=False
)

# Задаем дефолтные значения в глобальный конфиг юзербота
init_config(__name__, {
    "is_afk": False,
    "reason": "Занят, отвечу позже."
})
# Глобальные переменные: кэш юзеров (анти-спам) и локальные AFK чаты
notified_users = set()
afk_chats = {}  # chat_id -> reason
handlers_registered = False

@register_cmd("afk", desc="Врубить AFK. Юзай: .afk [твоя причина]")
async def cmd_afk(client, event, args):
    # Если аргументы не переданы, ставим дефолтную фразу
    reason = args if args else "Отдыхаю от интернетов."
    
    # Сохраняем статус в конфиг
    set_config(__name__, "is_afk", True)
    set_config(__name__, "reason", reason)
    
    # Очищаем кэш уведомленных юзеров на случай, если мы перезашли в AFK
    notified_users.clear() 
    
    await event.edit(f"💤 **Я ушел в AFK.**\n💬 Причина: {reason}")

@register_cmd("unafk", desc="Вырубить AFK руками.")
async def cmd_unafk(client, event, args):
    # Проверяем, включен ли вообще AFK
    if not get_config(__name__, "is_afk"):
        return await event.edit("❌ **Кент, ты и так не в AFK.**")
    
    # Выключаем
    set_config(__name__, "is_afk", False)
    notified_users.clear()
    
    await event.edit("👋 **AFK отключен, я снова на связи!**")

async def afk_incoming_handler(event):
    try:
        # Проверяем флаг в конфиге. Если мы не AFK - игнорим все.
        if not get_config(__name__, "is_afk"):
            return
            
        chat_id = event.chat_id
        
        # Если мы уже писали этому кенту, не будем спамить ему на каждое слово
        if chat_id in notified_users:
            return
            
        # Достаем причину из конфига и отвечаем
        reason = get_config(__name__, "reason")
        await event.reply(f"🤖 **[АВТООТВЕТ]**\nЯ сейчас AFK.\n\n💬 Причина: {reason}")
        
        # Записываем чела в кэш
        notified_users.add(chat_id)
        
    except Exception as e:
        # Всегда перехватываем ошибки в фоне, чтобы бот не лег
        print(f"Ошибка в afk_incoming_handler: {e}")

async def afk_outgoing_handler(event):
    try:
        if not get_config(__name__, "is_afk"):
            return
            
        # Игнорируем команды самого юзербота (все, что начинается на точку)
        if event.raw_text and event.raw_text.startswith("."):
            return
            
        # Если мы отправили обычное сообщение — значит мы вернулись. Вырубаем AFK.
        set_config(__name__, "is_afk", False)
        notified_users.clear()
        
        # Кидаем себе системное сообщение и удаляем его через 3 секунды, чтобы не мусорить
        msg = await event.respond("👋 **[СИСТЕМА]** AFK автоматически отключен.")
        await asyncio.sleep(3)
        await msg.delete()
        
    except Exception as e:
        print(f"Ошибка в afk_outgoing_handler: {e}")

@register_bg()
async def afk_bg_task(client):
    global handlers_registered
    
    # Вешаем хендлеры только один раз при инициализации модуля
    if not handlers_registered:
        # 1. Слушаем только ВХОДЯЩИЕ и только в ЛИЧКЕ (чтобы не спамить в чатах)
        client.add_event_handler(
            afk_incoming_handler, 
            events.NewMessage(incoming=True, func=lambda e: e.is_private)
        )
        
        # 2. Слушаем ИСХОДЯЩИЕ (наши сообщения), чтобы понимать, когда мы вернулись
        client.add_event_handler(
            afk_outgoing_handler, 
            events.NewMessage(outgoing=True)
        )
        
        handlers_registered = True
        print("[AFK Модуль] Хендлеры успешно зарегистрированы!")

    # Фоновой задаче нужен бесконечный цикл с асинхронным сном,
    # чтобы функция не завершилась и ядро не подумало, что таска "упала".
    # Основную работу делают хендлеры выше.
    while True:
        await asyncio.sleep(3600)
@register_cmd("afkhere", desc="Врубить AFK только в текущем чате. Юзай: .afkhere [причина]")
async def cmd_afkhere(client, event, args):
    reason = args if args else "Отдыхаю именно в этом чате."
    chat_id = event.chat_id
    
    afk_chats[chat_id] = reason
    notified_users.discard(chat_id)
    
    await event.edit(f"💤 **Я ушел в AFK в этом чате.**\n💬 Причина: {reason}")

@register_cmd("unafk", desc="Вырубить AFK руками.")
async def cmd_unafk(client, event, args):
    chat_id = event.chat_id
    global_afk = get_config(__name__, "is_afk")
    local_afk = chat_id in afk_chats
    
    if not global_afk and not local_afk and not afk_chats:
        return await event.edit("❌ **Кент, ты и так нигде не в AFK.**")
    
    set_config(__name__, "is_afk", False)
    afk_chats.clear()
    notified_users.clear()
    
    await event.edit("👋 **AFK отключен везде, я снова на связи!**")

async def afk_incoming_handler(event):
    try:
        chat_id = event.chat_id
        is_global = get_config(__name__, "is_afk")
        is_local = chat_id in afk_chats
        
        # Если ни глобальный, ни локальный AFK не включен — сваливаем
        if not is_global and not is_local:
            return
            
        # Для глобального AFK в группах не автоотвечаем
        if is_global and not is_local and not event.is_private:
            return
            
        # Для локального AFK в группах автоотвечаем только если нас упомянули или ответили на наше сообщение
        if not event.is_private and is_local and not is_global:
            if not (event.mentioned or event.is_reply):
                return
            
        if chat_id in notified_users:
            return
            
        reason = afk_chats.get(chat_id) if is_local else get_config(__name__, "reason")
        await event.reply(f"🤖 **[АВТООТВЕТ]**\nЯ сейчас AFK.\n\n💬 Причина: {reason}")
        
        notified_users.add(chat_id)
        
    except Exception as e:
        print(f"Ошибка в afk_incoming_handler: {e}")

async def afk_outgoing_handler(event):
    try:
        chat_id = event.chat_id
        is_global = get_config(__name__, "is_afk")
        is_local = chat_id in afk_chats
        
        if not is_global and not is_local:
            return
            
        # Игнорируем команды самого юзербота
        if event.raw_text and event.raw_text.startswith("."):
            return
            
        if is_global:
            set_config(__name__, "is_afk", False)
            msg_text = "👋 **[СИСТЕМА]** Глобальный AFK автоматически отключен."
        else:
            afk_chats.pop(chat_id, None)
            msg_text = "👋 **[СИСТЕМА]** AFK в этом чате автоматически отключен."
            
        notified_users.discard(chat_id)
        
        msg = await event.respond(msg_text)
        await asyncio.sleep(3)
        await msg.delete()
        
    except Exception as e:
        print(f"Ошибка в afk_outgoing_handler: {e}")

@register_bg()
async def afk_bg_task(client):
    global handlers_registered
    
    if not handlers_registered:
        # Слушаем входящие сообщения без ограничения is_private (проверка идет внутри)
        client.add_event_handler(
            afk_incoming_handler, 
            events.NewMessage(incoming=True)
        )
        
        client.add_event_handler(
            afk_outgoing_handler, 
            events.NewMessage(outgoing=True)
        )
        
        handlers_registered = True
        print("[AFK Модуль] Хендлеры успешно зарегистрированы!")

    while True:
        await asyncio.sleep(3600)