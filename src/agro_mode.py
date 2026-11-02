from registry import register_cmd, set_module_meta, init_config, get_config, set_config, register_bg
from telethon import events
import random
import asyncio
import re

# Метаданные для команды .help
set_module_meta(
    name="Agro Mode", 
    desc="Автоматически делает твои сообщения максимально токсичными (мат, капс, агрессия). Вкл/Выкл: .agro", 
    system=False
)

# Инициализируем конфиг. По умолчанию режим выключен.
init_config(__name__, {
    "enabled": False
})

# Наборы данных для генерации токсичности
SWEARS = [
    "блять", "сука", "нахуй", "ебать", "пиздец", "епт", "нах", "бля", "заебал",
    "хуй", "блядь", "ебаный", "охуеть", "еблан", "пизда", "ебанутый", "хер",
    "хуйня", "блядство", "ебанина", "заебись", "ебтвоюмать", "пиздюк", "хуесос",
    "ебарь", "пиздос", "хуище", "хуйло", "ебень", "залупа", "опизденеть", "хуета",
    "мудозвон", "ебобо", "пиздобол", "ебать-копать", "ептить"
]

INSULTS = [
    "клоун", "чепуха", "долбаеб", "слитый", "мусор", "бездарь", "чушпан", "даун", "хуило",
    "терпило", "нытик", "опущенец", "шлюха", "пидорас", "гандон", "мразь", "уебок",
    "выблядок", "уебище", "чмо", "петух", "ничтожество", "биомусор", "выпердыш",
    "дегенерат", "отброс", "аутист", "соевый", "куколд", "черт", "животное", "обрыган",
    "шмара", "шваль", "пес", "олух", "полупокер", "душнила"
]

def agroify(text):
    """Функция превращения обычного текста в агрессивный и токсичный (упор на мат)"""
    if not text:
        return text
        
    words = text.split()
    new_words = []
    
    # 1. Шанс на то, что всё сообщение будет написано КАПСОМ (повышен до 40%)
    full_caps = random.random() < 0.4
    
    for i, w in enumerate(words):
        # Игнорируем ссылки, юзернеймы и команды
        if w.startswith(('http', '@', '.', '/')):
            new_words.append(w)
            continue
            
        # 2. Агрессивная вставка мата (шанс 35% перед почти каждым словом)
        if random.random() < 0.35:
            swear = random.choice(SWEARS)
            new_words.append(swear.upper() if full_caps else swear)
                
        # 3. Применение КАПСА к слову (точечно)
        if full_caps or random.random() < 0.25:
            w = w.upper()
            
        new_words.append(w)
        
    res = " ".join(new_words)
        
    # 4. Мощное завершение фразы матом или оскорблением (шанс 80%)
    if random.random() < 0.8:
        ending_word = random.choice(INSULTS + SWEARS)
        if full_caps:
            ending_word = ending_word.upper()
        res += f" {ending_word}"
        
    return res

@register_cmd("agro", desc="Включить/выключить режим токсика. Использование: .agro")
async def toggle_agro(client, event, args):
    """Команда для переключения состояния модуля в конфиге"""
    current_state = get_config(__name__, "enabled")
    new_state = not current_state
    
    # Сохраняем новое состояние
    set_config(__name__, "enabled", new_state)
    
    status_text = "ВКЛЮЧЕН 🤬 (режим берсерка активирован)" if new_state else "ВЫКЛЮЧЕН 🧘‍♂️ (возвращаемся к спокойствию)"
    
    await event.edit(f"🔥 **Agro Mode:** {status_text}")
    
    # Удаляем сообщение с командой через 3 секунды
    await asyncio.sleep(3)
    await event.delete()

# Флаг, чтобы избежать двойной регистрации при рестартах
_agro_handler_registered = False

@register_bg()
async def agro_interceptor(client):
    """
    Фоновый процесс, который перехватывает исходящие сообщения
    и применяет к ним токсичный фильтр перед отправкой.
    """
    global _agro_handler_registered
    
    if _agro_handler_registered:
        return
        
    @client.on(events.NewMessage(outgoing=True))
    async def auto_agro_handler(event):
        # Если режим выключен - пропускаем
        if not get_config(__name__, "enabled"):
            return
            
        if not event.raw_text:
            return
            
        # Игнорируем команды юзербота, чтобы не сломать управление
        if event.raw_text.startswith('.'):
            return
            
        try:
            # Преобразуем текст
            new_text = agroify(event.raw_text)
            
            # Небольшая задержка
            await asyncio.sleep(0.1)
            
            # Заменяем оригинальное сообщение на агрессивное
            await event.edit(new_text)
            
        except Exception as e:
            # Игнорируем ошибки (например, если сообщение нельзя редактировать)
            pass

    _agro_handler_registered = True
    print("[Agro Mode] Перехватчик сообщений (Токсик) успешно установлен!")
    
    # Поддержание жизни фоновой таски
    while True:
        await asyncio.sleep(3600)