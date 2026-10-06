from __future__ import annotations

from itertools import product

from .game import Action, Game
from .models import ATTRIBUTES, Attribute, PetCard, Player
from .rules import RuleError, payment_for
from .specializations import legal_card_targets, legal_player_targets


def _all_choices(player: Player) -> list[tuple[Attribute, ...]]:
    dual_cards = player.dual_cards()
    if not dual_cards:
        return [()]
    return [tuple(choices) for choices in product(*(card.attributes for card in dual_cards))]


def _discounts(player: Player, choices: tuple[Attribute, ...]) -> dict[Attribute, int]:
    discounts = player.permanent_discounts
    for attribute in choices:
        discounts[attribute] += 1
    return discounts


def _card_value(card: PetCard, reserved: bool = False) -> float:
    cost = sum(card.cost.values())
    engine_value = 7 if not card.is_dual else 5
    reserve_value = 8 if reserved else 0
    return card.score * 55 + card.level * 7 + engine_value + reserve_value - cost * 0.7


def _needs(player: Player, card: PetCard, choices: tuple[Attribute, ...]) -> dict[Attribute, int]:
    discounts = _discounts(player, choices)
    return {
        attribute: max(0, amount - discounts[attribute] - player.resources[attribute])
        for attribute, amount in card.cost.items()
    }


def _best_target(player: Player, candidates: list[PetCard]) -> tuple[PetCard, tuple[Attribute, ...]] | None:
    best: tuple[float, PetCard, tuple[Attribute, ...]] | None = None
    for card in candidates:
        for choices in _all_choices(player):
            value = _card_value(card, card in player.reserved)
            needs = _needs(player, card, choices)
            value += sum(needs.values()) * 1.5
            item = (value, card, choices)
            if best is None or item[0] > best[0]:
                best = item
    return None if best is None else (best[1], best[2])


def _resource_action(game: Game, target: tuple[PetCard, tuple[Attribute, ...]]) -> Action | None:
    player = game.state.current()
    card, choices = target
    needs = _needs(player, card, choices)
    available = [attribute for attribute in ATTRIBUTES if game.state.resource_pool[attribute] > 0]
    if player.resource_count <= player.resource_capacity - 3 and len(available) >= 3:
        ranked = sorted(
            available,
            key=lambda attribute: (needs.get(attribute, 0) * 10 + card.cost.get(attribute, 0) * 2, game.state.resource_pool[attribute]),
            reverse=True,
        )
        return Action("different", attributes=tuple(ranked[:3]))
    if player.resource_count <= player.resource_capacity - 2:
        same_options = [attribute for attribute in available if game.state.resource_pool[attribute] >= 4]
        if same_options:
            attribute = max(same_options, key=lambda item: (needs.get(item, 0) * 10 + card.cost.get(item, 0) * 2, game.state.resource_pool[item]))
            return Action("same", attributes=(attribute,))
    return None


def choose_action(game: Game) -> Action:
    if game.state.pending_specializations:
        effect = game.state.pending_specializations[0]
        cards = legal_card_targets(game.state, effect)
        if cards:
            if effect.attribute == Attribute.WATER:
                card = max(cards, key=lambda item: (sum(item.cost.values()), item.score, item.level))
            elif effect.attribute == Attribute.GRASS:
                card = max(cards, key=lambda item: (_card_value(item), item.score, item.level))
            else:
                card = max(cards, key=lambda item: (item.score, item.level, sum(item.cost.values())))
            return Action("specialization", card=card)
        players = legal_player_targets(game.state, effect)
        if players:
            target = max(
                players,
                key=lambda index: (
                    game.state.players[index].score,
                    game.state.players[index].resource_count,
                    len(game.state.players[index].purchased),
                ),
            )
            return Action("specialization", target_player=target)
        return Action("specialization")

    player = game.state.current()
    candidates = list(game.state.market.cards[1] + game.state.market.cards[2] + game.state.market.cards[3] + player.reserved)
    affordable: list[tuple[float, PetCard, tuple[Attribute, ...]]] = []
    for card in candidates:
        for choices in _all_choices(player):
            try:
                payment = payment_for(player, card, list(choices))
            except RuleError:
                continue
            value = _card_value(card, card in player.reserved) - payment.light * 0.5
            affordable.append((value, card, choices))
    if affordable:
        _, card, choices = max(affordable, key=lambda item: (item[0], item[1].score, item[1].level))
        return Action("buy", card=card, dual_choices=choices)
    target = _best_target(player, candidates)
    if target is not None:
        resource_action = _resource_action(game, target)
        if resource_action is not None:
            return resource_action
    if game.state.light_pool > 0 and player.resource_count < player.resource_capacity and len(player.reserved) < 3 and game.state.market.cards[1]:
        reserve_candidates = game.state.market.cards[1] + game.state.market.cards[2] + game.state.market.cards[3]
        card = max(reserve_candidates, key=_card_value)
        return Action("reserve", card=card)
    return Action("pass")
