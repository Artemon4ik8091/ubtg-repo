import re
import asyncio
from datetime import datetime, timedelta
from telethon import functions, types
from telethon.errors import (
    UserAdminInvalidError,
    ChatAdminRequiredError,
    RightForbiddenError,
    UserIdInvalidError
)
from registry import (
    register_cmd,
    set_module_meta,
    init_config,
    get_config,
    set_config
)

# Задаем красивое имя и описание модуля для .help
set_module_meta(
    name="Чат Менеджер",
    desc="Полный комплекс модерации: муты, баны, кики, варны, пурж, пины и управление правами.",
    system=False
)

# Инициализируем стартовый конфиг для системы варнов и настроек
init_config(__name__, {
    "max_warns": 3,
    "warn_action": "mute",  # Варианты: mute, ban, kick
    "warns": {}             # Формат: {"chat_id_user_id": count}
})


def parse_time_delta(time_str: str):
    """
    Парсит строку времени формата: 10s, 15m, 2h, 1d, 1w.
    Возвращает timedelta или None, если формат не совпал.
    """
    if not time_str:
        return None
    
    pattern = r"^(\d+)([smhdwSMHDW])$"
    match = re.match(pattern, time_str)
    if not match:
        return None
    
    amount, unit = match.groups()
    amount = int(amount)
    unit = unit.lower()
    
    if unit == 's':
        return timedelta(seconds=amount)
    elif unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'd':
        return timedelta(days=amount)
    elif unit == 'w':
        return timedelta(weeks=amount)
    return None


async def extract_target_and_args(client, event, args: str):
    """
    Вспомогательная функция для определения цели (User) и аргументов (Время, Причина).
    Сначала проверяет реплай, если реплая нет — ищет юзернейм/ID в первых аргументах.
    """
    reply = await event.get_reply_message()
    user = None
    remaining_text = args.strip() if args else ""
    
    if reply:
        user = await client.get_entity(reply.sender_id)
    elif remaining_text:
        parts = remaining_text.split(maxsplit=1)
        potential_user = parts[0]
        
        # Проверяем, похож ли первый аргумент на ID или @username
        if potential_user.startswith('@') or potential_user.isdigit() or (potential_user.startswith('-') and potential_user[1:].isdigit()):
            try:
                target_id = int(potential_user) if potential_user.isdigit() or potential_user.startswith('-') else potential_user
                user = await client.get_entity(target_id)
                remaining_text = parts[1] if len(parts) > 1 else ""
            except Exception:
                user = None

    return user, remaining_text


def format_user_mention(user) -> str:
    """Форматирует красивое упоминание пользователя."""
    if not user:
        return "Неизвестный пользователь"
    first_name = user.first_name or "Пользователь"
    return f"[{first_name}](tg://user?id={user.id})"


@register_cmd("mute", desc="Замутить пользователя. Использование: .mute [реплай/@user/ID] [время: 10m/2h/1d] [причина]")
async def mute_cmd(client, event, args):
    """Команда ограничения отправки сообщений пользователю."""
    if not event.is_group:
        return await event.edit("❌ Эта команда работает только в группах/супергруппах!")
    
    user, rest_args = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ **Ошибка:** Укажите пользователя через реплай или `.mute @username [время] [причина]`")

    # Разбиваем оставшийся текст на потенциальное время и причину
    time_delta = None
    reason = "Не указана"
    
    if rest_args:
        parts = rest_args.split(maxsplit=1)
        parsed_delta = parse_time_delta(parts[0])
        if parsed_delta:
            time_delta = parsed_delta
            reason = parts[1] if len(parts) > 1 else "Не указана"
        else:
            reason = rest_args

    until_date = datetime.now() + time_delta if time_delta else None
    time_str = f"на {rest_args.split()[0]}" if time_delta else "навсегда"

    try:
        # Ограничиваем право отправки сообщений
        await client.edit_permissions(
            event.chat_id,
            user.id,
            until_date=until_date,
            send_messages=False
        )
        mention = format_user_mention(user)
        await event.edit(f"🔇 **Пользователь** {mention} **замучен {time_str}.**\n📝 **Причина:** `{reason}`")
    except ChatAdminRequiredError:
        await event.edit("❌ ** Ошибка:** У вас нет прав администратора на ограничение пользователей!")
    except UserAdminInvalidError:
        await event.edit("❌ Нельзя замутить администратора этой группы!")
    except Exception as e:
        await event.edit(f"❌ Ошибка при попытке замутить: `{e}`")


@register_cmd("unmute", desc="Размутить пользователя. Использование: .unmute [реплай/@user/ID]")
async def unmute_cmd(client, event, args):
    """Снятие ограничений на отправку сообщений."""
    if not event.is_group:
        return await event.edit("❌ Эта команда работает только в группах!")

    user, _ = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя через реплай или `.unmute @username`")

    try:
        # Возвращаем право писать сообщения
        await client.edit_permissions(
            event.chat_id,
            user.id,
            send_messages=True
        )
        mention = format_user_mention(user)
        await event.edit(f"🔊 **С пользователя** {mention} **сняты все ограничения!**")
    except ChatAdminRequiredError:
        await event.edit("❌ У вас нет прав администратора!")
    except Exception as e:
        await event.edit(f"❌ Ошибка при снятии мута: `{e}`")


@register_cmd("ban", desc="Забанить пользователя в чате. Использование: .ban [реплай/@user/ID] [время] [причина]")
async def ban_cmd(client, event, args):
    """Команда полной блокировки пользователя в чате."""
    if not event.is_group:
        return await event.edit("❌ Эта команда работает только в группах!")

    user, rest_args = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя через реплай или `.ban @username [время] [причина]`")

    time_delta = None
    reason = "Не указана"
    
    if rest_args:
        parts = rest_args.split(maxsplit=1)
        parsed_delta = parse_time_delta(parts[0])
        if parsed_delta:
            time_delta = parsed_delta
            reason = parts[1] if len(parts) > 1 else "Не указана"
        else:
            reason = rest_args

    until_date = datetime.now() + time_delta if time_delta else None
    time_str = f"на {rest_args.split()[0]}" if time_delta else "навсегда"

    try:
        # Запрещаем просмотр сообщений (бан)
        await client.edit_permissions(
            event.chat_id,
            user.id,
            until_date=until_date,
            view_messages=False
        )
        mention = format_user_mention(user)
        await event.edit(f"⛔️ **Пользователь** {mention} **забанен {time_str}.**\n📝 **Причина:** `{reason}`")
    except ChatAdminRequiredError:
        await event.edit("❌ Недостаточно прав для бана пользователей!")
    except UserAdminInvalidError:
        await event.edit("❌ Нельзя забанить администратора чата!")
    except Exception as e:
        await event.edit(f"❌ Ошибка бана: `{e}`")


@register_cmd("unban", desc="Разбанить пользователя. Использование: .unban [реплай/@user/ID]")
async def unban_cmd(client, event, args):
    """Разблокировка пользователя в чате."""
    if not event.is_group:
        return await event.edit("❌ Эта команда работает только в группах!")

    user, _ = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя для разбана.")

    try:
        await client.edit_permissions(
            event.chat_id,
            user.id,
            until_date=0,
            view_messages=True,
            send_messages=True
        )
        mention = format_user_mention(user)
        await event.edit(f"✅ **Пользователь** {mention} **успешно разбанен!**")
    except Exception as e:
        await event.edit(f"❌ Ошибка разбана: `{e}`")


@register_cmd("kick", desc="Исключить пользователя из группы. Использование: .kick [реплай/@user/ID] [причина]")
async def kick_cmd(client, event, args):
    """Исключает участника из чата с возможностью сразу вернуться обратно по ссылке."""
    if not event.is_group:
        return await event.edit("❌ Эта команда работает только в группах!")

    user, reason = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя через реплай или `.kick @username [причина]`")

    reason_str = reason if reason else "Не указана"

    try:
        await client.kick_participant(event.chat_id, user.id)
        mention = format_user_mention(user)
        await event.edit(f"👢 **Пользователь** {mention} **был кикнут из чата.**\n📝 **Причина:** `{reason_str}`")
    except ChatAdminRequiredError:
        await event.edit("❌ Недостаточно прав для кика пользователей!")
    except UserAdminInvalidError:
        await event.edit("❌ Нельзя кикнуть администратора!")
    except Exception as e:
        await event.edit(f"❌ Ошибка при кике: `{e}`")


@register_cmd("warn", desc="Выдать предупреждение пользователю. Использование: .warn [реплай/@user] [причина]")
async def warn_cmd(client, event, args):
    """Выдает предупреждение. При достижении лимита применяет автоматическое наказание."""
    if not event.is_group:
        return await event.edit("❌ Функция работает только в группах!")

    user, reason = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Кого предупреждаем? Сделайте реплай или укажите `@username`")

    reason_str = reason if reason else "Не указана"
    chat_id = event.chat_id
    user_id = user.id
    warn_key = f"{chat_id}_{user_id}"

    # Читаем конфиг
    max_warns = get_config(__name__, "max_warns") or 3
    warn_action = get_config(__name__, "warn_action") or "mute"
    warns_db = get_config(__name__, "warns") or {}

    current_warns = warns_db.get(warn_key, 0) + 1
    warns_db[warn_key] = current_warns
    set_config(__name__, "warns", warns_db)

    mention = format_user_mention(user)

    if current_warns >= max_warns:
        # Сбрасываем варны
        warns_db[warn_key] = 0
        set_config(__name__, "warns", warns_db)
        
        # Применяем наказание
        try:
            if warn_action == "ban":
                await client.edit_permissions(chat_id, user_id, view_messages=False)
                action_text = "⛔️ **Забанен** (Превышен лимит варнов)"
            elif warn_action == "kick":
                await client.kick_participant(chat_id, user_id)
                action_text = "👢 **Кикнут** (Превышен лимит варнов)"
            else:
                await client.edit_permissions(chat_id, user_id, send_messages=False)
                action_text = "🔇 **Замучен** (Превышен лимит варнов)"
                
            await event.edit(f"⚠️ **Пользователь** {mention} **получил {current_warns}/{max_warns} варн!**\n💥 **Наказание:** {action_text}\n📝 **Причина:** `{reason_str}`")
        except Exception as e:
            await event.edit(f"⚠️ Пользователь набрал {current_warns}/{max_warns} варнов, но не удалось применить наказание: `{e}`")
    else:
        await event.edit(f"⚠️ **Пользователю** {mention} **выдано предупреждение [{current_warns}/{max_warns}]**\n📝 **Причина:** `{reason_str}`")


@register_cmd("unwarn", desc="Снять одно предупреждение с пользователя. Использование: .unwarn [реплай/@user]")
async def unwarn_cmd(client, event, args):
    """Снимает 1 варн у пользователя."""
    if not event.is_group:
        return await event.edit("❌ Работает только в группах!")

    user, _ = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя.")

    warn_key = f"{event.chat_id}_{user.id}"
    warns_db = get_config(__name__, "warns") or {}
    max_warns = get_config(__name__, "max_warns") or 3

    current_warns = warns_db.get(warn_key, 0)
    if current_warns <= 0:
        return await event.edit("ℹ️ У этого пользователя нет активных предупреждений.")

    current_warns -= 1
    warns_db[warn_key] = current_warns
    set_config(__name__, "warns", warns_db)
    count = warns_db.get(warn_key, 0)
    mention = format_user_mention(user)
    await event.edit(f"📊 **Предупреждения пользователя** {mention}:\n⚠️ `[{count}/{max_warns}]` варнов.")


@register_cmd("del", desc="Удалить сообщение. Использование: .del в ответ на сообщение")
async def del_cmd(client, event, args):
    """Удаляет сообщение, на которое был дан ответ, и само сообщение с командой."""
    reply = await event.get_reply_message()
    if not reply:
        msg = await event.edit("❌ Ответьте на сообщение, которое нужно удалить!")
        await asyncio.sleep(3)
        return await msg.delete()

    try:
        # Удаляем и исходное сообщение, и сообщение с командой
        await client.delete_messages(event.chat_id, [event.id, reply.id])
    except Exception as e:
        await event.edit(f"❌ Ошибка при удалении: `{e}`")


@register_cmd("purge", desc="Удалить сообщения. Использование: .purge [количество] или ответом на начальное сообщение")
async def purge_cmd(client, event, args):
    """Очистка сообщений пачкой."""
    reply = await event.get_reply_message()
    messages_to_delete = []

    if reply:
        # Удаляем от сообщения в реплае до текущего
        async for msg in client.iter_messages(event.chat_id, min_id=reply.id - 1, max_id=event.id):
            messages_to_delete.append(msg.id)
    elif args and args.isdigit():
        # Удаляем указанное количество
        count = int(args) + 1  # Учитываем само сообщение .purge
        async for msg in client.iter_messages(event.chat_id, limit=count):
            messages_to_delete.append(msg.id)
    else:
        return await event.edit("❌ Ответьте на сообщение, с которого нужно начать очистку, или укажите число: `.purge 10`")

    if not messages_to_delete:
        return await event.edit("❌ Не найдено сообщений для удаления.")

    try:
        # Удаляем сообщения частями (по 100 за раз для избежания лимитов API)
        for i in range(0, len(messages_to_delete), 100):
            await client.delete_messages(event.chat_id, messages_to_delete[i:i + 100])
        
        status_msg = await event.respond(f"🧹 **Успешно удалено сообщений:** `{len(messages_to_delete)}`")
        await asyncio.sleep(3)
        await status_msg.delete()
    except Exception as e:
        await event.edit(f"❌ Ошибка при удалении сообщений: `{e}`")


@register_cmd("pin", desc="Закрепить сообщение в ответе. Использование: .pin [loud]")
async def pin_cmd(client, event, args):
    """Закрепляет сообщение."""
    reply = await event.get_reply_message()
    if not reply:
        return await event.edit("❌ Ответьте на сообщение, которое нужно закрепить!")

    notify = "loud" in args.lower() or "громко" in args.lower()

    try:
        await client.pin_message(event.chat_id, reply.id, notify=notify)
        await event.edit(f"📌 **Сообщение успешно закреплено!**" + (" (с уведомлением)" if notify else ""))
    except Exception as e:
        await event.edit(f"❌ Не удалось закрепить сообщение: `{e}`")


@register_cmd("unpin", desc="Открепить сообщение или все сообщения. Использование: .unpin [all]")
async def unpin_cmd(client, event, args):
    """Открепляет последнее сообщение или все закрепленные сразу."""
    try:
        if "all" in args.lower() or "все" in args.lower():
            await client(functions.messages.UnpinAllMessagesRequest(peer=event.chat_id))
            await event.edit("📌 **Все закрепленные сообщения в этом чате откреплены!**")
        else:
            reply = await event.get_reply_message()
            msg_id = reply.id if reply else None
            await client.unpin_message(event.chat_id, msg_id)
            await event.edit("📌 **Сообщение откреплено!**")
    except Exception as e:
        await event.edit(f"❌ Ошибка при откреплении: `{e}`")


@register_cmd("promote", desc="Назначить пользователя администратором. Использование: .promote [реплай/@user] [Титул]")
async def promote_cmd(client, event, args):
    """Выдает права администратора с гибким набором базовых прав."""
    if not event.is_group:
        return await event.edit("❌ Работает только в группах!")

    user, title = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя для повышения.")

    custom_title = title if title else "Admin"

    try:
        await client.edit_admin(
            event.chat_id,
            user.id,
            change_info=True,
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            add_admins=False,
            title=custom_title
        )
        mention = format_user_mention(user)
        await event.edit(f"👑 **Пользователь** {mention} **теперь администратор!**\n🏷 **Титул:** `{custom_title}`")
    except Exception as e:
        await event.edit(f"❌ Не удалось назначить админа: `{e}`")


@register_cmd("demote", desc="Снять права администратора. Использование: .demote [реплай/@user]")
async def demote_cmd(client, event, args):
    """Забирает все административные права у пользователя."""
    if not event.is_group:
        return await event.edit("❌ Работает только в группах!")

    user, _ = await extract_target_and_args(client, event, args)
    if not user:
        return await event.edit("❌ Укажите пользователя.")

    try:
        await client.edit_admin(
            event.chat_id,
            user.id,
            change_info=False,
            post_messages=False,
            edit_messages=False,
            delete_messages=False,
            ban_users=False,
            invite_users=False,
            pin_messages=False,
            add_admins=False,
            manage_call=False
        )
        mention = format_user_mention(user)
        await event.edit(f"⚡️ **С пользователя** {mention} **были сняты права администратора.**")
    except Exception as e:
        await event.edit(f"❌ Ошибка разжалования: `{e}`")


@register_cmd("slowmode", desc="Установить задержку отправки сообщений (в секундах). Использование: .slowmode [0/10/30/60/300/900/3600]")
async def slowmode_cmd(client, event, args):
    """Устанавливает или отключает режим Медленного Чат-Режима (Slow Mode)."""
    if not event.is_group:
        return await event.edit("❌ Работает только в группах!")

    if not args or not args.isdigit():
        return await event.edit("❌ Укажите секундную задержку (0 для отключения): `.slowmode 10`")

    seconds = int(args)
    try:
        await client(functions.channels.ToggleSlowModeRequest(
            channel=await event.get_input_chat(),
            seconds=seconds
        ))
        if seconds == 0:
            await event.edit("⏳ **Медленный режим отключен.**")
        else:
            await event.edit(f"⏳ **Установлен медленный режим:** `{seconds}` сек.")
    except Exception as e:
        await event.edit(f"❌ Не удалось изменить медленный режим: `{e}`")


@register_cmd("admins", desc="Показать список всех администраторов чата.")
async def admins_list_cmd(client, event, args):
    """Выводит список админов текущей группы."""
    if not event.is_group:
        return await event.edit("❌ Работает только в группах!")

    await event.edit("🔄 *Загрузка списка администраторов...*")
    
    try:
        admins = await client.get_participants(event.chat_id, filter=types.ChannelParticipantsAdmins())
        text = f"🛡 **Администраторы чата** (`{len(admins)}`):\n\n"
        
        for admin in admins:
            if admin.bot:
                continue
            name = admin.first_name or "Без имени"
            username = f"(@{admin.username})" if admin.username else ""
            custom_title = admin.participant.rank if hasattr(admin.participant, 'rank') and admin.participant.rank else "Админ"
            text += f"• [{name}](tg://user?id={admin.id}) {username} — *{custom_title}*\n"

        await event.edit(text)
    except Exception as e:
        await event.edit(f"❌ Ошибка при получении списка: `{e}`")