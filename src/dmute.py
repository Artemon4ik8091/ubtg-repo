import asyncio
from telethon import events
from telethon.errors import MessageDeleteForbiddenError
from registry import register_cmd, set_module_meta, register_bg

set_module_meta(
    name="Delete Mute", 
    desc="Мутит пользователей путем мгновенного удаления их новых сообщений.", 
    system=False
)

# Хранилище замученных пользователей. 
# Формат: {(chat_id, user_id)}
dmuted_users = set()

# Флаг для предотвращения двойной регистрации хендлера при перезагрузках
is_handler_registered = False


@register_cmd("dmute", desc="Замутить пользователя (удалять его сообщения). Использование: реплай.")
async def dmute_cmd(client, event, args):
    """Команда для добавления пользователя в список на удаление сообщений."""
    
    # Получаем сообщение, на которое ответил пользователь
    reply = await event.get_reply_message()
    if not reply:
        return await event.edit("❌ **Ошибка:** Сделай реплай на сообщение пользователя, которого нужно замутить!")
    
    user_id = reply.sender_id
    chat_id = event.chat_id

    # Защита от мута самого себя
    me = await client.get_me()
    if user_id == me.id:
         return await event.edit("❌ **Ошибка:** Нельзя замутить самого себя!")

    # Добавляем в глобальный сет
    dmuted_users.add((chat_id, user_id))
    
    # Пытаемся получить имя пользователя для красивого вывода
    try:
        user = await client.get_entity(user_id)
        user_name = user.first_name or "Пользователь"
    except Exception:
        user_name = "Пользователь"

    await event.edit(f"🔇 **{user_name}** `[{user_id}]` замучен в этом чате.\n🗑 Все его новые сообщения будут удаляться.")


@register_cmd("dunmute", desc="Размутить пользователя. Использование: реплай.")
async def dunmute_cmd(client, event, args):
    """Команда для удаления пользователя из списка замученных."""
    
    reply = await event.get_reply_message()
    if not reply:
        return await event.edit("❌ **Ошибка:** Сделай реплай на сообщение пользователя, которого нужно размутить!")
    
    user_id = reply.sender_id
    chat_id = event.chat_id

    # Проверяем, есть ли он в списке
    if (chat_id, user_id) in dmuted_users:
        dmuted_users.remove((chat_id, user_id))
        await event.edit(f"🔊 **Пользователь** `[{user_id}]` размучен в этом чате.\n✅ Его сообщения больше не удаляются.")
    else:
        await event.edit("⚠️ Этот пользователь не был замучен в данном чате.")


@register_cmd("dmutelist", desc="Показать список всех замученных пользователей в текущем чате.")
async def dmutelist_cmd(client, event, args):
    """Показывает, кто замучен в текущем чате."""
    
    chat_id = event.chat_id
    # Фильтруем сет, оставляя только тех, кто замучен в текущем чате
    muted_in_this_chat = [uid for cid, uid in dmuted_users if cid == chat_id]
    
    if not muted_in_this_chat:
        return await event.edit("📋 В этом чате нет замученных пользователей.")
    
    text = "📋 **Список замученных в этом чате:**\n"
    for uid in muted_in_this_chat:
        text += f"👤 `ID: {uid}`\n"
        
    await event.edit(text)


@register_bg()
async def setup_dmute_handler(client):
    """
    Фоновая задача, которая запускается при старте юзербота.
    Она регистрирует глобальный слушатель входящих сообщений.
    """
    global is_handler_registered
    
    # Проверка, чтобы не плодить слушатели при горячей перезагрузке модулей
    if is_handler_registered:
        return
    
    @client.on(events.NewMessage())
    async def mute_interceptor(event):
        # Если отправителя нет (например, системное сообщение), пропускаем
        if not event.sender_id:
            return
            
        # Проверяем, находится ли связка (Чат, Пользователь) в нашем черном списке
        if (event.chat_id, event.sender_id) in dmuted_users:
            try:
                # Пытаемся удалить сообщение
                await event.delete()
            except MessageDeleteForbiddenError:
                # Если у нас нет прав на удаление в этой группе/канале,
                # мы удаляем его из списка, чтобы не спамить ошибками в консоль
                dmuted_users.discard((event.chat_id, event.sender_id))
                print(f"[DMute] Отмена мута: нет прав на удаление в чате {event.chat_id} для {event.sender_id}")
            except Exception as e:
                # Игнорируем другие ошибки (например, если сообщение уже удалено)
                pass

    is_handler_registered = True
    print("[DMute] Перехватчик сообщений успешно запущен в фоне!")
    
    # Фоновая задача должна оставаться активной, чтобы ядро считало ее "работающей"
    while True:
        await asyncio.sleep(3600) # Спим час, цикл ничего не потребляет
