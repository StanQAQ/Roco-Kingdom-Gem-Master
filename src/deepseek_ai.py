"""可选的 DeepSeek 对手；不改变本地 AI 的决策实现。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai import choose_action
from .game import Action, Game, VICTORY_SCORE
from .models import ATTRIBUTES, Attribute, PetCard, Player, WizardCard
from .rules import RuleError, payment_for
from .specializations import legal_card_targets, legal_player_targets, single_attribute_count


API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
LOCAL_CONFIG_NAME = ".env.deepseek"
MAX_API_RETRIES = 2  # 首次请求失败后最多重试两次
RETRY_BASE_DELAY = 0.5  # 重试间隔基数，后续按次数递增


class DeepSeekAPIError(ValueError):
    """接口返回错误或不符合预期的响应结构。"""


def _short_error_text(value: object, limit: int = 240) -> str:
    text = " ".join(str(value).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _response_error(response: object) -> str | None:
    if not isinstance(response, dict):
        return f"接口响应应为 JSON 对象，实际为 {type(response).__name__}"
    error = response.get("error")
    if error is not None:
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            message = error.get("message") or "未提供错误说明"
            prefix = f"{code}: " if code else ""
            return "接口返回错误：" + _short_error_text(prefix + str(message))
        return "接口返回错误：" + _short_error_text(error)
    return None


def _describe_request_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        detail = ""
        try:
            body = json.loads(error.read(4096).decode("utf-8", errors="replace"))
            detail = _response_error(body) or ""
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        status = f"HTTP {error.code} {error.reason}"
        return f"{status}；{detail}" if detail else status
    if isinstance(error, URLError):
        reason = error.reason
        if isinstance(reason, (TimeoutError,)):
            return "网络连接超时"
        return "网络连接失败：" + _short_error_text(reason)
    if isinstance(error, TimeoutError):
        return "请求超时"
    if isinstance(error, DeepSeekAPIError):
        return str(error)
    if isinstance(error, json.JSONDecodeError):
        return "接口返回内容不是有效 JSON"
    return _short_error_text(f"{type(error).__name__}: {error}")


def _is_retryable_error(error: Exception) -> bool:
    """网络波动、限流和服务端异常可重试；明确的客户端 HTTP 错误不重试。"""
    if isinstance(error, HTTPError):
        return error.code in {408, 409, 425, 429} or error.code >= 500
    if isinstance(error, (URLError, TimeoutError, OSError)):
        return True
    if isinstance(error, DeepSeekAPIError):
        message = str(error).lower()
        permanent_markers = (
            "invalid_api_key", "authentication", "model_not_found", "invalid_request",
            "insufficient_balance", "invalid parameter", "invalid_params",
        )
        return not any(marker in message for marker in permanent_markers)
    # 模型偶尔返回格式错误或无效行动编号时，再请求一次让它重新按格式作答。
    return isinstance(error, (ValueError, KeyError, IndexError, TypeError))


def _local_config_values() -> dict[str, str]:
    """读取工作区或可执行文件旁的本地配置，不将密钥打包进程序。"""
    candidates = [Path(__file__).resolve().parents[1] / LOCAL_CONFIG_NAME]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / LOCAL_CONFIG_NAME)
    candidates.append(Path.cwd() / LOCAL_CONFIG_NAME)
    values: dict[str, str] = {}
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#") or "=" not in entry:
                    continue
                name, value = entry.split("=", 1)
                name = name.strip()
                value = value.strip().strip("\"'")
                if name in {"DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"} and value:
                    values.setdefault(name, value)
        except OSError:
            continue
    return values


def configured_api_key() -> str:
    """环境变量优先，其次使用本地 .env.deepseek 文件。"""
    return os.getenv("DEEPSEEK_API_KEY", "").strip() or _local_config_values().get("DEEPSEEK_API_KEY", "")


def configured_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "").strip() or _local_config_values().get(
        "DEEPSEEK_MODEL", DEFAULT_MODEL
    )


@dataclass(frozen=True)
class DeepSeekDecision:
    action: Action
    used_api: bool
    notice: str = ""


def _card_data(card: PetCard) -> dict:
    return {
        "name": card.display_name,
        "level": card.level,
        "attributes": [attribute.value for attribute in card.attributes],
        "score": card.effective_score,
        "cost": {attribute.value: amount for attribute, amount in card.cost.items()},
    }


def _wizard_data(wizard: WizardCard) -> dict:
    return {
        "name": wizard.name,
        "score": wizard.score,
        "requirements": {attribute.value: amount for attribute, amount in wizard.requirements},
    }


def _wizard_attribute_counts(player: Player) -> dict[str, int]:
    counts = Counter(
        attribute.value
        for card, _chosen_attribute in player.purchased
        for attribute in card.attributes
    )
    return {attribute.value: counts[attribute.value] for attribute in ATTRIBUTES}


def _dual_choices(player: Player):
    cards = player.dual_cards()
    return product(*(card.attributes for card in cards)) if cards else [()]


def _best_payment(player: Player, card: PetCard):
    """为每张可买卡挑一个合法折扣方案，避免指数级方案进入提示词。"""
    best = None
    for choices in _dual_choices(player):
        try:
            payment = payment_for(player, card, list(choices))
        except RuleError:
            continue
        rank = (payment.light + payment.temporary_light, sum(payment.normal.values()))
        if best is None or rank < best[0]:
            best = (rank, choices, payment)
    return None if best is None else (best[1], best[2])


def legal_options(game: Game) -> list[tuple[Action, dict]]:
    """只暴露当前真正可执行的动作，不让模型自行构造游戏命令。"""
    state = game.state
    player = state.current()
    options: list[tuple[Action, dict]] = []
    if state.pending_specializations:
        effect = state.pending_specializations[0]
        for card in legal_card_targets(state, effect):
            options.append((Action("specialization", card=card), {
                "action": "结算专精并选择卡牌", "card": _card_data(card),
            }))
        for index in legal_player_targets(state, effect):
            target = state.players[index]
            options.append((Action("specialization", target_player=index), {
                "action": "结算专精并选择玩家", "player": target.name,
                "score": target.score, "cards": len(target.purchased),
                "immune": target.next_attack_immune,
            }))
        return options or [(Action("specialization"), {"action": "结算自动专精效果"})]

    available = [attribute for attribute in ATTRIBUTES if state.resource_pool[attribute] > 0]
    if player.resource_count <= player.resource_capacity - 3:
        for attributes in combinations(available, 3):
            options.append((Action("different", attributes=attributes), {
                "action": "领取三种灵碎", "attributes": [item.value for item in attributes],
            }))
    if player.resource_count <= player.resource_capacity - 2:
        for attribute in available:
            if state.resource_pool[attribute] >= 4:
                options.append((Action("same", attributes=(attribute,)), {
                    "action": "领取两枚同属性灵碎", "attribute": attribute.value,
                }))
    market = [card for level in (1, 2, 3) for card in state.market.cards[level]]
    reserved_ids = {card.card_id for card in player.reserved}
    for card in market + player.reserved:
        plan = _best_payment(player, card)
        if plan is None:
            continue
        choices, payment = plan
        score_gain = card.effective_score * (2 if player.next_purchase_score_doubled else 1)
        options.append((Action("buy", card=card, dual_choices=choices), {
            "action": "购买宠物", "card": _card_data(card),
            "from_reserved": card.card_id in reserved_ids,
            "payment": {attribute.value: amount for attribute, amount in payment.normal.items() if amount},
            "sage_payment": payment.light + payment.temporary_light,
            "regular_sage_payment": payment.light,
            "temporary_sage_payment": payment.temporary_light,
            "dual_discount_choices": [attribute.value for attribute in choices],
            "immediate_score_gain": score_gain,
            "remaining_resources": {
                attribute.value: player.resources[attribute] - payment.normal.get(attribute, 0)
                for attribute in ATTRIBUTES
            },
            "remaining_sage": player.light - payment.light,
            "remaining_temporary_sage": player.temporary_light - payment.temporary_light,
        }))
    if state.light_pool > 0 and player.resource_count < player.resource_capacity and len(player.reserved) < 3:
        for card in market:
            options.append((Action("reserve", card=card), {
                "action": "预购宠物并获得一枚贤者碎晶", "card": _card_data(card),
            }))
    return options or [(Action("pass"), {"action": "跳过；当前没有其他合法行动"})]


def turn_prompt(game: Game, options: list[tuple[Action, dict]]) -> str:
    """只发送可见局面；不发送随机种子、未来牌序或对手预购卡身份。"""
    state = game.state
    actor = state.current()
    players = []
    for index, player in enumerate(state.players):
        wizard_cards = [_wizard_data(wizard) for wizard in player.wizard_cards]
        players.append({
            "seat": index,
            "name": player.name,
            "score": player.score,
            "resources": {attribute.value: player.resources[attribute] for attribute in ATTRIBUTES},
            "sage": player.light,
            "temporary_sage": player.temporary_light,
            "resource_count": player.resource_count,
            "resource_capacity": player.resource_capacity,
            "permanent_discounts": {
                attribute.value: player.permanent_discounts[attribute] for attribute in ATTRIBUTES
            },
            "single_attribute_pet_counts": {
                attribute.value: single_attribute_count(player, attribute) for attribute in ATTRIBUTES
            },
            "wizard_attribute_counts": _wizard_attribute_counts(player),
            "dual_attribute_pet_count": len(player.dual_cards()),
            "purchased": [_card_data(card) for card, _ in player.purchased],
            "reserved": [_card_data(card) for card in player.reserved] if index == state.current_player else len(player.reserved),
            "wizard_cards": wizard_cards,
            "next_purchase_free": player.next_purchase_free,
            "next_purchase_score_doubled": player.next_purchase_score_doubled,
            "attack_immune": player.next_attack_immune,
        })
    data = {
        "round": state.round_number,
        "current_player_index": state.current_player,
        "current_player": actor.name,
        "victory_score": VICTORY_SCORE,
        "final_scoring": "只在整轮结束时结算；轮末仍达到20分的玩家中最高分者获胜，并列共同获胜。若无人达到20分且市场未耗尽则继续游戏；市场耗尽时结束对局但无人达标则无人获胜",
        "end_triggered": state.end_triggered,
        "market_empty": not any(state.market.cards[level] for level in (1, 2, 3)),
        "resource_pool": {attribute.value: state.resource_pool[attribute] for attribute in ATTRIBUTES},
        "sage_pool": state.light_pool,
        "players": players,
        "market": [_card_data(card) for level in (1, 2, 3) for card in state.market.cards[level]],
        "visible_wizards": [_wizard_data(card) for card in state.wizard_market if card is not None],
        "pending_specialization": (
            {"attribute": state.pending_specializations[0].attribute.value,
             "stage": state.pending_specializations[0].stage,
             "occurrence": state.pending_specializations[0].occurrence}
            if state.pending_specializations else None
        ),
        "pending_specialization_queue": [
            {
                "player_index": effect.player_index,
                "player": state.players[effect.player_index].name,
                "attribute": effect.attribute.value,
                "stage": effect.stage,
                "occurrence": effect.occurrence,
            }
            for effect in state.pending_specializations
        ],
        "legal_actions": [{"id": f"A{index}", **description} for index, (_, description) in enumerate(options)],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _post_chat(api_key: str, payload: dict, timeout: float) -> dict:
    request = Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read(200_000).decode("utf-8"))


class DeepSeekOpponent:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        timeout: float = 20.0,
        request_json: Callable[[str, dict, float], dict] = _post_chat,
        max_retries: int = MAX_API_RETRIES,
        retry_base_delay: float = RETRY_BASE_DELAY,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else configured_api_key()
        self.model = model or configured_model()
        self.timeout = timeout
        self.request_json = request_json
        self.max_retries = max(0, max_retries)
        self.retry_base_delay = max(0.0, retry_base_delay)
        self.sleep = sleep
        self.disabled_reason = ""

    def decide(self, game: Game, *, fallback_difficulty: str = "hard") -> DeepSeekDecision:
        if self.disabled_reason:
            return DeepSeekDecision(choose_action(game, difficulty=fallback_difficulty), False)
        options = legal_options(game)
        if len(options) == 1:
            return DeepSeekDecision(options[0][0], False)
        if not self.api_key:
            self.disabled_reason = "未设置 DEEPSEEK_API_KEY"
            return DeepSeekDecision(choose_action(game, difficulty=fallback_difficulty), False, self.disabled_reason)
        payload = {
            "model": self.model,
            "thinking": {"type": "disabled"},
            "max_tokens": 128,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "你是《洛克王国：魔法宝石》的对战玩家。首要目标是赢得整局，而不是只追求本轮分数："
                    "未触发终局时兼顾分数、资源效率、永久折扣、魔法师卡进度和专精收益；终局已触发时，"
                    "优先确保本轮结束时自己的分数高于所有对手。每次只从 legal_actions 中选择一个行动编号，"
                    "不可自造行动。资源上限为10；领取资源可拿三种不同属性各1枚，或在公共该属性至少有4枚时拿同属性2枚。"
                    "贤者碎晶可补足任意属性的支付缺口。预购消耗一次行动、保留一张市场卡并获得1枚贤者碎晶，"
                    "每人最多预购3张，之后仍需行动购买；只有自己的预购卡身份会在局面中给出。"
                    "单属性宠物提供对应属性永久折扣；双属性宠物的两个属性都计入魔法师条件，但不计入单属性专精，"
                    "且每次购买时，已拥有的每张双属性宠物都要从其两个属性中选择一个折扣属性。"
                    "单属性卡专精门槛为：阶段一第2/5/8…张，阶段二第3/6/9…张。效果如下："
                    "水一选择市场卡，将其当前最高的一项成本减1（并列时具体属性随机）；水二下一次购买免费。"
                    "火一由游戏随机选择对手及其可引燃卡，攻击可能被免疫；火二下一张购买宠物的分数翻倍。"
                    "草一选择市场卡使其分数加1；草二获得临时贤者碎晶，数量等于全部玩家单属性草卡总数。购买时优先消耗临时贤者碎晶，临时碎晶不进入公共池。"
                    "萌一获得一次免疫其他玩家攻击；萌二对每位未免疫的对手，优先在未萌化的3级已购卡中随机选一张；没有可选3级卡时，才在未萌化的2级卡中随机选一张。1级卡不能萌化；正分卡分数归零并标记为已萌化，原本0分的卡不变且不标记；两级都没有可选卡时跳过。"
                    "恶一选择有普通属性灵碎的对手，随机偷1枚；恶二选择有已购卡的对手，随机夺取其一张卡及对应分数。"
                    "攻击可能被对手的一次性免疫挡下。购买触发专精时要先结算专精；回合结束后最多获得一张符合条件的"
                    "公开魔法师卡（每局随机5张，每张3分），获得后原位留空，本局不再补充。所有1级宠物基础分数为0，专精仍可改变分数。胜负只在整轮结束时结算：轮末仍有至少20分的玩家才有获胜资格，资格玩家中最高分者获胜，并列共同获胜。若无人达标且市场未耗尽则继续游戏；市场耗尽时轮末结束对局，若仍无人达标则无人获胜。只依据提供的局面和行动，不猜测隐藏牌。"
                    "只输出 JSON，例如 {\"action_id\":\"A0\"}，不要附加说明。"
                )},
                {"role": "user", "content": turn_prompt(game, options)},
            ],
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = self.request_json(self.api_key, payload, self.timeout)
                response_error = _response_error(response)
                if response_error:
                    raise DeepSeekAPIError(response_error)
                choices = response.get("choices")
                if not isinstance(choices, list) or not choices:
                    fields = ", ".join(sorted(str(key) for key in response)) or "无"
                    raise DeepSeekAPIError(f"响应缺少有效 choices 字段（收到字段：{fields}）")
                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    raise DeepSeekAPIError("choices[0] 不是 JSON 对象")
                message = first_choice.get("message")
                if not isinstance(message, dict):
                    raise DeepSeekAPIError("响应缺少 choices[0].message 对象")
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    finish_reason = first_choice.get("finish_reason")
                    suffix = f"（finish_reason={finish_reason}）" if finish_reason else ""
                    raise DeepSeekAPIError("响应没有可解析的 message.content" + suffix)
                try:
                    result = json.loads(content)
                except json.JSONDecodeError as error:
                    raise DeepSeekAPIError("模型返回内容不是有效 JSON") from error
                if not isinstance(result, dict):
                    raise DeepSeekAPIError("模型返回的 JSON 顶层不是对象")
                chosen = result.get("action_id")
                if not isinstance(chosen, str) or not chosen.startswith("A") or not chosen[1:].isdigit():
                    raise ValueError("响应缺少有效行动编号")
                index = int(chosen[1:])
                if index >= len(options) or chosen != f"A{index}":
                    raise ValueError("响应选择了列表外的行动")
                return DeepSeekDecision(options[index][0], True)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
                if _is_retryable_error(error) and attempt < self.max_retries:
                    self.sleep(self.retry_base_delay * (2 ** attempt))
                    continue
                # 暂时性故障耗尽重试后只接管当前回合；下一回合仍可重新请求。
                # 密钥、模型等明确配置错误则停止本局后续请求，避免每回合重复报错。
                detail = _describe_request_error(error)
                prefix = "DeepSeek 接口不可用：" + detail
                if not _is_retryable_error(error):
                    self.disabled_reason = prefix
                retry_note = "（已重试并耗尽次数）" if attempt > 0 else ""
                notice = f"{prefix}{retry_note}；本回合由本地 AI 接管"
                return DeepSeekDecision(
                    choose_action(game, difficulty=fallback_difficulty), False, notice,
                )
        raise AssertionError("unreachable")
