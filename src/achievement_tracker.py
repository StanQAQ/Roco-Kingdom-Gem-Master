"""单局成就进度追踪与玩家档案解锁保存。"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .achievement_definitions import ACHIEVEMENTS, ACHIEVEMENT_BY_ID
from .achievement_events import GameEvent
from .models import Attribute, GameState
from .profile import PlayerProfile, ProfileError, ProfileStore


def sync_profile_achievements(profile: PlayerProfile, store: ProfileStore) -> str | None:
    """为旧档案补齐未完成成就 ID，并移除已完成项。"""
    completed = list(dict.fromkeys(item for item in profile.completed if isinstance(item, str)))
    incomplete = [item.achievement_id for item in ACHIEVEMENTS if item.achievement_id not in completed]
    if profile.completed == completed and profile.incomplete == incomplete:
        return None
    profile.completed = completed
    profile.incomplete = incomplete
    try:
        store.save(profile)
    except ProfileError as error:
        return str(error)
    return None


class AchievementTracker:
    """为本局已登录玩家追踪规则事件；所有计数只属于当前对局。"""

    def __init__(self, profile: PlayerProfile, store: ProfileStore, difficulty: str) -> None:
        self.profile = profile
        self.store = store
        self.difficulty = difficulty
        self.dual_purchases = 0
        self.attribute_purchases: Counter[str] = Counter()
        self.wizard_awards = 0
        self.stage_attributes = {1: set(), 2: set()}
        self.blocked_attacks = 0
        self.successful_hits = 0
        self.pending_save: set[str] = set()

    def consume(self, events: Iterable[GameEvent], state: GameState) -> tuple[list[str], str | None]:
        unlocked: list[str] = []
        for event in events:
            actor = event.actor_index
            target = event.target_index
            data = event.data
            kind = event.event_type

            if kind == "card_purchased" and actor == 0:
                attributes = tuple(data.get("attributes", ()))
                if data.get("is_dual"):
                    self.dual_purchases += 1
                    if "first_dual_purchase" not in self.profile.completed:
                        self._unlock("first_dual_purchase", unlocked)
                    if self.dual_purchases >= 5:
                        self._unlock("five_dual_purchases", unlocked)
                elif len(attributes) == 1:
                    attribute = attributes[0]
                    self.attribute_purchases[attribute] += 1
                    if self.attribute_purchases[attribute] >= 5:
                        self._unlock(f"badge_{self._attribute_key(attribute)}", unlocked)
                if data.get("sage_paid", 0) >= 3:
                    self._unlock("pay_three_sage_shards", unlocked)
                if data.get("free_used") and data.get("effective_score_after", 0) == 5:
                    self._unlock("free_five_point_card", unlocked)
                if data.get("doubled_used") and data.get("effective_score_after", 0) == 10:
                    self._unlock("doubled_ten_point_card", unlocked)

            elif kind == "card_reserved" and actor == 0 and data.get("reserved_count", 0) >= 3:
                self._unlock("three_reserved_cards", unlocked)

            elif kind == "wizard_awarded" and actor == 0:
                self.wizard_awards += 1
                if self.wizard_awards >= 3:
                    self._unlock("three_wizard_awards", unlocked)

            elif kind == "specialization_triggered" and actor == 0:
                stage = int(data.get("stage", 0))
                attribute = str(data.get("attribute", ""))
                if stage in self.stage_attributes:
                    self.stage_attributes[stage].add(attribute)
                    if len(self.stage_attributes[stage]) == len(Attribute):
                        self._unlock("all_stage_one" if stage == 1 else "all_stage_two", unlocked)

            elif kind == "card_stolen" and actor == 0:
                self._unlock("steal_any_card", unlocked)
                if data.get("effective_score", 0) == 5:
                    self._unlock("steal_five_point_card", unlocked)

            elif kind == "attack_blocked" and target == 0:
                self.blocked_attacks += 1
                if data.get("specialization") == "dark_stage_two":
                    self._unlock("block_demon_contract", unlocked)
                if self.blocked_attacks >= 2:
                    self._unlock("block_two_attacks", unlocked)

            elif kind == "attack_applied" and target == 0:
                self.successful_hits += 1
                if self.successful_hits >= 3:
                    self._unlock("hit_three_times", unlocked)

            elif kind == "cute_stage_two_result" and actor == 0:
                if data.get("opponents_count") == 3 and data.get("immune_count") == 3:
                    self._unlock("all_opponents_immune_to_cute", unlocked)
                if data.get("points_removed", 0) >= 10:
                    self._unlock("cute_drain_ten_points", unlocked)

            elif kind == "grass_absorbed" and actor == 0:
                gained = data.get("amount", 0)
                if gained == 10:
                    self._unlock("absorb_ten_sage_shards", unlocked)
                if gained == 3:
                    self._unlock("absorb_three_sage_shards", unlocked)

            elif kind == "card_modified" and actor == 0:
                if data.get("attribute") == "水" and data.get("already_marked"):
                    self._unlock("water_twice_same_card", unlocked)
                if data.get("attribute") == "草" and data.get("already_marked"):
                    self._unlock("grass_twice_same_card", unlocked)

            elif kind == "card_burned" and actor == 0 and data.get("effective_score", 0) == 1:
                self._unlock("burn_one_point_card", unlocked)

            elif kind == "resource_stolen" and actor == 0:
                if data.get("victim_attribute_total_before") == 1 and data.get("victim_attribute_total_after") == 0:
                    self._unlock("devour_last_resource", unlocked)

            elif kind == "match_finished":
                if 0 in data.get("winner_indices", ()):
                    player = state.players[0]
                    self._unlock("first_win", unlocked)
                    mode_id = "first_simple_win" if self.difficulty == "simple" else "first_hard_win"
                    self._unlock(mode_id, unlocked)
                    if player.score >= 25:
                        self._unlock("win_at_least_25", unlocked)
                    self._check_score_route(player, unlocked)

        save_error = self._save_unlocked() if unlocked or self.pending_save else None
        return [item for item in unlocked], save_error

    def _check_score_route(self, player, unlocked: list[str]) -> None:
        cards = [card for card, _chosen in player.purchased]
        wizard_score = sum(wizard.score for wizard in player.wizard_cards)
        pet_score = sum(card.effective_score for card in cards)
        scoring_cards = [card for card in cards if card.effective_score > 0]
        if scoring_cards and not player.wizard_cards and pet_score == player.score:
            attributes = {card.attributes[0].value for card in scoring_cards if len(card.attributes) == 1}
            all_scoring_cards_single = all(not card.is_dual for card in scoring_cards)
            if all_scoring_cards_single and len(attributes) == 1:
                self._unlock("win_one_attribute_score_only", unlocked)
        if wizard_score == player.score and player.score > 0:
            self._unlock("win_wizard_score_only", unlocked)
        if cards and all(card.is_dual for card in cards):
            self._unlock("win_dual_purchases_only", unlocked)

    @staticmethod
    def _attribute_key(value: str) -> str:
        return {"水": "water", "火": "fire", "草": "grass", "萌": "cute", "恶": "dark"}.get(value, value)

    def _unlock(self, achievement_id: str, unlocked: list[str]) -> None:
        if achievement_id not in ACHIEVEMENT_BY_ID:
            return
        if achievement_id in self.profile.completed:
            return
        self.profile.completed.append(achievement_id)
        self.profile.incomplete = [
            item for item in self.profile.incomplete if item != achievement_id
        ]
        self.pending_save.add(achievement_id)
        unlocked.append(achievement_id)

    def _save_unlocked(self) -> str | None:
        if not self.pending_save:
            return None
        try:
            self.store.save(self.profile)
        except ProfileError as error:
            return str(error)
        self.pending_save.clear()
        return None
