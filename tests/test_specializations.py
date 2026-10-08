import pytest

from src.cards import all_cards, build_decks
from src.game import Action, Game
from src.models import Attribute, PetCard, Player, SpecializationEffect
from src.rules import RuleError, buy_card, create_state, refill_market, reserve_card
from src.specializations import STAGE_NAMES, detect_specializations, resolve_specialization


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
    assert Attribute.WATER in target.specialization_glows

    resolve_specialization(state, SpecializationEffect(0, Attribute.WATER, 2))
    expensive = PetCard("FREE", 1, (Attribute.GRASS,), {Attribute.DARK: 99}, 2)
    state.market.cards[1][0] = expensive
    buy_card(state, player, expensive)
    assert player.score == 2
    assert not player.next_purchase_free


def test_specialization_names_are_updated():
    assert STAGE_NAMES[(Attribute.WATER, 1)] == "泡沫幻影"
    assert STAGE_NAMES[(Attribute.GRASS, 1)] == "根吸收"
    assert STAGE_NAMES[(Attribute.GRASS, 2)] == "汲取"
    assert STAGE_NAMES[(Attribute.FIRE, 1)] == "引燃"
    assert STAGE_NAMES[(Attribute.FIRE, 2)] == "阳火增辉"
    assert STAGE_NAMES[(Attribute.CUTE, 1)] == "撒娇"
    assert STAGE_NAMES[(Attribute.CUTE, 2)] == "甜心续航"


def test_fire_stage_one_burns_opponents_reserved_card_to_its_deck_and_keeps_light():
    state = make_state()
    owner = state.players[1]
    card = state.market.cards[2][0]
    deck_size_before = len(state.decks[2])
    reserve_card(state, owner, card)
    refill_market(state)  # The next player's turn begins before the attack resolves.
    light_after_reserving = owner.light

    message = resolve_specialization(state, SpecializationEffect(0, Attribute.FIRE, 1))

    assert card not in owner.reserved
    assert card not in state.market.cards[2]
    assert card in state.decks[2]
    assert len(state.decks[2]) == deck_size_before
    assert owner.light == light_after_reserving
    assert "牌库" in message
    assert "贤者碎晶" in message


def test_fire_stage_one_without_target_reservation_burns_target_lowest_card_not_caster_card():
    state = make_state()
    caster = state.players[0]
    target = state.players[1]
    low = single_card(Attribute.FIRE, level=1, score=2, card_id="LOW")
    high = single_card(Attribute.FIRE, level=3, score=5, card_id="HIGH")
    caster_card = single_card(Attribute.WATER, level=1, score=4, card_id="CASTER")
    target.purchased.extend([(low, None), (high, None)])
    target.score = 7
    caster.purchased.append((caster_card, None))
    caster.score = 4

    resolve_specialization(state, SpecializationEffect(0, Attribute.FIRE, 1))

    assert all(card is not low for card, _ in target.purchased)
    assert any(card is high for card, _ in target.purchased)
    assert target.score == 5
    assert caster.purchased == [(caster_card, None)]
    assert caster.score == 4
    assert low in state.discarded[1]
    assert low not in state.market.cards[1]


def test_fire_stage_two_doubles_the_score_of_exactly_the_next_purchase():
    state = make_state()
    player = state.players[0]
    first = single_card(Attribute.FIRE, score=3, card_id="DOUBLE")
    second = single_card(Attribute.FIRE, score=2, card_id="NORMAL")
    state.market.cards[1][:2] = [first, second]

    resolve_specialization(state, SpecializationEffect(0, Attribute.FIRE, 2))
    buy_card(state, player, first)

    assert player.score == 6
    assert first.effective_score == 6
    assert first.score == 3
    assert not player.next_purchase_score_doubled
    buy_card(state, player, second)
    assert player.score == 8
    assert second.effective_score == 2


def test_grass_effect_adds_score_and_temporary_light_is_not_returned():
    state = make_state()
    target = state.market.cards[1][0]
    original_score = target.score
    resolve_specialization(state, SpecializationEffect(0, Attribute.GRASS, 1), card=target)
    assert target.score == original_score + 1
    assert Attribute.GRASS in target.specialization_glows

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


def test_cute_stage_one_grants_immunity_to_one_other_player_attack():
    state = make_state()
    protected = state.players[1]
    protected.resources[Attribute.FIRE] = 1
    resolve_specialization(state, SpecializationEffect(1, Attribute.CUTE, 1))
    assert protected.next_attack_immune

    message = resolve_specialization(
        state,
        SpecializationEffect(0, Attribute.DARK, 1),
        target_player=1,
    )

    assert protected.resources[Attribute.FIRE] == 1
    assert state.players[0].resources[Attribute.FIRE] == 0
    assert not protected.next_attack_immune
    assert "免疫" in message


def test_cute_stage_two_downgrades_one_random_card_for_each_other_player():
    state = make_state()
    own = PetCard("OWN-HIGH", 3, (Attribute.WATER,), {}, 5)
    state.players[0].purchased.append((own, None))
    state.players[0].score = own.effective_score
    targets = []
    for index, player in enumerate(state.players[1:], start=1):
        card = PetCard(f"TARGET-{index}", 3, own.attributes, {}, 5)
        player.purchased.append((card, None))
        player.score = card.effective_score
        targets.append((player, card, card.effective_score))

    resolve_specialization(state, SpecializationEffect(0, Attribute.CUTE, 2))

    assert own.level == 3
    for player, card, old_score in targets:
        assert card.level == 2
        assert player.score == card.effective_score < old_score


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
