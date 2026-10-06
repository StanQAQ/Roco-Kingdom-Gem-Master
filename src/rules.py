from __future__ import annotations

from dataclasses import dataclass
import random

from .models import ATTRIBUTES, Attribute, GameState, Market, PetCard, Player


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class Payment:
    normal: dict[Attribute, int]
    light: int
    temporary_light: int = 0


def _check_capacity(player: Player, amount: int) -> None:
    if player.resource_count + amount > player.resource_capacity:
        raise RuleError(f"资源持有量不能超过 {player.resource_capacity} 枚")


def take_different(player: Player, state: GameState, attributes: list[Attribute]) -> None:
    if len(attributes) != 3 or len(set(attributes)) != 3:
        raise RuleError("必须选择 3 种不同属性")
    if any(state.resource_pool[attribute] < 1 for attribute in attributes):
        raise RuleError("所选属性资源不足")
    _check_capacity(player, 3)
    for attribute in attributes:
        state.resource_pool[attribute] -= 1
        player.resources[attribute] += 1


def take_same(player: Player, state: GameState, attribute: Attribute) -> None:
    if state.resource_pool[attribute] < 4:
        raise RuleError("领取前该属性资源必须至少剩余 4 枚")
    _check_capacity(player, 2)
    state.resource_pool[attribute] -= 2
    player.resources[attribute] += 2


def discount_for(player: Player, card: PetCard, selected_dual: list[Attribute] | None = None) -> dict[Attribute, int]:
    discounts = player.permanent_discounts
    selected_dual = selected_dual or []
    dual_cards = player.dual_cards()
    if len(selected_dual) != len(dual_cards):
        raise RuleError(f"需要为 {len(dual_cards)} 张双属性宠物选择本次折扣")
    for owned_card, chosen in zip(dual_cards, selected_dual):
        if chosen not in owned_card.attributes:
            raise RuleError("双属性折扣选择无效")
        discounts[chosen] += 1
    return discounts


def payment_for(player: Player, card: PetCard, selected_dual: list[Attribute] | None = None) -> Payment:
    if player.next_purchase_free:
        return Payment({}, 0, 0)
    discounts = discount_for(player, card, selected_dual)
    normal = {}
    required_cost = {}
    light_needed = 0
    for attribute, amount in card.cost.items():
        required = max(0, amount - discounts[attribute])
        required_cost[attribute] = required
        paid = min(player.resources[attribute], required)
        normal[attribute] = paid
        light_needed += required - paid
    if light_needed > player.light + player.temporary_light:
        required_text = " ".join(f"{attribute.value}{amount}" for attribute, amount in required_cost.items() if amount)
        available_text = " ".join(f"{attribute.value}{player.resources[attribute]}" for attribute in required_cost)
        raise RuleError(
            f"资源不足：{card.card_id} 折扣后需要 {required_text}，当前为 {available_text}，"
            f"还需要光系 {light_needed}，已有光系 {player.light + player.temporary_light}"
        )
    ordinary_light = min(player.light, light_needed)
    return Payment(normal, ordinary_light, light_needed - ordinary_light)


def _return_payment(state: GameState, payment: Payment) -> None:
    for attribute, amount in payment.normal.items():
        state.resource_pool[attribute] += amount
    state.light_pool += payment.light


def _remove_market_card(state: GameState, card: PetCard) -> None:
    cards = state.market.cards[card.level]
    if card not in cards:
        raise RuleError("市场中没有这张宠物")
    cards.remove(card)
    if len(cards) < 5 and state.decks[card.level]:
        cards.append(state.decks[card.level].pop())


def buy_card(state: GameState, player: Player, card: PetCard, selected_dual: list[Attribute] | None = None) -> None:
    payment = payment_for(player, card, selected_dual)
    if card in state.market.cards[card.level]:
        _remove_market_card(state, card)
    elif card in player.reserved:
        player.reserved.remove(card)
    else:
        raise RuleError("这张宠物不可购买")
    for attribute, amount in payment.normal.items():
        player.resources[attribute] -= amount
    player.light -= payment.light
    player.temporary_light -= payment.temporary_light
    _return_payment(state, payment)
    player.purchased.append((card, None))
    player.score += card.score
    if player.next_purchase_free:
        player.next_purchase_free = False


def reserve_card(state: GameState, player: Player, card: PetCard) -> None:
    if len(player.reserved) >= 3:
        raise RuleError("预购区最多保留 3 张宠物")
    if card not in state.market.cards[card.level]:
        raise RuleError("只能预购公共市场中的宠物")
    if state.light_pool <= 0:
        raise RuleError("公共光系资源不足")
    _check_capacity(player, 1)
    _remove_market_card(state, card)
    player.reserved.append(card)
    player.light += 1
    state.light_pool -= 1


def create_state(players: list[Player], decks: dict[int, list[PetCard]], seed: int | None = None) -> GameState:
    market_cards = {level: [decks[level].pop() for _ in range(min(5, len(decks[level])))] for level in (1, 2, 3)}
    return GameState(
        players,
        {attribute: 7 for attribute in ATTRIBUTES},
        5,
        Market(market_cards),
        decks,
        rng=random.Random(seed),
    )
