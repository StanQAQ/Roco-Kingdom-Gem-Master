from __future__ import annotations

from itertools import combinations, product

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
    return card.effective_score * 55 + card.level * 7 + engine_value + reserve_value - cost * 0.7


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


def _resource_progress(player: Player, target: tuple[PetCard, tuple[Attribute, ...]], action: Action) -> int:
    card, choices = target
    needs = _needs(player, card, choices)
    if action.kind == "different":
        return sum(needs.get(attribute, 0) > 0 for attribute in action.attributes)
    return min(2, needs.get(action.attributes[0], 0))


def _reserve_action(game: Game, market_cards: list[PetCard]) -> Action | None:
    player = game.state.current()
    if (
        not market_cards
        or game.state.light_pool <= 0
        or player.resource_count >= player.resource_capacity
        or len(player.reserved) >= 3
    ):
        return None

    available_light = player.light + player.temporary_light + 1

    def reserve_rank(card: PetCard) -> tuple[int, float]:
        remaining = min(
            max(0, sum(_needs(player, card, choices).values()) - available_light)
            for choices in _all_choices(player)
        )
        return -remaining, _card_value(card)

    return Action("reserve", card=max(market_cards, key=reserve_rank))


def _choose_simple_action(game: Game) -> Action:
    """Choose a legal but deliberately less goal-directed action."""
    state = game.state
    rng = state.rng
    if state.pending_specializations:
        effect = state.pending_specializations[0]
        cards = legal_card_targets(state, effect)
        if cards:
            return Action("specialization", card=rng.choice(cards))
        players = legal_player_targets(state, effect)
        if players:
            return Action("specialization", target_player=rng.choice(players))
        return Action("specialization")

    player = state.current()
    market_cards = state.market.cards[1] + state.market.cards[2] + state.market.cards[3]
    candidates = market_cards + player.reserved
    affordable: list[Action] = []
    for card in candidates:
        for choices in _all_choices(player):
            try:
                payment_for(player, card, list(choices))
            except RuleError:
                continue
            affordable.append(Action("buy", card=card, dual_choices=choices))

    resource_actions: list[Action] = []
    available = [attribute for attribute in ATTRIBUTES if state.resource_pool[attribute] > 0]
    if player.resource_count <= player.resource_capacity - 3:
        resource_actions.extend(
            Action("different", attributes=choice)
            for choice in combinations(available, 3)
        )
    if player.resource_count <= player.resource_capacity - 2:
        resource_actions.extend(
            Action("same", attributes=(attribute,))
            for attribute in available
            if state.resource_pool[attribute] >= 4
        )

    reserve_actions = [
        Action("reserve", card=card)
        for card in market_cards
        if state.light_pool > 0 and player.resource_count < player.resource_capacity and len(player.reserved) < 3
    ]

    # Simple mode intentionally makes short-sighted choices: it sometimes buys
    # an arbitrary affordable pet, sometimes takes unrelated resources, and
    # sometimes reserves instead of pursuing the strongest available plan.
    roll = rng.randrange(100)
    if affordable and roll < 42:
        return rng.choice(affordable)
    if resource_actions and roll < 84:
        return rng.choice(resource_actions)
    if reserve_actions and roll < 96:
        return rng.choice(reserve_actions)

    fallback = affordable + resource_actions + reserve_actions
    return rng.choice(fallback) if fallback else Action("pass")


def choose_action(game: Game, difficulty: str = "hard") -> Action:
    if difficulty == "simple":
        return _choose_simple_action(game)
    if game.state.pending_specializations:
        effect = game.state.pending_specializations[0]
        cards = legal_card_targets(game.state, effect)
        if cards:
            if effect.attribute == Attribute.WATER:
                card = max(cards, key=lambda item: (sum(item.cost.values()), item.effective_score, item.level))
            elif effect.attribute == Attribute.GRASS:
                card = max(cards, key=lambda item: (_card_value(item), item.effective_score, item.level))
            else:
                card = max(cards, key=lambda item: (item.effective_score, item.level, sum(item.cost.values())))
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
    market_cards = game.state.market.cards[1] + game.state.market.cards[2] + game.state.market.cards[3]
    candidates = market_cards + player.reserved
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
        _, card, choices = max(affordable, key=lambda item: (item[0], item[1].effective_score, item[1].level))
        return Action("buy", card=card, dual_choices=choices)
    target = _best_target(player, candidates)
    resource_action = None
    if target is not None:
        resource_action = _resource_action(game, target)
        if resource_action is not None and _resource_progress(player, target, resource_action) > 0:
            return resource_action
    reserve_action = _reserve_action(game, market_cards)
    if reserve_action is not None:
        return reserve_action
    if resource_action is not None:
        return resource_action
    return Action("pass")
