"""Pages unlocked during a Qt tutorial match."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Attribute, GameState, Player
from .rules import RuleError, payment_for


@dataclass(frozen=True)
class TutorialHint:
    topic: str
    title: str
    body: str


TUTORIAL_INTRO = TutorialHint(
    "intro",
    "欢迎来到魔法宝石！",
    "你需要通过获取零碎、购买宠物来赢得胜利\n"
    "当卡片右上角的分数达到20分时，即可获胜\n"
    "先试试在右下角获取零碎吧！",
)


HINTS = {
    "resources": TutorialHint(
        "resources", "获取零碎",
        "获取零碎会消耗本回合的行动机会。你可以拿三种不同属性的零碎各 1 枚；公共池该属性至少剩 4 枚时，也可以拿同一属性的零碎 2 枚。零碎与贤者碎晶合计最多持有 10 枚。",
    ),
    "buy": TutorialHint(
        "buy", "购买卡片",
        "购买卡片需要支付费用，并获得卡面分数。之后购买时，已购卡提供永久折扣；贤者碎晶可以补足任意属性的费用。购买会消耗本回合的行动机会。",
    ),
    "reserve": TutorialHint(
        "reserve", "预购卡片",
        "预购会把选择的市场卡片移到自己的预购区，并获得 1 枚贤者碎晶。预购卡不能在同一行动中购买；之后仍要用一次行动支付费用。每名玩家最多预购 3 张卡。",
    ),
    "discount": TutorialHint(
        "discount", "属性折扣",
        "单属性宠物提供对应属性的永久折扣。双属性宠物购买时要为每张已购双属性卡选择本次计入的一个属性；你也可以在自己的回合拖动已购双属性卡来调整折扣属性。",
    ),
    "specialization": TutorialHint(
        "specialization", "属性专精",
        "单属性宠物会推进对应属性的专精进度，达到门槛后可能触发特殊效果。双属性宠物不计入专精张数；部分效果会在行动结算时要求你选择目标。",
    ),
    "wizard": TutorialHint(
        "wizard", "魔法师卡",
        "每局随机公开 5 张魔法师卡，检查你已购买宠物的属性组合。符合条件时会在回合结算自动获得，每张增加 3 分；领取后原位留空，本局不再补充。双属性宠物同时计入两种属性，资源和预购卡不计入。",
    ),
    "victory": TutorialHint(
        "victory", "胜利结算",
        "有人达到 20 分后，本轮仍会让其他玩家各完成一次行动。只在整轮结束时结算；达到 20 分的玩家中，分数最高者获胜，并列则共同获胜。",
    ),
}

TUTORIAL_ORDER = (
    "intro", "resources", "reserve", "buy", "discount", "specialization", "wizard", "victory",
)
INITIAL_TUTORIAL_TOPICS = frozenset(("intro", "resources", "reserve", "victory"))
TUTORIAL_HINTS = {"intro": TUTORIAL_INTRO, **HINTS}


@dataclass
class TutorialGuide:
    """Keep unlocked pages in a fixed order while remembering the selected page."""

    unlocked: set[str] = field(default_factory=lambda: set(INITIAL_TUTORIAL_TOPICS))
    current_topic: str = "intro"

    @property
    def topics(self) -> tuple[str, ...]:
        return tuple(topic for topic in TUTORIAL_ORDER if topic in self.unlocked)

    @property
    def current_hint(self) -> TutorialHint:
        return TUTORIAL_HINTS[self.current_topic]

    @property
    def page_index(self) -> int:
        return self.topics.index(self.current_topic)

    def unlock(self, topic: str) -> bool:
        if topic not in TUTORIAL_HINTS:
            raise ValueError(f"未知教程主题: {topic}")
        if topic in self.unlocked:
            return False
        self.unlocked.add(topic)
        self.current_topic = topic
        return True

    def turn_page(self, step: int) -> None:
        topics = self.topics
        index = max(0, min(self.page_index + step, len(topics) - 1))
        self.current_topic = topics[index]


def _dual_discount_choices(player: Player) -> list[Attribute]:
    return [
        chosen if chosen in card.attributes else card.attributes[0]
        for card, chosen in player.purchased
        if card.is_dual
    ]


def can_purchase_card(state: GameState, player_index: int = 0) -> bool:
    """Whether the player can currently buy any market or reserved card."""
    player = state.players[player_index]
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
