import pytest

from src.cards import all_cards, build_decks
from src.game import Action, Game
from src.models import ATTRIBUTES, Attribute, Player
from src.rules import RuleError, create_state, payment_for


def game() -> Game:
    return Game(create_state([Player("A"), Player("B"), Player("C"), Player("D")], build_decks(1)))


def test_catalog_has_90_cards_and_market_has_five_each():
    current = game()
    assert len(all_cards()) == 90
    assert sum(len(deck) for deck in current.state.decks.values()) == 75
    assert [len(current.state.market.cards[level]) for level in (1, 2, 3)] == [5, 5, 5]


def test_take_three_different_resources():
    current = game()
    current.execute(Action("different", attributes=(Attribute.WATER, Attribute.FIRE, Attribute.GRASS)))
    assert current.state.players[0].resource_count == 3
    assert current.state.resource_pool[Attribute.WATER] == 6


def test_same_resource_requires_four_before_taking():
    current = game()
    current.state.resource_pool[Attribute.WATER] = 3
    with pytest.raises(RuleError):
        current.execute(Action("same", attributes=(Attribute.WATER,)))


def test_reserve_gets_light_and_buy_returns_it():
    current = game()
    card = current.state.market.cards[1][0]
    current.execute(Action("reserve", card=card))
    assert current.state.players[0].light == 1
    assert card in current.state.players[0].reserved


def test_dual_discount_is_selected_per_purchase():
    current = game()
    player = current.state.players[0]
    dual = next(card for card in current.state.market.cards[1] if card.is_dual)
    player.purchased.append((dual, None))
    for attribute, amount in dual.cost.items():
        player.resources[attribute] = amount
    chosen = [dual.attributes[0]]
    payment = payment_for(player, dual, chosen)
    assert payment.light == 0


def test_end_trigger_finishes_after_full_round():
    current = game()
    current.state.players[0].score = 18
    current.execute(Action("different", attributes=(Attribute.WATER, Attribute.FIRE, Attribute.GRASS)))
    assert current.state.end_triggered
    assert not current.state.finished
    for _ in range(3):
        current.execute(Action("different", attributes=(Attribute.WATER, Attribute.FIRE, Attribute.GRASS)))
    assert current.state.finished


def test_empty_market_also_finishes_after_full_round():
    current = game()
    for cards in current.state.market.cards.values():
        cards.clear()
    for deck in current.state.decks.values():
        deck.clear()
    for _ in range(4):
        current.execute(Action("pass"))
    assert current.state.finished
