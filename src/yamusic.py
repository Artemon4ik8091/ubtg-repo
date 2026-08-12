# requires: aiohttp requests pillow yandex-music

import asyncio
import io
import json
import logging
import random
import string
import textwrap

import aiohttp
import requests
import telethon
import yandex_music
import yandex_music.exceptions
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from registry import (
    register_cmd,
    register_bg,
    set_module_meta,
    init_config,
    get_config,
    set_config,
)

logger = logging.getLogger(__name__)

set_module_meta(
    name="YaMusic",
    desc="Яндекс.Музыка: автобио по треку, баннер и инфо о том, что играет сейчас",
    system=False,
)

# --------------------------------------------------------------
# Конфиг модуля
# --------------------------------------------------------------
init_config(__name__, {
    "token": "",
    "now_playing_text": (
        "🎧 <b>{performer} — {title}</b>\n\n"
        "⌨️ <b>Играет на устройстве:</b> <code>{device}</code> (🔊 {volume}%)\n"
        "🗂 <b>Играет из:</b> {playing_from}\n\n"
        "🎵 <a href=\"{link}\">Яндекс.Музыка</a> | "
        "<a href=\"https://song.link/ya/{track_id}\">song.link</a>"
    ),
    "autobio_text": "{performer} — {title}",
    "no_playing_bio_text": "🎧 Сейчас ничего не слушаю",
    "banner_version": "new",   # "new" или "old"
    "autobio_enabled": False,
})

GUIDE_TEXT = (
    "📜 <b>Гайд по получению токена Яндекс.Музыки:</b>\n"
    "https://yandex-music.readthedocs.io/en/main/token.html\n\n"
    "Когда получишь токен — сохрани его командой:\n"
    "<code>.yset &lt;токен&gt;</code>"
)

ENTITY_TYPES = {
    "TRACK": "Трека",
    "PLAYLIST": "плейлиста {}",
    "ALBUM": "альбома {}",
    "ARTIST": "исполнителя {}",
    "VARIOUS": "Моей коллекции",
}

# --------------------------------------------------------------
# Кэш шрифтов (чтобы не качать их при каждом вызове)
# Используем jsdelivr для обхода возможных блокировок raw.githubusercontent
# --------------------------------------------------------------
_FONT_URLS = {
    "onest_bold": "https://cdn.jsdelivr.net/gh/kamekuro/assets@master/fonts/Onest-Bold.ttf",
    "onest_regular": "https://cdn.jsdelivr.net/gh/kamekuro/assets@master/fonts/Onest-Regular.ttf",
    "onest_bold_fb": "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Bold.ttf",
    "onest_regular_fb": "https://raw.githubusercontent.com/kamekuro/assets/master/fonts/Onest-Regular.ttf",
}
_font_cache = {}


def _get_font(key: str, size: int) -> ImageFont.FreeTypeFont:
    cache_key = (key, size)
    if cache_key not in _font_cache:
        raw = None
        # Пробуем загрузить через CDN
        try:
            raw = requests.get(_FONT_URLS[key], timeout=10).content
        except Exception as e:
            logger.warning(f"[YaMusic] Ошибка загрузки шрифта с CDN, пробуем GitHub: {e}")
            # Fallback на GitHub
            try:
                raw = requests.get(_FONT_URLS[f"{key}_fb"], timeout=10).content
            except Exception as e2:
                logger.error(f"[YaMusic] Не удалось загрузить шрифт {key}: {e2}")
                # Если всё упало, возвращаем стандартный шрифт, чтобы не крашить баннер
                _font_cache[cache_key] = ImageFont.load_default()
                return _font_cache[cache_key]
        
        # Если загрузка успешна
        _font_cache[cache_key] = ImageFont.truetype(io.BytesIO(raw), size)

    return _font_cache[cache_key]

# --------------------------------------------------------------
# Генератор баннера трека
# --------------------------------------------------------------
class Banners:
    def __init__(self, title, artists, duration, progress, track_cover):
        self.title = title
        self.artists = artists
        self.duration = duration
        self.progress = progress
        self.track_cover = track_cover

    def _measure(self, text, font, draw):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def new(self):
        W, H = 1920, 768
        title_font = _get_font("onest_bold", 80)
        artist_font = _get_font("onest_bold", 55)
        time_font = _get_font("onest_bold", 36)

        track_cov = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")
        banner = (
            track_cov.resize((W, W))
            .crop((0, (W - H) // 2, W, ((W - H) // 2) + H))
            .filter(ImageFilter.GaussianBlur(radius=14))
        )
        banner = ImageEnhance.Brightness(banner).enhance(0.3)
        draw = ImageDraw.Draw(banner)

        track_cov = track_cov.resize((H - 250, H - 250))
        mask = Image.new("L", track_cov.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, track_cov.size[0], track_cov.size[1]), radius=35, fill=255
        )
        track_cov.putalpha(mask)
        track_cov = track_cov.crop(track_cov.getbbox())
        banner.paste(track_cov, (75, 75), mask)

        space = (643, 75, 1870, 593)
        title_lines = textwrap.wrap(self.title, width=23)
        if len(title_lines) > 2:
            title_lines = title_lines[:2]
            title_lines[-1] = title_lines[-1][:-1] + "…"
        artist_lines = textwrap.wrap(", ".join(self.artists), width=23)
        if len(artist_lines) > 1:
            artist_lines = artist_lines[:1]
            artist_lines[-1] = artist_lines[-1][:-1] + "…"
        lines = title_lines + artist_lines
        lines_sizes = [
            self._measure(line, artist_font if (i == len(lines) - 1) else title_font, draw)
            for i, line in enumerate(lines)
        ]
        total_h = sum(h for _, h in lines_sizes)
        spacing = title_font.size + 10
        y_start = space[1] + ((space[3] - space[1] - total_h) / 2)
        for i, line in enumerate(lines):
            w, _ = lines_sizes[i]
            draw.text(
                (space[0] + (space[2] - space[0] - w) / 2, y_start),
                line,
                font=(artist_font if (i == (len(lines) - 1)) else title_font),
                fill="#FFFFFF",
            )
            y_start += spacing

        draw.text(
            (75, 650),
            f"{(self.progress // 1000 // 60):02}:{(self.progress // 1000 % 60):02}",
            font=time_font, fill="#FFFFFF",
        )
        draw.text(
            (1745, 650),
            f"{(self.duration // 1000 // 60):02}:{(self.duration // 1000 % 60):02}",
            font=time_font, fill="#FFFFFF",
        )
        draw.rounded_rectangle([75, 700, 1845, 715], radius=7, fill="#A0A0A0")
        draw.rounded_rectangle(
            [75, 700, int(75 + (1770 * self.progress / self.duration)), 715],
            radius=7, fill="#FFFFFF",
        )

        by = io.BytesIO()
        banner.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by

    def old(self):
        w, h = 1920, 768
        title_font = _get_font("onest_bold", 80)
        art_font = _get_font("onest_regular", 55)
        time_font = _get_font("onest_bold", 36)

        track_cov = Image.open(io.BytesIO(self.track_cover)).convert("RGBA")
        banner = (
            track_cov.resize((w, w))
            .crop((0, (w - h) // 2, w, ((w - h) // 2) + h))
            .filter(ImageFilter.GaussianBlur(radius=14))
        )
        banner = ImageEnhance.Brightness(banner).enhance(0.3)

        track_cov = track_cov.resize((banner.size[1] - 150, banner.size[1] - 150))
        mask = Image.new("L", track_cov.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, track_cov.size[0], track_cov.size[1]), radius=35, fill=255
        )
        track_cov.putalpha(mask)
        track_cov = track_cov.crop(track_cov.getbbox())
        banner.paste(track_cov, (75, 75), mask)

        title_lines = textwrap.wrap(self.title, 23)
        if len(title_lines) > 1:
            title_lines[1] = title_lines[1] + "..." if len(title_lines) > 2 else title_lines[1]
        title_lines = title_lines[:2]
        artists_lines = textwrap.wrap(" • ".join(self.artists), width=40)
        if len(artists_lines) > 1:
            for index, art in enumerate(artists_lines):
                if "•" in art[-2:]:
                    artists_lines[index] = art[: art.rfind("•") - 1]

        draw = ImageDraw.Draw(banner)
        x, y = 150 + track_cov.size[0], 110
        for index, line in enumerate(title_lines):
            draw.text((x, y), line, font=title_font, fill="#FFFFFF")
            if index != len(title_lines) - 1:
                y += 70
        x, y = 150 + track_cov.size[0], 110 * 2
        if len(title_lines) > 1:
            y += 70
        for index, line in enumerate(artists_lines):
            draw.text((x, y), line, font=art_font, fill="#A0A0A0")
            if index != len(artists_lines) - 1:
                y += 50

        draw.rounded_rectangle([768, 650, 768 + 1072, 650 + 15], radius=7, fill="#A0A0A0")
        draw.rounded_rectangle(
            [768, 650, 768 + int(1072 * (self.progress / self.duration)), 650 + 15],
            radius=7, fill="#FFFFFF",
        )
        draw.text(
            (768, 600),
            f"{(self.progress // 1000 // 60):02}:{(self.progress // 1000 % 60):02}",
            font=time_font, fill="#FFFFFF",
        )
        draw.text(
            (1745, 600),
            f"{(self.duration // 1000 // 60):02}:{(self.duration // 1000 % 60):02}",
            font=time_font, fill="#FFFFFF",
        )

        by = io.BytesIO()
        banner.save(by, format="PNG")
        by.seek(0)
        by.name = "banner.png"
        return by

# --------------------------------------------------------------
# Работа с Ynison (получение того, что играет прямо сейчас)
# --------------------------------------------------------------
async def _get_ynison(token: str) -> dict:
    async def create_ws(ws_proto):
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                "wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison",
                headers={
                    "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                    "Origin": "http://music.yandex.ru",
                    "Authorization": f"OAuth {token}",
                },
            ) as ws:
                response = await ws.receive()
                return json.loads(response.data)

    device_id = "".join(random.choices(string.ascii_lowercase, k=16))
    ws_proto = {
        "Ynison-Device-Id": device_id,
        "Ynison-Device-Info": json.dumps({"app_name": "Chrome", "type": 1}),
    }
    data = await create_ws(ws_proto)
    ws_proto["Ynison-Redirect-Ticket"] = data["redirect_ticket"]
    payload = {
        "update_full_state": {
            "player_state": {
                "player_queue": {
                    "current_playable_index": -1,
                    "entity_id": "",
                    "entity_type": "VARIOUS",
                    "playable_list": [],
                    "options": {"repeat_mode": "NONE"},
                    "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                    "version": {
                        "device_id": device_id,
                        "version": 9021243204784341000,
                        "timestamp_ms": 0,
                    },
                    "from_optional": "",
                },
                "status": {
                    "duration_ms": 0,
                    "paused": True,
                    "playback_speed": 1,
                    "progress_ms": 0,
                    "version": {
                        "device_id": device_id,
                        "version": 8321822175199937000,
                        "timestamp_ms": 0,
                    },
                },
            },
            "device": {
                "capabilities": {
                    "can_be_player": True,
                    "can_be_remote_controller": False,
                    "volume_granularity": 16,
                },
                "info": {
                    "device_id": device_id,
                    "type": "WEB",
                    "title": "Chrome Browser",
                    "app_name": "Chrome",
                },
                "volume_info": {"volume": 0},
                "is_shadow": True,
            },
            "is_currently_active": False,
        },
        "rid": "ac281c26-a047-4419-ad00-e4fbfda1cba3",
        "player_action_timestamp_ms": 0,
        "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
    }
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            f"wss://{data['host']}/ynison_state.YnisonStateService/PutYnisonState",
            headers={
                "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                "Origin": "http://music.yandex.ru",
                "Authorization": f"OAuth {token}",
            },
        ) as ws:
            await ws.send_str(json.dumps(payload))
            response = await ws.receive()
            return json.loads(response.data)

async def _get_now_playing(token: str) -> dict:
    """Возвращает информацию о треке, который сейчас играет (или {})."""
    if not token:
        return {}
    ym_client = await yandex_music.ClientAsync(token).init()

    ynison = await _get_ynison(token)
    queue = ynison.get("player_state", {}).get("player_queue", {})
    if len(queue.get("playable_list", [])) == 0:
        return {}
    raw_track = queue["playable_list"][queue["current_playable_index"]]
    if raw_track["playable_type"] == "LOCAL_TRACK":
        return {}

    track_object = (await ym_client.tracks(raw_track["playable_id"]))[0]
    return {
        "paused": ynison["player_state"]["status"]["paused"],
        "playable_id": raw_track["playable_id"],
        "duration_ms": int(ynison["player_state"]["status"]["duration_ms"]),
        "progress_ms": int(ynison["player_state"]["status"]["progress_ms"]),
        "entity_id": queue["entity_id"],
        "entity_type": queue["entity_type"],
        "device": [
            x for x in ynison["devices"]
            if x["info"]["device_id"] == ynison.get("active_device_id_optional", "")
        ],
        "track": {
            "track_id": track_object.track_id,
            "album_id": track_object.albums[0].id if track_object.albums else None,
            "title": track_object.title,
            "artist": track_object.artists_name(),
            "img": (
                f"https://{track_object.cover_uri[:-2]}1000x1000"
                if track_object.cover_uri else None
            ),
        },
    }

async def _download_track(ym_client, track_id):
    for attempt in range(5):
        try:
            info = await ym_client.tracks_download_info(track_id, get_direct_links=True)
            by = io.BytesIO(await info[0].download_bytes_async())
            by.name = "audio.mp3"
            return by
        except Exception:
            if attempt != 4:
                await asyncio.sleep(1)
                continue
            raise


async def _resolve_playing_from(ym_client, now: dict) -> str:
    entity_type = now["entity_type"]
    if entity_type not in ENTITY_TYPES:
        entity_type = "VARIOUS"
    name = ""
    try:
        if entity_type == "PLAYLIST":
            playlist = (await ym_client.playlists_list(now["entity_id"]))[0]
            name = (
                f'<a href="https://music.yandex.ru/users/{playlist.owner.login}'
                f'/playlists/{playlist.kind}">{playlist.title}</a>'
            )
        elif entity_type == "ALBUM":
            album = (await ym_client.albums(now["entity_id"]))[0]
            name = f'<a href="https://music.yandex.ru/album/{album.id}">{album.title}</a>'
        elif entity_type == "ARTIST":
            artist = (await ym_client.artists(now["entity_id"]))[0]
            name = f'<a href="https://music.yandex.ru/artist/{artist.id}">{artist.name}</a>'
    except Exception:
        pass
    template = ENTITY_TYPES.get(entity_type, ENTITY_TYPES["VARIOUS"])
    return template.format(name) if "{}" in template else template

# --------------------------------------------------------------
# Команды
# --------------------------------------------------------------
@register_cmd(
    "yguide",
    desc="👉 Гайд по получению токена Яндекс.Музыки. Юзай: .yguide",
)
async def yguide_cmd(client, event, args):
    await event.edit(GUIDE_TEXT, link_preview=False, parse_mode="html")


@register_cmd(
    "yset",
    desc="👉 Сохранить токен Яндекс.Музыки. Юзай: .yset <токен>",
)
async def yset_cmd(client, event, args):
    if not args:
        return await event.edit(
            "❌ Укажи токен: `.yset <токен>`\nГайд по получению токена: `.yguide`"
        )
    token = args.strip()
    try:
        await yandex_music.ClientAsync(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        return await event.edit("❌ Этот токен недействителен, проверь его.")
    except Exception as e:
        return await event.edit(f"❌ Не удалось проверить токен: {e}")
    set_config(__name__, "token", token)
    await event.edit("✅ Токен Яндекс.Музыки сохранён.")

async def _apply_bio_text(client, text: str):
    try:
        me = await client.get_me()
        premium = bool(getattr(me, "premium", False))
    except Exception:
        premium = False
    limit = 140 if premium else 70
    try:
        await client(telethon.functions.account.UpdateProfileRequest(about=text[:limit]))
    except telethon.errors.FloodWaitError as e:
        await asyncio.sleep(max(e.seconds, 60))
    except Exception as e:
        logger.error(f"[YaMusic] Не удалось обновить био: {e}")


async def _update_bio_once(client):
    token = get_config(__name__, "token")
    if not token:
        return
    try:
        now = await _get_now_playing(token)
    except yandex_music.exceptions.UnauthorizedError:
        return
    except Exception as e:
        logger.error(f"[YaMusic] Ошибка получения трека для автобио: {e}")
        return

    if now and not now.get("paused"):
        text = get_config(__name__, "autobio_text").format(
            title=now["track"]["title"],
            performer=", ".join(now["track"]["artist"]),
        )
    else:
        text = get_config(__name__, "no_playing_bio_text")
    await _apply_bio_text(client, text)


@register_cmd(
    "ybio",
    desc="👉 Включить/выключить автобио по треку, который сейчас играет. Юзай: .ybio",
)
async def ybio_cmd(client, event, args):
    token = get_config(__name__, "token")
    if not token:
        return await event.edit("❌ Сначала укажи токен: `.yset <токен>` (см. `.yguide`)")

    enabled = not get_config(__name__, "autobio_enabled")
    set_config(__name__, "autobio_enabled", enabled)

    if enabled:
        await _update_bio_once(client)
        await event.edit("✅ Автобио включено.")
    else:
        await _apply_bio_text(client, get_config(__name__, "no_playing_bio_text"))
        await event.edit("🚫 Автобио выключено.")


@register_bg()
async def yamusic_autobio_loop(client):
    print("[YaMusic] Фоновый цикл автобио запущен")
    while True:
        try:
            if get_config(__name__, "autobio_enabled"):
                await _update_bio_once(client)
        except Exception as e:
            print(f"[YaMusic] Ошибка в фоне автобио: {e}")
        await asyncio.sleep(30)


async def _build_now_playing_caption(ym_client, now: dict) -> str:
    playing_from = await _resolve_playing_from(ym_client, now)
    device, volume = "Неизвестное устройство", "❔"
    if now["device"]:
        device = now["device"][0]["info"]["title"]
        volume = round(now["device"][0]["volume"] * 100, 2)
    return get_config(__name__, "now_playing_text").format(
        performer=", ".join(now["track"]["artist"]),
        title=now["track"]["title"],
        device=device,
        volume=volume,
        track_id=now["track"]["track_id"],
        album_id=now["track"]["album_id"],
        playing_from=playing_from,
        link=f"https://music.yandex.ru/track/{now['playable_id']}",
    )

@register_cmd(
    "ynow",
    desc="👉 Баннер трека, который играет сейчас. Юзай: .ynow",
)
async def ynow_cmd(client, event, args):
    token = get_config(__name__, "token")
    if not token:
        return await event.edit("❌ Сначала укажи токен: `.yset <токен>` (см. `.yguide`)")

    try:
        ym_client = await yandex_music.ClientAsync(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        return await event.edit("❌ Токен недействителен.")

    await event.edit("🔎 Ищу трек...")
    try:
        now = await _get_now_playing(token)
    except Exception as e:
        return await event.edit(f"❌ Ошибка: {e}")

    if not now:
        return await event.edit("❌ Сейчас ничего не играет.")
    if not now["track"]["img"]:
        return await event.edit("❌ У этого трека нет обложки, баннер сделать нельзя.")

    caption = await _build_now_playing_caption(ym_client, now)
    await event.edit("🖼 Рисую баннер...")

    # Скачиваем обложку асинхронно, чтобы не заблокировать бота
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(now["track"]["img"], timeout=20) as resp:
                cover_bytes = await resp.read()
    except Exception as e:
        return await event.edit(f"❌ Ошибка загрузки обложки: {e}")

    banners = Banners(
        title=now["track"]["title"],
        artists=now["track"]["artist"],
        duration=now["duration_ms"],
        progress=now["progress_ms"],
        track_cover=cover_bytes,
    )
    version = get_config(__name__, "banner_version")
    render = getattr(banners, version, banners.new)

    # Рендер картинки уводим в отдельный поток
    loop = asyncio.get_event_loop()
    file = await loop.run_in_executor(None, render)

    await client.send_file(event.chat_id, file, caption=caption, parse_mode="html")
    try:
        await event.delete()
    except Exception:
        pass

@register_cmd(
    "ynowt",
    desc="👉 Скачать mp3 трека, который играет сейчас. Юзай: .ynowt",
)
async def ynowt_cmd(client, event, args):
    token = get_config(__name__, "token")
    if not token:
        return await event.edit("❌ Сначала укажи токен: `.yset <токен>` (см. `.yguide`)")

    try:
        ym_client = await yandex_music.ClientAsync(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        return await event.edit("❌ Токен недействителен.")

    await event.edit("🔎 Ищу трек...")
    now = await _get_now_playing(token)
    if not now:
        return await event.edit("❌ Сейчас ничего не играет.")

    caption = await _build_now_playing_caption(ym_client, now)
    
    # ИСПРАВЛЕНИЕ ТУТ: Добавлен parse_mode="html" и отключено превью,
    # чтобы HTML-теги правильно рендерились, пока качается файл.
    await event.edit(
        caption + "\n\n⬇️ Скачиваю трек...",
        parse_mode="html",
        link_preview=False
    )

    audio = await _download_track(ym_client, now["track"]["track_id"])
    await client.send_file(
        event.chat_id,
        audio,
        caption=caption,
        parse_mode="html",
        attributes=[
            telethon.types.DocumentAttributeAudio(
                duration=int(now["duration_ms"] / 1000),
                title=now["track"]["title"],
                performer=", ".join(now["track"]["artist"]),
            )
        ],
    )
    try:
        await event.delete()
    except Exception:
        pass

@register_cmd(
    "ylike",
    desc="👉 Лайкнуть трек, который играет сейчас. Юзай: .ylike",
)
async def ylike_cmd(client, event, args):
    token = get_config(__name__, "token")
    if not token:
        return await event.edit("❌ Сначала укажи токен: `.yset <токен>`")
    try:
        ym_client = await yandex_music.ClientAsync(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        return await event.edit("❌ Токен недействителен.")
    now = await _get_now_playing(token)
    if not now:
        return await event.edit("❌ Сейчас ничего не играет.")
    await ym_client.users_likes_tracks_add(now["track"]["track_id"])
    await event.edit(
        f"❤️ Лайкнул: {', '.join(now['track']['artist'])} — {now['track']['title']}"
    )


@register_cmd(
    "yunlike",
    desc="👉 Снять лайк с трека, который играет сейчас. Юзай: .yunlike",
)
async def yunlike_cmd(client, event, args):
    token = get_config(__name__, "token")
    if not token:
        return await event.edit("❌ Сначала укажи токен: `.yset <токен>`")
    try:
        ym_client = await yandex_music.ClientAsync(token).init()
    except yandex_music.exceptions.UnauthorizedError:
        return await event.edit("❌ Токен недействителен.")
    now = await _get_now_playing(token)
    if not now:
        return await event.edit("❌ Сейчас ничего не играет.")
    await ym_client.users_likes_tracks_remove(now["track"]["track_id"])
    await event.edit(
        f"💔 Убрал лайк: {', '.join(now['track']['artist'])} — {now['track']['title']}"
    )