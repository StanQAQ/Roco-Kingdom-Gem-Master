"""成就目录：ID 是存档键，名称和要求以成就.docx 为准。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AchievementDefinition:
    achievement_id: str
    name: str
    requirement: str
    difficulty_score: int

    def __post_init__(self) -> None:
        if not 1 <= self.difficulty_score <= 10:
            raise ValueError("成就难度分必须介于 1 到 10")

    @property
    def rarity(self) -> str:
        """按达成难度估算分映射到三档稀有程度。"""
        if self.difficulty_score <= 3:
            return "见习"
        if self.difficulty_score <= 6:
            return "中级"
        return "高级"


ACHIEVEMENTS = (
    AchievementDefinition("first_dual_purchase", "你可以在右侧拖动它来切换折扣属性！", "购买第一张双属性卡", 1),
    AchievementDefinition("first_win", "菜鸟上路", "获得第一次胜利", 3),
    AchievementDefinition("first_simple_win", "一个轻松的拿下", "在标准模式-简单模式中获得第一次胜利", 3),
    AchievementDefinition("first_hard_win", "这也能赢？", "在标准模式-困难模式中获得第一次胜利", 5),
    AchievementDefinition("win_at_least_25", "欲求不满", "获得胜利时分数大于等于二十五分", 6),
    AchievementDefinition("three_wizard_awards", "亲传弟子", "一局内获得三次魔法师的认可", 7),
    AchievementDefinition("five_dual_purchases", "拖来拖去好爽啊", "一局内购买5张双属性卡", 6),
    AchievementDefinition("badge_water", "水系徽章", "一局内购买5张水系单属性卡", 6),
    AchievementDefinition("badge_fire", "火系徽章", "一局内购买5张火系单属性卡", 6),
    AchievementDefinition("badge_grass", "草系徽章", "一局内购买5张草系单属性卡", 6),
    AchievementDefinition("badge_cute", "萌系徽章", "一局内购买5张萌系单属性卡", 6),
    AchievementDefinition("badge_dark", "恶系徽章", "一局内购买5张恶系单属性卡", 6),
    AchievementDefinition("all_stage_one", "我全都要！", "一局内触发所有属性的专精阶段一", 9),
    AchievementDefinition("all_stage_two", "还想要？那就再来！", "一局内触发所有属性的专精阶段二", 10),
    AchievementDefinition("steal_any_card", "你的就是我的", "使用【恶魔契约】偷走一张卡牌", 5),
    AchievementDefinition("block_demon_contract", "我的还是我的", "使用【撒娇】抵挡一次【恶魔契约】", 9),
    AchievementDefinition("free_five_point_card", "零元购", "通过【泡沫幻影】购入一张效果结算后价值5分的卡牌", 6),
    AchievementDefinition("doubled_ten_point_card", "好事成双", "通过【阳火增辉】购入一张效果结算后价值10分的卡牌", 6),
    AchievementDefinition("all_opponents_immune_to_cute", "无法选中", "使用【甜心续航】时，其他三名玩家都因【撒娇】而免疫", 10),
    AchievementDefinition("cute_drain_ten_points", "啊啊啊啊啊啊啊你是一个宝宝", "使用【甜心续航】扣除对手分数之和大于等于10分", 9),
    AchievementDefinition("absorb_ten_sage_shards", "大草原", "使用【汲取】一次获得10片贤者碎晶", 10),
    AchievementDefinition("absorb_three_sage_shards", "你们都被恩佐捉走了吗", "使用【汲取】一次获得3片贤者碎晶", 4),
    AchievementDefinition("win_one_attribute_score_only", "老大我们这样买卡真的能赢吗", "仅通过某一属性的卡得分获得胜利", 8),
    # 保留旧存档 ID；现行条件改为单局获得五张魔法师卡，不要求获胜。
    AchievementDefinition("win_wizard_score_only", "做题区", "一局内获得五张魔法师卡", 10),
    AchievementDefinition("win_dual_purchases_only", "金色的麦田", "只购买双属性卡赢得胜利", 8),
    AchievementDefinition("steal_five_point_card", "这么会偷全给你偷走得了呗", "使用【恶魔契约】偷走一张效果结算后价值5分的卡牌", 7),
    AchievementDefinition("hit_three_times", "怎么倒霉的总是我", "一局内被造成有效攻击三次", 8),
    AchievementDefinition("block_two_attacks", "萌萌哒", "一局内使用【撒娇】抵挡2次攻击", 9),
    AchievementDefinition("three_reserved_cards", "超前消费", "预购区同时有三张卡牌", 2),
    AchievementDefinition("pay_three_sage_shards", "不好意思，刷信用卡", "购买一张卡牌时使用至少3片贤者碎晶", 3),
    AchievementDefinition("devour_last_resource", "底裤都不剩了", "使用【吞噬】使受害者的属性灵碎总数从1变成0", 6),
    AchievementDefinition("water_twice_same_card", "加强版手机排水音频", "对一张已经被【润泽】的卡牌再次使用【润泽】", 8),
    AchievementDefinition("grass_twice_same_card", "草。。", "对一张已经被【根吸收】的卡牌再次使用【根吸收】", 8),
    AchievementDefinition("burn_one_point_card", "燃起来了", "使用【引燃】烧掉一张效果结算后价值1分的卡牌", 5),
)

ACHIEVEMENT_BY_ID = {item.achievement_id: item for item in ACHIEVEMENTS}

# 估算分 1—3 为见习、4—6 为中级、7—10 为高级；同分沿用目录顺序。
# 估算依据为最少购买/操作次数、对手配合或随机结果的要求，以及获胜路线限制。
ACHIEVEMENT_RARITY_ORDER = {"见习": 0, "中级": 1, "高级": 2}
ACHIEVEMENTS_BY_DIFFICULTY = tuple(sorted(
    ACHIEVEMENTS,
    key=lambda item: (ACHIEVEMENT_RARITY_ORDER[item.rarity], item.difficulty_score),
))
