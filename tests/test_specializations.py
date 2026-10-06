import pytest

from src.cards import all_cards, build_decks
from src.game import Action, Game
from src.models import Attribute, PetCard, Player, SpecializationEffect
from src.rules import RuleError, buy_card, create_state
from src.specializations import detect_specializations, resolve_specialization


def make_state(seed: int = 7):
    players = [Player("A"), Player("B"), Player("C"), Player("D")]
    return create_state(players, build_decks(seed), seed)


def single_card(attribute: Attribute, *, level: int = 1, score: int = 0, card_id: str = "T") -> PetCard:
    return PetCard(card_id, level, (attribute,), {}, score)


def test_buying_second_single_card_pauses_turn_until_specialization_resolves():
    state = make_state()
    player = state.players[0]
    player.purchased.append((single_card(Attribute.WATER, card_id="OWNED"), None))
    bought = single_card(Attribute.WATER, card_id="BUY")
    state.market.cards[1][0] = bought
    game = Game(state)

    messages = game.execute(Action("buy", card=bought))

    assert messages == ["A 触发 水系专精阶段1"]
    assert state.current_player == 0
    assert state.pending_specializations == [SpecializationEffect(0, Attribute.WATER, 1)]
    with pytest.raises(RuleError, match="必须先结算"):
        game.execute(Action("pass"))

    target = state.market.cards[2][0]
    game.execute(Action("specialization", card=target))
    assert state.current_player == 1
    assert not state.pending_specializations


def test_dual_cards_do_not_count_and_each_stage_only_triggers_once():
    state = make_state()
    player = state.players[0]
    duals = [card for card in all_cards() if card.is_dual][:3]
    player.purchased.extend((card, None) for card in duals)
    assert detect_specializations(state, 0) == []

    player.purchased.extend(
        (single_card(Attribute.FIRE, card_id=f"F{index}"), None)
        for index in range(3)
    )
    effects = detect_specializations(state, 0)
    assert [(effect.attribute, effect.stage) for effect in effects] == [
        (Attribute.FIRE, 1),
        (Attribute.FIRE, 2),
    ]
    assert detect_specializations(state, 0) == []


def test_water_effect_reduces_highest_cost_and_then_grants_one_free_purchase():
    state = make_state()
    player = state.players[0]
    target = PetCard("TARGET", 1, (Attribute.FIRE,), {Attribute.FIRE: 3, Attribute.GRASS: 1}, 1)
    state.market.cards[1][0] = target

    resolve_specialization(state, SpecializationEffect(0, Attribute.WATER, 1), card=target)
    assert target.cost == {Attribute.FIRE: 2, Attribute.GRASS: 1}

    resolve_specialization(state, SpecializationEffect(0, Attribute.WATER, 2))
    expensive = PetCard("FREE", 1, (Attribute.GRASS,), {Attribute.DARK: 99}, 2)
    state.market.cards[1][0] = expensive
    buy_card(state, player, expensive)
    assert player.score == 2
    assert not player.next_purchase_free


def test_fire_effect_increases_capacity_and_replaces_the_market():
    state = make_state()
    old_ids = {card.card_id for cards in state.market.cards.values() for card in cards}

    resolve_specialization(state, SpecializationEffect(0, Attribute.FIRE, 1))
    message = resolve_specialization(state, SpecializationEffect(0, Attribute.FIRE, 2))

    new_ids = {card.card_id for cards in state.market.cards.values() for card in cards}
    assert state.players[0].resource_capacity == 11
    assert len(state.discarded[1]) + len(state.discarded[2]) + len(state.discarded[3]) == 15
    assert len(new_ids) == 15
    assert not old_ids & new_ids
    assert "15 张" in message


def test_grass_effect_adds_score_and_temporary_light_is_not_returned():
    state = make_state()
    target = state.market.cards[1][0]
    original_score = target.score
    resolve_specialization(state, SpecializationEffect(0, Attribute.GRASS, 1), card=target)
    assert target.score == original_score + 1

    state.players[1].purchased.extend(
        [(single_card(Attribute.GRASS, card_id="G1"), None), (single_card(Attribute.GRASS, card_id="G2"), None)]
    )
    resolve_specialization(state, SpecializationEffect(0, Attribute.GRASS, 2))
    assert state.players[0].temporary_light == 3

    paid_with_temporary = PetCard("TEMP", 1, (Attribute.WATER,), {Attribute.FIRE: 3}, 0)
    state.market.cards[1][0] = paid_with_temporary
    light_pool_before = state.light_pool
    buy_card(state, state.players[0], paid_with_temporary)
    assert state.players[0].temporary_light == 0
    assert state.light_pool == light_pool_before


def test_cute_effect_moves_market_card_down_and_weakens_purchased_cards():
    state = make_state()
    target = next(card for card in state.market.cards[3] if not card.is_dual)
    old_score = target.score
    resolve_specialization(state, SpecializationEffect(0, Attribute.CUTE, 1), card=target)
    assert target.level == 2
    assert target.score < old_score
    assert target in state.market.cards[2]
    assert len(state.market.cards[3]) == 5
    assert len(state.market.cards[2]) == 6

    state.players[0].next_purchase_free = True
    buy_card(state, state.players[0], target)
    assert len(state.market.cards[2]) == 5

    high_card = next(card for card in all_cards() if card.level == 3 and not card.is_dual)
    state.players[1].purchased.append((high_card, None))
    state.players[1].score = high_card.score
    before = state.players[1].score
    resolve_specialization(state, SpecializationEffect(0, Attribute.CUTE, 2))
    assert state.players[1].score < before
    assert high_card.level == 2


def test_dark_effect_steals_a_resource_and_a_card_from_a_leading_player():
    state = make_state()
    victim = state.players[1]
    victim.resources[Attribute.FIRE] = 1
    resolve_specialization(state, SpecializationEffect(0, Attribute.DARK, 1), target_player=1)
    assert victim.resources[Attribute.FIRE] == 0
    assert state.players[0].resources[Attribute.FIRE] == 1

    stolen = single_card(Attribute.GRASS, score=3, card_id="STOLEN")
    victim.purchased.append((stolen, None))
    victim.score = 3
    resolve_specialization(state, SpecializationEffect(0, Attribute.DARK, 2), target_player=1)
    assert not victim.purchased
    assert victim.score == 0
    assert state.players[0].purchased[-1][0] is stolen
    assert state.players[0].score == 3


def test_random_specialization_results_are_reproducible_with_seed():
    states = [make_state(42), make_state(42)]
    for state in states:
        state.players[1].resources[Attribute.WATER] = 1
        state.players[1].resources[Attribute.FIRE] = 1
        resolve_specialization(state, SpecializationEffect(0, Attribute.DARK, 1), target_player=1)
    assert states[0].players[0].resources == states[1].players[0].resources
