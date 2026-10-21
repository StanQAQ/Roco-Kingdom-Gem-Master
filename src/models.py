from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Iterable


class Attribute(str, Enum):
    WATER = "水"
    FIRE = "火"
    GRASS = "草"
    CUTE = "萌"
    DARK = "恶"


ATTRIBUTES = tuple(Attribute)


@dataclass
class PetCard:
    card_id: str
    level: int
    attributes: tuple[Attribute, ...]
    cost: dict[Attribute, int]
    score: int
    transformed_from: str | None = None
    score_multiplier: int = 1
    specialization_glows: set[Attribute] = field(default_factory=set)
    name: str = ""
    cuteified: bool = False

    @property
    def effective_score(self) -> int:
        return self.score * self.score_multiplier

    @property
    def is_dual(self) -> bool:
        return len(self.attributes) == 2

    @property
    def display_name(self) -> str:
        """Return the card's visible name, falling back for custom/test cards."""
        return self.name or self.card_id

    def cost_text(self) -> str:
        return " ".join(f"{attribute.value}{amount}" for attribute, amount in self.cost.items())


@dataclass(frozen=True)
class WizardCard:
    name: str
    requirements: tuple[tuple[Attribute, int], ...]
    score: int = 3
    card_id: str = ""

    @property
    def requirement_text(self) -> str:
        return "＋".join(f"{attribute.value}{amount}" for attribute, amount in self.requirements)


@dataclass
class Player:
    name: str
    resources: dict[Attribute, int] = field(default_factory=lambda: {attribute: 0 for attribute in ATTRIBUTES})
    light: int = 0
    temporary_light: int = 0
    purchased: list[tuple[PetCard, Attribute | None]] = field(default_factory=list)
    reserved: list[PetCard] = field(default_factory=list)
    score: int = 0
    resource_capacity: int = 10
    next_purchase_free: bool = False
    next_purchase_score_doubled: bool = False
    next_attack_immune: bool = False
    wizard_cards: list[WizardCard] = field(default_factory=list)
    specialization_triggered: set[tuple[Attribute, int, int]] = field(default_factory=set)

    @property
    def resource_count(self) -> int:
        return sum(self.resources.values()) + self.light + self.temporary_light

    @property
    def permanent_discounts(self) -> dict[Attribute, int]:
        discounts = {attribute: 0 for attribute in ATTRIBUTES}
        for card, chosen_attribute in self.purchased:
            if not card.is_dual:
                discounts[card.attributes[0]] += 1
        return discounts

    def dual_cards(self) -> list[PetCard]:
        return [card for card, _ in self.purchased if card.is_dual]


@dataclass
class Market:
    cards: dict[int, list[PetCard]]


@dataclass(frozen=True)
class SpecializationEffect:
    player_index: int
    attribute: Attribute
    stage: int
    occurrence: int = 1


@dataclass
class GameState:
    players: list[Player]
    resource_pool: dict[Attribute, int]
    light_pool: int
    market: Market
    decks: dict[int, list[PetCard]]
    current_player: int = 0
    round_number: int = 1
    end_triggered: bool = False
    market_exhausted_triggered: bool = False
    finished: bool = False
    action_count: int = 0
    discarded: dict[int, list[PetCard]] = field(default_factory=lambda: {1: [], 2: [], 3: []})
    pending_specializations: list[SpecializationEffect] = field(default_factory=list)
    # 保留固定的公开牌位；None 表示已被领取，本局不再补充。
    wizard_market: list[WizardCard | None] = field(default_factory=list)
    wizard_deck: list[WizardCard] = field(default_factory=list)
    rng: random.Random = field(default_factory=random.Random, repr=False)

    first_player: int = 0

    def current(self) -> Player:
        return self.players[self.current_player]

    def next_player(self) -> None:
        self.current_player = (self.current_player + 1) % len(self.players)
        if self.current_player == self.first_player:
            self.round_number += 1

    def all_players_have_equal_actions(self) -> bool:
        return self.current_player == self.first_player


def normalize_cost(items: Iterable[tuple[Attribute, int]]) -> dict[Attribute, int]:
    return {attribute: amount for attribute, amount in items if amount}
