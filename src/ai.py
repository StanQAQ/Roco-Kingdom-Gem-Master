from __future__ import annotations

from collections import Counter
from itertools import combinations, product

from .game import Action, Game, VICTORY_SCORE
from .models import ATTRIBUTES, Attribute, PetCard, Player
from .rules import RuleError, payment_for
from .specializations import legal_card_targets, legal_player_targets


# 仅用于困难 AI 的专精收益估值，单位近似为“分数”。
_SPECIALIZATION_SCORE_VALUE = {
    (Attribute.WATER, 1): 0.6,
    (Attribute.WATER, 2): 2.0,
    (Attribute.FIRE, 1): 0.7,
    (Attribute.FIRE, 2): 1.8,
    (Attribute.GRASS, 1): 0.5,
    (Attribute.GRASS, 2): 1.0,
    (Attribute.CUTE, 1): 0.6,
    (Attribute.CUTE, 2): 0.8,
    (Attribute.DARK, 1): 0.5,
    (Attribute.DARK, 2): 1.8,
}


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


def _wizard_bonus(player: Player, card: PetCard, game: Game) -> float:
    """Reward completing, and slightly reward progressing toward, visible wizards."""
    before = Counter(
        attribute
        for owned, _chosen in player.purchased
        for attribute in owned.attributes
    )
    after = before.copy()
    after.update(card.attributes)
    value = 0.0
    owned_wizard_ids = {owned.card_id for owned in player.wizard_cards}
    for wizard in game.state.wizard_market:
        if wizard.card_id in owned_wizard_ids:
            continue
        requirements = dict(wizard.requirements)
        was_eligible = all(before[attribute] >= amount for attribute, amount in requirements.items())
        is_eligible = all(after[attribute] >= amount for attribute, amount in requirements.items())
        if is_eligible and not was_eligible:
            value += wizard.score * 55
            continue
        if was_eligible:
            continue
        old_missing = sum(max(0, amount - before[attribute]) for attribute, amount in requirements.items())
        new_missing = sum(max(0, amount - after[attribute]) for attribute, amount in requirements.items())
        value += max(0, old_missing - new_missing) * 3
    return value


def _specialization_bonus(player: Player, card: PetCard) -> float:
    """Estimate specialization effects crossed by buying this single-attribute card."""
    if card.is_dual:
        return 0.0
    attribute = card.attributes[0]
    before = sum(
        1 for owned, _chosen in player.purchased
        if not owned.is_dual and owned.attributes[0] == attribute
    )
    after = before + 1
    value = 0.0
    for stage, first_threshold in ((1, 2), (2, 3)):
        threshold = first_threshold
        occurrence = 1
        while threshold <= after:
            key = (attribute, stage, occurrence)
            if before < threshold and key not in player.specialization_triggered:
                value += _SPECIALIZATION_SCORE_VALUE[(attribute, stage)] * 55
            threshold += 3
            occurrence += 1
    return value


def _hard_card_value(
    game: Game,
    player: Player,
    card: PetCard,
    choices: tuple[Attribute, ...],
) -> float:
    """Evaluate a legal purchase using current scoring, discounts, and visible rewards."""
    payment = payment_for(player, card, list(choices))
    value = card.effective_score * 55 + card.level * 7
    value += 7 if not card.is_dual else 5
    value += _wizard_bonus(player, card, game)
    value += _specialization_bonus(player, card)
    # 普通灵碎可替代未来购卡资源；贤者碎晶更灵活，因此计入更高机会成本。
    value -= sum(payment.normal.values()) * 0.8
    value -= payment.light * 2.5 + payment.temporary_light * 1.5
    if player.score + card.effective_score >= VICTORY_SCORE:
        value += 10_000  # 立即达成胜利的购买优先于长期收益。
    return value


def _needs(player: Player, card: PetCard, choices: tuple[Attribute, ...]) -> dict[Attribute, int]:
    discounts = _discounts(player, choices)
    return {
        attribute: max(0, amount - discounts[attribute] - player.resources[attribute])
        for attribute, amount in card.cost.items()
    }


def _hard_target_value(
    game: Game,
    card: PetCard,
    *,
    player: Player | None = None,
) -> float:
    """Estimate the value and resource distance of a card as a future goal."""
    player = player or game.state.current()
    best_value = float("-inf")
    reserved_ids = {reserved.card_id for reserved in player.reserved}
    for choices in _all_choices(player):
        value = _card_value(card, card.card_id in reserved_ids)
        value += _wizard_bonus(player, card, game)
        value += _specialization_bonus(player, card)
        value -= sum(_needs(player, card, choices).values()) * 5
        best_value = max(best_value, value)
    return best_value


def _best_target(game: Game, candidates: list[PetCard]) -> tuple[PetCard, tuple[Attribute, ...]] | None:
    player = game.state.current()
    best: tuple[float, PetCard, tuple[Attribute, ...]] | None = None
    reserved_ids = {reserved.card_id for reserved in player.reserved}
    for card in candidates:
        for choices in _all_choices(player):
            needs = _needs(player, card, choices)
            value = _card_value(card, card.card_id in reserved_ids)
            value += _wizard_bonus(player, card, game)
            value += _specialization_bonus(player, card)
            # 目标越近越好；仍让高分卡值得逐步积累，但避免只追逐遥不可及的高价卡。
            value -= sum(needs.values()) * 5
            item = (value, card, choices)
            if best is None or item[0] > best[0]:
                best = item
    return None if best is None else (best[1], best[2])


def _resource_action(game: Game, target: tuple[PetCard, tuple[Attribute, ...]]) -> Action | None:
    player = game.state.current()
    card, choices = target
    needs = _needs(player, card, choices)
    available = [attribute for attribute in ATTRIBUTES if game.state.resource_pool[attribute] > 0]
    options: list[Action] = []
    if player.resource_count <= player.resource_capacity - 3 and len(available) >= 3:
        options.extend(
            Action("different", attributes=choice)
            for choice in combinations(available, 3)
        )
    if player.resource_count <= player.resource_capacity - 2:
        options.extend(
            Action("same", attributes=(attribute,))
            for attribute in available
            if game.state.resource_pool[attribute] >= 4
        )
    if not options:
        return None

    def resource_value(action: Action) -> tuple[float, int, int]:
        taken = Counter(action.attributes)
        if action.kind == "same":
            taken[action.attributes[0]] = 2
        progress = sum(min(needs.get(attribute, 0), amount) for attribute, amount in taken.items())
        useful_extra = sum(
            max(0, amount - needs.get(attribute, 0)) for attribute, amount in taken.items()
        )
        # 相同进展时优先三种资源，保留资源组合的灵活性；但两枚同属性若更贴近目标则胜出。
        return progress + useful_extra * 0.1, len(taken), int(action.kind == "different")

    best_action = max(options, key=resource_value)
    return best_action if _resource_progress(player, target, best_action) > 0 else None


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
        best_rank: tuple[int, float] | None = None
        for choices in _all_choices(player):
            needs = _needs(player, card, choices)
            remaining = max(0, sum(needs.values()) - available_light)
            target_value = _card_value(card) + _wizard_bonus(player, card, game)
            target_value += _specialization_bonus(player, card)
            target_value -= remaining * 5
            rank = (-remaining, target_value)
            if best_rank is None or rank > best_rank:
                best_rank = rank
        return best_rank or (0, _card_value(card))

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
            if effect.attribute == Attribute.DARK and effect.stage == 2:
                target = max(players, key=lambda index: state.players[index].score)
                return Action("specialization", target_player=target)
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
                card = max(
                    cards,
                    key=lambda item: (
                        max(item.cost.values(), default=0),
                        _hard_target_value(game, item),
                    ),
                )
            elif effect.attribute == Attribute.GRASS:
                player = game.state.players[effect.player_index]
                card = max(
                    cards,
                    key=lambda item: (
                        item.score_multiplier,
                        _hard_target_value(game, item, player=player),
                        item.effective_score,
                    ),
                )
            else:
                card = max(cards, key=lambda item: (item.effective_score, item.level, sum(item.cost.values())))
            return Action("specialization", card=card)
        players = legal_player_targets(game.state, effect)
        if players:
            if effect.attribute == Attribute.DARK and effect.stage == 1:
                unprotected = [index for index in players if not game.state.players[index].next_attack_immune]
                candidates = unprotected or players
                target = max(
                    candidates,
                    key=lambda index: (
                        game.state.players[index].resource_count,
                        game.state.players[index].score,
                    ),
                )
                return Action("specialization", target_player=target)
            if effect.attribute == Attribute.DARK and effect.stage == 2:
                unprotected = [index for index in players if not game.state.players[index].next_attack_immune]
                candidates = unprotected or players
                target = max(candidates, key=lambda index: game.state.players[index].score)
                return Action("specialization", target_player=target)
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
    reserved_ids = {reserved.card_id for reserved in player.reserved}
    affordable: list[tuple[float, PetCard, tuple[Attribute, ...]]] = []
    for card in candidates:
        for choices in _all_choices(player):
            try:
                payment = payment_for(player, card, list(choices))
            except RuleError:
                continue
            value = _hard_card_value(game, player, card, choices)
            if card.card_id in reserved_ids:
                value += 8
            affordable.append((value, card, choices))
    if affordable:
        _, card, choices = max(affordable, key=lambda item: (item[0], item[1].effective_score, item[1].level))
        return Action("buy", card=card, dual_choices=choices)
    target = _best_target(game, candidates)
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
