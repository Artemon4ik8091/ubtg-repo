# ---------------------------------------------------------------------------------
# Name: DoxTool
# Description: Your Best doxing tool! (Joke module)
# Author: @codrago_m
# Adapted for New Userbot Architecture
# ---------------------------------------------------------------------------------

import asyncio
import random
from registry import register_cmd, set_module_meta

set_module_meta(
    name="DoxTool",
    desc="Шуточный модуль для 'деанона'. Создан в развлекательных целях.",
    system=False
)

strings = {
    "gb_1": "Поиск номера жертвы...",
    "gb_2": "Поиск адреса и имени жертвы...",
    "gb_3": "Поиск родителей...",
    "gb_4": "Поиск школы...",
    "gb_5": "Поиск работы родителей...",
    "gb_r": "Мой хозяин плохо себя вел, и я решил слить инфу о нем!\n\n├ Телефон: разъебанный\n├ Страна: обычная\n├ Регион: пиздоболов\n├ Родители: скоро не будет\n├ Адрес: канава на Арбате\n├ Имя: нахуй ты родился\n├ Отчество: отсутствует\n├ Фамилия: отсутствует\n├ Сколько раз ебали в дырку: 32\n├ Пол: ленолиум\n├ Дом: канава на Арбате\n├ Сосёт в день: 20 (раз) за 10 руб\n├ Больница: не пускают\n├ Цвет говна: нету, ибо не хавает\n├ Простата: массирована\n├ Рот: выебан\n└ #####################\n\nМать: шлюха\nМесто работы матери: трасса\nСтрана: состоящаяся в СНГ\nГород: я ебу?\nРодилась: где-то под забором\n\nОтец: бомж,\nМесто работы: на улице бичевать, просить мелочь\nСтрана: состоящаяся в СНГ\nГород: я ебу?\nРодился: в канализации\nШкола: далбоебов",
    "info": "Этот модуль создан исключительно в развлекательных целях, его функциональность сделана исключительно ради шутки"
}

@register_cmd("gb", desc="Поиск в базах данных (шутка)")
async def gb_cmd(client, event, args):
    await event.edit(strings["gb_1"])
    await asyncio.sleep(1)
    await event.edit(strings["gb_2"])
    await asyncio.sleep(1)
    await event.edit(strings["gb_3"])
    await asyncio.sleep(1)
    await event.edit(strings["gb_4"])
    await asyncio.sleep(1)
    await event.edit(strings["gb_5"])
    await asyncio.sleep(1)
    await event.edit(strings["gb_r"])

@register_cmd("deanon", desc="Полная информация о пользователе (шутка)")
async def deanon_cmd(client, event, args):
    deanon_phrases = [
        "Плохо поступать вот так вот...",
        "Как же ты меня достал!", 
        "Ещё одна такая выходка, и я удалю твой аккаунт.", 
        "С первого раза не понял?", 
        "Зачем ты продолжаешь это делать??", 
        "Мы оба знаем, что ни к чему хорошему это", 
        "не приведет."
    ]
    await event.edit(random.choice(deanon_phrases))

@register_cmd("dinfo", desc="Информация о модуле")
async def dinfo_cmd(client, event, args):
    await event.edit(strings["info"])