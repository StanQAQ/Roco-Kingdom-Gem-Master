from __future__ import annotations

from collections import Counter

from .models import Attribute, Player, WizardCard


MAGICIAN_CARDS = (
    WizardCard("萌萌", ((Attribute.CUTE, 4), (Attribute.GRASS, 4))),
    WizardCard("可丽希亚", ((Attribute.FIRE, 4), (Attribute.WATER, 4))),
    WizardCard("菲尔特", ((Attribute.WATER, 3), (Attribute.DARK, 3), (Attribute.GRASS, 3))),
    WizardCard("皮卡", ((Attribute.FIRE, 4), (Attribute.CUTE, 4))),
    WizardCard("万事通", ((Attribute.GRASS, 3), (Attribute.DARK, 3), (Attribute.WATER, 3))),
    WizardCard("博得", ((Attribute.WATER, 4), (Attribute.GRASS, 4))),
    WizardCard("路易斯", ((Attribute.FIRE, 3), (Attribute.DARK, 3), (Attribute.CUTE, 3))),
    WizardCard("恩佐", ((Attribute.DARK, 4), (Attribute.CUTE, 4))),
    WizardCard("兰斯洛", ((Attribute.WATER, 3), (Attribute.FIRE, 3), (Attribute.GRASS, 3))),
    WizardCard("斯诺克", ((Attribute.GRASS, 3), (Attribute.CUTE, 3), (Attribute.DARK, 3))),
)


def award_eligible_wizard_cards(player: Player, available_wizards: list[WizardCard]) -> list[WizardCard]:
    """Award eligible cards from the public wizard market based on purchased pets."""
    attribute_counts: Counter[Attribute] = Counter()
    for pet, _chosen_attribute in player.purchased:
        attribute_counts.update(pet.attributes)

    acquired: list[WizardCard] = []
    for wizard in tuple(available_wizards):
        if wizard in player.wizard_cards:
            continue
        if all(attribute_counts[attribute] >= amount for attribute, amount in wizard.requirements):
            player.wizard_cards.append(wizard)
            player.score += wizard.score
            acquired.append(wizard)
    return acquired
