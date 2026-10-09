from __future__ import annotations

from collections import Counter

from .models import Attribute, Player, WizardCard


MAGICIAN_CARDS = (
    WizardCard("萌萌", ((Attribute.CUTE, 4), (Attribute.GRASS, 4)), card_id="W01"),
    WizardCard("格里芬", ((Attribute.FIRE, 4), (Attribute.WATER, 4)), card_id="W02"),
    WizardCard("伊里斯", ((Attribute.WATER, 3), (Attribute.DARK, 3), (Attribute.GRASS, 3)), card_id="W03"),
    WizardCard("皮卡", ((Attribute.FIRE, 4), (Attribute.CUTE, 4)), card_id="W04"),
    WizardCard("万事通", ((Attribute.GRASS, 3), (Attribute.DARK, 3), (Attribute.WATER, 3)), card_id="W05"),
    WizardCard("博得", ((Attribute.WATER, 4), (Attribute.GRASS, 4)), card_id="W06"),
    WizardCard("路易斯", ((Attribute.FIRE, 3), (Attribute.DARK, 3), (Attribute.CUTE, 3)), card_id="W07"),
    WizardCard("恩佐", ((Attribute.DARK, 4), (Attribute.CUTE, 4)), card_id="W08"),
    WizardCard("兰斯洛", ((Attribute.WATER, 3), (Attribute.FIRE, 3), (Attribute.GRASS, 3)), card_id="W09"),
    WizardCard("斯诺克", ((Attribute.GRASS, 3), (Attribute.CUTE, 3), (Attribute.DARK, 3)), card_id="W10"),
)


def award_eligible_wizard_cards(player: Player, available_wizards: list[WizardCard]) -> list[WizardCard]:
    """Award the leftmost eligible card, at most one per turn."""
    attribute_counts: Counter[Attribute] = Counter()
    for pet, _chosen_attribute in player.purchased:
        attribute_counts.update(pet.attributes)

    owned_wizard_ids = {wizard.card_id for wizard in player.wizard_cards}
    for wizard in tuple(available_wizards):
        if wizard.card_id in owned_wizard_ids:
            continue
        if all(attribute_counts[attribute] >= amount for attribute, amount in wizard.requirements):
            player.wizard_cards.append(wizard)
            player.score += wizard.score
            return [wizard]
    return []
