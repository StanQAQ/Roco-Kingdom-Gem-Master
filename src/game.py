from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .achievement_events import GameEvent
from .models import Attribute, GameState, PetCard, Player
from .rules import RuleError, buy_card, payment_for, refill_market, reserve_card, take_different, take_same
from .specializations import detect_specializations, resolve_specialization
from .wizards import award_eligible_wizard_cards

VICTORY_SCORE = 20


@dataclass(frozen=True)
class Action:
    kind: str
    card: PetCard | None = None
    attributes: tuple[Attribute, ...] = ()
    dual_choices: tuple[Attribute, ...] = ()
    target_player: int | None = None


class Game:
    def __init__(self, state: GameState):
        self.state = state
        self.match_id = uuid4().hex
        self._event_sequence = 0
        self.last_events: tuple[GameEvent, ...] = ()

    def _emit(self, event_type: str, *, actor_index=None, target_index=None,
              card_id=None, data: dict | None = None) -> None:
        self._event_sequence += 1
        self._current_events.append(GameEvent(
            self.match_id, self._event_sequence, self.state.action_count,
            event_type, actor_index, target_index, card_id, data or {},
        ))

    @staticmethod
    def _card_data(card: PetCard) -> dict:
        return {
            "card_id": card.card_id,
            "level": card.level,
            "attributes": tuple(attribute.value for attribute in card.attributes),
            "is_dual": card.is_dual,
            "effective_score": card.effective_score,
            "score": card.score,
            "cost": {attribute.value: amount for attribute, amount in card.cost.items()},
            "glows": tuple(attribute.value for attribute in card.specialization_glows),
        }

    def _snapshot(self) -> dict:
        return {
            "players": [
                {
                    "resources": {attribute.value: player.resources[attribute] for attribute in Attribute},
                    "attribute_total": sum(player.resources.values()),
                    "score": player.score,
                    "purchased": {card.card_id: self._card_data(card) for card, _ in player.purchased},
                    "reserved": {card.card_id: self._card_data(card) for card in player.reserved},
                    "immune": player.next_attack_immune,
                    "temporary_light": player.temporary_light,
                }
                for player in self.state.players
            ],
            "market": {
                card.card_id: self._card_data(card)
                for cards in self.state.market.cards.values() for card in cards
            },
        }

    def _record_specialization_events(self, effect, before: dict, selected_card_id: str | None) -> None:
        actor = effect.player_index
        attr = effect.attribute.value
        stage = effect.stage
        old_players = before["players"]

        if (attr, stage) in (("水", 1), ("草", 1)) and selected_card_id:
            old_card = before["market"].get(selected_card_id)
            new_card = next((card for cards in self.state.market.cards.values()
                             for card in cards if card.card_id == selected_card_id), None)
            if old_card and new_card:
                changed = (attr == "水" and
                           {attribute.value: amount for attribute, amount in new_card.cost.items()} != old_card["cost"]) or (
                               attr == "草" and new_card.score > old_card["score"]
                           )
                if changed:
                    self._emit("card_modified", actor_index=actor, card_id=selected_card_id,
                               data={"attribute": attr, "already_marked": attr in old_card["glows"]})
            return

        blocked_count = 0
        points_removed = 0
        for index, player in enumerate(self.state.players):
            if index == actor:
                continue
            old = old_players[index]
            if old["immune"] and not player.next_attack_immune:
                blocked_count += 1
                specialization = "dark_stage_two" if (attr, stage) == ("恶", 2) else "cute_stage_two" if (attr, stage) == ("萌", 2) else "dark_stage_one" if (attr, stage) == ("恶", 1) else "fire_stage_one"
                self._emit("attack_blocked", actor_index=actor, target_index=index,
                           data={"specialization": specialization})
                continue

            if (attr, stage) == ("火", 1):
                now_reserved = {card.card_id for card in player.reserved}
                now_purchased = {card.card_id for card, _ in player.purchased}
                removed = (set(old["reserved"]) - now_reserved) | (set(old["purchased"]) - now_purchased)
                for card_id in removed:
                    card_data = old["reserved"].get(card_id) or old["purchased"].get(card_id)
                    self._emit("card_burned", actor_index=actor, target_index=index, card_id=card_id,
                               data={"effective_score": card_data["effective_score"], "level": card_data["level"]})
                    self._emit("attack_applied", actor_index=actor, target_index=index, card_id=card_id,
                               data={"specialization": "fire_stage_one"})

            elif (attr, stage) == ("萌", 2):
                target_points_removed = 0
                for card, _ in player.purchased:
                    previous = old["purchased"].get(card.card_id)
                    if previous and card.effective_score < previous["effective_score"]:
                        points_removed += previous["effective_score"] - card.effective_score
                        target_points_removed += previous["effective_score"] - card.effective_score
                        self._emit("card_modified", actor_index=actor, target_index=index, card_id=card.card_id,
                                   data={"attribute": "萌", "effective_score_before": previous["effective_score"], "effective_score_after": card.effective_score})
                if target_points_removed:
                    self._emit("attack_applied", actor_index=actor, target_index=index,
                               data={"specialization": "cute_stage_two", "points_removed": target_points_removed})

            elif (attr, stage) == ("恶", 1):
                for resource in Attribute:
                    old_amount = old["resources"][resource.value]
                    if player.resources[resource] < old_amount:
                        gained = self.state.players[actor].resources[resource] - old_players[actor]["resources"][resource.value]
                        if gained > 0:
                            self._emit("resource_stolen", actor_index=actor, target_index=index,
                                       data={"attribute": resource.value, "victim_attribute_total_before": old["attribute_total"], "victim_attribute_total_after": sum(player.resources.values())})
                            self._emit("attack_applied", actor_index=actor, target_index=index,
                                       data={"specialization": "dark_stage_one"})
                        break

            elif (attr, stage) == ("恶", 2):
                actor_ids = {card.card_id for card, _ in self.state.players[actor].purchased}
                lost = set(old["purchased"]) - {card.card_id for card, _ in player.purchased}
                for card_id in lost & actor_ids:
                    card_data = old["purchased"][card_id]
                    self._emit("card_stolen", actor_index=actor, target_index=index, card_id=card_id,
                               data={"effective_score": card_data["effective_score"], "attributes": card_data["attributes"], "is_dual": card_data["is_dual"]})
                    self._emit("attack_applied", actor_index=actor, target_index=index, card_id=card_id,
                               data={"specialization": "dark_stage_two"})

        if (attr, stage) == ("萌", 2):
            self._emit("cute_stage_two_result", actor_index=actor,
                       data={"opponents_count": len(self.state.players) - 1, "immune_count": blocked_count, "points_removed": points_removed})
        elif (attr, stage) == ("草", 2):
            gained = self.state.players[actor].temporary_light - old_players[actor]["temporary_light"]
            self._emit("grass_absorbed", actor_index=actor, data={"amount": gained})

    def execute(self, action: Action) -> list[str]:
        self._current_events: list[GameEvent] = []
        self.last_events = ()
        if self.state.finished:
            raise RuleError("对局已经结束")
        # 保留回合准备接口；魔法师牌位在领取后永久留空。
        self.begin_turn()
        if self.state.pending_specializations:
            if action.kind != "specialization":
                raise RuleError("必须先结算当前属性专精效果")
            effect = self.state.pending_specializations[0]
            event_before = self._snapshot()
            selected_card_id = action.card.card_id if action.card is not None else None
            owned_card_count = len(self.state.players[effect.player_index].purchased)
            message = resolve_specialization(
                self.state,
                effect,
                card=action.card,
                target_player=action.target_player,
            )
            messages = [message]
            self._record_specialization_events(effect, event_before, selected_card_id)
            self._emit("specialization_resolved", actor_index=effect.player_index,
                       data={"attribute": effect.attribute.value, "stage": effect.stage,
                             "occurrence": effect.occurrence, "message": message})
            self.state.pending_specializations.pop(0)
            if (
                effect.attribute == Attribute.DARK
                and effect.stage == 2
                and len(self.state.players[effect.player_index].purchased) > owned_card_count
            ):
                # 恶魔契约夺来的单属性宠物会改变当前专精计数；新触发效果
                # 紧接夺卡结算，先于其他排队效果处理，且仍属于本回合。
                newly_triggered = detect_specializations(self.state, effect.player_index)
                for triggered in newly_triggered:
                    self._emit("specialization_triggered", actor_index=triggered.player_index,
                               data={"attribute": triggered.attribute.value, "stage": triggered.stage,
                                     "occurrence": triggered.occurrence})
                if newly_triggered:
                    del self.state.pending_specializations[-len(newly_triggered):]
                    self.state.pending_specializations[0:0] = newly_triggered
            if not self.state.pending_specializations:
                messages.extend(self._finish_turn())
            self.last_events = tuple(self._current_events)
            return messages
        if action.kind == "specialization":
            raise RuleError("当前没有待结算的属性专精")

        player = self.state.current()
        actor_index = self.state.current_player
        purchase_info = None
        reserved_event = None
        if action.kind == "buy" and action.card is not None:
            reserved = any(card.card_id == action.card.card_id for card in player.reserved)
            payment = payment_for(player, action.card, list(action.dual_choices))
            purchase_info = {
                "attributes": tuple(attribute.value for attribute in action.card.attributes),
                "is_dual": action.card.is_dual,
                "free_used": player.next_purchase_free,
                "doubled_used": player.next_purchase_score_doubled,
                "sage_paid": payment.light + payment.temporary_light,
                "source": "reserved" if reserved else "market",
            }
        if action.kind == "different":
            take_different(player, self.state, list(action.attributes))
        elif action.kind == "same":
            if len(action.attributes) != 1:
                raise ValueError("同属性领取需要一个属性")
            take_same(player, self.state, action.attributes[0])
        elif action.kind == "buy":
            if action.card is None:
                raise ValueError("购买需要指定宠物")
            buy_card(self.state, player, action.card, list(action.dual_choices))
            purchased = next(card for card, _chosen in player.purchased if card.card_id == action.card.card_id)
            purchase_info = {**purchase_info, "effective_score_after": purchased.effective_score}
        elif action.kind == "reserve":
            if action.card is None:
                raise ValueError("预购需要指定宠物")
            reserve_card(self.state, player, action.card)
            reserved_event = (action.card.card_id, len(player.reserved))
        elif action.kind == "pass":
            pass
        else:
            raise ValueError(f"未知动作: {action.kind}")
        self.state.action_count += 1
        if action.kind == "buy" and action.card is not None:
            self._emit("card_purchased", actor_index=actor_index, card_id=action.card.card_id,
                       data=purchase_info)
        elif reserved_event is not None:
            self._emit("card_reserved", actor_index=actor_index, card_id=reserved_event[0],
                       data={"reserved_count": reserved_event[1]})
        messages: list[str] = []
        if action.kind == "buy":
            effects = detect_specializations(self.state, self.state.current_player)
            for effect in effects:
                self._emit("specialization_triggered", actor_index=effect.player_index,
                           data={"attribute": effect.attribute.value, "stage": effect.stage,
                                 "occurrence": effect.occurrence})
            messages.extend(
                f"{player.name} 触发 {effect.attribute.value}系专精阶段{('一' if effect.stage == 1 else '二')}"
                f"{f'（第{effect.occurrence}次）' if effect.occurrence > 1 else ''}"
                for effect in effects
            )
        if not self.state.pending_specializations:
            messages.extend(self._finish_turn())
        self.last_events = tuple(self._current_events)
        return messages

    def begin_turn(self) -> list:
        """保留 GUI 与命令行的回合准备接口；本局魔法师卡不补充。"""
        return []

    def _finish_turn(self) -> list[str]:
        acting_index = self.state.current_player
        player = self.state.current()
        acquired_wizards = award_eligible_wizard_cards(player, self.state.wizard_market)
        messages = [f"获得魔法师卡【{wizard.name}】（+{wizard.score}分）" for wizard in acquired_wizards]
        for wizard in acquired_wizards:
            self._emit("wizard_awarded", actor_index=acting_index, card_id=wizard.card_id,
                       data={"wizard_id": wizard.card_id, "name": wizard.name, "score": wizard.score})
            wizard_index = next(
                index for index, available in enumerate(self.state.wizard_market)
                if available is not None and available.card_id == wizard.card_id
            )
            # 领取后永久保留空位，右侧卡片不移动，也不会补入新卡。
            self.state.wizard_market[wizard_index] = None
        market_exhausted = not any(self.state.market.cards[level] for level in (1, 2, 3))
        if any(player.score >= VICTORY_SCORE for player in self.state.players):
            self.state.end_triggered = True
        if market_exhausted:
            self.state.end_triggered = True
            self.state.market_exhausted_triggered = True
        self.state.next_player()
        # 只有整轮结束时才结算。达标玩家若在本轮后续行动中失去分数，
        # 不具备获胜资格；若市场也未耗尽，则清除终局标记并继续游戏。
        if self.state.end_triggered and self.state.current_player == 0:
            has_eligible_winner = any(player.score >= VICTORY_SCORE for player in self.state.players)
            self.state.finished = has_eligible_winner or self.state.market_exhausted_triggered
            if not self.state.finished:
                self.state.end_triggered = False
        if self.state.finished:
            winning_players = self.winners()
            self._emit("match_finished", data={
                "winner_indices": tuple(index for index, candidate in enumerate(self.state.players)
                                         if any(candidate is winner for winner in winning_players)),
                "scores": tuple(candidate.score for candidate in self.state.players),
                "round_number": self.state.round_number,
            })
        if not self.state.finished:
            refill_market(self.state)
        return messages

    def winners(self) -> list[Player]:
        eligible = [player for player in self.state.players if player.score >= VICTORY_SCORE]
        if not eligible:
            return []
        highest = max(player.score for player in eligible)
        return [player for player in eligible if player.score == highest]
