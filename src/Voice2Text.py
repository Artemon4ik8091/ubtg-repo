# requires: SpeechRecognition pydub
import os
import speech_recognition as sr
from pydub import AudioSegment
from registry import register_cmd, set_module_meta, init_config, get_config

set_module_meta(
    name="Google STT",
    desc="Бесплатная расшифровка голосовых через Google Speech API (Требует ffmpeg)",
    system=False
)

# Инициализируем настройки в Global_config.json
init_config(__name__, {
    "language": "ru-RU" # Можно поменять на en-US или uk-UA через .cfg
})

@register_cmd("stt", desc="Расшифровать войс/кружок через Google: .stt")
async def stt_cmd(client, event, args):
    reply = await event.get_reply_message()
    if not reply or not (reply.voice or reply.video_note or reply.audio):
        return await event.edit("❌ Ответь реплаем на голосовое или кружок!")

    await event.edit("⏳ *Скачиваю аудио...*")
    
    # Скачиваем файл во временную директорию (pydub требует физический файл для работы с ffmpeg)
    in_file = await reply.download_media(file="downloads/")
    if not in_file:
        return await event.edit("❌ Не удалось скачать медиафайл.")
        
    out_file = in_file + ".wav"

    try:
        await event.edit("⚙️ *Конвертирую формат...*")
        # Конвертируем ogg/mp4 в wav
        audio = AudioSegment.from_file(in_file)
        audio.export(out_file, format="wav")
        
        await event.edit("⚡️ *Отправляю в Google...*")
        
        # Работа с Google SpeechRecognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(out_file) as source:
            # Считываем данные
            audio_data = recognizer.record(source)
            
        lang = get_config(__name__, "language", default="ru-RU")
        
        # Отправляем запрос (используется бесплатный endpoint без ключа)
        text = recognizer.recognize_google(audio_data, language=lang)
        
        if not text:
            text = "🤷‍♂️ [Тишина или неразборчивый звук]"
            
        formatted = f"🗣 **Google Расшифровка:**\n\n{text}"
        
        # Защита от лимита сообщений в Telegram (4096 символов)
        if len(formatted) > 4096:
            await event.edit(formatted[:4090] + "...")
            for chunk in range(4090, len(text), 4000):
                await event.respond(text[chunk:chunk + 4000])
        else:
            await event.edit(formatted)
            
    except sr.UnknownValueError:
        await event.edit("🤷‍♂️ Google не смог разобрать речь (возможно, сильный шум или тишина).")
    except sr.RequestError as e:
        await event.edit(f"❌ Ошибка подключения к серверам Google:\n`{e}`")
    except FileNotFoundError:
        await event.edit("❌ **Ошибка:** На сервере не установлен `ffmpeg`!\nДля работы Google STT установите его: `sudo apt install ffmpeg` (Ubuntu) или скачайте для Windows.")
    except Exception as e:
        await event.edit(f"❌ Ошибка обработки: `{e}`")
    finally:
        # Убираем за собой временные файлы в любом случае
        if os.path.exists(in_file):
            os.remove(in_file)
        if os.path.exists(out_file):
            os.remove(out_file)