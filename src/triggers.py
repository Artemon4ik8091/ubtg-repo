# requires: cachetools
import ast
import json
import asyncio
import logging
from contextlib import suppress
from typing import Dict, List, TypedDict, Any, Callable, Optional, Tuple, Union

from cachetools import TTLCache
from telethon import Button, errors, events

from registry import (
    register_cmd, 
    set_module_meta,
    send_inline, 
    register_callback, 
    init_config, 
    get_config, 
    set_config, 
    register_bg
)

set_module_meta(
    name="Triggers", 
    desc="Триггеры следят за сообщениями в чатах и могут реагировать текстом, удалять сообщения.",
    system=False
)

MODULE_NAME = "Triggers"
logger = logging.getLogger(__name__)

# Инициализация конфигурации в Global_config.json
init_config(MODULE_NAME, {
    "status": True,
    "allow_invoke": False,
    "throttle_time": 1.0,
    "triggers": [],
    "chats": []
})

class Action(TypedDict):
    type: str
    data: Dict[str, str]

class Filters(TypedDict, total=False):
    from_users: List[int]
    chats: List[int]
    is_admin: bool
    contains: bool
    ignorecase: bool

class Trigger(TypedDict):
    id: int
    m: str
    action: Action
    filters: Filters
    delay: float

ACTION_TYPES = ["invoke", "answer", "delete"]

def dict_updater(obj: Dict[str, Union[dict, Any]], query: str, value: Any) -> None:
    keys = query.split(".")
    current = obj
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"key {key} not found")
        current = current[key]

    if not isinstance(current, dict) or keys[-1] not in current:
        raise ValueError(f"key {keys[-1]} not found")
    if not isinstance(current[keys[-1]], type(value)):
        raise ValueError(f"value in dict must be the same type as value")
    current[keys[-1]] = value

def dict_getter(obj: Dict[str, Union[dict, Any]], query: str) -> Any:
    keys = query.split(".")
    current = obj
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"key {key} not found")
        current = current[key]
    return current.get(keys[-1])

class TriggerManager:
    def __init__(self):
        pass

    def get_triggers(self) -> List[Trigger]:
        return get_config(MODULE_NAME, "triggers") or []

    def get_trigger(self, t_id: int) -> Optional[Trigger]:
        triggers = self.get_triggers()
        for t in triggers:
            if t["id"] == t_id:
                return t
        return None

    def set_triggers(self, value: List[Trigger]) -> bool:
        set_config(MODULE_NAME, "triggers", value)
        return True

    def add_trigger(self, value: Trigger) -> bool:
        triggers = self.get_triggers()
        triggers.append(value)
        return self.set_triggers(triggers)

    def set_trigger(self, trigger: Trigger) -> bool:
        triggers = self.get_triggers()
        for i, t in enumerate(triggers):
            if t["id"] == trigger["id"]:
                triggers[i] = trigger
                return self.set_triggers(triggers)
        return self.add_trigger(trigger)

manager = TriggerManager()

def increment_trigger_id() -> int:
    triggers = manager.get_triggers()
    if triggers:
        return triggers[-1]["id"] + 1
    return 0

# --- Фоновый обработчик сообщений ---

watcher_added = False
throttle_val = get_config(MODULE_NAME, "throttle_time")
cache = TTLCache(maxsize=10_000, ttl=float(throttle_val) if throttle_val else 1.0)

async def triggers_handler(event):
    if not get_config(MODULE_NAME, "status"):
        return
    if not event.text:
        return

    chats = get_config(MODULE_NAME, "chats") or []
    chat_id = event.chat_id
    if chat_id not in chats:
        return

    triggers = manager.get_triggers()
    if not triggers:
        return

    t = []
    for trigger in triggers:
        filters = trigger.get("filters", {})
        if filters.get("chats") and chat_id not in filters["chats"]:
            continue
        if filters.get("from_users") and event.sender_id not in filters["from_users"]:
            continue

        m_text = trigger["m"]
        msg_text = event.text
        if filters.get("ignorecase"):
            msg_text = msg_text.lower()
            m_text = m_text.lower()

        if msg_text == m_text:
            t.append(trigger)
            continue

        if filters.get("contains") and m_text in msg_text:
            t.append(trigger)

    for trigger in t:
        if trigger["id"] in cache:
            continue
        cache[trigger["id"]] = None

        action_type = trigger["action"]["type"]
        if trigger.get("delay", 0) > 0:
            await asyncio.sleep(trigger["delay"])

        try:
            if action_type == "answer":
                text = trigger["action"]["data"]["text"].format(text=event.text)
                await event.reply(text)
            elif action_type == "delete":
                await event.delete()
            elif action_type == "invoke":
                if get_config(MODULE_NAME, "allow_invoke"):
                    cmd = trigger["action"]["data"].get("command", "")
                    args = trigger["action"]["data"].get("args", "")
                    # Отправляем сообщение от своего имени, чтобы юзербот поймал команду
                    await event.client.send_message(event.chat_id, f"{cmd} {args}")
        except Exception as e:
            logger.error(f"Trigger execution error: {e}")

@register_bg()
async def trigger_bg_loop(client):
    global watcher_added
    if not watcher_added:
        # Регистрируем обработчик событий один раз при загрузке плагина
        client.add_event_handler(triggers_handler, events.NewMessage())
        watcher_added = True
    
    # Фоновая задача поддерживает жизнь модуля
    while True:
        await asyncio.sleep(86400)


# --- Команды Модуля ---

@register_cmd("taddbase", desc="[текст] <реплай на текст> - Добавить базовый текстовый триггер")
async def triggeraddbase(client, event, args):
    if not args:
        return await event.edit("❌ Нет аргументов!")

    reply = await event.get_reply_message()
    if not reply or not reply.text:
        return await event.edit("❌ Нет реплая с текстом ответа!")

    trigger = Trigger(
        m=args,
        id=increment_trigger_id(),
        action=Action(type="answer", data={"text": reply.text}),
        delay=0,
        filters=Filters()
    )
    manager.add_trigger(trigger)
    await event.edit(f"✅ **Триггер успешно добавлен**\n*id:* `{trigger['id']}`")

@register_cmd("tadd", desc="[JSON] - Добавить триггер из сырых данных")
async def triggeradd(client, event, args):
    if not args:
        return await event.edit("❌ Укажите JSON-данные триггера!")

    try:
        trigger = json.loads(args)
    except Exception:
        return await event.edit("❌ Ошибка парсинга JSON!")

    if not isinstance(trigger, dict) or not trigger.get("m") or not trigger.get("action") or not trigger.get("filters"):
        return await event.edit("❌ Неверный формат триггера!")

    trigger["id"] = increment_trigger_id()
    if not trigger.get("delay") or trigger["delay"] < 0:
        trigger["delay"] = 0
        
    manager.add_trigger(trigger)
    await event.edit(f"✅ **Триггер успешно добавлен**\n*id:* `{trigger['id']}`")

@register_cmd("triggers", desc="Посмотреть все триггеры")
async def triggers_cmd(client, event, args):
    triggers = manager.get_triggers()
    chats = get_config(MODULE_NAME, "chats") or []
    
    if not triggers:
        t = "  🫗 Пусто\n"
    else:
        t = ""
        for trigger in triggers:
            t += f"  • `{trigger['m']}` (ID: {trigger['id']}) action={trigger['action']['type'].lower()};\n"

    text = f"💬 **Ваши триггеры:**\n{t}\n*Включены в {len(chats)} чатах*"
    await event.edit(text)

@register_cmd("tchat", desc="Включить/выключить триггеры в текущем чате")
async def triggerchat(client, event, args):
    chats = get_config(MODULE_NAME, "chats") or []
    chat_id = event.chat_id

    if chat_id not in chats:
        chats.append(chat_id)
        set_config(MODULE_NAME, "chats", chats)
        await event.edit(f"⚡️ **Чат {chat_id} успешно добавлен в список разрешенных.**")
    else:
        chats.remove(chat_id)
        set_config(MODULE_NAME, "chats", chats)
        await event.edit(f"‼️ **Чат {chat_id} успешно удален из списка.**")

@register_cmd("tdel", desc="[id] - Удалить триггер")
async def triggerdel(client, event, args):
    if not args or not args.split()[0].isdigit():
        return await event.edit("❌ Укажите ID триггера (число)!")

    t_id = int(args.split()[0])
    triggers = manager.get_triggers()
    
    for trigger in triggers:
        if trigger["id"] == t_id:
            triggers.remove(trigger)
            manager.set_triggers(triggers)
            return await event.edit("✅ **Успешно удалено**")

    await event.edit("❌ **Триггер не найден!**")

@register_cmd("tget", desc="[id] - Получить сырые данные триггера")
async def triggerget(client, event, args):
    if not args or not args.split()[0].isdigit():
        return await event.edit("❌ Укажите ID триггера!")

    t_id = int(args.split()[0])
    trigger = manager.get_trigger(t_id)
    
    if trigger:
        # Убираем опасные символы при выводе
        trigger_str = json.dumps(trigger, ensure_ascii=False, indent=2)
        return await event.edit(f"```json\n{trigger_str}\n```")

    await event.edit("❌ **Триггер не найден!**")

@register_cmd("tset", desc="[id] [новый JSON] - Перезаписать триггер полностью")
async def triggerset(client, event, args):
    parts = args.split(maxsplit=1)
    if len(parts) < 2 or not parts[0].isdigit():
        return await event.edit("❌ Использование: `.tset [id] [JSON]`")

    t_id = int(parts[0])
    trigger = manager.get_trigger(t_id)
    if not trigger:
        return await event.edit("❌ **Триггер не найден!**")

    try:
        new_trigger = json.loads(parts[1])
        if not isinstance(new_trigger, dict) or "m" not in new_trigger or "action" not in new_trigger:
            raise ValueError("JSON должен содержать ключи 'm' и 'action'")

        new_trigger["id"] = t_id
        if not new_trigger.get("delay") or new_trigger["delay"] < 0:
            new_trigger["delay"] = 0

        manager.set_trigger(new_trigger)
    except Exception as e:
        return await event.edit(f"❌ **Ошибка:** {e}")

    await event.edit("✅ **Успешно обновлено**")

@register_cmd("tupd", desc="[id] [путь] [значение] - Изменить одно поле триггера")
async def triggerupdate(client, event, args):
    parts = args.split(maxsplit=2)
    if len(parts) < 3 or not parts[0].isdigit():
        return await event.edit("❌ Использование: `.tupd [id] [путь.к.ключу] [значение]`")

    t_id = int(parts[0])
    path = parts[1]
    val_str = parts[2]

    trigger = manager.get_trigger(t_id)
    if not trigger:
        return await event.edit("❌ **Триггер не найден!**")

    try:
        tvalue = dict_getter(trigger, path)
    except Exception as e:
        return await event.edit(f"❌ **Ошибка пути:** {e}")

    if tvalue is None:
        with suppress(Exception):
            val_str = ast.literal_eval(val_str)
    else:
        if not isinstance(tvalue, str):
            val_str = ast.literal_eval(val_str)

    try:
        dict_updater(trigger, path, val_str)
        manager.set_trigger(trigger)
    except Exception as e:
        return await event.edit(f"❌ **Ошибка обновления:** {e}")

    await event.edit("✅ **Успешно обновлено**")


# --- Inline Меню Управления Триггерами ---

@register_cmd("tconfig", desc="Инлайн-меню управления триггерами")
async def tconfig_cmd(client, event, args):
    triggers = manager.get_triggers()
    if not triggers:
        return await event.edit("🫗 **У вас нет активных триггеров.**")

    buttons = _build_trigger_list_buttons(triggers)
    await send_inline(
        client, 
        event.chat_id, 
        "⚙️ **Управление Триггерами**\nВыберите триггер для взаимодействия:", 
        buttons=buttons, 
        reply_to=event.reply_to_msg_id
    )
    await event.delete()

def _build_trigger_list_buttons(triggers):
    buttons = []
    row = []
    for t in triggers:
        # callback data max 64 bytes
        btn = Button.inline(f"ID: {t['id']}", f"tview_{t['id']}".encode())
        row.append(btn)
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("❌ Закрыть", b"tclose")])
    return buttons

@register_callback("tview_")
async def tview_cb(event, data):
    tid = int(data.replace("tview_", ""))
    t = manager.get_trigger(tid)
    
    if not t:
        return await event.answer("⚠️ Триггер не найден или удален!", alert=True)

    text = f"🛠 **Триггер #{tid}**\n\n```json\n{json.dumps(t, ensure_ascii=False, indent=2)}\n```"
    buttons = [
        [
            Button.inline("🗑 Удалить", f"tdel_{tid}".encode()),
            Button.inline("⬅️ Назад", b"tback")
        ]
    ]
    try:
        await event.edit(text, buttons=buttons)
    except errors.MessageNotModifiedError:
        await event.answer()

@register_callback("tdel_")
async def tdel_cb(event, data):
    tid = int(data.replace("tdel_", ""))
    triggers = manager.get_triggers()
    
    for i, t in enumerate(triggers):
        if t["id"] == tid:
            triggers.pop(i)
            manager.set_triggers(triggers)
            await event.answer(f"✅ Триггер {tid} успешно удален!", alert=True)
            return await tback_cb(event, "tback")
            
    await event.answer("⚠️ Триггер не найден!", alert=True)

@register_callback("tback")
async def tback_cb(event, data):
    triggers = manager.get_triggers()
    buttons = _build_trigger_list_buttons(triggers)
    try:
        await event.edit("⚙️ **Управление Триггерами**\nВыберите триггер для взаимодействия:", buttons=buttons)
    except errors.MessageNotModifiedError:
        await event.answer()

@register_callback("tclose")
async def tclose_cb(event, data):
    await event.delete()