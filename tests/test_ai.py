from src.ai import choose_action
from src.cards import build_decks
from src.game import Game
from src.models import ATTRIBUTES, Attribute, PetCard, Player
from src.rules import create_state


def game_with_market(*cards: PetCard) -> Game:
    game = Game(create_state([Player(name) for name in "ABCD"], build_decks(1), 1))
    for market_cards in game.state.market.cards.values():
        market_cards.clear()
    for card in cards:
        game.state.market.cards[card.level].append(card)
    return game


def test_ai_can_reserve_from_level_three_when_level_one_is_empty():
    card = PetCard("HIGH", 3, (Attribute.WATER,), {Attribute.WATER: 7}, 5)
    game = game_with_market(card)
    for attribute in ATTRIBUTES:
        game.state.resource_pool[attribute] = 0

    action = choose_action(game)

    assert action.kind == "reserve"
    assert action.card is card
    game.execute(action)
    assert card in game.state.players[0].reserved
    assert game.state.players[0].light == 1


def test_ai_reserves_a_card_it_can_buy_with_the_gained_light():
    distant = PetCard("DISTANT", 3, (Attribute.WATER,), {Attribute.WATER: 7}, 5)
    reachable = PetCard("REACHABLE", 1, (Attribute.FIRE,), {Attribute.WATER: 1}, 0)
    game = game_with_market(distant, reachable)
    for attribute in ATTRIBUTES:
        game.state.resource_pool[attribute] = 0

    action = choose_action(game)

    assert action.kind == "reserve"
    assert action.card is reachable


def test_ai_reserves_when_available_resources_do_not_help_its_target():
    card = PetCard("NEED_WATER", 1, (Attribute.WATER,), {Attribute.WATER: 2}, 1)
    game = game_with_market(card)
    game.state.resource_pool[Attribute.WATER] = 0
    game.state.resource_pool[Attribute.DARK] = 0

    action = choose_action(game)

    assert action.kind == "reserve"
    assert action.card is card


def test_ai_keeps_taking_resources_when_they_help_its_target():
    card = PetCard("NEED_WATER", 1, (Attribute.WATER,), {Attribute.WATER: 2}, 1)
    game = game_with_market(card)
    game.state.resource_pool[Attribute.CUTE] = 0
    game.state.resource_pool[Attribute.DARK] = 0

    action = choose_action(game)

    assert action.kind == "different"
    assert Attribute.WATER in action.attributes


def test_simple_difficulty_can_choose_a_legal_resource_that_does_not_help_its_target():
    card = PetCard("NEED_WATER", 1, (Attribute.WATER,), {Attribute.WATER: 2}, 1)
    game = game_with_market(card)
    for attribute in ATTRIBUTES:
        game.state.resource_pool[attribute] = 0
    for attribute in (Attribute.WATER, Attribute.FIRE, Attribute.GRASS):
        game.state.resource_pool[attribute] = 4

    game.state.rng.seed(0)
    hard_action = choose_action(game)
    game.state.rng.seed(0)
    simple_action = choose_action(game, difficulty="simple")

    assert hard_action.kind == "different"
    assert Attribute.WATER in hard_action.attributes
    assert simple_action.kind == "same"
    assert simple_action.attributes == (Attribute.GRASS,)
