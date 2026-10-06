from __future__ import annotations

from .cards import all_cards
from .models import Attribute, GameState, PetCard, Player, SpecializationEffect
from .rules import RuleError


STAGE_NAMES = {
    (Attribute.WATER, 1): "润泽",
    (Attribute.WATER, 2): "免费捕捉",
    (Attribute.FIRE, 1): "炽热背包",
    (Attribute.FIRE, 2): "火云车",
    (Attribute.GRASS, 1): "生机",
    (Attribute.GRASS, 2): "万物生",
    (Attribute.CUTE, 1): "萌化",
    (Attribute.CUTE, 2): "示弱",
    (Attribute.DARK, 1): "吞噬",
    (Attribute.DARK, 2): "恶魔契约",
}


def specialization_name(effect: SpecializationEffect) -> str:
    return f"{effect.attribute.value}系阶段{effect.stage}·{STAGE_NAMES[(effect.attribute, effect.stage)]}"


def single_attribute_count(player: Player, attribute: Attribute) -> int:
    return sum(1 for card, _ in player.purchased if not card.is_dual and card.attributes[0] == attribute)


def detect_specializations(state: GameState, player_index: int) -> list[SpecializationEffect]:
    """检测购买后新跨过的 2/3 张门槛。"""
    player = state.players[player_index]
    found: list[SpecializationEffect] = []
    for attribute in Attribute:
        count = single_attribute_count(player, attribute)
        for stage, threshold in ((1, 2), (2, 3)):
            key = (attribute, stage)
            if count >= threshold and key not in player.specialization_triggered:
                player.specialization_triggered.add(key)
                effect = SpecializationEffect(player_index, attribute, stage)
                state.pending_specializations.append(effect)
                found.append(effect)
    return found


def legal_card_targets(state: GameState, effect: SpecializationEffect) -> list[PetCard]:
    cards = [card for level in (1, 2, 3) for card in state.market.cards[level]]
    if effect.attribute == Attribute.CUTE and effect.stage == 1:
        return [card for card in cards if card.level > 1]
    if (effect.attribute, effect.stage) in {
        (Attribute.WATER, 1),
        (Attribute.GRASS, 1),
    }:
        return cards
    return []


def legal_player_targets(state: GameState, effect: SpecializationEffect) -> list[int]:
    owner = state.players[effect.player_index]
    if effect.attribute != Attribute.DARK:
        return []
    if effect.stage == 1:
        if owner.resource_count >= owner.resource_capacity:
            return []
        return [
            index
            for index, player in enumerate(state.players)
            if index != effect.player_index and any(player.resources.values())
        ]
    candidates = [index for index in range(len(state.players)) if index != effect.player_index]
    if not candidates:
        return []
    largest = max(len(state.players[index].purchased) for index in candidates)
    if largest == 0:
        return []
    return [index for index in candidates if len(state.players[index].purchased) == largest]


def _template_for_downgrade(card: PetCard) -> PetCard:
    target_level = card.level - 1
    candidates = [
        template
        for template in all_cards()
        if template.level == target_level and template.attributes == card.attributes
    ]
    if not candidates:
        raise RuleError(f"{card.card_id} 没有可用的低一级对应形态")
    digits = "".join(character for character in card.card_id if character.isdigit())
    index = (int(digits) if digits else 0) % len(candidates)
    return sorted(candidates, key=lambda item: item.card_id)[index]


def downgrade_card(card: PetCard) -> tuple[int, int, str]:
    """按同属性的低一级卡牌模板萌化，保留原卡 ID 作为对局身份。"""
    if card.level <= 1:
        raise RuleError("一级宠物不能继续萌化")
    old_level = card.level
    old_score = card.score
    template = _template_for_downgrade(card)
    card.level = template.level
    card.cost = dict(template.cost)
    card.score = template.score
    card.transformed_from = template.card_id
    return old_level, old_score, template.card_id


def _refill_level(state: GameState, level: int, target_size: int) -> None:
    while len(state.market.cards[level]) < target_size and state.decks[level]:
        state.market.cards[level].append(state.decks[level].pop())


def resolve_specialization(
    state: GameState,
    effect: SpecializationEffect,
    *,
    card: PetCard | None = None,
    target_player: int | None = None,
) -> str:
    player = state.players[effect.player_index]
    attribute = effect.attribute
    stage = effect.stage
    name = specialization_name(effect)

    if (attribute, stage) == (Attribute.WATER, 1):
        legal_cards = legal_card_targets(state, effect)
        if not legal_cards:
            return f"{name}：市场中没有可选宠物，效果失效"
        if card not in legal_cards:
            raise RuleError("润泽需要选择公共市场中的宠物")
        assert card is not None
        highest = max(card.cost.values())
        choices = [item for item, amount in card.cost.items() if amount == highest]
        reduced = state.rng.choice(choices)
        card.cost = dict(card.cost)
        card.cost[reduced] -= 1
        if card.cost[reduced] == 0:
            del card.cost[reduced]
        return f"{name}：{card.card_id} 的{reduced.value}系成本 -1"

    if (attribute, stage) == (Attribute.WATER, 2):
        player.next_purchase_free = True
        return f"{name}：{player.name} 下一次购买免费"

    if (attribute, stage) == (Attribute.FIRE, 1):
        player.resource_capacity += 1
        return f"{name}：{player.name} 的资源上限提高到 {player.resource_capacity}"

    if (attribute, stage) == (Attribute.FIRE, 2):
        burned = 0
        for level in (1, 2, 3):
            old_cards = list(state.market.cards[level])
            state.market.cards[level].clear()
            state.discarded[level].extend(old_cards)
            burned += len(old_cards)
            _refill_level(state, level, len(old_cards))
        return f"{name}：烧掉市场 {burned} 张宠物并重新补牌"

    if (attribute, stage) == (Attribute.GRASS, 1):
        legal_cards = legal_card_targets(state, effect)
        if not legal_cards:
            return f"{name}：市场中没有可选宠物，效果失效"
        if card not in legal_cards:
            raise RuleError("生机需要选择公共市场中的宠物")
        assert card is not None
        card.score += 1
        return f"{name}：{card.card_id} 的分数 +1"

    if (attribute, stage) == (Attribute.GRASS, 2):
        grass_cards = sum(
            single_attribute_count(other, Attribute.GRASS)
            for index, other in enumerate(state.players)
            if index != effect.player_index
        )
        gained = grass_cards + 1
        player.temporary_light += gained
        return f"{name}：{player.name} 获得 {gained} 枚临时光系灵碎"

    if (attribute, stage) == (Attribute.CUTE, 1):
        legal_cards = legal_card_targets(state, effect)
        if not legal_cards:
            return f"{name}：市场中没有可萌化的宠物，效果失效"
        if card not in legal_cards:
            raise RuleError("萌化需要选择公共市场中的二级或三级宠物")
        assert card is not None
        old_level = card.level
        old_market_size = len(state.market.cards[old_level])
        state.market.cards[old_level].remove(card)
        _, _, template_id = downgrade_card(card)
        state.market.cards[card.level].append(card)
        _refill_level(state, old_level, old_market_size)
        return f"{name}：{card.card_id} 萌化为 {template_id} 数值模板并移入 {card.level} 级市场"

    if (attribute, stage) == (Attribute.CUTE, 2):
        changed: list[str] = []
        for owner in state.players:
            eligible = [owned for owned, _ in owner.purchased if owned.level > 1]
            if not eligible:
                continue
            chosen = state.rng.choice(eligible)
            _, old_score, template_id = downgrade_card(chosen)
            owner.score += chosen.score - old_score
            changed.append(f"{owner.name}:{chosen.card_id}→{template_id}")
        detail = "、".join(changed) if changed else "没有可萌化的宠物"
        return f"{name}：{detail}"

    if (attribute, stage) == (Attribute.DARK, 1):
        legal_players = legal_player_targets(state, effect)
        if not legal_players:
            return f"{name}：没有可偷取的灵碎，效果失效"
        if target_player not in legal_players:
            raise RuleError("吞噬需要选择一名持有属性灵碎的其他玩家")
        assert target_player is not None
        victim = state.players[target_player]
        choices = [item for item, amount in victim.resources.items() if amount > 0]
        stolen = state.rng.choice(choices)
        victim.resources[stolen] -= 1
        player.resources[stolen] += 1
        return f"{name}：{player.name} 从 {victim.name} 偷取 1 枚{stolen.value}系灵碎"

    if (attribute, stage) == (Attribute.DARK, 2):
        legal_players = legal_player_targets(state, effect)
        if not legal_players:
            return f"{name}：没有可偷取的宠物"
        if target_player is None and len(legal_players) == 1:
            target_player = legal_players[0]
        if target_player not in legal_players:
            raise RuleError("恶魔契约必须从已购宠物数最多的其他玩家中选择")
        assert target_player is not None
        victim = state.players[target_player]
        stolen_entry = state.rng.choice(victim.purchased)
        victim.purchased.remove(stolen_entry)
        player.purchased.append(stolen_entry)
        stolen_card = stolen_entry[0]
        victim.score -= stolen_card.score
        player.score += stolen_card.score
        return f"{name}：{player.name} 从 {victim.name} 偷走 {stolen_card.card_id}"

    raise RuleError("未知的属性专精效果")
