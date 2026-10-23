"""Versioned, player-visible features and deterministic legal candidate actions."""
from __future__ import annotations

from itertools import combinations

import numpy as np

from src.game import Action, Game
from src.models import ATTRIBUTES, PetCard, Player
from src.rules import RuleError, payment_for
from src.specializations import legal_card_targets, legal_player_targets

FEATURE_VERSION = "visible-v1"
KINDS = ("different", "same", "buy", "reserve", "specialization", "pass")
PAIRS = tuple(combinations(ATTRIBUTES, 2))


def card_features(card: PetCard | None) -> list[float]:
    if card is None:
        return [0.] * 21
    return [1., card.level / 3, card.score / 20, card.effective_score / 20,
            card.score_multiplier / 2, float(card.cuteified),
            *[float(a in card.attributes) for a in ATTRIBUTES],
            *[card.cost.get(a, 0) / 10 for a in ATTRIBUTES],
            *[float(a in card.specialization_glows) for a in ATTRIBUTES]]


def payment_variants(player: Player, card: PetCard) -> list[tuple]:
    """Merge dual choices with identical capped discounts, then identical payments.

    Retain a real choice tuple for the engine; no candidate depends on a teacher.
    """
    base = player.permanent_discounts
    required = tuple(max(0, card.cost.get(a, 0) - base[a]) for a in ATTRIBUTES)
    states = {(0,) * 5: ()}
    if player.next_purchase_free:
        return [tuple(c.attributes[0] for c in player.dual_cards())]
    for dual in player.dual_cards():
        updated = {}
        for discounts, choices in states.items():
            for attribute in dual.attributes:
                index = ATTRIBUTES.index(attribute)
                values = list(discounts)
                values[index] = min(required[index], values[index] + 1)
                updated.setdefault(tuple(values), choices + (attribute,))
        states = updated
    payments = {}
    for choices in states.values():
        try:
            payment = payment_for(player, card, list(choices))
        except RuleError:
            continue
        key = (*[payment.normal.get(a, 0) for a in ATTRIBUTES], payment.light, payment.temporary_light)
        payments.setdefault(key, choices)
    return list(payments.values())


def candidates(game: Game) -> list[Action]:
    state = game.state
    if state.pending_specializations:
        effect = state.pending_specializations[0]
        result = [Action("specialization", card=c) for c in legal_card_targets(state, effect)]
        result += [Action("specialization", target_player=i) for i in legal_player_targets(state, effect)]
        return result or [Action("specialization")]
    player = state.current()
    available = [a for a in ATTRIBUTES if state.resource_pool[a] > 0]
    result = []
    if player.resource_count + 3 <= player.resource_capacity:
        result += [Action("different", attributes=c) for c in combinations(available, 3)]
    if player.resource_count + 2 <= player.resource_capacity:
        result += [Action("same", attributes=(a,)) for a in available if state.resource_pool[a] >= 4]
    market = [c for level in (1, 2, 3) for c in state.market.cards[level]]
    for card in market + player.reserved:
        result += [Action("buy", card=card, dual_choices=choices)
                   for choices in payment_variants(player, card)]
    if len(player.reserved) < 3 and state.light_pool > 0 and player.resource_count < player.resource_capacity:
        result += [Action("reserve", card=c) for c in market]
    # The engine allows passing even when other actions exist; the teacher can do so.
    return result + [Action("pass")]


def action_key(game: Game, action: Action) -> tuple:
    payment_key = ()
    if action.kind == "buy":
        p = payment_for(game.state.current(), action.card, list(action.dual_choices))
        payment_key = (*[p.normal.get(a, 0) for a in ATTRIBUTES], p.light, p.temporary_light)
    return (action.kind, action.card.card_id if action.card else None,
            tuple(sorted(a.value for a in action.attributes)), action.target_player, payment_key)


def observation(game: Game) -> np.ndarray:
    """Never read decks, RNG, names, or identities of opponents' reserved cards."""
    s = game.state
    actor = s.current_player
    f = [s.round_number / 50, game.target_score / 50, (game.max_rounds or 0) / 50,
         float(game.max_rounds is not None), float(s.end_triggered),
         ((actor - s.first_player) % 4) / 3, s.light_pool / 5,
         *[s.resource_pool[a] / 7 for a in ATTRIBUTES]]
    for offset in range(4):
        index = (actor + offset) % 4
        p = s.players[index]
        owned = [c for c, _ in p.purchased]
        f += [p.score / 50, p.light / 10, p.temporary_light / 10,
              p.resource_count / 15, p.resource_capacity / 15,
              len(p.reserved) / 3, len(owned) / 30, len(p.wizard_cards) / 5,
              float(p.next_purchase_free), float(p.next_purchase_score_doubled), float(p.next_attack_immune)]
        f += [p.resources[a] / 10 for a in ATTRIBUTES]
        f += [p.permanent_discounts[a] / 10 for a in ATTRIBUTES]
        f += [sum(a in c.attributes for c in owned) / 20 for a in ATTRIBUTES]
        f += [sum(c.effective_score for c in owned if a in c.attributes) / 50 for a in ATTRIBUTES]
        f += [sum(set(c.attributes) == set(pair) for c in owned) / 10 for pair in PAIRS]
        f += [max((occ for a0, st, occ in p.specialization_triggered if a0 == a and st == stage), default=0) / 10
              for a in ATTRIBUTES for stage in (1, 2)]
        f += [sum(e.player_index == index and e.attribute == a and e.stage == stage
                  for e in s.pending_specializations) / 10 for a in ATTRIBUTES for stage in (1, 2)]
    for level in (1, 2, 3):
        cards = s.market.cards[level]
        for i in range(5):
            f += card_features(cards[i] if i < len(cards) else None)
    for i in range(3):
        own = s.current().reserved
        f += card_features(own[i] if i < len(own) else None)
    for i in range(5):
        wizard = s.wizard_market[i] if i < len(s.wizard_market) else None
        f += ([1., wizard.score / 10, *[dict(wizard.requirements).get(a, 0) / 10 for a in ATTRIBUTES]]
              if wizard else [0.] * 7)
    effect = s.pending_specializations[0] if s.pending_specializations else None
    f += [float(effect is not None and effect.attribute == a) for a in ATTRIBUTES]
    f += [effect.stage / 2 if effect else 0., effect.occurrence / 10 if effect else 0.]
    return np.asarray(f, dtype=np.float32)


def action_features(game: Game, action: Action) -> list[float]:
    player = game.state.current()
    f = [float(action.kind == kind) for kind in KINDS] + card_features(action.card)
    f += [(2 if action.kind == "same" else 1) / 3 if a in action.attributes else 0. for a in ATTRIBUTES]
    payment = payment_for(player, action.card, list(action.dual_choices)) if action.kind == "buy" else None
    f += [payment.normal.get(a, 0) / 10 if payment else 0. for a in ATTRIBUTES]
    f += [payment.light / 10 if payment else 0., payment.temporary_light / 10 if payment else 0.]
    f += [float(action.target_player is not None and
                (action.target_player - game.state.current_player) % 4 == i) for i in range(4)]
    f += [float(action.card is not None and any(c.card_id == action.card.card_id for c in player.reserved)),
          action.card.effective_score * (2 if player.next_purchase_score_doubled else 1) / 20
          if action.kind == "buy" else 0.]
    return f


def encode(game: Game, options: list[Action]) -> tuple[np.ndarray, np.ndarray]:
    return observation(game), np.asarray([action_features(game, a) for a in options], dtype=np.float32)
