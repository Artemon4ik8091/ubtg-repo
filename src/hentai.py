# ---------------------------------------------------------------------------------
# Name: Hentai!
# Description: random hentai media
# Author: @codrago_m
# Adapted for New Userbot Architecture
# ---------------------------------------------------------------------------------

import random
import asyncio
import datetime
from telethon import functions
from telethon.errors import FloodWaitError
from registry import register_cmd, set_module_meta

set_module_meta(
    name="Hentai",
    desc="Отправляет случайные hentai/sfw/furry медиа",
    system=False
)

strings = {
    "loading_photo_loli": "⏳ **Загрузка вашей лоли фотографии...**",
    "error_loading": "❌ **Не удалось получить фотографии. Пожалуйста, разблокируйте @ferganteusbot**",
    "search": "🔴 **Загрузка вашего медиа...**"
}

@register_cmd("loli", desc="Рандомное лоли фото")
async def loli_cmd(client, event, args):
    await event.edit(strings["loading_photo_loli"])
    
    try:
        async with client.conversation("@ferganteusbot") as conv:
            try:
                lh = await conv.send_message("/lh")
                otvet = await conv.get_response()
                await lh.delete()
                
                if otvet.media:
                    await client.send_message(
                        event.chat_id,
                        message=otvet,
                        reply_to=event.reply_to_msg_id
                    )
                    await otvet.delete()
                    await event.delete()
                else:
                    await event.edit("❌ **Бот не прислал медиа.**")
            except Exception as e:
                await event.edit(strings["error_loading"])
    except Exception as e:
        await event.edit(f"❌ Ошибка: `{e}`")

@register_cmd("fem", desc="Рандомное фембой медиа")
async def fem_cmd(client, event, args):
    await event.edit(strings["search"])
    
    try:
        async with client.conversation("@ferganteusbot") as conv:
            try:
                fm = await conv.send_message("/fm")
                response = await conv.get_response()
                await fm.delete()
                
                if response.media:
                    await client.send_message(
                        event.chat_id,
                        message=response,
                        reply_to=event.reply_to_msg_id
                    )
                    await response.delete()
                    await event.delete()
                else:
                    await event.edit("❌ **Бот не прислал медиа.**")
            except Exception as e:
                await event.edit(strings["error_loading"])
    except Exception as e:
        await event.edit(f"❌ Ошибка: `{e}`")

@register_cmd("sfw", desc="Рандомное SFW медиа")
async def sfw_cmd(client, event, args):
    await event.edit(strings["search"])
    
    try:
        async with client.conversation("@ferganteusbot") as conv:
            try:
                rc = await conv.send_message("/rc")
                response = await conv.get_response()
                await rc.delete()
                
                if response.media:
                    await client.send_message(
                        event.chat_id,
                        message=response,
                        reply_to=event.reply_to_msg_id
                    )
                    await response.delete()
                    await event.delete()
                else:
                    await event.edit("❌ **Бот не прислал медиа.**")
            except Exception as e:
                await event.edit(strings["error_loading"])
    except Exception as e:
        await event.edit(f"❌ Ошибка: `{e}`")

@register_cmd("furry", desc="Рандомное фурри медиа")
async def furry_cmd(client, event, args):
    await event.edit(strings["search"])
    await asyncio.sleep(0.5) # Replaced time.sleep with asyncio.sleep
    
    chat = "furrylov"
    try:
        result = await client(
            functions.messages.GetHistoryRequest(
                peer=chat,
                offset_id=0,
                offset_date=datetime.datetime.now(),
                add_offset=random.choice(range(1, 12436, 2)),
                limit=1,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        
        if result.messages and result.messages[0].media:
            await client.send_file(
                event.chat_id,
                result.messages[0].media,
                reply_to=event.reply_to_msg_id
            )
            await event.delete()
        else:
             await event.edit("❌ **Медиа не найдено.**")
    except Exception as e:
        await event.edit(f"❌ Ошибка при получении: `{e}`")

@register_cmd("nsfw", desc="Рандомное NSFW медиа")
async def nsfw_cmd(client, event, args):
    await event.edit(strings["search"])
    await asyncio.sleep(0.5) # Replaced time.sleep with asyncio.sleep
    
    chat = "hdjrkdjrkdkd"
    try:
        result = await client(
            functions.messages.GetHistoryRequest(
                peer=chat,
                offset_id=0,
                offset_date=datetime.datetime.now(),
                add_offset=random.choice(range(1, 851, 2)),
                limit=1,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )
        
        if result.messages and result.messages[0].media:
            await client.send_file(
                event.chat_id,
                result.messages[0].media,
                reply_to=event.reply_to_msg_id
            )
            await event.delete()
        else:
            await event.edit("❌ **Медиа не найдено.**")
    except Exception as e:
        await event.edit(f"❌ Ошибка при получении: `{e}`")
