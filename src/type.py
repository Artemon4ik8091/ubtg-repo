import asyncio
from telethon.errors import MessageNotModifiedError, FloodWaitError
from registry import register_cmd, set_module_meta, init_config, get_config

# 1. Задаем метаданные модуля
set_module_meta("Type text", "Печатает текст с анимацией и мигающим курсором")

# 2. Инициализируем настройки по умолчанию
# delay — задержка между символами при печати
# cursor — символ курсора
# blink_count — сколько раз курсор моргнет в конце
# blink_interval — скорость мигания курсора в конце (в секундах)
init_config(__name__, {
    "delay": 0.15,
    "cursor": "▒",
    "blink_count": 3,
    "blink_interval": 0.35
})

@register_cmd("type", desc="Печатает текст с эффектом мигающего курсора")
async def type_cmd(client, event, args):
    # Если юзер забыл написать текст
    if not args:
        return await event.edit("❌ А текст-то где? Напиши: `.type Привет, как дела?`")

    # Читаем настройки из конфига
    delay = get_config(__name__, "delay")
    cursor = get_config(__name__, "cursor")
    blink_count = get_config(__name__, "blink_count")
    blink_interval = get_config(__name__, "blink_interval")
    
    current_text = ""
    show_cursor = True

    # 1. Сначала показываем просто пустой курсор
    try:
        await event.edit(cursor)
        await asyncio.sleep(delay)
    except Exception:
        pass

    # 2. Посимвольно печатаем текст с мигающим курсором
    for char in args:
        current_text += char
        
        # Чередуем курсор на каждом шаге печати для эффекта мерцания
        display_text = f"{current_text}{cursor}" if show_cursor else current_text
        show_cursor = not show_cursor  # Меняем состояние для следующего символа
        
        try:
            await event.edit(display_text)
            await asyncio.sleep(delay)
        except MessageNotModifiedError:
            pass
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"[Typewriter Error] {e}")
            break

    # 3. Эффект блинка: когда весь текст напечатан, заставляем курсор мигнуть в конце еще несколько раз
    # Начинаем с того, что курсор гарантированно горит
    last_text_with_cursor = f"{args}{cursor}"
    last_text_clean = args
    
    # Задаем текущее состояние под финал
    is_cursor_on = True
    
    for _ in range(blink_count * 2):  # Умножаем на 2, т.к. один цикл — это включить/выключить
        is_cursor_on = not is_cursor_on
        final_text = last_text_with_cursor if is_cursor_on else last_text_clean
        
        try:
            await event.edit(final_text)
            await asyncio.sleep(blink_interval)
        except MessageNotModifiedError:
            pass
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception:
            break

    # 4. Финальный штрих: убираем курсор насовсем
    try:
        await event.edit(last_text_clean)
    except Exception:
        pass