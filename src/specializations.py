from __future__ import annotations

from .models import Attribute, GameState, PetCard, Player, SpecializationEffect
from .rules import RuleError


STAGE_NAMES = {
    (Attribute.WATER, 1): "润泽",
    (Attribute.WATER, 2): "泡沫幻影",
    (Attribute.FIRE, 1): "引燃",
    (Attribute.FIRE, 2): "阳火增辉",
    (Attribute.GRASS, 1): "根吸收",
    (Attribute.GRASS, 2): "汲取",
    (Attribute.CUTE, 1): "撒娇",
    (Attribute.CUTE, 2): "甜心续航",
    (Attribute.DARK, 1): "吞噬",
    (Attribute.DARK, 2): "恶魔契约",
}


def specialization_name(effect: SpecializationEffect) -> str:
    stage_name = {1: "一", 2: "二"}.get(effect.stage, str(effect.stage))
    repeat = f"（第{effect.occurrence}次）" if effect.occurrence > 1 else ""
    return f"{effect.attribute.value}系阶段{stage_name}·{STAGE_NAMES[(effect.attribute, effect.stage)]}{repeat}"


def single_attribute_count(player: Player, attribute: Attribute) -> int:
    return sum(1 for card, _ in player.purchased if not card.is_dual and card.attributes[0] == attribute)


def detect_specializations(state: GameState, player_index: int) -> list[SpecializationEffect]:
    """检测购买后新跨过的专精门槛：2/3 张首次触发，之后每3张重复。"""
    player = state.players[player_index]
    found: list[SpecializationEffect] = []
    for attribute in Attribute:
        count = single_attribute_count(player, attribute)
        due: list[tuple[int, int, int]] = []
        for stage, first_threshold in ((1, 2), (2, 3)):
            occurrence = 1
            threshold = first_threshold
            while count >= threshold:
                key = (attribute, stage, occurrence)
                if key not in player.specialization_triggered:
                    due.append((threshold, stage, occurrence))
                occurrence += 1
                threshold += 3
        for _threshold, stage, occurrence in sorted(due):
            player.specialization_triggered.add((attribute, stage, occurrence))
            effect = SpecializationEffect(player_index, attribute, stage, occurrence)
            state.pending_specializations.append(effect)
            found.append(effect)
    return found


def legal_card_targets(state: GameState, effect: SpecializationEffect) -> list[PetCard]:
    cards = [card for level in (1, 2, 3) for card in state.market.cards[level]]
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
    return [
        index
        for index, player in enumerate(state.players)
        if index != effect.player_index and player.purchased
    ]


def _return_to_deck(state: GameState, card: PetCard) -> None:
    """Shuffle a burned reservation back into its level deck."""
    card.score_multiplier = 1
    deck = state.decks[card.level]
    deck.insert(state.rng.randrange(len(deck) + 1), card)


def _burn_for_fire_stage_one(state: GameState, player_index: int) -> str:
    opponents = [target for index, target in enumerate(state.players) if index != player_index]
    if not opponents:
        return "没有可选的对手，效果未生效"

    # Preserve the effect's original behavior when a burn is possible. Select
    # an empty-handed opponent only when nobody has any eligible card, so the
    # failed outcome can still name an actual selected player.
    targets = [target for target in opponents if target.reserved or target.purchased]
    if not targets:
        targets = opponents
    target = state.rng.choice(targets)
    if target.reserved or target.purchased:
        blocked = _apply_attack_immunity(
            state.players[player_index], target, "火系阶段一·引燃"
        )
        if blocked:
            return blocked.partition("：")[2]

    if target.reserved:
        card = state.rng.choice(target.reserved)
        target.reserved = [reserved for reserved in target.reserved if reserved.card_id != card.card_id]
        _return_to_deck(state, card)
        return (
            f"选中玩家【{target.name}】：引燃其预购卡【{card.display_name}】，"
            f"归还至{card.level}级牌库；其预购获得的贤者碎晶保留"
        )

    if not target.purchased:
        return f"选中玩家【{target.name}】：没有预购卡或已购卡可引燃，效果未生效"

    lowest_level = min(card.level for card, _ in target.purchased)
    candidates = [card for card, _ in target.purchased if card.level == lowest_level]
    card = state.rng.choice(candidates)
    old_score = card.effective_score
    target.purchased = [
        (owned, chosen)
        for owned, chosen in target.purchased
        if owned.card_id != card.card_id
    ]
    target.score -= old_score
    state.discarded[card.level].append(card)
    return (
        f"选中玩家【{target.name}】：没有预购卡，引燃其最低等级卡【{card.display_name}】，"
        f"该卡移出对局，失去{old_score}分"
    )


def _apply_attack_immunity(attacker: Player, target: Player, name: str) -> str | None:
    if attacker is target or not target.next_attack_immune:
        return None
    target.next_attack_immune = False
    return f"{name}：{target.name}触发撒娇，免疫了来自{attacker.name}的攻击"


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
        selected_card_id = card.card_id if card is not None else None
        card = next(
            (candidate for candidate in legal_cards if candidate.card_id == selected_card_id),
            None,
        )
        if card is None:
            raise RuleError("润泽需要选择公共市场中的宠物")
        highest = max(card.cost.values())
        choices = [item for item, amount in card.cost.items() if amount == highest]
        reduced = state.rng.choice(choices)
        card.cost = dict(card.cost)
        card.cost[reduced] -= 1
        if card.cost[reduced] == 0:
            del card.cost[reduced]
        card.specialization_glows.add(Attribute.WATER)
        return f"{name}：{card.display_name} 的{reduced.value}系成本 -1"

    if (attribute, stage) == (Attribute.WATER, 2):
        player.next_purchase_free = True
        return f"{name}：{player.name} 下一次购买免费"

    if (attribute, stage) == (Attribute.FIRE, 1):
        return f"{name}：{_burn_for_fire_stage_one(state, effect.player_index)}"

    if (attribute, stage) == (Attribute.FIRE, 2):
        player.next_purchase_score_doubled = True
        return f"{name}：{player.name}下一张购买的宠物分数翻倍"

    if (attribute, stage) == (Attribute.GRASS, 1):
        legal_cards = legal_card_targets(state, effect)
        if not legal_cards:
            return f"{name}：市场中没有可选宠物，效果失效"
        selected_card_id = card.card_id if card is not None else None
        card = next(
            (candidate for candidate in legal_cards if candidate.card_id == selected_card_id),
            None,
        )
        if card is None:
            raise RuleError("根吸收需要选择公共市场中的宠物")
        card.score += 1
        card.specialization_glows.add(Attribute.GRASS)
        return f"{name}：{card.display_name} 的分数 +1"

    if (attribute, stage) == (Attribute.GRASS, 2):
        grass_cards = sum(
            single_attribute_count(owner, Attribute.GRASS)
            for owner in state.players
        )
        gained = grass_cards
        player.temporary_light += gained
        return f"{name}：{player.name} 获得 {gained} 枚临时贤者碎晶"

    if (attribute, stage) == (Attribute.CUTE, 1):
        player.next_attack_immune = True
        return f"{name}：{player.name}获得一次攻击免疫，直到免疫一次其他玩家的攻击"

    if (attribute, stage) == (Attribute.CUTE, 2):
        changed: list[str] = []
        unchanged_zero: list[str] = []
        unavailable: list[str] = []
        immune: list[str] = []
        for index, owner in enumerate(state.players):
            if index == effect.player_index:
                continue
            # 优先从未萌化的3级卡中选；没有时才退到未萌化的2级卡。
            # 1级卡和已萌化卡不参与选择。
            level_three = [
                card for card, _ in owner.purchased
                if card.level == 3 and not card.cuteified
            ]
            level_two = [
                card for card, _ in owner.purchased
                if card.level == 2 and not card.cuteified
            ]
            eligible = level_three or level_two
            if not eligible:
                unavailable.append(owner.name)
                continue
            blocked = _apply_attack_immunity(player, owner, name)
            if blocked:
                immune.append(owner.name)
                continue
            highest_level = max(card.level for card in eligible)
            eligible = [card for card in eligible if card.level == highest_level]
            chosen = state.rng.choice(eligible)
            old_score = chosen.effective_score
            if old_score == 0:
                unchanged_zero.append(
                    f"{owner.name}:{chosen.display_name}（{highest_level}级）原本0分，未萌化"
                )
                continue
            chosen.score = 0
            chosen.cuteified = True
            owner.score -= old_score
            changed.append(f"{owner.name}:{chosen.display_name}（{highest_level}级）{old_score}分→0分")
        details = []
        if changed:
            details.append("已萌化：" + "；".join(changed))
        if unchanged_zero:
            details.append("选中原本0分卡（未改变且未标记萌化）：" + "；".join(unchanged_zero))
        if unavailable:
            details.append("没有可萌化的2级或3级卡：" + "、".join(unavailable))
        if immune:
            details.append("免疫了攻击：" + "、".join(immune))
        if not details:
            details.append("没有可萌化的2级或3级卡")
        return f"{name}：3级优先、否则2级中随机萌化；{'；'.join(details)}"

    if (attribute, stage) == (Attribute.DARK, 1):
        legal_players = legal_player_targets(state, effect)
        if not legal_players:
            return f"{name}：没有可偷取的灵碎，效果失效"
        if target_player not in legal_players:
            raise RuleError("吞噬需要选择一名持有属性灵碎的其他玩家")
        assert target_player is not None
        victim = state.players[target_player]
        blocked = _apply_attack_immunity(player, victim, name)
        if blocked:
            return blocked
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
            raise RuleError("恶魔契约需要选择一名持有已购宠物的其他玩家")
        assert target_player is not None
        victim = state.players[target_player]
        blocked = _apply_attack_immunity(player, victim, name)
        if blocked:
            return blocked
        stolen_entry = state.rng.choice(victim.purchased)
        stolen_card_id = stolen_entry[0].card_id
        victim.purchased = [
            entry for entry in victim.purchased if entry[0].card_id != stolen_card_id
        ]
        player.purchased.append(stolen_entry)
        stolen_card = stolen_entry[0]
        victim.score -= stolen_card.effective_score
        player.score += stolen_card.effective_score
        return f"{name}：{player.name} 从 {victim.name} 偷走 {stolen_card.display_name}"

    raise RuleError("未知的属性专精效果")
