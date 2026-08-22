# requires: aiohttp
import time
import asyncio
import aiohttp
from telethon import Button, errors
from registry import register_cmd, register_callback, set_module_meta, send_inline

# 1. Задаем метаданные модуля
set_module_meta(
    name="LoveMagic",
    desc="Известная TikTok анимация сердечек",
    system=False
)

# Кэш для кадров анимации и текстов инлайн-кнопок
classic_frames = []
gay_frames = []
inline_texts = {}

async def get_frames():
    """Асинхронно скачивает и кэширует JSON с кадрами анимации"""
    global classic_frames, gay_frames
    if not classic_frames or not gay_frames:
        try:
            async with aiohttp.ClientSession() as session:
                # Используем content_type=None, так как Gist отдает файлы как text/plain
                async with session.get("https://gist.github.com/hikariatama/89d0246c72e5882e12af43be63f5bca5/raw/08a5df7255d5e925ab2ede1efc892d9dc93af8e1/ily_classic.json") as resp:
                    classic_frames = await resp.json(content_type=None)
                async with session.get("https://gist.github.com/hikariatama/3596a7c4f273a41e5289586ccff53a71/raw/f680c04f5855dcb02645b603d84d2496a8ea3350/ily_gay.json") as resp:
                    gay_frames = await resp.json(content_type=None)
        except Exception as e:
            print(f"[LoveMagic] Ошибка загрузки кадров: {e}")

async def run_animation(event, text: str, is_gay: bool = False, is_inline: bool = False):
    """Ядро анимации, поочередно редактирующее сообщение"""
    await get_frames()
    frames_to_use = gay_frames if is_gay else classic_frames

    if not frames_to_use:
        return  # Защита от сбоя при скачивании

    words = text.split()
    text_frames = [f'<b>{" ".join(words[:i + 1])}</b>' for i in range(len(words))]
    all_frames = frames_to_use + text_frames

    for frame in all_frames:
        try:
            # Указываем parse_mode="html", чтобы теги <b> правильно обрабатывались
            await event.edit(frame, parse_mode="html")
            await asyncio.sleep(0.5)
        except errors.MessageNotModifiedError:
            pass
        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception:
            break

    await asyncio.sleep(10)

    # В конце для инлайн режима оставляем красивую кнопку (как в оригинале)
    if is_inline:
        try:
            # Указываем parse_mode="html" и для финального сообщения
            await event.edit(
                f"<b>{text}</b>",
                parse_mode="html",
                buttons=[[Button.url("💔 Хочу также!", "https://t.me/UBTG_aswer")]]
            )
        except Exception:
            pass

def _get_cid(text: str) -> str:
    """Генерирует ID и кэширует текст (очищая старый кэш от переполнения)"""
    if len(inline_texts) > 100:
        inline_texts.clear()
    cid = str(int(time.time() * 1000))
    inline_texts[cid] = text
    return cid


# ==========================================
#         ОБЫЧНЫЕ КОМАНДЫ (БЕЗ ИНЛАЙНА)
# ==========================================

@register_cmd("ily", desc="Отправить анимацию сердец. Юзай: .ily <текст>")
async def ily_cmd(client, event, args):
    text = args if args else "I ❤️ you!"
    # Запускаем без создания отдельного таска, чтобы дождаться конца анимации
    await run_animation(event, text, is_gay=False, is_inline=False)

@register_cmd("ilygay", desc="Отправить гейскую анимацию сердец. Юзай: .ilygay <текст>")
async def ilygay_cmd(client, event, args):
    text = args if args else "I am gay and I 💙 you!"
    await run_animation(event, text, is_gay=True, is_inline=False)


# ==========================================
#         ИНЛАЙН КОМАНДЫ (ЧЕРЕЗ БОТА)
# ==========================================

@register_cmd("ilyi", desc="Отправить инлайн анимацию сердец. Юзай: .ilyi <текст>")
async def ilyi_cmd(client, event, args):
    text = args if args else "I ❤️ you!"
    cid = _get_cid(text)

    stars = "*" * (len(args) or 9)
    msg_text = f"<b>❤️‍🔥 Я хочу тебе сказать кое-что...</b>\n<i>{stars}</i>"
    buttons = [[Button.inline("🧸 Open", f"ilm_cl_{cid}".encode())]]

    await send_inline(client, event.chat_id, msg_text, buttons=buttons, reply_to=event.reply_to_msg_id)
    await event.delete()

@register_cmd("ilygayi", desc="Отправить инлайн гейскую анимацию сердец. Юзай: .ilygayi <текст>")
async def ilygayi_cmd(client, event, args):
    text = args if args else "I am gay and I 💙 you!"
    cid = _get_cid(text)

    stars = "*" * (len(args) or 21)
    msg_text = f"<b>❤️‍🔥 Я хочу тебе сказать кое-что...</b>\n<i>{stars}</i>"
    buttons = [[Button.inline("🧸 Open", f"ilm_gy_{cid}".encode())]]

    await send_inline(client, event.chat_id, msg_text, buttons=buttons, reply_to=event.reply_to_msg_id)
    await event.delete()


# ==========================================
#         ОБРАБОТЧИКИ ИНЛАЙН КНОПОК
# ==========================================

@register_callback("ilm_cl_")
async def on_inline_ily(event, data):
    await event.answer() # Обязательно убираем "часики" загрузки на кнопке

    cid = data.replace("ilm_cl_", "")
    text = inline_texts.get(cid, "I ❤️ you!")

    # Запускаем анимацию в самом инлайн-сообщении
    await run_animation(event, text, is_gay=False, is_inline=True)

@register_callback("ilm_gy_")
async def on_inline_ilygay(event, data):
    await event.answer()

    cid = data.replace("ilm_gy_", "")
    text = inline_texts.get(cid, "I am gay and I 💙 you!")

    await run_animation(event, text, is_gay=True, is_inline=True)
