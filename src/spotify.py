# requires: spotipy
import asyncio
import re
import time
from functools import wraps

import spotipy
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors.rpcerrorlist import FloodWaitError

from registry import (
    register_cmd, 
    register_bg, 
    set_module_meta, 
    init_config, 
    get_config, 
    set_config
)

set_module_meta(
    name="Spotify",
    desc="Интеграция со Spotify: управление плеером, авто-статус",
    system=False
)

init_config(__name__, {
    "autobio_enabled": False,
    "autobio_template": "🎧 {} ───○ 🔊 ᴴᴰ",
    "access_token_dict": {},
    "next_refresh": 0
})

CLIENT_ID = "e0708753ab60499c89ce263de9b4f57a"
CLIENT_SECRET = "80c927166c664ee98a43a2c0e2981b4a"
REDIRECT_URI = "https://thefsch.github.io/spotify/"
SCOPE = (
    "user-read-playback-state playlist-read-private playlist-read-collaborative "
    "app-remote-control user-modify-playback-state user-library-modify user-library-read"
)

sp_oauth = spotipy.oauth2.SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope=SCOPE,
)

def get_spotify_client():
    """Возвращает клиент spotipy, если токен есть в конфиге."""
    token_info = get_config(__name__, "access_token_dict", default={})
    if not token_info or "access_token" not in token_info:
        return None
    return spotipy.Spotify(auth=token_info["access_token"])

def spotify_cmd(func):
    """Декоратор для команд, требующих авторизации Spotify + обработка ошибок"""
    @wraps(func)
    async def wrapper(client, event, args):
        sp = get_spotify_client()
        if not sp:
            return await event.edit("🚫 **Сначала авторизуйтесь через `.sauth`!**", link_preview=False)
        try:
            await func(client, event, args, sp)
        except Exception as e:
            await event.edit(f"🚫 **Ошибка Spotify (возможно не запущена музыка):**\n`{str(e)}`", link_preview=False)
    return wrapper

async def edit_and_delete(event, text, delay=5, link_preview=False):
    """Отправляет сообщение и удаляет его через delay секунд"""
    await event.edit(text, link_preview=link_preview)
    await asyncio.sleep(delay)
    try:
        await event.delete()
    except:
        pass

@register_cmd("sauth", desc="Авторизация Spotify (Шаг 1)")
async def sauth_cmd(client, event, args):
    sp = get_spotify_client()
    if sp:
        return await event.edit("🚫 **Ты уже авторизован!**")
    
    url = sp_oauth.get_authorize_url()
    text = (
        f"🔐 **Авторизация Spotify**\n\n"
        f"1. [Перейди по ссылке]({url}) и разреши доступ.\n"
        f"2. Тебя перекинет на другую страницу.\n"
        f"3. Скопируй ссылку этой новой страницы и напиши:\n"
        f"`.scode <скопированная_ссылка>`"
    )
    await event.edit(text, link_preview=False)

@register_cmd("scode", desc="Авторизация Spotify (Шаг 2)")
async def scode_cmd(client, event, args):
    if not args:
        return await edit_and_delete(event, "❌ Укажи ссылку после команды!")
    
    await event.edit("⏳ **Проверка...**")
    try:
        code = sp_oauth.parse_auth_response_url(args)
        # Выполняем синхронный запрос токена в отдельном потоке
        token_info = await asyncio.to_thread(sp_oauth.get_access_token, code, as_dict=True)
        
        set_config(__name__, "access_token_dict", token_info)
        set_config(__name__, "next_refresh", time.time() + 45 * 60)
        
        await edit_and_delete(event, "🎧 **Успешная авторизация в Spotify!**", 5)
    except Exception as e:
        await edit_and_delete(event, f"❌ Ошибка: `{e}`", 10)

@register_cmd("sunauth", desc="Выйти из Spotify")
async def sunauth_cmd(client, event, args):
    set_config(__name__, "access_token_dict", {})
    await edit_and_delete(event, "🚪 **Успешный выход из Spotify.**", 5)

@register_cmd("srepeat", desc="Включить повтор текущего трека")
@spotify_cmd
async def srepeat_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.repeat, "track")
    await edit_and_delete(event, "💫 **Повторение включено.**")

@register_cmd("sderepeat", desc="Выключить повтор")
@spotify_cmd
async def sderepeat_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.repeat, "context")
    await edit_and_delete(event, "✋ **Повторение выключено.**")

@register_cmd("snext", desc="Следующий трек")
@spotify_cmd
async def snext_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.next_track)
    await edit_and_delete(event, "👉 **Трек переключен.**")

@register_cmd("spause", desc="Пауза")
@spotify_cmd
async def spause_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.pause_playback)
    await edit_and_delete(event, "🤚 **Пауза.**")

@register_cmd("sback", desc="Предыдущий трек")
@spotify_cmd
async def sback_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.previous_track)
    await edit_and_delete(event, "👈 **Переключил назад.**")

@register_cmd("sbegin", desc="Начать трек сначала")
@spotify_cmd
async def sbegin_cmd(client, event, args, sp):
    await asyncio.to_thread(sp.seek_track, 0)
    await edit_and_delete(event, "👈 **Начал трек сначала.**")

@register_cmd("slike", desc="Поставить лайк текущему треку")
@spotify_cmd
async def slike_cmd(client, event, args, sp):
    cupl = await asyncio.to_thread(sp.current_playback)
    if not cupl or not cupl.get("item"):
        return await edit_and_delete(event, "🚫 **Не удалось получить текущий трек.**")
    await asyncio.to_thread(sp.current_user_saved_tracks_add, [cupl["item"]["id"]])
    await edit_and_delete(event, "❤️ **Трек добавлен в любимые.**")

@register_cmd("sbio", desc="Включить/Выключить автоматический статус")
async def sbio_cmd(client, event, args):
    current = get_config(__name__, "autobio_enabled", default=False)
    new_state = not current
    set_config(__name__, "autobio_enabled", new_state)
    state_str = "включено" if new_state else "выключено"
    await edit_and_delete(event, f"🎧 **Обновление био {state_str}!**")

@register_cmd("splay", desc="Воспроизвести трек (.splay <название или ссылка>)")
@spotify_cmd
async def splay_cmd(client, event, args, sp):
    reply = await event.get_reply_message()
    
    if not args:
        if reply and "open.spotify.com/track/" in reply.text:
            match = re.search(r'open\.spotify\.com/track/([a-zA-Z0-9]+)', reply.text)
            if match:
                args = match.group(1)
        else:
            await asyncio.to_thread(sp.start_playback)
            return await edit_and_delete(event, "🎧 **Продолжаю играть...**")
            
    try:
        track = await asyncio.to_thread(sp.track, args)
    except:
        search = await asyncio.to_thread(sp.search, q=args, type="track", limit=1)
        if not search or not search["tracks"]["items"]:
            return await edit_and_delete(event, "🚫 **Нет результатов!**")
        track = search["tracks"]["items"][0]

    await asyncio.to_thread(sp.add_to_queue, track["id"])
    await asyncio.to_thread(sp.next_track)

    artists = ", ".join([_["name"] for _ in track["artists"]])
    track_url = track.get("external_urls", {}).get("spotify", "")
    
    caption_text = (
        f"🎧 **Трек включен и добавлен в очередь**\n\n"
        f"🎶 **{track['name']}** — {artists}\n"
        f"🎵 [Слушать в Spotify]({track_url})" # Скрытая маркдаун ссылка
    )
    
    # link_preview=True заставит телеграм нарисовать красивую плитку плеера
    await event.edit(caption_text, link_preview=True)

@register_cmd("snow", desc="Показать текущий трек")
@spotify_cmd
async def snow_cmd(client, event, args, sp):
    try:
        cp = await asyncio.to_thread(sp.current_playback)
    except Exception as e:
        return await edit_and_delete(event, f"🚫 **Ошибка Spotify API:** `{e}`")

    if not cp or not cp.get("item"):
        return await edit_and_delete(event, "🚫 **Музыка не играет!**")

    track = cp["item"]
    device = f"{cp['device']['name']} {cp['device']['type'].lower()}" if cp.get("device") else "Неизвестно"
    
    artists = ", ".join([_["name"] for _ in track["artists"]])
    track_url = track.get("external_urls", {}).get("spotify", "")
    
    try:
        playlist_id = cp["context"]["uri"].split(":")[-1] if cp.get("context") else None
        if playlist_id:
            playlist_data = await asyncio.to_thread(sp.playlist, playlist_id)
            playlist_name = playlist_data.get("name")
        else:
            playlist_name = None
    except:
        playlist_name = None

    text = f"🎶 **{track['name']}** — {artists}\n\n"
    icon = "💻" if "computer" in str(device).lower() else "📱"
    text += f"{icon} **Сейчас слушаю на** `{device}`\n"
    if playlist_name:
        text += f"🗂 **Плейлист**: {playlist_name}\n"
        
    text += f"\n🎵 **[Spotify]({track_url})**"

    # Явно включаем предпросмотр ссылок для генерации красивой карточки от Telegram
    await event.edit(text, link_preview=True)

@register_bg()
async def spotify_background_task(client):
    """
    Фоновый процесс: 
    1. Автоматически обновляет Token, если он скоро истекает.
    2. Изменяет био, если включена настройка autobio.
    """
    while True:
        try:
            token_info = get_config(__name__, "access_token_dict", default={})
            
            # Проверка токена и рефреш
            if token_info and "refresh_token" in token_info:
                next_ref = get_config(__name__, "next_refresh", default=0)
                if time.time() > next_ref:
                    new_token = await asyncio.to_thread(sp_oauth.refresh_access_token, token_info["refresh_token"])
                    set_config(__name__, "access_token_dict", new_token)
                    set_config(__name__, "next_refresh", time.time() + 45 * 60)
            
            # Обновление автобио
            autobio_on = get_config(__name__, "autobio_enabled", default=False)
            if autobio_on and token_info:
                sp = get_spotify_client()
                if sp:
                    try:
                        cp = await asyncio.to_thread(sp.current_playback)
                    except:
                        cp = None
                        
                    if cp and cp.get("item"):
                        track_name = cp["item"]["name"]
                        track_name = re.sub(r"([(].*?[)])", "", track_name).strip()
                        
                        template = get_config(__name__, "autobio_template", default="🎧 {} ───○ 🔊 ᴴᴰ")
                        bio_text = template.format(track_name)[:70]
                        
                        await client(UpdateProfileRequest(about=bio_text))
                        
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception:
            pass
            
        await asyncio.sleep(90)
