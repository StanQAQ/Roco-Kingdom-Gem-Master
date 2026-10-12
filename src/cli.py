from __future__ import annotations

import argparse
import os
import sys
import time

from .ai import choose_action
from .cards import build_decks
from .game import Action, Game
from .models import ATTRIBUTES, Attribute, Player
from .rules import RuleError, create_state
from .seeding import create_rng, seed_description, select_seed
from .specializations import legal_card_targets, legal_player_targets, specialization_name
from .deepseek_ai import DeepSeekOpponent, configured_api_key


def show(game: Game) -> None:
    state = game.state
    print(f"\n第 {state.round_number} 轮 | 当前玩家：{state.current().name}")
    if state.pending_specializations:
        print("待结算：" + specialization_name(state.pending_specializations[0]))
    print("公共资源：" + " ".join(f"{a.value}{state.resource_pool[a]}" for a in ATTRIBUTES) + f" 光{state.light_pool}")
    print("魔法师市场：" + (" | ".join(
        f"{card.name}({card.requirement_text})" if card is not None else "（空位）"
        for card in state.wizard_market
    ) or "空"))
    for level in (1, 2, 3):
        print(f"{level}级市场：" + " | ".join(f"{card.display_name}({card.cost_text()}=>{card.effective_score})" for card in state.market.cards[level]))
    for player in state.players:
        discounts = " ".join(f"{a.value}{n}" for a, n in player.permanent_discounts.items() if n)
        wizard_cards = "、".join(card.name for card in player.wizard_cards) or "无"
        print(
            f"{player.name}: 分数{player.score} 资源{player.resource_count}/{player.resource_capacity} "
            f"折扣[{discounts or '-'}] 预购{len(player.reserved)}"
            f" 魔法师卡{len(player.wizard_cards)}/10[{wizard_cards}]"
            f"{' 下张分数×2' if player.next_purchase_score_doubled else ''}"
            f"{' 攻击免疫待触发' if player.next_attack_immune else ''}"
        )


def run(
    seed: int,
    ai_only: bool,
    interval: float = 0.0,
    deepseek_player: int | None = None,
    deepseek_all: bool = False,
    seed_mode: str = "fixed",
) -> None:
    players = [Player("你" if not ai_only else "AI-1")] + [Player(f"AI-{index}") for index in range(2, 5)]
    deepseek_opponents = (
        {index: DeepSeekOpponent() for index in range(4)}
        if deepseek_all
        else {deepseek_player: DeepSeekOpponent()}
        if deepseek_player is not None
        else {}
    )
    if deepseek_all:
        players = [Player(f"DeepSeek-{index + 1}") for index in range(4)]
    elif deepseek_player is not None:
        players[deepseek_player].name = "DeepSeek"
    deck_rng = create_rng(seed, seed_mode)
    state_rng = create_rng(seed, seed_mode)
    game = Game(create_state(players, build_decks(rng=deck_rng), seed, rng=state_rng))
    if ai_only:
        print(f"四 AI 对战开始，{seed_description(seed, seed_mode)}，每次行动间隔：{interval:g} 秒")
    while not game.state.finished:
        show(game)
        if game.state.current_player != 0 or ai_only:
            opponent = deepseek_opponents.get(game.state.current_player)
            if opponent is not None:
                decision = opponent.decide(game)
                action = decision.action
                if decision.notice:
                    print(decision.notice)
            else:
                action = choose_action(game)
            print(f"{game.state.current().name} 执行：{action.kind}")
        else:
            action = read_action(game)
        try:
            messages = game.execute(action)
            for message in messages:
                print(message)
        except (RuleError, ValueError) as error:
            print(f"操作无效：{error}")
        if ai_only and interval > 0:
            time.sleep(interval)
    show(game)
    winners = game.winners()
    print("胜者：" + ", ".join(player.name for player in winners) if winners else "无人获胜（轮末无人达到20分）")


def read_action(game: Game) -> Action:
    player = game.state.current()
    if game.state.pending_specializations:
        effect = game.state.pending_specializations[0]
        cards = legal_card_targets(game.state, effect)
        players = legal_player_targets(game.state, effect)
        print("结算属性专精：" + specialization_name(effect))
        if cards:
            print("可选卡片：")
            for index, card in enumerate(cards, start=1):
                print(f"  {index}. {card.display_name}（{card.level}级，{card.cost_text() or '无成本'}，{card.effective_score}分）")
            choice = int(input("选择卡片序号：").strip())
            if not 1 <= choice <= len(cards):
                raise RuleError("无效的专精卡片选择")
            return Action("specialization", card=cards[choice - 1])
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
    candidates = [
        *((card, "市场") for card in game.state.market.cards[level]),
        *((card, "预购") for card in player.reserved),
    ]
    if not candidates:
        raise RuleError(f"{level}级市场没有可选卡片")
    print("可选卡片：")
    for index, (card, zone) in enumerate(candidates, start=1):
        print(f"  {index}. {card.display_name}（{zone}，{card.level}级，{card.cost_text() or '无成本'}，{card.effective_score}分）")
    choice = int(input("选择卡片序号：").strip())
    if not 1 <= choice <= len(candidates):
        raise RuleError("无效的卡片选择")
    card = candidates[choice - 1][0]
    if command == "r":
        return Action("reserve", card=card)
    choices = tuple(Attribute(value) for value in input("双属性折扣选择（每张双属性宠物输入一个属性）：").strip()) if player.dual_cards() else ()
    return Action("buy", card=card, dual_choices=choices)


def main() -> None:
    parser = argparse.ArgumentParser(description="洛克王国：魔法宝石")
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int, help="使用指定的固定随机种子")
    seed_group.add_argument("--random-seed", action="store_true", help="每次启动时自动生成随机种子")
    parser.add_argument("--ai-only", action="store_true")
    parser.add_argument("--ai-battle", action="store_true", help="启动四 AI 自动对战模式")
    deepseek_mode = parser.add_mutually_exclusive_group()
    deepseek_mode.add_argument("--deepseek-player", type=int, choices=range(1, 5), metavar="1-4",
                               help="在四 AI 对战中让指定座位由 DeepSeek 控制")
    deepseek_mode.add_argument("--deepseek-all", action="store_true",
                               help="在四 AI 对战中让全部四个座位由 DeepSeek 控制")
    parser.add_argument("--interval", type=float, help="AI 每次行动间隔秒数")
    parser.add_argument("--gui", action="store_true", help="启动 Qt6 图形界面")
    args = parser.parse_args()
    if args.deepseek_player is not None or args.deepseek_all:
        if not args.ai_battle:
            parser.error("DeepSeek 对手选项只能与 --ai-battle 一起使用")
        if not configured_api_key():
            parser.error("请先在项目根目录的 .env.deepseek 文件中填写 DEEPSEEK_API_KEY")
    if args.gui:
        if sys.version_info < (3, 11):
            parser.error("图形界面需要 Python 3.11+")
        try:
            from PySide6.QtWidgets import QApplication  # noqa: F401
            from PySide6.QtGui import QColor
        except ImportError:
            parser.error("Qt6 图形界面需要安装 PySide6：python -m pip install PySide6")
        if sys.version_info < (3, 12):
            # PySide6 6.12's abi3 bindings can over-decrement None when called
            # from CPython 3.11. Detect it before the paint loop turns that
            # reference-count error into a process-wide none_dealloc abort.
            color = QColor()
            none_refcount = sys.getrefcount(None)
            color.setAlpha(255)
            if sys.getrefcount(None) < none_refcount:
                parser.error(
                    "当前 PySide6 与 CPython 3.11 的组合会错误减少 None 的引用计数，"
                    "可能导致 none_dealloc 崩溃。请改用 Python 3.12+，并在该版本中安装 PySide6。"
                )
    if args.gui and not args.ai_battle:
        # 普通 GUI 要等玩家选定具体难度后再生成随机种子。
        seed = args.seed
        seed_mode = "fixed" if seed is not None else "random"
    else:
        seed, seed_mode = select_seed(args.seed, args.random_seed, default_random=args.gui)
        print("本局使用" + seed_description(seed, seed_mode))
    if args.gui:
        from .qt_gui import MagicGemsQtApp

        # 设置全局 Qt 缩放比例后再创建 QApplication，使窗口、卡片、文字、
        # 弹窗和图标统一按 1.25 倍显示（设计逻辑尺寸为 1200×800）。
        os.environ["QT_SCALE_FACTOR"] = str(MagicGemsQtApp.UI_SCALE_FACTOR)

        if args.ai_battle:
            if args.interval is None:
                raw_interval = input("请输入 GUI AI 对战每次行动间隔（秒，直接回车为 0.5）：").strip()
                interval = float(raw_interval) if raw_interval else 0.5
            else:
                interval = args.interval
            if interval < 0:
                parser.error("--interval 不能小于 0")
            app = QApplication(sys.argv)
            window = MagicGemsQtApp(
                seed, ai_battle=True, interval=interval, seed_mode=seed_mode,
                deepseek_player=args.deepseek_player - 1 if args.deepseek_player is not None else None,
                deepseek_all=args.deepseek_all,
                deepseek_opponents={
                    seat: DeepSeekOpponent()
                    for seat in (
                        range(4) if args.deepseek_all
                        else [args.deepseek_player - 1] if args.deepseek_player is not None
                        else []
                    )
                },
            )
            window.show()
            sys.exit(app.exec())
        else:
            app = QApplication(sys.argv)
            window = MagicGemsQtApp(seed, seed_mode=seed_mode)
            window.show()
            sys.exit(app.exec())
        return
    if args.ai_battle:
        if args.interval is None:
            raw_interval = input("请输入 AI 每次行动间隔（秒，直接回车为 0）：").strip()
            interval = float(raw_interval) if raw_interval else 0.0
        else:
            interval = args.interval
        if interval < 0:
            parser.error("--interval 不能小于 0")
        run(
            seed,
            True,
            interval,
            args.deepseek_player - 1 if args.deepseek_player is not None else None,
            args.deepseek_all,
            seed_mode,
        )
        return
    run(seed, args.ai_only, args.interval or 0.0, seed_mode=seed_mode)


if __name__ == "__main__":
    main()
