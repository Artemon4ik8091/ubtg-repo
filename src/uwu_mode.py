from registry import register_cmd, set_module_meta, init_config, get_config, set_config, register_bg
from telethon import events
import random
import asyncio
import re

# Задаем метаданные для команды .help
set_module_meta(
    name="UwU Mode", 
    desc="Автоматически превращает твои сообщения в милые (заикание, каомодзи, действия). Вкл/Выкл: .uwu", 
    system=False
)

# Инициализируем конфиг. По умолчанию режим выключен.
init_config(__name__, {
    "enabled": False
})

# Наборы данных для генерации сообщений (взято на основе видео)
KAOMOJIS = [
    "(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(๑>ᴗ<๑)", "(,,,•﹏•,,,)", "(≧◡≦) ♡", 
    "(´ ω `♡)", "(◕‿◕✿)", "(*^ω^*)"
]

ACTIONS = [
    "*ломается на секунду*", "*улыбается*", "*тихо мур*", 
    "*перезагружается*", "*поджимает ушки*", "*краснеет*", 
    "*смотрит в пол*"
]

ENDINGS = [
    "💕", "🌸", "🐾", "hihi~", "mrr~", "kyaa~", "🎀", "🥺", "💖", "✨"
]

VOWELS = "аеёиоуыэюя"

def uwuify(text):
    """Основная функция превращения обычного текста в 'милый'"""
    if not text:
        return text
        
    words = text.lower().split()
    new_words = []
    
    for w in words:
        # Игнорируем ссылки, юзернеймы и команды
        if w.startswith(('http', '@', '.', '/')):
            new_words.append(w)
            continue
            
        # 1. Шанс на "заикание" (берем первую букву и дублируем)
        if len(w) > 2 and random.random() < 0.6:
            # Делаем п-п-привет или п-привет
            if random.random() < 0.5:
                w = f"{w[0]}-{w[0]}-{w}"
            else:
                w = f"{w[0]}-{w}"
                
        # 2. Шанс на растягивание гласных (бляяяяяять)
        if random.random() < 0.4:
            # Ищем все гласные в слове
            found_vowels = [char for char in w if char in VOWELS]
            if found_vowels:
                # Берем случайную гласную и умножаем её
                target = random.choice(found_vowels)
                w = w.replace(target, target * random.randint(3, 6), 1)
                
        new_words.append(w)
        
    res = " ".join(new_words)
    
    # 3. Вставка каомодзи где-то в середине текста
    if random.random() < 0.5:
        parts = res.split()
        if len(parts) > 1:
            insert_idx = random.randint(1, len(parts)-1)
            parts.insert(insert_idx, random.choice(KAOMOJIS))
            res = " ".join(parts)
        else:
            res += f" {random.choice(KAOMOJIS)}"
            
    # 4. Добавление действия (RP) в конец
    if random.random() < 0.7:
        res += f" {random.choice(ACTIONS)}"
        
    # 5. Добавление милого окончания/эмодзи
    if random.random() < 0.8:
        res += f" {random.choice(ENDINGS)}"
        
    # Если вдруг скрипт ничего не добавил (из-за рандома), принудительно кинем эмодзи
    if res == text.lower():
        res += " 🥺"
        
    return res

@register_cmd("uwu", desc="Включить/выключить режим милашки. Использование: .uwu")
async def toggle_uwu(client, event, args):
    """Команда для переключения состояния модуля в конфиге"""
    current_state = get_config(__name__, "enabled")
    new_state = not current_state
    
    # Сохраняем новое состояние
    set_config(__name__, "enabled", new_state)
    
    status_text = "ВКЛЮЧЕН 🌸 (теперь все сообщения будут милыми)" if new_state else "ВЫКЛЮЧЕН 🧊 (возвращаемся к норме)"
    
    await event.edit(f"🎀 **UwU Mode:** {status_text}")
    
    # Удаляем сообщение с командой через 3 секунды, чтобы не мусорить
    await asyncio.sleep(3)
    await event.delete()

# Флаг, чтобы не зарегистрировать обработчик дважды при перезагрузках
_handler_registered = False

@register_bg()
async def uwu_interceptor(client):
    """
    Фоновый процесс. Мы используем его не для цикличной работы, 
    а для того, чтобы внедрить стандартный обработчик Telethon (events.NewMessage)
    в клиент юзербота при запуске.
    """
    global _handler_registered
    
    if _handler_registered:
        return
        
    # Навешиваем слушатель на все ИСХОДЯЩИЕ сообщения
    @client.on(events.NewMessage(outgoing=True))
    async def auto_uwu_handler(event):
        # Если режим выключен в конфиге - ничего не делаем
        if not get_config(__name__, "enabled"):
            return
            
        # Проверяем, есть ли текст
        if not event.raw_text:
            return
            
        # ВАЖНО: Игнорируем команды юзербота, иначе ты не сможешь выключить режим!
        # Предполагаем, что префикс команд это точка (.)
        if event.raw_text.startswith('.'):
            return
            
        try:
            # Генерируем новый текст
            new_text = uwuify(event.raw_text)
            
            # Ждем миллисекунды, имитируя процесс изменения
            await asyncio.sleep(0.1)
            
            # Редактируем отправленное сообщение
            await event.edit(new_text)
            
        except Exception as e:
            # Игнорируем ошибки (например, если сообщение нельзя редактировать - пересылка)
            pass

    _handler_registered = True
    print("[UwU Mode] Перехватчик сообщений успешно установлен!")
    
    # Бесконечный цикл, требуемый архитектурой фоновых задач, чтобы таска жила
    while True:
        await asyncio.sleep(3600)