import asyncio
from registry import register_cmd, set_module_meta

# Задаем метаданные, чтобы в .help всё было по красоте
set_module_meta(
    name="Spammer",
    desc="Модуль для спама сообщениями. Команды: .spam и .stopspam",
    system=False
)

# Глобальный флаг, чтобы понимать, спамим мы сейчас или нет
is_spamming = False

@register_cmd("spam", desc="Запустить спам. Использование: .spam <количество> <текст>")
async def spam_cmd(client, event, args):
    global is_spamming
    
    # Проверка, ввел ли юзер вообще хоть что-то
    if not args:
        return await event.edit("❌ Ну ты хоть напиши че спамить. Юзай: `.spam 20 текст`")
        
    # Разбиваем аргументы: первое слово берем как число, остальное - как текст
    parts = args.split(maxsplit=1)
    
    if len(parts) < 2:
        return await event.edit("❌ Не хватает аргументов! Надо вот так: `.spam 20 текст`")
        
    # Пробуем достать число
    try:
        count = int(parts[0])
    except ValueError:
        return await event.edit("❌ Первым аргументом должно быть число!")
        
    text = parts[1]
    
    # Удаляем само сообщение с командой, чтобы не мусорить в чате
    await event.delete()
    
    # Запускаем машину
    is_spamming = True
    
    for _ in range(count):
        # Если кто-то прописал .stopspam - выходим из цикла
        if not is_spamming:
            break
            
        try:
            # Отправляем текст в тот же чат
            await event.respond(text)
            # Обязательная задержка, чтобы ТГ не дал пизды за спам
            await asyncio.sleep(0.3) 
        except Exception as e:
            print(f"[Spammer] Ошибка при отправке: {e}")
            break
            
    # Когда всё закончилось, сбрасываем флаг на всякий пожарный
    is_spamming = False

@register_cmd("stopspam", desc="Остановить текущий спам")
async def stopspam_cmd(client, event, args):
    global is_spamming
    
    if not is_spamming:
        return await event.edit("⚠ Да я вроде и так не спамлю сейчас.")
        
    # Глушим мотор
    is_spamming = False
    await event.edit("🛑 Спам успешно тормознули.")
