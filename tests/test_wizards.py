from src.cards import build_decks
from src.game import Action, Game
from src.models import ATTRIBUTES, Attribute, PetCard, Player, SpecializationEffect
from src.rules import create_state
from src.wizards import MAGICIAN_CARDS, award_eligible_wizard_cards


def make_game(seed: int = 31) -> Game:
    players = [Player(f"玩家{index}") for index in range(1, 5)]
    return Game(create_state(players, build_decks(seed), seed))


def set_wizard_market(game: Game, visible: list) -> None:
    game.state.wizard_market = list(visible)
    game.state.wizard_deck = [card for card in MAGICIAN_CARDS if card not in visible]


def add_single_attribute_pets(player: Player, attribute: Attribute, amount: int) -> None:
    player.purchased.extend(
        (PetCard(f"{attribute.value}{index}", 1, (attribute,), {}, 0), None)
        for index in range(amount)
    )


def test_ten_wizard_cards_have_the_expected_requirements_and_fixed_score():
    assert len(MAGICIAN_CARDS) == 10
    assert all(card.score == 3 for card in MAGICIAN_CARDS)
    assert {card.name: dict(card.requirements) for card in MAGICIAN_CARDS} == {
        "萌萌": {Attribute.CUTE: 4, Attribute.GRASS: 4},
        "可丽希亚": {Attribute.FIRE: 4, Attribute.WATER: 4},
        "菲尔特": {Attribute.WATER: 3, Attribute.DARK: 3, Attribute.GRASS: 3},
        "皮卡": {Attribute.FIRE: 4, Attribute.CUTE: 4},
        "万事通": {Attribute.GRASS: 3, Attribute.DARK: 3, Attribute.WATER: 3},
        "博得": {Attribute.WATER: 4, Attribute.GRASS: 4},
        "路易斯": {Attribute.FIRE: 3, Attribute.DARK: 3, Attribute.CUTE: 3},
        "恩佐": {Attribute.DARK: 4, Attribute.CUTE: 4},
        "兰斯洛": {Attribute.WATER: 3, Attribute.FIRE: 3, Attribute.GRASS: 3},
        "斯诺克": {Attribute.GRASS: 3, Attribute.CUTE: 3, Attribute.DARK: 3},
    }


def test_game_starts_with_three_seeded_wizard_market_cards():
    game = make_game(seed=31)
    same_seed_game = make_game(seed=31)

    assert len(game.state.wizard_market) == 3
    assert len(game.state.wizard_deck) == 7
    assert game.state.wizard_market == same_seed_game.state.wizard_market
    assert set(game.state.wizard_market + game.state.wizard_deck) == set(MAGICIAN_CARDS)


def test_dual_pets_count_for_both_attributes_when_awarding_visible_wizard():
    game = make_game()
    player = game.state.players[0]
    set_wizard_market(game, [MAGICIAN_CARDS[0]])
    player.purchased.extend(
        (PetCard(f"D{index}", 1, (Attribute.CUTE, Attribute.GRASS), {}, 0), None)
        for index in range(4)
    )

    messages = game.execute(Action("pass"))

    assert [card.name for card in player.wizard_cards] == ["萌萌"]
    assert player.score == 3
    assert messages == ["获得魔法师卡【萌萌】（+3分）"]


def test_one_turn_awards_all_eligible_visible_wizards_but_not_replacements():
    game = make_game()
    player = game.state.players[0]
    set_wizard_market(game, list(MAGICIAN_CARDS[:3]))
    for attribute in ATTRIBUTES:
        add_single_attribute_pets(player, attribute, 4)

    messages = game.execute(Action("pass"))

    assert player.wizard_cards == list(MAGICIAN_CARDS[:3])
    assert player.score == 9
    assert len(messages) == 3
    assert game.state.wizard_market == list(MAGICIAN_CARDS[3:6])
    assert game.state.wizard_deck == list(MAGICIAN_CARDS[6:])


def test_wizard_score_contributes_to_the_game_end_threshold():
    game = make_game()
    player = game.state.players[0]
    set_wizard_market(game, [MAGICIAN_CARDS[0]])
    player.score = 15
    add_single_attribute_pets(player, Attribute.CUTE, 4)
    add_single_attribute_pets(player, Attribute.GRASS, 4)

    game.execute(Action("pass"))

    assert player.score == 18
    assert game.state.end_triggered
    assert game.state.finished
    assert game.state.current_player == 0


def test_wizard_check_happens_after_specialization_resolution():
    game = make_game()
    player = game.state.players[0]
    set_wizard_market(game, [next(card for card in MAGICIAN_CARDS if card.name == "博得")])
    add_single_attribute_pets(player, Attribute.WATER, 4)
    add_single_attribute_pets(player, Attribute.GRASS, 4)
    game.state.pending_specializations.append(SpecializationEffect(0, Attribute.WATER, 1))
    target = game.state.market.cards[1][0]

    messages = game.execute(Action("specialization", card=target))

    assert [card.name for card in player.wizard_cards] == ["博得"]
    assert player.score == 3
    assert messages[-1:] == [
        "获得魔法师卡【博得】（+3分）",
    ]


def test_only_purchased_pet_attributes_count_for_wizard_cards():
    game = make_game()
    player = game.state.players[0]
    set_wizard_market(game, [MAGICIAN_CARDS[0]])
    for attribute in ATTRIBUTES:
        player.resources[attribute] = 10
    player.reserved.extend(
        PetCard(f"R{index}", 1, (Attribute.CUTE, Attribute.GRASS), {}, 0)
        for index in range(4)
    )

    game.execute(Action("pass"))

    assert not player.wizard_cards
    assert player.score == 0


def test_awarded_wizard_card_is_not_awarded_again():
    player = Player("玩家")
    add_single_attribute_pets(player, Attribute.CUTE, 4)
    add_single_attribute_pets(player, Attribute.GRASS, 4)

    available = [MAGICIAN_CARDS[0]]
    first_award = award_eligible_wizard_cards(player, available)
    second_award = award_eligible_wizard_cards(player, available)

    assert [card.name for card in first_award] == ["萌萌"]
    assert second_award == []
    assert player.score == 3
    assert len(player.wizard_cards) == 1
