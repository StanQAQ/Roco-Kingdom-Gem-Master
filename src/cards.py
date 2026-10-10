from __future__ import annotations

import random

from .models import Attribute, PetCard, normalize_cost

A = Attribute

# 卡片名称以卡片.md为准；卡号仅用于游戏逻辑和定位卡片。
CARD_NAMES = {
    'S01': '水蓝蓝', 'S02': '板板壳', 'S03': '小鼠獭', 'S04': '水滴蛇', 'S05': '乖乖鹄',
    'S06': '护主犬', 'S07': '小勇狮', 'S08': '热团团', 'S09': '火花', 'S10': '红火尾',
    'S11': '蹦蹦果', 'S12': '小草虫', 'S13': '松仔', 'S14': '喵喵', 'S15': '格兰种子',
    'S16': '加灵', 'S17': '蝴蝶陶陶', 'S18': '逗逗', 'S19': '大耳帽兜', 'S20': '毛毛',
    'S21': '小帕尔', 'S22': '小夜', 'S23': '阿米亚特', 'S24': '恶魔叮', 'S25': '恶魔小萝',
    'D01': '熔岩布丁', 'D02': '熔岩布丁', 'D03': '抹茶布丁', 'D04': '加油海葵', 'D05': '甜田螺',
    'D06': '芽眼魔', 'D07': '苞米仔', 'D08': '柴渣虫', 'D09': '火山丢丢', 'D10': '治愈兔',
    'D11': '治愈兔', 'D12': '乌达', 'D13': '乌达', 'D14': '蒲公英', 'D15': '蒲公英',
    'S26': '波波拉', 'S27': '咔咔壳', 'S28': '燕尾獭', 'S29': '水蛇锁', 'S30': '音速犬',
    'S31': '炽焰狮', 'S32': '雅丹鬃', 'S33': '焰火', 'S34': '蹦蹦果', 'S35': '草衣虫',
    'S36': '松叶羊', 'S37': '喵呜', 'S38': '加益', 'S39': '爬爬', 'S40': '气球猫',
    'S41': '帽兜娃娃', 'S42': '帕尔萨斯', 'S43': '紫夜', 'S44': '阿米樱',
    'D16': '超级熔岩布丁', 'D17': '燃燃熔岩布丁', 'D18': '抹茶茉莉布丁', 'D19': '特浓抹茶布丁',
    'D20': '叶眼魔', 'D21': '火山卡卡虫', 'D22': '燃薪虫', 'D23': '红丝绒', 'D24': '红丝绒',
    'D25': '迷你乌', 'D26': '蒲公英娃娃',
    'S45': '水灵', 'S46': '化蝶', 'S47': '火神', 'S48': '魔力猫', 'S49': '龙息帕尔',
    'S50': '水泡壳', 'S51': '朔夜伊芙', 'S52': '加尔', 'S53': '翠顶夫人', 'S54': '罗隐',
    'S55': '风暴战犬', 'S56': '花衣蝶', 'S57': '梦想三三', 'S58': '恶魔男爵', 'S59': '雪影娃娃',
    'S60': '针叶巡林', 'D27': '障眼魔', 'D28': '红绒十字', 'D29': '卡洛儿', 'D30': '乌拉塔',
}


def name_for_card_id(card_id: str | None) -> str:
    """Return a visible card name for a stored card identifier."""
    if card_id is None:
        return ""
    return CARD_NAMES.get(card_id, card_id)

# 卡片.md中与旧牌库不同的属性、分数和成本，格式为：(属性, 分数, 成本)。
CARD_DATA_CORRECTIONS = {
    'D04': ((A.WATER, A.CUTE), 0, [(A.FIRE, 1), (A.CUTE, 1), (A.DARK, 2)]),
    'D05': ((A.WATER, A.CUTE), 1, [(A.FIRE, 2), (A.CUTE, 1), (A.DARK, 1)]),
    'D07': ((A.FIRE, A.GRASS), 1, [(A.WATER, 1), (A.GRASS, 1), (A.CUTE, 2)]),
    'S26': ((A.WATER,), 1, [(A.FIRE, 3), (A.GRASS, 2), (A.CUTE, 2)]),
    'S27': ((A.WATER,), 1, [(A.FIRE, 3), (A.GRASS, 2), (A.CUTE, 2)]),
    'S28': ((A.WATER,), 2, [(A.FIRE, 5)]),
    'S29': ((A.WATER,), 3, [(A.FIRE, 6)]),
    'S30': ((A.FIRE,), 2, [(A.WATER, 4), (A.GRASS, 2), (A.CUTE, 1)]),
    'S31': ((A.FIRE,), 2, [(A.WATER, 5), (A.GRASS, 3)]),
    'S32': ((A.FIRE,), 2, [(A.WATER, 5), (A.GRASS, 3)]),
    'S33': ((A.FIRE,), 2, [(A.WATER, 4), (A.GRASS, 2), (A.CUTE, 1)]),
    'S34': ((A.GRASS,), 2, [(A.WATER, 4), (A.FIRE, 2), (A.CUTE, 1)]),
    'S35': ((A.GRASS,), 1, [(A.WATER, 3), (A.FIRE, 3), (A.CUTE, 2)]),
    'S36': ((A.GRASS,), 2, [(A.WATER, 5)]),
    'S37': ((A.GRASS,), 1, [(A.WATER, 3), (A.FIRE, 3), (A.CUTE, 2)]),
    'S38': ((A.CUTE,), 1, [(A.WATER, 3), (A.FIRE, 3), (A.GRASS, 2)]),
    'S39': ((A.CUTE,), 2, [(A.WATER, 5)]),
    'S40': ((A.CUTE,), 2, [(A.WATER, 5), (A.FIRE, 3)]),
    'S41': ((A.CUTE,), 2, [(A.WATER, 5), (A.FIRE, 3)]),
    'S42': ((A.DARK,), 1, [(A.WATER, 3), (A.FIRE, 2), (A.GRASS, 2)]),
    'S43': ((A.DARK,), 2, [(A.WATER, 4), (A.FIRE, 2), (A.GRASS, 1)]),
    'S44': ((A.DARK,), 3, [(A.WATER, 6)]),
    'D16': ((A.WATER, A.FIRE), 2, [(A.GRASS, 5), (A.CUTE, 3)]),
    'D17': ((A.WATER, A.FIRE), 2, [(A.GRASS, 5)]),
    'D18': ((A.WATER, A.GRASS), 3, [(A.FIRE, 6)]),
    'D19': ((A.WATER, A.GRASS), 1, [(A.FIRE, 3), (A.CUTE, 2), (A.DARK, 2)]),
    'D20': ((A.WATER, A.DARK), 1, [(A.FIRE, 3), (A.GRASS, 3), (A.CUTE, 2)]),
    'D21': ((A.FIRE, A.GRASS), 1, [(A.WATER, 3), (A.CUTE, 2), (A.DARK, 2)]),
    'D22': ((A.FIRE, A.GRASS), 1, [(A.WATER, 3), (A.CUTE, 3), (A.DARK, 2)]),
    'D23': ((A.FIRE, A.CUTE), 3, [(A.WATER, 6)]),
    'D24': ((A.FIRE, A.CUTE), 2, [(A.WATER, 4), (A.GRASS, 2), (A.DARK, 1)]),
    'D25': ((A.FIRE, A.DARK), 3, [(A.WATER, 6)]),
    'D26': ((A.GRASS, A.CUTE), 2, [(A.WATER, 5)]),
    'D29': ((A.WATER, A.CUTE), 5, [(A.CUTE, 3), (A.WATER, 7)]),
}


def _card(card_id: str, level: int, attributes: tuple[A, ...], score: int, *cost: tuple[A, int]) -> PetCard:
    return PetCard(card_id, level, attributes, normalize_cost(cost), score)


def all_cards() -> list[PetCard]:
    cards: list[PetCard] = []

    level_one = [
        ("S01", A.WATER, 0, [(A.FIRE, 2), (A.GRASS, 2)]), ("S02", A.WATER, 0, [(A.FIRE, 2), (A.CUTE, 2)]),
        ("S03", A.WATER, 0, [(A.WATER, 2), (A.DARK, 2)]), ("S04", A.WATER, 1, [(A.FIRE, 1), (A.GRASS, 1), (A.CUTE, 2)]),
        ("S05", A.WATER, 0, [(A.FIRE, 1), (A.DARK, 1), (A.GRASS, 2)]), ("S06", A.FIRE, 0, [(A.WATER, 2), (A.GRASS, 2)]),
        ("S07", A.FIRE, 0, [(A.WATER, 2), (A.DARK, 2)]), ("S08", A.FIRE, 0, [(A.GRASS, 2), (A.CUTE, 2)]),
        ("S09", A.FIRE, 1, [(A.WATER, 1), (A.GRASS, 1), (A.DARK, 2)]), ("S10", A.FIRE, 0, [(A.WATER, 1), (A.CUTE, 1), (A.GRASS, 2)]),
        ("S11", A.GRASS, 0, [(A.WATER, 2), (A.FIRE, 2)]), ("S12", A.GRASS, 0, [(A.GRASS, 2), (A.CUTE, 2)]),
        ("S13", A.GRASS, 0, [(A.FIRE, 2), (A.DARK, 2)]), ("S14", A.GRASS, 1, [(A.WATER, 1), (A.FIRE, 1), (A.CUTE, 2)]),
        ("S15", A.GRASS, 0, [(A.FIRE, 1), (A.DARK, 1), (A.WATER, 2)]), ("S16", A.CUTE, 0, [(A.FIRE, 2), (A.GRASS, 2)]),
        ("S17", A.CUTE, 0, [(A.FIRE, 2), (A.WATER, 2)]), ("S18", A.CUTE, 0, [(A.CUTE, 2), (A.DARK, 2)]),
        ("S19", A.CUTE, 1, [(A.FIRE, 1), (A.GRASS, 1), (A.WATER, 2)]), ("S20", A.CUTE, 0, [(A.FIRE, 1), (A.DARK, 1), (A.GRASS, 2)]),
        ("S21", A.DARK, 0, [(A.WATER, 2), (A.FIRE, 2)]), ("S22", A.DARK, 0, [(A.WATER, 2), (A.CUTE, 2)]),
        ("S23", A.DARK, 0, [(A.FIRE, 2), (A.DARK, 2)]), ("S24", A.DARK, 1, [(A.WATER, 1), (A.FIRE, 1), (A.CUTE, 2)]),
        ("S25", A.DARK, 0, [(A.FIRE, 1), (A.GRASS, 1), (A.WATER, 2)]),
    ]
    for card_id, attribute, score, cost in level_one:
        cards.append(_card(card_id, 1, (attribute,), score, *cost))

    dual_one = [
        ("D01", (A.WATER, A.FIRE), 0, [(A.GRASS, 2), (A.CUTE, 2)]), ("D02", (A.WATER, A.FIRE), 0, [(A.GRASS, 1), (A.DARK, 1), (A.CUTE, 2)]),
        ("D03", (A.WATER, A.GRASS), 0, [(A.FIRE, 2), (A.DARK, 2)]), ("D04", (A.WATER, A.GRASS), 0, [(A.FIRE, 1), (A.CUTE, 1), (A.DARK, 2)]),
        ("D05", (A.WATER, A.GRASS), 1, [(A.FIRE, 2), (A.CUTE, 1), (A.DARK, 1)]), ("D06", (A.WATER, A.DARK), 0, [(A.FIRE, 2), (A.GRASS, 2)]),
        ("D07", (A.WATER, A.DARK), 1, [(A.FIRE, 1), (A.GRASS, 1), (A.CUTE, 2)]), ("D08", (A.FIRE, A.GRASS), 0, [(A.WATER, 2), (A.CUTE, 2)]),
        ("D09", (A.FIRE, A.GRASS), 0, [(A.WATER, 1), (A.DARK, 1), (A.CUTE, 2)]), ("D10", (A.FIRE, A.CUTE), 0, [(A.CUTE, 2), (A.DARK, 2)]),
        ("D11", (A.FIRE, A.CUTE), 0, [(A.GRASS, 1), (A.WATER, 1), (A.DARK, 2)]), ("D12", (A.FIRE, A.DARK), 0, [(A.WATER, 2), (A.CUTE, 2)]),
        ("D13", (A.FIRE, A.DARK), 1, [(A.WATER, 1), (A.GRASS, 1), (A.CUTE, 2)]), ("D14", (A.GRASS, A.CUTE), 0, [(A.FIRE, 2), (A.WATER, 2)]),
        ("D15", (A.GRASS, A.CUTE), 0, [(A.FIRE, 1), (A.WATER, 1), (A.DARK, 2)]),
    ]
    for card_id, attributes, score, cost in dual_one:
        cards.append(_card(card_id, 1, attributes, score, *cost))

    level_two = [
        ("S26", A.WATER, 1, [(A.FIRE, 3), (A.GRASS, 2)]), ("S27", A.WATER, 1, [(A.FIRE, 2), (A.CUTE, 2), (A.DARK, 1)]), ("S28", A.WATER, 2, [(A.GRASS, 3), (A.DARK, 2)]), ("S29", A.WATER, 2, [(A.FIRE, 2), (A.GRASS, 2), (A.CUTE, 2)]),
        ("S30", A.FIRE, 1, [(A.WATER, 3), (A.GRASS, 2)]), ("S31", A.FIRE, 1, [(A.WATER, 2), (A.DARK, 2), (A.CUTE, 1)]), ("S32", A.FIRE, 2, [(A.GRASS, 3), (A.CUTE, 2)]), ("S33", A.FIRE, 3, [(A.WATER, 2), (A.GRASS, 2), (A.DARK, 2)]),
        ("S34", A.GRASS, 1, [(A.WATER, 3), (A.FIRE, 2)]), ("S35", A.GRASS, 1, [(A.WATER, 2), (A.CUTE, 2), (A.DARK, 1)]), ("S36", A.GRASS, 2, [(A.FIRE, 3), (A.DARK, 2)]), ("S37", A.GRASS, 2, [(A.WATER, 2), (A.FIRE, 2), (A.CUTE, 2)]),
        ("S38", A.CUTE, 1, [(A.FIRE, 3), (A.GRASS, 2)]), ("S39", A.CUTE, 1, [(A.FIRE, 2), (A.WATER, 2), (A.DARK, 1)]), ("S40", A.CUTE, 2, [(A.GRASS, 3), (A.DARK, 2)]), ("S41", A.CUTE, 3, [(A.FIRE, 2), (A.GRASS, 2), (A.WATER, 2)]),
        ("S42", A.DARK, 1, [(A.WATER, 3), (A.FIRE, 2)]), ("S43", A.DARK, 2, [(A.WATER, 2), (A.CUTE, 2), (A.GRASS, 1)]), ("S44", A.DARK, 3, [(A.FIRE, 3), (A.GRASS, 2)]),
    ]
    for card_id, attribute, score, cost in level_two:
        cards.append(_card(card_id, 2, (attribute,), score, *cost))

    dual_two = [
        ("D16", (A.WATER, A.FIRE), 1, [(A.GRASS, 3), (A.CUTE, 2)]), ("D17", (A.WATER, A.FIRE), 2, [(A.GRASS, 2), (A.DARK, 2), (A.CUTE, 1)]),
        ("D18", (A.WATER, A.GRASS), 1, [(A.FIRE, 3), (A.DARK, 2)]), ("D19", (A.WATER, A.GRASS), 2, [(A.FIRE, 2), (A.CUTE, 2), (A.DARK, 1)]),
        ("D20", (A.WATER, A.DARK), 1, [(A.FIRE, 3), (A.GRASS, 2)]), ("D21", (A.FIRE, A.GRASS), 1, [(A.WATER, 3), (A.CUTE, 2)]),
        ("D22", (A.FIRE, A.GRASS), 2, [(A.WATER, 2), (A.DARK, 2), (A.CUTE, 1)]), ("D23", (A.FIRE, A.CUTE), 1, [(A.GRASS, 3), (A.DARK, 2)]),
        ("D24", (A.FIRE, A.CUTE), 2, [(A.GRASS, 2), (A.WATER, 2), (A.DARK, 1)]), ("D25", (A.FIRE, A.DARK), 2, [(A.WATER, 3), (A.GRASS, 2)]),
        ("D26", (A.GRASS, A.CUTE), 1, [(A.FIRE, 3), (A.WATER, 2)]),
    ]
    for card_id, attributes, score, cost in dual_two:
        cards.append(_card(card_id, 2, attributes, score, *cost))

    level_three = [
        ("S45", A.WATER, 5, [(A.WATER, 3), (A.FIRE, 7)]), ("S46", A.CUTE, 5, [(A.CUTE, 3), (A.DARK, 7)]), ("S47", A.FIRE, 5, [(A.FIRE, 3), (A.GRASS, 7)]), ("S48", A.GRASS, 5, [(A.GRASS, 3), (A.WATER, 7)]), ("S49", A.DARK, 5, [(A.DARK, 3), (A.FIRE, 7)]),
        ("S50", A.WATER, 4, [(A.FIRE, 7)]), ("S51", A.DARK, 4, [(A.GRASS, 7)]), ("S52", A.CUTE, 4, [(A.FIRE, 7)]),
        ("S53", A.WATER, 4, [(A.WATER, 6), (A.FIRE, 3), (A.GRASS, 3)]), ("S54", A.DARK, 4, [(A.DARK, 6), (A.FIRE, 3), (A.CUTE, 3)]), ("S55", A.FIRE, 4, [(A.FIRE, 6), (A.WATER, 3), (A.DARK, 3)]), ("S56", A.GRASS, 4, [(A.GRASS, 6), (A.WATER, 3), (A.CUTE, 3)]), ("S57", A.CUTE, 4, [(A.CUTE, 6), (A.FIRE, 3), (A.GRASS, 3)]),
        ("S58", A.DARK, 3, [(A.CUTE, 3), (A.FIRE, 3), (A.GRASS, 3), (A.DARK, 5)]), ("S59", A.CUTE, 3, [(A.FIRE, 3), (A.DARK, 3), (A.GRASS, 3), (A.CUTE, 5)]), ("S60", A.GRASS, 3, [(A.CUTE, 3), (A.WATER, 3), (A.FIRE, 3), (A.GRASS, 5)]),
    ]
    for card_id, attribute, score, cost in level_three:
        cards.append(_card(card_id, 3, (attribute,), score, *cost))

    dual_three = [
        ("D27", (A.WATER, A.DARK), 4, [(A.GRASS, 6), (A.CUTE, 3), (A.DARK, 3)]),
        ("D28", (A.FIRE, A.CUTE), 4, [(A.WATER, 6), (A.CUTE, 3), (A.DARK, 3)]),
        ("D29", (A.GRASS, A.CUTE), 5, [(A.CUTE, 3), (A.WATER, 7)]),
        ("D30", (A.FIRE, A.DARK), 5, [(A.DARK, 3), (A.GRASS, 7)]),
    ]
    for card_id, attributes, score, cost in dual_three:
        cards.append(_card(card_id, 3, attributes, score, *cost))
    for card in cards:
        card.name = CARD_NAMES[card.card_id]
        if correction := CARD_DATA_CORRECTIONS.get(card.card_id):
            card.attributes, card.score, cost = correction
            card.cost = normalize_cost(cost)
    return cards


def build_decks(seed: int | None = None) -> dict[int, list[PetCard]]:
    randomizer = random.Random(seed)
    decks = {level: [card for card in all_cards() if card.level == level] for level in (1, 2, 3)}
    for deck in decks.values():
        randomizer.shuffle(deck)
    return decks
