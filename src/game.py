from __future__ import annotations

from dataclasses import dataclass

from .models import Attribute, GameState, PetCard, Player
from .rules import RuleError, buy_card, refill_market, reserve_card, take_different, take_same
from .specializations import detect_specializations, resolve_specialization
from .wizards import award_eligible_wizard_cards

VICTORY_SCORE = 18


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
        if self.state.pending_specializations:
            if action.kind != "specialization":
                raise RuleError("必须先结算当前属性专精效果")
            effect = self.state.pending_specializations[0]
            message = resolve_specialization(
                self.state,
                effect,
                card=action.card,
                target_player=action.target_player,
            )
            messages = [message]
            self.state.pending_specializations.pop(0)
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
                f"{player.name} 触发 {effect.attribute.value}系专精阶段{effect.stage}"
                for effect in effects
            )
        if not self.state.pending_specializations:
            messages.extend(self._finish_turn())
        return messages

    def _finish_turn(self) -> list[str]:
        player = self.state.current()
        acquired_wizards = award_eligible_wizard_cards(player, self.state.wizard_market)
        messages = [f"获得魔法师卡【{wizard.name}】（+{wizard.score}分）" for wizard in acquired_wizards]
        for wizard in acquired_wizards:
            self.state.wizard_market.remove(wizard)
            if self.state.wizard_deck:
                self.state.wizard_market.append(self.state.wizard_deck.pop(0))
        market_exhausted = not any(self.state.market.cards[level] for level in (1, 2, 3))
        if any(player.score >= VICTORY_SCORE for player in self.state.players):
            self.state.end_triggered = True
            self.state.finished = True
            return messages
        if market_exhausted:
            self.state.end_triggered = True
        self.state.next_player()
        if self.state.end_triggered and self.state.current_player == 0:
            self.state.finished = True
        if not self.state.finished:
            refill_market(self.state)
        return messages

    def winners(self) -> list[Player]:
        highest = max(player.score for player in self.state.players)
        return [player for player in self.state.players if player.score == highest]
