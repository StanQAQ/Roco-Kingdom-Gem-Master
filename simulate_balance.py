"""Run reproducible all-AI games and export resource/route balance statistics."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai import choose_action
from src.cards import build_decks
from src.game import Action, Game
from src.models import ATTRIBUTES, Attribute, Player, SpecializationEffect
from src.rules import create_state
from src.specializations import STAGE_NAMES, specialization_name


ATTR_NAMES = [attribute.value for attribute in ATTRIBUTES]
EFFECTS = [(attribute, stage) for attribute in ATTRIBUTES for stage in (1, 2)]
EFFECT_LABELS = {
    specialization_name(SpecializationEffect(0, attribute, stage)): (attribute, stage)
    for attribute, stage in EFFECTS
}


def empty_attribute_values(value=0):
    return {name: value for name in ATTR_NAMES}


def effect_label(attribute: Attribute, stage: int) -> str:
    return specialization_name(SpecializationEffect(0, attribute, stage))


def simulate_game(seed: int) -> dict:
    players = [Player(f"玩家{i + 1}") for i in range(4)]
    game = Game(create_state(players, build_decks(seed), seed))
    resource_flow = {
        name: {
            "public_drawn": 0,
            "purchase_paid": 0,
            "stolen_in": 0,
            "stolen_out": 0,
            "depletion_events": 0,
        }
        for name in ATTR_NAMES
    }
    player_flow = [
        {
            "acquired": empty_attribute_values(),
            "consumed": empty_attribute_values(),
            "capacity_hits": 0,
            "triggered": [],
            "used": [],
            "successful": [],
        }
        for _ in players
    ]
    light = Counter()
    action_count = 0
    consecutive_passes = 0
    guard = 0

    while not game.state.finished and consecutive_passes < len(players):
        guard += 1
        if guard > 5000:
            raise RuntimeError(f"seed {seed}: game exceeded 5000 actions")
        actor_index = game.state.current_player
        action = choose_action(game)
        pending_effect = game.state.pending_specializations[0] if action.kind == "specialization" else None
        actor_before_triggers = set(game.state.players[actor_index].specialization_triggered)
        previous_duals = game.state.players[actor_index].dual_cards() if action.kind == "buy" else []
        pools_before = dict(game.state.resource_pool)
        public_light_before = game.state.light_pool
        players_before = [
            {
                "resources": dict(player.resources),
                "light": player.light,
                "temporary_light": player.temporary_light,
                "resource_count": player.resource_count,
                "capacity": player.resource_capacity,
            }
            for player in game.state.players
        ]

        messages = game.execute(action)
        action_count += 1
        consecutive_passes = consecutive_passes + 1 if action.kind == "pass" else 0

        if action.kind == "buy":
            buyer = game.state.players[actor_index]
            for card, chosen in zip(previous_duals, action.dual_choices):
                if chosen in card.attributes:
                    for index, (owned, _old_choice) in enumerate(buyer.purchased):
                        if owned is card:
                            buyer.purchased[index] = (owned, chosen)
                            break
            if action.card is not None and action.card.is_dual:
                for index, (owned, _old_choice) in enumerate(buyer.purchased):
                    if owned is action.card:
                        buyer.purchased[index] = (owned, action.card.attributes[0])
                        break

            new_triggers = game.state.players[actor_index].specialization_triggered - actor_before_triggers
            for attribute, stage in new_triggers:
                player_flow[actor_index]["triggered"].append(effect_label(attribute, stage))

        if action.kind in {"different", "same"}:
            actor_after = game.state.players[actor_index]
            for attribute in ATTRIBUTES:
                gained = actor_after.resources[attribute] - players_before[actor_index]["resources"][attribute]
                if gained > 0:
                    name = attribute.value
                    resource_flow[name]["public_drawn"] += gained
                    player_flow[actor_index]["acquired"][name] += gained
                    if pools_before[attribute] > 0 and game.state.resource_pool[attribute] == 0:
                        resource_flow[name]["depletion_events"] += 1

        elif action.kind == "buy":
            buyer = game.state.players[actor_index]
            for attribute in ATTRIBUTES:
                spent = players_before[actor_index]["resources"][attribute] - buyer.resources[attribute]
                if spent > 0:
                    resource_flow[attribute.value]["purchase_paid"] += spent
                    player_flow[actor_index]["consumed"][attribute.value] += spent

        if pending_effect is not None:
            label = effect_label(pending_effect.attribute, pending_effect.stage)
            player_flow[actor_index]["used"].append(label)
            result = messages[0] if messages else ""
            if not any(fragment in result for fragment in ("效果失效", "没有可偷取", "没有可萌化的宠物")):
                player_flow[actor_index]["successful"].append(label)
            if pending_effect.attribute == Attribute.DARK and pending_effect.stage == 1:
                for index, player in enumerate(game.state.players):
                    for attribute in ATTRIBUTES:
                        delta = player.resources[attribute] - players_before[index]["resources"][attribute]
                        if delta > 0:
                            resource_flow[attribute.value]["stolen_in"] += delta
                            player_flow[index]["acquired"][attribute.value] += delta
                        elif delta < 0:
                            amount = -delta
                            resource_flow[attribute.value]["stolen_out"] += amount
                            player_flow[index]["consumed"][attribute.value] += amount

        if action.kind == "reserve":
            gained = max(0, game.state.players[actor_index].light - players_before[actor_index]["light"])
            light["public_gained"] += gained
        if pending_effect == SpecializationEffect(actor_index, Attribute.GRASS, 2):
            gained = max(0, game.state.players[actor_index].temporary_light - players_before[actor_index]["temporary_light"])
            light["temporary_gained"] += gained
        if action.kind == "buy":
            buyer = game.state.players[actor_index]
            light["public_used"] += max(0, players_before[actor_index]["light"] - buyer.light)
            light["temporary_used"] += max(0, players_before[actor_index]["temporary_light"] - buyer.temporary_light)

        for index, player in enumerate(game.state.players):
            previous = players_before[index]
            if previous["resource_count"] < previous["capacity"] and player.resource_count >= player.resource_capacity:
                player_flow[index]["capacity_hits"] += 1

    winners = game.winners()
    winner_ids = {id(player) for player in winners}
    winner_share = 1 / len(winners)
    player_records = []
    for index, player in enumerate(game.state.players):
        singles = Counter()
        duals = Counter()
        discounts = player.permanent_discounts
        for card, selected in player.purchased:
            if card.is_dual:
                for attribute in card.attributes:
                    duals[attribute.value] += 1
                assigned = selected if selected in card.attributes else card.attributes[0]
                discounts[assigned] += 1
            else:
                singles[card.attributes[0].value] += 1
        max_singles = max(singles.values(), default=0)
        route_attributes = [name for name in ATTR_NAMES if singles[name] == max_singles] if max_singles else []
        route = "/".join(route_attributes) if route_attributes else "未定"
        is_winner = id(player) in winner_ids
        player_records.append({
            "player_index": index,
            "player": player.name,
            "winner": is_winner,
            "win_share": winner_share if is_winner else 0,
            "score": player.score,
            "pet_count": len(player.purchased),
            "single_count": sum(singles.values()),
            "dual_count": sum(1 for card, _ in player.purchased if card.is_dual),
            "single_ratio": sum(singles.values()) / max(1, len(player.purchased)),
            "dual_ratio": sum(1 for card, _ in player.purchased if card.is_dual) / max(1, len(player.purchased)),
            "single_by_attribute": {name: singles[name] for name in ATTR_NAMES},
            "dual_attribute_appearances": {name: duals[name] for name in ATTR_NAMES},
            "discounts": {attribute.value: discounts[attribute] for attribute in ATTRIBUTES},
            "resources_remaining": {attribute.value: player.resources[attribute] for attribute in ATTRIBUTES},
            "acquired_by_attribute": player_flow[index]["acquired"],
            "consumed_by_attribute": player_flow[index]["consumed"],
            "light_remaining": player.light,
            "temporary_light_remaining": player.temporary_light,
            "capacity": player.resource_capacity,
            "capacity_hits": player_flow[index]["capacity_hits"],
            "primary_route": route,
            "primary_route_attributes": route_attributes,
            "primary_route_weights": {name: 1 / len(route_attributes) for name in route_attributes},
            "triggered_specializations": sorted(player_flow[index]["triggered"]),
            "used_specializations": sorted(player_flow[index]["used"]),
            "successful_specializations": sorted(player_flow[index]["successful"]),
        })

    resources = {}
    for attribute in ATTRIBUTES:
        name = attribute.value
        pool_final = game.state.resource_pool[attribute]
        player_remaining = sum(player.resources[attribute] for player in game.state.players)
        resources[name] = {
            **resource_flow[name],
            "player_acquired": resource_flow[name]["public_drawn"] + resource_flow[name]["stolen_in"],
            "player_consumed": resource_flow[name]["purchase_paid"] + resource_flow[name]["stolen_out"],
            "player_remaining": player_remaining,
            "public_pool_remaining": pool_final,
            "global_remaining": player_remaining + pool_final,
        }

    return {
        "seed": seed,
        "ending_round": max(1, game.state.round_number - 1),
        "end_reason": (
            "stalemate_after_full_round_of_passes"
            if not game.state.finished
            else "score_threshold" if any(player.score >= 18 for player in game.state.players)
            else "market_exhausted"
        ),
        "actions": action_count,
        "winners": [player.name for player in winners],
        "winning_score": max(player.score for player in game.state.players),
        "capacity_hits": sum(item["capacity_hits"] for item in player_flow),
        "resource_stats": resources,
        "light": {
            "public_gained": light["public_gained"],
            "temporary_gained": light["temporary_gained"],
            "public_used": light["public_used"],
            "temporary_used": light["temporary_used"],
            "public_pool_remaining": game.state.light_pool,
            "player_public_remaining": sum(player.light for player in game.state.players),
            "player_temporary_remaining": sum(player.temporary_light for player in game.state.players),
        },
        "players": player_records,
    }


class Aggregate:
    def __init__(self) -> None:
        self.games = 0
        self.actions = 0
        self.rounds = 0
        self.scores = 0
        self.capacity_hits = 0
        self.resource = {name: Counter() for name in ATTR_NAMES}
        self.light = Counter()
        self.attributes = {
            name: Counter({"route_weight": 0.0, "route_win_weight": 0.0, "route_score_weight": 0.0, "route_round_weight": 0.0})
            for name in ATTR_NAMES
        }
        self.routes = defaultdict(Counter)
        self.winning_routes = Counter()
        self.effects = {label: Counter() for label in EFFECT_LABELS}
        self.games_with_depletion = Counter()
        self.end_reasons = Counter()
        self.tied_games = 0

    def add(self, record: dict) -> None:
        self.games += 1
        self.end_reasons[record["end_reason"]] += 1
        self.actions += record["actions"]
        self.rounds += record["ending_round"]
        self.capacity_hits += record["capacity_hits"]
        if len(record["winners"]) > 1:
            self.tied_games += 1
        for key, value in record["light"].items():
            self.light[key] += value
        for name, flow in record["resource_stats"].items():
            for key, value in flow.items():
                self.resource[name][key] += value
            if flow["depletion_events"]:
                self.games_with_depletion[name] += 1

        for player in record["players"]:
            self.scores += player["score"]
            route_weights = player["primary_route_weights"]
            route_stats = self.routes[player["primary_route"]]
            route_stats["player_games"] += 1
            route_stats["score_total"] += player["score"]
            route_stats["round_total"] += record["ending_round"]
            route_stats["win_share"] += player["win_share"]
            for name, weight in route_weights.items():
                stats = self.attributes[name]
                stats["route_weight"] += weight
                stats["route_win_weight"] += player["win_share"] * weight
                stats["route_score_weight"] += player["score"] * weight
                stats["route_round_weight"] += record["ending_round"] * weight
            if player["win_share"]:
                self.winning_routes[player["primary_route"]] += player["win_share"]

            for name in ATTR_NAMES:
                stats = self.attributes[name]
                stats["single_purchases"] += player["single_by_attribute"][name]
                stats["dual_card_attribute_appearances"] += player["dual_attribute_appearances"][name]
                stats["final_discount_units"] += player["discounts"][name]
            triggered = set(player["triggered_specializations"])
            used = set(player["used_specializations"])
            successful = set(player["successful_specializations"])
            for label in EFFECT_LABELS:
                stats = self.effects[label]
                if label in triggered:
                    stats["triggered_player_games"] += 1
                if label in used:
                    stats["used_player_games"] += 1
                    stats["used_win_share"] += player["win_share"]
                    stats["used_score_total"] += player["score"]
                    if label in successful:
                        stats["successful_uses"] += 1
                else:
                    stats["unused_player_games"] += 1
                    stats["unused_win_share"] += player["win_share"]
                    stats["unused_score_total"] += player["score"]
        for player in record["players"]:
            for label in player["used_specializations"]:
                attr, _stage = EFFECT_LABELS[label]
                self.attributes[attr.value]["specialization_uses"] += 1
            for label in player["triggered_specializations"]:
                attr, _stage = EFFECT_LABELS[label]
                self.attributes[attr.value]["specialization_triggers"] += 1

    def as_dict(self, config: dict) -> dict:
        resource_summary = {}
        for name in ATTR_NAMES:
            values = self.resource[name]
            resource_summary[name] = {
                "public_drawn_total": values["public_drawn"],
                "purchase_paid_total": values["purchase_paid"],
                "stolen_in_total": values["stolen_in"],
                "stolen_out_total": values["stolen_out"],
                "player_acquired_total": values["player_acquired"],
                "player_consumed_total": values["player_consumed"],
                "public_net_withdrawal": values["public_drawn"] - values["purchase_paid"],
                "player_final_remaining_total": values["player_remaining"],
                "public_pool_final_remaining_total": values["public_pool_remaining"],
                "global_final_remaining_total": values["global_remaining"],
                "depletion_events": values["depletion_events"],
                "games_with_depletion": self.games_with_depletion[name],
                "average_public_drawn_per_game": values["public_drawn"] / max(1, self.games),
                "average_purchase_paid_per_game": values["purchase_paid"] / max(1, self.games),
                "average_public_pool_remaining": values["public_pool_remaining"] / max(1, self.games),
                "average_player_remaining": values["player_remaining"] / max(1, self.games),
            }

        total_player_games = self.games * 4
        route_by_attribute = {}
        for name in ATTR_NAMES:
            stats = self.attributes[name]
            weight = stats["route_weight"]
            route_by_attribute[name] = {
                "primary_route_share_percent": 100 * weight / max(1, total_player_games),
                "primary_route_weighted_player_games": weight,
                "route_win_rate_percent": 100 * stats["route_win_weight"] / max(1e-12, weight),
                "average_final_score_on_route": stats["route_score_weight"] / max(1e-12, weight),
                "average_ending_round_on_route": stats["route_round_weight"] / max(1e-12, weight),
                "single_attribute_purchases": stats["single_purchases"],
                "dual_card_attribute_appearances_nonexclusive": stats["dual_card_attribute_appearances"],
                "final_discount_units": stats["final_discount_units"],
                "specialization_triggers": stats["specialization_triggers"],
                "specialization_uses": stats["specialization_uses"],
            }

        exact_routes = {
            route: {
                "player_games": stats["player_games"],
                "win_share": stats["win_share"],
                "win_rate_percent": 100 * stats["win_share"] / max(1, stats["player_games"]),
                "average_final_score": stats["score_total"] / max(1, stats["player_games"]),
                "average_ending_round": stats["round_total"] / max(1, stats["player_games"]),
            }
            for route, stats in sorted(self.routes.items())
        }

        effect_impact = {}
        for label, stats in self.effects.items():
            used = stats["used_player_games"]
            unused = stats["unused_player_games"]
            used_rate = stats["used_win_share"] / max(1, used)
            unused_rate = stats["unused_win_share"] / max(1, unused)
            used_score = stats["used_score_total"] / max(1, used)
            unused_score = stats["unused_score_total"] / max(1, unused)
            effect_impact[label] = {
                "triggered_player_games": stats["triggered_player_games"],
                "used_player_games": used,
                "successful_uses": stats["successful_uses"],
                "win_rate_when_used_percent": 100 * used_rate,
                "win_rate_without_use_percent": 100 * unused_rate,
                "win_rate_difference_percentage_points": 100 * (used_rate - unused_rate),
                "average_score_when_used": used_score,
                "average_score_without_use": unused_score,
                "score_difference_when_used": used_score - unused_score,
                "interpretation": "相关性统计；专精使用并非随机分配，不能单独视为因果效果。",
            }

        rankable = [(name, data) for name, data in route_by_attribute.items() if self.attributes[name]["route_weight"] > 0]
        strongest = max(rankable, key=lambda item: (item[1]["route_win_rate_percent"], item[1]["average_final_score_on_route"]))[0] if rankable else None
        weakest = min(rankable, key=lambda item: (item[1]["route_win_rate_percent"], item[1]["average_final_score_on_route"]))[0] if rankable else None
        common_winning_route = max(self.winning_routes, key=self.winning_routes.get) if self.winning_routes else None

        return {
            "config": config,
            "overall": {
                "completed_games": self.games,
                "average_ending_round": self.rounds / max(1, self.games),
                "average_actions_per_game": self.actions / max(1, self.games),
                "average_final_score_per_player": self.scores / max(1, total_player_games),
                "resource_capacity_reach_events": self.capacity_hits,
                "average_capacity_reach_events_per_game": self.capacity_hits / max(1, self.games),
                "games_with_tied_winners": self.tied_games,
                "stalemate_games": self.end_reasons["stalemate_after_full_round_of_passes"],
                "end_reasons": dict(self.end_reasons),
            },
            "resource_balance": resource_summary,
            "light_balance": {
                "public_light_gained_from_reserves": self.light["public_gained"],
                "temporary_light_generated_by_specialization": self.light["temporary_gained"],
                "total_light_gained": self.light["public_gained"] + self.light["temporary_gained"],
                "public_light_spent": self.light["public_used"],
                "temporary_light_spent": self.light["temporary_used"],
                "total_light_spent": self.light["public_used"] + self.light["temporary_used"],
                "public_pool_final_remaining_total": self.light["public_pool_remaining"],
                "player_public_light_final_remaining_total": self.light["player_public_remaining"],
                "player_temporary_light_final_remaining_total": self.light["player_temporary_remaining"],
            },
            "routes_by_attribute": route_by_attribute,
            "exact_primary_routes": exact_routes,
            "winning_routes_by_frequency": [
                {"route": route, "win_share": count}
                for route, count in self.winning_routes.most_common()
            ],
            "strongest_observed_attribute_route": strongest,
            "weakest_observed_attribute_route": weakest,
            "most_common_winning_route": common_winning_route,
            "specialization_impact": effect_impact,
            "methodology": {
                "players": "每局4名玩家，均使用当前 src.ai.choose_action；策略相同，随机种子改变牌序。",
                "seed_range": "包含首尾，逐个整数作为牌库与局内随机种子。",
                "end_round": "记录最后一个完整结束的回合；达到18分后仍完成当前轮。",
                "stalemate": "若四名 AI 连续空过一整轮，则判为无法继续的僵局并按当时最高分结算；这用于终止模拟死循环，不会修改正式游戏规则。",
                "primary_route": "主路线按单属性宠物数量最多的属性确定；并列保留为复合路线，属性占比按并列数平均分配。",
                "dual_purchases": "双属性购买按卡面属性分别记一次，因此属性列统计不互斥；玩家总购买比例按卡牌实际张数计算。",
                "resource_balance": "公共池领取、购买支付返池、玩家间偷取分别统计；净公共需求=领取-支付返池。",
                "specialization_impact": "使用者与未使用者的胜率和分数为观察性对比，不代表因果关系。",
            },
        }


def write_exports(output: Path, games_path: Path, summary: dict) -> None:
    with games_path.open(encoding="utf-8") as source, \
            (output / "games.csv").open("w", encoding="utf-8-sig", newline="") as games_file, \
            (output / "players.csv").open("w", encoding="utf-8-sig", newline="") as players_file, \
            (output / "resources.csv").open("w", encoding="utf-8-sig", newline="") as resources_file:
        games_writer = csv.DictWriter(games_file, fieldnames=(
            "seed", "ending_round", "end_reason", "actions", "winners", "winning_score", "capacity_hits",
            "specialization_triggers", "specialization_uses", "light_public_gained", "light_temporary_gained",
            "light_public_used", "light_temporary_used", "winning_routes",
        ))
        player_fields = ["seed", "player_index", "player", "winner", "win_share", "score", "pet_count", "single_count", "dual_count", "single_ratio", "dual_ratio", "primary_route", "primary_route_attributes", "capacity", "capacity_hits", "light_remaining", "temporary_light_remaining", "triggered_specializations", "used_specializations", "successful_specializations"]
        for name in ATTR_NAMES:
            player_fields.extend((f"single_{name}", f"dual_appearance_{name}", f"discount_{name}", f"resource_remaining_{name}", f"resource_acquired_{name}", f"resource_consumed_{name}"))
        players_writer = csv.DictWriter(players_file, fieldnames=player_fields)
        resources_writer = csv.DictWriter(resources_file, fieldnames=(
            "seed", "attribute", "public_drawn", "purchase_paid", "stolen_in", "stolen_out",
            "player_acquired", "player_consumed", "player_remaining", "public_pool_remaining",
            "global_remaining", "depletion_events",
        ))
        games_writer.writeheader()
        players_writer.writeheader()
        resources_writer.writeheader()

        for line in source:
            record = json.loads(line)
            triggered = sum(len(player["triggered_specializations"]) for player in record["players"])
            used = sum(len(player["used_specializations"]) for player in record["players"])
            games_writer.writerow({
                "seed": record["seed"], "ending_round": record["ending_round"], "end_reason": record["end_reason"], "actions": record["actions"],
                "winners": ";".join(record["winners"]), "winning_score": record["winning_score"],
                "capacity_hits": record["capacity_hits"], "specialization_triggers": triggered,
                "specialization_uses": used, "light_public_gained": record["light"]["public_gained"],
                "light_temporary_gained": record["light"]["temporary_gained"],
                "light_public_used": record["light"]["public_used"],
                "light_temporary_used": record["light"]["temporary_used"],
                "winning_routes": ";".join(player["primary_route"] for player in record["players"] if player["winner"]),
            })
            for player in record["players"]:
                row = {key: player[key] for key in player_fields if key in player}
                row.update({
                    "seed": record["seed"],
                    "primary_route_attributes": ";".join(player["primary_route_attributes"]),
                    "triggered_specializations": ";".join(player["triggered_specializations"]),
                    "used_specializations": ";".join(player["used_specializations"]),
                    "successful_specializations": ";".join(player["successful_specializations"]),
                })
                for name in ATTR_NAMES:
                    row[f"single_{name}"] = player["single_by_attribute"][name]
                    row[f"dual_appearance_{name}"] = player["dual_attribute_appearances"][name]
                    row[f"discount_{name}"] = player["discounts"][name]
                    row[f"resource_remaining_{name}"] = player["resources_remaining"][name]
                    row[f"resource_acquired_{name}"] = player["acquired_by_attribute"][name]
                    row[f"resource_consumed_{name}"] = player["consumed_by_attribute"][name]
                players_writer.writerow(row)
            for name, flow in record["resource_stats"].items():
                resources_writer.writerow({"seed": record["seed"], "attribute": name, **flow})

    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.md").write_text(render_report(summary), encoding="utf-8")


def render_report(summary: dict) -> str:
    config = summary["config"]
    overall = summary["overall"]
    lines = [
        "# 自动对局平衡报告", "",
        f"- 完成对局：{overall['completed_games']:,} 局；种子 {config['seed_start']}–{config['seed_end']}。",
        f"- AI：四名玩家均使用当前 `choose_action`；平均结束回合 {overall['average_ending_round']:.2f}，平均最终分数 {overall['average_final_score_per_player']:.2f}。",
        f"- 资源上限触发：{overall['resource_capacity_reach_events']:,} 次；平局局数 {overall['games_with_tied_winners']:,}；僵局提前结算 {overall['stalemate_games']:,} 局。", "",
        "## 五种资源供需", "",
        "| 属性 | 玩家获取总量 | 玩家消耗总量 | 公共池领取 | 购买返池 | 净公共需求 | 玩家最终持有 | 公共池最终剩余 | 被拿空次数 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ATTR_NAMES:
        data = summary["resource_balance"][name]
        lines.append(f"| {name} | {data['player_acquired_total']:,} | {data['player_consumed_total']:,} | {data['public_drawn_total']:,} | {data['purchase_paid_total']:,} | {data['public_net_withdrawal']:,} | {data['player_final_remaining_total']:,} | {data['public_pool_final_remaining_total']:,} | {data['depletion_events']:,} |")
    lines.extend(["", "## 属性路线表现", "", "| 属性 | 主路线占比 | 单属性购买 | 双属性卡面数* | 专精触发/使用 | 主路线胜率 | 平均分 | 平均结束回合 |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for name in ATTR_NAMES:
        data = summary["routes_by_attribute"][name]
        lines.append(f"| {name} | {data['primary_route_share_percent']:.1f}% | {data['single_attribute_purchases']:,} | {data['dual_card_attribute_appearances_nonexclusive']:,} | {data['specialization_triggers']:,}/{data['specialization_uses']:,} | {data['route_win_rate_percent']:.1f}% | {data['average_final_score_on_route']:.2f} | {data['average_ending_round_on_route']:.2f} |")
    best = summary["strongest_observed_attribute_route"] or "无"
    weak = summary["weakest_observed_attribute_route"] or "无"
    common = summary["most_common_winning_route"] or "无"
    lines.extend(["", f"按主路线样本胜率，当前最强路线为 **{best}**，最弱为 **{weak}**；最常见胜利路线为 **{common}**。", "", "## 专精与胜率", "", "| 专精 | 触发玩家局 | 成功使用 | 使用者胜率 | 未使用者胜率 | 胜率差 | 平均分差 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for label, data in summary["specialization_impact"].items():
        lines.append(f"| {label} | {data['triggered_player_games']:,} | {data['successful_uses']:,} | {data['win_rate_when_used_percent']:.1f}% | {data['win_rate_without_use_percent']:.1f}% | {data['win_rate_difference_percentage_points']:+.1f}pp | {data['score_difference_when_used']:+.2f} |")
    lines.extend(["", "* 双属性宠物按卡面两个属性各计一次，所以双属性列不能相加当作总购买数。主路线按单属性宠物数量最多的属性判定，并列路线按权重平分。专精胜率对比是观察性结果，不代表因果。", "", "逐局与逐玩家明细见 `games.csv`、`players.csv` 和 `resources.csv`；完整指标见 `summary.json`。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible all-AI balance simulations.")
    parser.add_argument("--games", type=int, default=10000, help="number of games (default: 10000)")
    parser.add_argument("--seed-start", type=int, default=1, help="first deterministic seed")
    parser.add_argument("--output", type=Path, help="output directory")
    parser.add_argument("--progress-every", type=int, default=250, help="progress and checkpoint interval")
    args = parser.parse_args()
    if args.games < 1 or args.progress_every < 1:
        parser.error("--games and --progress-every must be positive")

    seed_end = args.seed_start + args.games - 1
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or ROOT / "analysis" / f"balance_{args.games}_seeds_{args.seed_start}_{seed_end}_{timestamp}"
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    games_path = output / "games.jsonl"
    aggregate = Aggregate()
    config = {
        "games_requested": args.games,
        "seed_start": args.seed_start,
        "seed_end": seed_end,
        "players_per_game": 4,
        "end_score_threshold": 18,
        "ai_policy": "src.ai.choose_action for every player",
    }

    started = datetime.now()
    with games_path.open("w", encoding="utf-8") as stream:
        for index in range(args.games):
            record = simulate_game(args.seed_start + index)
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            aggregate.add(record)
            if (index + 1) % args.progress_every == 0 or index + 1 == args.games:
                stream.flush()
                elapsed = (datetime.now() - started).total_seconds()
                rate = (index + 1) / max(elapsed, 1e-9)
                print(f"completed {index + 1:,}/{args.games:,} games; {rate:.1f} games/s; elapsed {elapsed:.0f}s", flush=True)

    summary = aggregate.as_dict(config)
    summary["run"] = {
        "started_local": started.isoformat(timespec="seconds"),
        "completed_local": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": (datetime.now() - started).total_seconds(),
    }
    write_exports(output, games_path, summary)
    print(f"report: {output / 'report.md'}", flush=True)
    print(f"summary: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
