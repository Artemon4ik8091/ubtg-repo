import asyncio
import time

from registry import set_module_meta, register_cmd, register_bg, init_config, get_config, set_config

# --- МЕТАДАННЫЕ МОДУЛЯ ---
set_module_meta(
    "Автофарм",
    "Раз в заданный интервал шлет сообщение в целевой чат"
)

# --- ДЕФОЛТНЫЕ НАСТРОЙКИ (хранятся в Global_config.json) ---
# Если чат публичный — юзернейм '@imya_chata'
# Если приватный — ID числом (обычно начинается с -100...)
init_config(__name__, {
    "target_chat": -1003724135016,
    "message_text": "Фарма",
    "interval": 14400,  # 4 часа
    "enabled": True
})


@register_bg()
async def auto_farm_loop(client):
    print("[Автофарм] Фоновый цикл запущен!")

    while True:
        # Читаем актуальные настройки из конфига на каждой итерации,
        # чтобы изменения через .cfg подхватывались на лету
        enabled = get_config(__name__, "enabled")
        target_chat = get_config(__name__, "target_chat")
        message_text = get_config(__name__, "message_text")
        interval = get_config(__name__, "interval")

        if enabled:
            try:
                await client.send_message(target_chat, message_text)
                current_time = time.strftime("%H:%M:%S", time.localtime())
                print(f"[Автофарм] [{current_time}] Сообщение '{message_text}' отправлено в {target_chat}!")
            except Exception as e:
                print(f"[Автофарм] Ошибка при отправке (может кикнули из чата?): {e}")
        else:
            print("[Автофарм] Пропуск цикла — модуль выключен через конфиг.")

        # ВАЖНО: спим асинхронно, чтобы не блокировать весь юзербот
        await asyncio.sleep(interval)


@register_cmd("farm", desc="Управление автофармом: .farm on / .farm off / .farm now / .farm status")
async def farm_cmd(client, event, args):
    arg = args.strip().lower()

    if arg == "on":
        set_config(__name__, "enabled", True)
        await event.edit("✅ Автофарм включен.")

    elif arg == "off":
        set_config(__name__, "enabled", False)
        await event.edit("⛔ Автофарм выключен.")

    elif arg == "now":
        target_chat = get_config(__name__, "target_chat")
        message_text = get_config(__name__, "message_text")
        try:
            await client.send_message(target_chat, message_text)
            await event.edit(f"📤 Сообщение отправлено вручную в `{target_chat}`.")
        except Exception as e:
            await event.edit(f"❌ Ошибка при отправке: {e}")

    else:
        enabled = get_config(__name__, "enabled")
        target_chat = get_config(__name__, "target_chat")
        message_text = get_config(__name__, "message_text")
        interval = get_config(__name__, "interval")
        status = "ВКЛЮЧЕН ✅" if enabled else "ВЫКЛЮЧЕН ⛔"

        await event.edit(
            f"**🌾 Статус автофарма:** {status}\n"
            f"**Чат:** `{target_chat}`\n"
            f"**Сообщение:** `{message_text}`\n"
            f"**Интервал:** `{interval}` сек. (~{interval // 3600} ч.)\n\n"
            f"💡 Используй `.farm on/off/now`, а также `.cfg set modules.{__name__} target_chat <id>` "
            f"и `.cfg set modules.{__name__} message_text <текст>` для настройки."
        )
