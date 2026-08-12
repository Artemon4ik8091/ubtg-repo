import random
import time
from telethon import Button, errors
from registry import register_cmd, set_module_meta, send_inline, register_callback

set_module_meta("TicTacToe", "Игра в Крестики-Нолики (PvP и против Бота) с инлайн-кнопками.")

# Хранилище активных игр: game_id -> dict
games = {}

def check_winner(board):
    """
    Проверяет поле на победу или ничью.
    Возвращает: 'X', 'O', 'draw' или None (игра продолжается).
    """
    win_combinations = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),  # Горизонтали
        (0, 3, 6), (1, 4, 7), (2, 5, 8),  # Вертикали
        (0, 4, 8), (2, 4, 6)               # Диагонали
    ]
    for a, b, c in win_combinations:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]

    if " " not in board:
        return "draw"

    return None

def bot_make_move(board, bot_symbol, human_symbol):
    """
    Умный алгоритм хода Бота:
    1. Если бот может победить в 1 ход — побеждает.
    2. Если соперник может победить в 1 ход — блокирует его.
    3. Занимает центр (4).
    4. Занимает углы (0, 2, 6, 8).
    5. Выбирает любую случайную свободную клетку.
    """
    empty_cells = [i for i, cell in enumerate(board) if cell == " "]
    if not empty_cells:
        return None

    # 1. Проверка на победный ход бота
    for cell in empty_cells:
        temp_board = board[:]
        temp_board[cell] = bot_symbol
        if check_winner(temp_board) == bot_symbol:
            return cell

    # 2. Проверка на блокировку соперника
    for cell in empty_cells:
        temp_board = board[:]
        temp_board[cell] = human_symbol
        if check_winner(temp_board) == human_symbol:
            return cell

    # 3. Центр
    if 4 in empty_cells:
        return 4

    # 4. Углы
    corners = [i for i in [0, 2, 6, 8] if i in empty_cells]
    if corners:
        return random.choice(corners)

    # 5. Любая доступная
    return random.choice(empty_cells)

def render_game_buttons(game_id, game):
    """Формирует кнопки для поля 3х3 и панель управления."""
    board = game["board"]
    buttons = []
    
    # 3х3 поле
    for row in range(3):
        row_buttons = []
        for col in range(3):
            idx = row * 3 + col
            val = board[idx]
            symbol = "⬜" if val == " " else ("❌" if val == "X" else "⭕")
            row_buttons.append(Button.inline(symbol, f"ttt_cell_{game_id}_{idx}".encode()))
        buttons.append(row_buttons)

    # Дополнительные кнопки управления
    if game["status"] == "playing":
        buttons.append([Button.inline("🏳️ Сдаться", f"ttt_surrender_{game_id}".encode())])
    elif game["status"] == "ended":
        buttons.append([Button.inline("🔄 Новая игра", b"ttt_mainmenu")])

    return buttons

def format_game_text(game):
    """Формирует статусный текст игры."""
    if game["status"] == "lobby":
        if game["mode"] == "pvp":
            return (
                f"🎮 **Крестики-Нолики (PvP)**\n\n"
                f"👑 Создатель: [{game['creator_name']}](tg://user?id={game['creator_id']})\n"
                f"⏳ Ожидание второго игрока..."
            )
        else:
            return (
                f"🤖 **Крестики-Нолики (Против Бота)**\n\n"
                f"⚡️ Первым ходит **Бот (❌)**!\n"
                f"Нажмите кнопку ниже, чтобы принять вызов и сыграть за **⭕**:"
            )

    p_x_str = f"[{game['player_x_name']}](tg://user?id={game['player_x']})" if game['player_x'] != "bot" else "🤖 Бот"
    p_o_str = f"[{game['player_o_name']}](tg://user?id={game['player_o']})" if game['player_o'] != "bot" else "🤖 Бот"

    text = f"🎮 **Крестики-Нолики**\n\n❌ {p_x_str} 🆚 ⭕ {p_o_str}\n\n"

    if game["status"] == "playing":
        curr_turn = game["turn"]
        curr_player = p_x_str if curr_turn == "X" else p_o_str
        curr_icon = "❌" if curr_turn == "X" else "⭕"
        text += f"👉 Сейчас ход: {curr_icon} {curr_player}"
    elif game["status"] == "ended":
        winner = game.get("winner")
        if winner == "draw":
            text += "🤝 **Игра завершена вничью!**"
        elif winner == "X":
            text += f"🎉 **Победитель: ❌ {p_x_str}!** 🏆"
        elif winner == "O":
            text += f"🎉 **Победитель: ⭕ {p_o_str}!** 🏆"

    return text


@register_cmd("ttt", desc="Запустить игру Крестики-Нолики. Юзай: .ttt")
@register_cmd("tictactoe", desc="Запустить игру Крестики-Нолики. Юзай: .tictactoe")
async def ttt_cmd(client, event, args):
    """Команда запуска меню игры Крестики-Нолики."""
    await event.edit("🔄 Загрузка меню игры...")

    buttons = [
        [Button.inline("👥 Игрок против Игрока (PvP)", b"ttt_pvpmode")],
        [Button.inline("🤖 Игра против Бота (PvBot)", b"ttt_botmode")]
    ]

    try:
        await send_inline(
            client,
            event.chat_id,
            "❌⭕ **Крестики-Нолики**\nВыберите режим игры:",
            buttons=buttons,
            reply_to=event.reply_to_msg_id
        )
        await event.delete()
    except Exception as e:
        await event.edit(f"❌ Ошибка вызова инлайн-игры: {e}")


# --- ОБРАБОТЧИКИ КНОПОК МЕНЮ И ЛОББИ ---

@register_callback("ttt_mainmenu")
async def on_ttt_menu(event, data):
    buttons = [
        [Button.inline("👥 Игрок против Игрока (PvP)", b"ttt_pvpmode")],
        [Button.inline("🤖 Игра против Бота (PvBot)", b"ttt_botmode")]
    ]
    try:
        await event.edit("❌⭕ **Крестики-Нолики**\nВыберите режим игры:", buttons=buttons)
    except errors.MessageNotModifiedError:
        await event.answer()
    except Exception as e:
        if "not modified" in str(e).lower():
            await event.answer()
        else:
            raise e

@register_callback("ttt_pvpmode")
async def on_start_pvp(event, data):
    user = await event.get_sender()
    game_id = f"g{int(time.time() * 1000)}"
    user_name = user.first_name if user else "Игрок 1"

    games[game_id] = {
        "mode": "pvp",
        "creator_id": user.id,
        "creator_name": user_name,
        "player_x": user.id,
        "player_x_name": user_name,
        "player_o": None,
        "player_o_name": None,
        "turn": "X",
        "board": [" "] * 9,
        "status": "lobby"
    }

    buttons = [[Button.inline("⚔️ Присоединиться к игре", f"ttt_join_{game_id}".encode())]]
    text = format_game_text(games[game_id])
    await event.edit(text, buttons=buttons)

@register_callback("ttt_botmode")
async def on_start_bot(event, data):
    user = await event.get_sender()
    game_id = f"g{int(time.time() * 1000)}"

    games[game_id] = {
        "mode": "pvbot",
        "creator_id": user.id,
        "creator_name": user.first_name if user else "Игрок",
        "player_x": "bot",  # Бот ходит первым (за ❌)
        "player_x_name": "🤖 Бот",
        "player_o": None,
        "player_o_name": None,
        "turn": "X",
        "board": [" "] * 9,
        "status": "lobby"
    }

    buttons = [[Button.inline("🎮 Сыграть против Бота", f"ttt_joinbot_{game_id}".encode())]]
    text = format_game_text(games[game_id])
    await event.edit(text, buttons=buttons)

@register_callback("ttt_join_")
async def on_join_pvp(event, data):
    game_id = data.replace("ttt_join_", "")
    game = games.get(game_id)
    if not game:
        return await event.answer("⚠️ Игра не найдена или устарела.", alert=True)

    if game["status"] != "lobby":
        return await event.answer("⚠️ Игра уже началась!", alert=True)

    user = await event.get_sender()
    if user.id == game["creator_id"]:
        return await event.answer("❌ Вы создатель этой игры! Позовите другого игрока.", alert=True)

    # Игрок 2 становится ⭕
    game["player_o"] = user.id
    game["player_o_name"] = user.first_name or "Игрок 2"
    game["status"] = "playing"

    text = format_game_text(game)
    buttons = render_game_buttons(game_id, game)
    await event.edit(text, buttons=buttons)

@register_callback("ttt_joinbot_")
async def on_join_bot(event, data):
    game_id = data.replace("ttt_joinbot_", "")
    game = games.get(game_id)
    if not game:
        return await event.answer("⚠️ Игра не найдена или устарела.", alert=True)

    if game["status"] != "lobby":
        return await event.answer("⚠️ Игра уже началась!", alert=True)

    user = await event.get_sender()
    game["player_o"] = user.id
    game["player_o_name"] = user.first_name or "Игрок"
    game["status"] = "playing"

    # Бот делает первый ход (за ❌)
    bot_move = bot_make_move(game["board"], bot_symbol="X", human_symbol="O")
    if bot_move is not None:
        game["board"][bot_move] = "X"

    # Следующий ход передаем человеку (⭕)
    game["turn"] = "O"

    text = format_game_text(game)
    buttons = render_game_buttons(game_id, game)
    await event.edit(text, buttons=buttons)


# --- ОБРАБОТКА ХОДОВ И УПРАВЛЕНИЯ ---

@register_callback("ttt_cell_")
async def on_cell_click(event, data):
    # data формат: ttt_cell_<game_id>_<idx>
    payload = data.replace("ttt_cell_", "")
    try:
        game_id, idx_str = payload.rsplit("_", 1)
        idx = int(idx_str)
    except Exception:
        return

    game = games.get(game_id)

    if not game or game["status"] != "playing":
        return await event.answer("⚠️ Игра завершена или не существует.", alert=True)

    user = await event.get_sender()
    curr_turn = game["turn"]

    # Проверка очередности хода
    if curr_turn == "X" and user.id != game["player_x"]:
        return await event.answer("⚠️ Сейчас не ваш ход!", alert=True)
    if curr_turn == "O" and user.id != game["player_o"]:
        return await event.answer("⚠️ Сейчас не ваш ход!", alert=True)

    # Проверка свободы клетки
    if game["board"][idx] != " ":
        return await event.answer("❌ Эта клетка уже занята!", alert=True)

    # Совершаем ход человека
    game["board"][idx] = curr_turn

    # Проверяем результат хода человека
    winner = check_winner(game["board"])
    if winner:
        game["status"] = "ended"
        game["winner"] = winner
    else:
        # Переключаем ход
        next_turn = "O" if curr_turn == "X" else "X"
        game["turn"] = next_turn

        # Если следующий ход за ботом
        next_player = game["player_x"] if next_turn == "X" else game["player_o"]
        if next_player == "bot":
            bot_move = bot_make_move(game["board"], bot_symbol=next_turn, human_symbol=curr_turn)
            if bot_move is not None:
                game["board"][bot_move] = next_turn
            
            # Проверяем результат хода бота
            bot_winner = check_winner(game["board"])
            if bot_winner:
                game["status"] = "ended"
                game["winner"] = bot_winner
            else:
                game["turn"] = curr_turn

    text = format_game_text(game)
    buttons = render_game_buttons(game_id, game)
    await event.edit(text, buttons=buttons)

@register_callback("ttt_surrender_")
async def on_surrender(event, data):
    game_id = data.replace("ttt_surrender_", "")
    game = games.get(game_id)
    if not game or game["status"] != "playing":
        return await event.answer("⚠️ Игра уже завершена.", alert=True)

    user = await event.get_sender()
    if user.id not in [game["player_x"], game["player_o"]]:
        return await event.answer("⚠️ Вы не участник этой игры!", alert=True)

    # Победителем становится второй игрок
    if user.id == game["player_x"]:
        game["winner"] = "O"
    else:
        game["winner"] = "X"

    game["status"] = "ended"
    text = format_game_text(game) + "\n🏳️ **Один из игроков сдался!**"
    buttons = render_game_buttons(game_id, game)
    await event.edit(text, buttons=buttons)
