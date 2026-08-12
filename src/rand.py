import random
from registry import register_cmd
from registry import set_module_meta

set_module_meta("Rand", desc="Модуль для генерации случайных чисел.")

@register_cmd("rand", desc="Выдает случайное число в заданных границах. Пример: .rand 10 100")
async def rand_command(client, event, args):
    # Проверяем, передал ли вообще кто-то аргументы
    if not args:
        await event.edit("Бро, ты забыл указать границы! 🤦‍♂️ Напиши типа `.rand 1 100`")
        return

    try:
        # Разбиваем строку с аргументами по пробелам
        parts = args.split()
        
        if len(parts) == 1:
            # Если ввели только одно число, считаем его верхней границей (от 0 до X)
            min_val = 0
            max_val = int(parts[0])
        else:
            # Если чисел два (или больше, но мы возьмем только первые два)
            min_val = int(parts[0])
            max_val = int(parts[1])
            
        # Защита от дурака: если первое число больше второго, просто меняем их местами
        if min_val > max_val:
            min_val, max_val = max_val, min_val

        # Генерим число и меняем сообщение
        result = random.randint(min_val, max_val)
        await event.edit(f"🎲 Рандомное число ({min_val} - {max_val}): **{result}**")

    except ValueError:
        # Если юзер ввел буквы вместо цифр типа ".rand a b"
        await event.edit("Нужны только цифры! Пример: `.rand 10 100`")