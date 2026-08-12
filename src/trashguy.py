# requires: grapheme
import asyncio
import grapheme
from telethon.errors import MessageNotModifiedError, FloodWaitError
from registry import register_cmd, set_module_meta, init_config, get_config

# Метаданные для .help
set_module_meta(
    name="TrashGuy",
    desc="Анимация человечка, который выкидывает мусор. С настройкой скорости!",
    system=False
)

# Инициализация конфига
# Дефолтная задержка 0.6 секунд. 
init_config(__name__, {
    "delay": 0.6
})

def get_trashguy_frames(text: str) -> list:
    """Генерит кадры для анимации"""
    DISTANCE = 5
    SPACER = "\u0020\u2800"
    
    text_chars = list(grapheme.graphemes(text))
    frames = []

    for offset, current_symbol in enumerate(text_chars):
        for i in range(DISTANCE):
            frame = f"🗑{SPACER * i}(> ^_^)>{SPACER * (DISTANCE - i)}{''.join(text_chars[offset:])}"
            frames.append(frame)
            
        for i in range(DISTANCE):
            frame = f"🗑{SPACER * (DISTANCE - i)}{current_symbol}<(^_^ <){SPACER * i}{''.join(text_chars[offset + 1:])}"
            frames.append(frame)

    return frames

@register_cmd("tguy", desc="Запустить анимацию TrashGuy. Юзай: .tguy <текст>")
async def tguy_cmd(client, event, args):
    text = args if args else "мой мозг"
    await event.edit("⏳ *Вызываю уборщика...*")

    frames = get_trashguy_frames(text)
    done_text = "🗑 \\ (•◡•) / 🗑\n\u0020\u2800\u0020\u2800**Я закончил!**\u0020\u2800\u0020\u2800"
    frames.append(done_text)

    # Достаем задержку из конфига
    delay = get_config(__name__, "delay")
    
    # На всякий случай делаем защиту от дурака, если в конфиг случайно запишут хуйню вместо числа
    try:
        delay = float(delay)
    except (ValueError, TypeError):
        delay = 0.6

    for frame in frames:
        try:
            await event.edit(frame)
            await asyncio.sleep(delay) # Скорость теперь берется из конфига!
        except MessageNotModifiedError:
            continue
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"[TrashGuy] Ошибка кадра: {e}")
            continue