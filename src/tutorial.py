"""Contextual, non-prescriptive rules reminders for the Qt tutorial match."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .models import ATTRIBUTES, Attribute, GameState, Player
from .rules import RuleError, payment_for
from .specializations import single_attribute_count


@dataclass(frozen=True)
class TutorialHint:
    topic: str
    title: str
    body: str


TUTORIAL_INTRO = TutorialHint(
    "intro",
    "欢迎来到魔法宝石！",
    "你需要通过获取资源、购买宠物来赢得胜利\n"
    "当卡片右上角的分数达到20分时，即可获胜\n"
    "先试试在右下角获取资源吧！",
)


HINTS = {
    "resources": TutorialHint(
        "resources", "本回合提示：领取资源",
        "领取资源会用掉本回合唯一的一项行动。你可以拿三种不同属性各 1 枚，也可以在公共池该属性至少剩 4 枚时拿同一种 2 枚。资源与贤者碎晶合计最多持有 10 枚。",
    ),
    "buy": TutorialHint(
        "buy", "本回合提示：购买宠物卡",
        "购买宠物卡需要支付费用，并会立刻获得卡面分数。之后购买其他宠物时，已购卡提供永久折扣；贤者碎晶可以补足任意属性的费用。购买同样会用掉本回合唯一的一项行动。",
    ),
    "reserve": TutorialHint(
        "reserve", "本回合提示：预购",
        "预购会把一张市场卡留给自己，并立即获得 1 枚贤者碎晶。预购卡不能在同一行动中购买；之后仍要用一次行动支付费用。每名玩家最多预购 3 张卡。",
    ),
    "discount": TutorialHint(
        "discount", "本回合提示：属性折扣",
        "单属性宠物提供对应属性的永久折扣。双属性宠物购买时要为每张已购双属性卡选择本次计入的一个属性；你也可以在自己的回合拖动已购双属性卡来调整折扣属性。",
    ),
    "specialization": TutorialHint(
        "specialization", "本回合提示：属性专精",
        "单属性宠物会推进对应属性的专精进度，达到门槛后可能触发特殊效果。双属性宠物不计入专精张数；部分效果会在行动结算时要求你选择目标。",
    ),
    "wizard": TutorialHint(
        "wizard", "本回合提示：魔法师卡",
        "公开的魔法师卡会检查你已购买宠物的属性组合。符合条件时会在回合结算自动获得，每张增加 3 分；双属性宠物同时计入两种属性，资源和预购卡不计入。",
    ),
    "victory": TutorialHint(
        "victory", "本回合提示：胜利结算",
        "有人达到 20 分后，本轮仍会让其他玩家各完成一次行动。只在整轮结束时结算；达到 20 分的玩家中，分数最高者获胜，并列则共同获胜。",
    ),
}


def _dual_discount_choices(player: Player) -> list[Attribute]:
    return [
        chosen if chosen in card.attributes else card.attributes[0]
        for card, chosen in player.purchased
        if card.is_dual
    ]


def _affordable_card_exists(state: GameState, player: Player) -> bool:
    cards = [card for level in (1, 2, 3) for card in state.market.cards[level]]
    cards.extend(player.reserved)
    choices = _dual_discount_choices(player)
    for card in cards:
        try:
            payment_for(player, card, choices)
        except RuleError:
            continue
        return True
    return False


def _can_reserve(state: GameState, player: Player) -> bool:
    return bool(
        any(state.market.cards[level] for level in (1, 2, 3))
        and len(player.reserved) < 3
        and state.light_pool > 0
        and player.resource_count < player.resource_capacity
    )


def select_tutorial_hint(
    state: GameState,
    shown_counts: Mapping[str, int] | None = None,
) -> TutorialHint:
    """Choose an eligible general rule, favoring useful and less-seen topics."""
    player = state.players[0]
    counts = shown_counts or {}
    eligible = {"resources", "wizard", "victory"}
    can_buy = _affordable_card_exists(state, player)
    relevance = {
        "resources": 4 if not can_buy else 1,
        "wizard": 1,
        "victory": 1 + (3 if player.score >= 15 else 0),
    }

    if can_buy:
        eligible.add("buy")
        relevance["buy"] = 5
    if _can_reserve(state, player):
        eligible.add("reserve")
        relevance["reserve"] = 2
    if player.purchased:
        eligible.add("discount")
        relevance["discount"] = 3
    if any(single_attribute_count(player, attribute) for attribute in ATTRIBUTES):
        eligible.add("specialization")
        relevance["specialization"] = 3
    if player.wizard_cards:
        relevance["wizard"] = 3

    stable_order = tuple(HINTS)
    topic = min(
        eligible,
        key=lambda item: (counts.get(item, 0), -relevance.get(item, 0), stable_order.index(item)),
    )
    return HINTS[topic]
