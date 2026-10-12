from __future__ import annotations

from dataclasses import dataclass

from .models import Attribute, GameState, PetCard, Player
from .rules import RuleError, buy_card, refill_market, reserve_card, take_different, take_same
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

    def execute(self, action: Action) -> list[str]:
        if self.state.finished:
            raise RuleError("对局已经结束")
        # CLI/模拟等非 Qt 调用也会在新回合第一次处理行动前补齐待补的魔法师牌位。
        self.begin_turn()
        if self.state.pending_specializations:
            if action.kind != "specialization":
                raise RuleError("必须先结算当前属性专精效果")
            effect = self.state.pending_specializations[0]
            owned_card_count = len(self.state.players[effect.player_index].purchased)
            message = resolve_specialization(
                self.state,
                effect,
                card=action.card,
                target_player=action.target_player,
            )
            messages = [message]
            self.state.pending_specializations.pop(0)
            if (
                effect.attribute == Attribute.DARK
                and effect.stage == 2
                and len(self.state.players[effect.player_index].purchased) > owned_card_count
            ):
                # 恶魔契约夺来的单属性宠物会改变当前专精计数；新触发效果
                # 紧接夺卡结算，先于其他排队效果处理，且仍属于本回合。
                newly_triggered = detect_specializations(self.state, effect.player_index)
                if newly_triggered:
                    del self.state.pending_specializations[-len(newly_triggered):]
                    self.state.pending_specializations[0:0] = newly_triggered
            if not self.state.pending_specializations:
                messages.extend(self._finish_turn())
            return messages
        if action.kind == "specialization":
            raise RuleError("当前没有待结算的属性专精")

        player = self.state.current()
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
        elif action.kind == "reserve":
            if action.card is None:
                raise ValueError("预购需要指定宠物")
            reserve_card(self.state, player, action.card)
        elif action.kind == "pass":
            pass
        else:
            raise ValueError(f"未知动作: {action.kind}")
        self.state.action_count += 1
        messages: list[str] = []
        if action.kind == "buy":
            effects = detect_specializations(self.state, self.state.current_player)
            messages.extend(
                f"{player.name} 触发 {effect.attribute.value}系专精阶段{('一' if effect.stage == 1 else '二')}"
                f"{f'（第{effect.occurrence}次）' if effect.occurrence > 1 else ''}"
                for effect in effects
            )
        if not self.state.pending_specializations:
            messages.extend(self._finish_turn())
        return messages

    def begin_turn(self) -> list:
        """在新回合开始时按原牌位补入魔法师卡，并返回补入的卡片。"""
        refilled = []
        for index, wizard in enumerate(self.state.wizard_market):
            if wizard is None and self.state.wizard_deck:
                replacement = self.state.wizard_deck.pop(0)
                self.state.wizard_market[index] = replacement
                refilled.append(replacement)
        return refilled

    def _finish_turn(self) -> list[str]:
        player = self.state.current()
        acquired_wizards = award_eligible_wizard_cards(player, self.state.wizard_market)
        messages = [f"获得魔法师卡【{wizard.name}】（+{wizard.score}分）" for wizard in acquired_wizards]
        for wizard in acquired_wizards:
            wizard_index = next(
                index for index, available in enumerate(self.state.wizard_market)
                if available is not None and available.card_id == wizard.card_id
            )
            # 领取后保留固定牌位为空；替补卡等下一回合开始时再补入。
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
        if not self.state.finished:
            refill_market(self.state)
        return messages

    def winners(self) -> list[Player]:
        eligible = [player for player in self.state.players if player.score >= VICTORY_SCORE]
        if not eligible:
            return []
        highest = max(player.score for player in eligible)
        return [player for player in eligible if player.score == highest]
