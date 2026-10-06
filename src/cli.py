from __future__ import annotations

import argparse
import sys
import time

from .ai import choose_action
from .cards import build_decks
from .game import Action, Game
from .models import ATTRIBUTES, Attribute, Player
from .rules import RuleError, create_state
from .seeding import seed_description, select_seed
from .specializations import legal_card_targets, legal_player_targets, specialization_name


def show(game: Game) -> None:
    state = game.state
    print(f"\n第 {state.round_number} 轮 | 当前玩家：{state.current().name}")
    if state.pending_specializations:
        print("待结算：" + specialization_name(state.pending_specializations[0]))
    print("公共资源：" + " ".join(f"{a.value}{state.resource_pool[a]}" for a in ATTRIBUTES) + f" 光{state.light_pool}")
    for level in (1, 2, 3):
        print(f"{level}级市场：" + " | ".join(f"{card.card_id}({card.cost_text()}=>{card.score})" for card in state.market.cards[level]))
    for player in state.players:
        discounts = " ".join(f"{a.value}{n}" for a, n in player.permanent_discounts.items() if n)
        print(
            f"{player.name}: 分数{player.score} 资源{player.resource_count}/{player.resource_capacity} "
            f"折扣[{discounts or '-'}] 预购{len(player.reserved)}"
        )


def run(seed: int, ai_only: bool, interval: float = 0.0) -> None:
    players = [Player("你" if not ai_only else "AI-1")] + [Player(f"AI-{index}") for index in range(2, 5)]
    game = Game(create_state(players, build_decks(seed), seed))
    if ai_only:
        print(f"四 AI 对战开始，随机种子：{seed}，每次行动间隔：{interval:g} 秒")
    while not game.state.finished:
        show(game)
        if game.state.current_player != 0 or ai_only:
            action = choose_action(game)
            print(f"{game.state.current().name} 执行：{action.kind}")
        else:
            action = read_action(game)
        try:
            game.execute(action)
        except (RuleError, ValueError) as error:
            print(f"操作无效：{error}")
        if ai_only and interval > 0:
            time.sleep(interval)
    show(game)
    print("胜者：" + ", ".join(player.name for player in game.winners()))


def read_action(game: Game) -> Action:
    player = game.state.current()
    if game.state.pending_specializations:
        effect = game.state.pending_specializations[0]
        cards = legal_card_targets(game.state, effect)
        players = legal_player_targets(game.state, effect)
        print("结算属性专精：" + specialization_name(effect))
        if cards:
            print("可选卡牌：" + " ".join(card.card_id for card in cards))
            card_id = input("选择卡牌编号：").strip().upper()
            card = next((item for item in cards if item.card_id == card_id), None)
            if card is None:
                raise RuleError("无效的专精卡牌目标")
            return Action("specialization", card=card)
        if players:
            print("可选玩家：" + " ".join(f"{index}:{game.state.players[index].name}" for index in players))
            target = int(input("选择玩家编号：").strip())
            return Action("specialization", target_player=target)
        return Action("specialization")

    command = input("操作 [d=三种资源, s=同属性, b=购买, r=预购, q=退出]：").strip().lower()
    if command == "q":
        raise SystemExit
    if command == "d":
        values = input("输入三个属性（水火草萌恶）：").strip()
        return Action("different", attributes=tuple(Attribute(value) for value in values))
    if command == "s":
        return Action("same", attributes=(Attribute(input("属性：").strip()),))
    level = int(input("等级："))
    card_id = input("卡牌编号：").strip().upper()
    card = next(card for card in game.state.market.cards[level] + player.reserved if card.card_id == card_id)
    if command == "r":
        return Action("reserve", card=card)
    choices = tuple(Attribute(value) for value in input("双属性折扣选择（每张双属性宠物输入一个属性）：").strip()) if player.dual_cards() else ()
    return Action("buy", card=card, dual_choices=choices)


def main() -> None:
    parser = argparse.ArgumentParser(description="洛克王国：魔法宝石 MVP")
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int, help="使用指定的固定随机种子")
    seed_group.add_argument("--random-seed", action="store_true", help="每次启动时自动生成随机种子")
    parser.add_argument("--ai-only", action="store_true")
    parser.add_argument("--ai-battle", action="store_true", help="启动四 AI 自动对战模式")
    parser.add_argument("--interval", type=float, help="AI 每次行动间隔秒数")
    parser.add_argument("--gui", action="store_true", help="启动 Tkinter 图形界面")
    args = parser.parse_args()
    if args.gui:
        import tkinter as tk

        if sys.version_info < (3, 11) or tk.TkVersion < 8.6:
            parser.error("图形界面需要 Python 3.11+ 和 Tk 8.6+；请换用符合要求的解释器（本机可试 python -m src.cli --gui）")
    seed, seed_mode = select_seed(args.seed, args.random_seed)
    print("本局使用" + seed_description(seed, seed_mode))
    if args.gui:
        from .gui import MagicGemsApp

        if args.ai_battle:
            if args.interval is None:
                raw_interval = input("请输入 GUI AI 对战每次行动间隔（秒，直接回车为 0.5）：").strip()
                interval = float(raw_interval) if raw_interval else 0.5
            else:
                interval = args.interval
            if interval < 0:
                parser.error("--interval 不能小于 0")
            MagicGemsApp(seed, ai_battle=True, interval=interval, seed_mode=seed_mode).mainloop()
        else:
            MagicGemsApp(seed, seed_mode=seed_mode).mainloop()
        return
    if args.ai_battle:
        if args.interval is None:
            raw_interval = input("请输入 AI 每次行动间隔（秒，直接回车为 0）：").strip()
            interval = float(raw_interval) if raw_interval else 0.0
        else:
            interval = args.interval
        if interval < 0:
            parser.error("--interval 不能小于 0")
        run(seed, True, interval)
        return
    run(seed, args.ai_only, args.interval or 0.0)


if __name__ == "__main__":
    main()
