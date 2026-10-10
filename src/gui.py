from __future__ import annotations

import argparse
from collections import Counter
import logging
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .ai import choose_action
from .cards import build_decks, name_for_card_id
from .game import Action, Game
from .models import ATTRIBUTES, Attribute, PetCard, Player
from .rules import RuleError, create_state, payment_for
from .seeding import seed_description, select_seed
from .specializations import legal_card_targets, legal_player_targets, single_attribute_count, specialization_name
from .theme import (
    CARD_AFFORDABLE_COLOR, CARD_FACE_COLOR, CARD_SELECTED_COLOR,
    CARD_FACE_CREAM_COLOR, LEGACY_CURRENT_PLAYER_COLOR, LEGACY_HEADER_COLOR,
    LEGACY_LOG_BACKGROUND, LEGACY_PLAYER_COLOR, LEGACY_RESOURCE_BACKGROUND,
    LEGACY_RESOURCE_SELECTED_TEXT, LEGACY_SIDEBAR_COLOR, LEGACY_TABLETOP_COLOR,
    RESOURCE_COLORS as ATTRIBUTE_COLORS,
)


class MagicGemsApp(tk.Tk):
    CARD_WIDTH = 84
    CARD_HEIGHT = 64
    RESOURCE_COLORS = ATTRIBUTE_COLORS

    def __init__(self, seed: int = 1, ai_battle: bool = False, interval: float = 0.5, seed_mode: str = "fixed") -> None:
        super().__init__()
        self.title(f"洛克王国：魔法宝石 · 种子 {seed}")
        self.attributes("-topmost", True)
        self.geometry("1260x820")
        self.minsize(1000, 700)
        self.configure(bg=LEGACY_TABLETOP_COLOR)

        self.ai_battle = ai_battle
        self.ai_interval = max(0.0, interval)
        self.seed = seed
        self.seed_mode = seed_mode
        players = [Player(f"AI-{index}") for index in range(1, 5)] if ai_battle else [Player("你"), Player("AI-2"), Player("AI-3"), Player("AI-4")]
        self.game = Game(create_state(players, build_decks(seed), seed))
        self.selected_card: PetCard | None = None
        self.resource_mode: str | None = None
        self.resource_selection: list[Attribute] = []
        self.next_dual_choices: list[Attribute] | None = None
        self.discount_choice_pending = False
        self.discount_prompt_scheduled = False
        self.discount_dialog: tk.Toplevel | None = None
        self.specialization_dialog: tk.Toplevel | None = None
        self.specialization_prompt_scheduled = False
        self.end_dialog: tk.Toplevel | None = None
        self.end_dialog_shown = False
        self.ai_turn_scheduled = False
        self.game_logger: logging.Logger
        self.game_log_handler: logging.FileHandler
        self.game_log_path: Path
        self.start_game_log()
        self.card_buttons: list[tk.Widget] = []
        self.status_var = tk.StringVar()
        self.selection_var = tk.StringVar(value="尚未选择卡片")
        self.market_frame: tk.Frame
        self.players_frame: tk.Frame
        self.resource_frame: tk.Frame
        self.action_frame: tk.Frame
        self.build_ui()
        self.refresh()
        self.after_idle(lambda: self.sidebar_canvas.yview_moveto(0))
        self.lift()
        self.focus_force()
        self.after(700, lambda: self.attributes("-topmost", False))
        self.log(f"对局开始，{seed_description(self.seed, self.seed_mode)}")

    def build_ui(self) -> None:
        header = tk.Frame(self, bg=LEGACY_HEADER_COLOR, height=72)
        header.pack(fill="x")
        self.display_button(header, text="魔法宝石", font=("Songti SC", 18, "bold")).pack(side="left", padx=18, pady=10)
        self.display_button(header, textvariable=self.status_var, font=("Songti SC", 11)).pack(side="right", padx=18, pady=10)

        body = tk.Frame(self, bg=LEGACY_TABLETOP_COLOR)
        body.pack(fill="both", expand=True, padx=18, pady=16)
        self.market_frame = tk.Frame(body, bg=LEGACY_TABLETOP_COLOR)
        self.market_frame.pack(side="left", fill="both", expand=True)

        sidebar_outer = tk.Frame(body, bg=LEGACY_SIDEBAR_COLOR, width=360)
        sidebar_outer.pack(side="right", fill="y", padx=(16, 0))
        sidebar_outer.pack_propagate(False)
        self.sidebar_canvas = tk.Canvas(sidebar_outer, bg=LEGACY_SIDEBAR_COLOR, highlightthickness=0)
        sidebar_scrollbar = ttk.Scrollbar(sidebar_outer, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)
        sidebar_scrollbar.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        self.sidebar_content = tk.Frame(self.sidebar_canvas, bg=LEGACY_SIDEBAR_COLOR)
        sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar_content, anchor="nw")
        self.sidebar_content.bind("<Configure>", lambda _event: self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all")))
        self.sidebar_canvas.bind("<Configure>", lambda event: self.sidebar_canvas.itemconfigure(sidebar_window, width=event.width))

        # 右侧全部内容共用外层滚动区；四位玩家固定排在同一块区域。
        controls = tk.Frame(self.sidebar_content, bg=LEGACY_SIDEBAR_COLOR, padx=14, pady=5)
        controls.pack(fill="x")
        self.display_button(
            controls,
            textvariable=self.selection_var,
            font=("Songti SC", 10),
        ).pack(fill="x", pady=(0, 3))
        self.resource_frame = tk.Frame(controls, bg=LEGACY_SIDEBAR_COLOR)
        self.resource_frame.pack(fill="x", pady=(0, 2))
        self.action_frame = tk.Frame(controls, bg=LEGACY_SIDEBAR_COLOR)
        self.action_frame.pack(fill="x", pady=(0, 2))
        ttk.Separator(self.sidebar_content, orient="horizontal").pack(fill="x", padx=12, pady=(0, 2))

        self.details_outer = tk.Frame(self.sidebar_content, bg=LEGACY_SIDEBAR_COLOR)
        self.details_outer.pack(fill="x")

        self.log_outer = tk.Frame(self.details_outer, bg=LEGACY_SIDEBAR_COLOR, height=130)
        self.log_outer.pack(fill="x", side="bottom")
        self.log_outer.pack_propagate(False)
        self.display_button(self.log_outer, text="行动记录（可滚动查看全部）", font=("Songti SC", 10, "bold")).pack(fill="x", padx=8, pady=(3, 2))
        log_body = tk.Frame(self.log_outer, bg=LEGACY_SIDEBAR_COLOR)
        log_body.pack(fill="both", expand=True)
        self.log_scrollbar = ttk.Scrollbar(log_body, orient="vertical", command=self.scroll_log)
        self.log_scrollbar.pack(side="right", fill="y")
        self.log_entries_frame = tk.Frame(log_body, bg=LEGACY_LOG_BACKGROUND, padx=3, pady=2)
        self.log_entries_frame.pack(side="left", fill="both", expand=True)
        self.log_entry_image = self.solid_image(268, 35, CARD_FACE_CREAM_COLOR)
        self.log_messages: list[str] = []
        self.log_offset = 0
        self.log_visible_count = 1
        self.log_entry_buttons = [
            tk.Button(
                self.log_entries_frame,
                image=self.log_entry_image,
                compound="center",
                font=("Songti SC", 9),
                wraplength=254,
                justify="left",
                command=lambda: None,
                cursor="arrow",
                takefocus=False,
            )
            for _ in range(self.log_visible_count)
        ]

        players_outer = tk.Frame(self.details_outer, bg=LEGACY_SIDEBAR_COLOR)
        players_outer.pack(fill="both", expand=True)
        self.display_button(players_outer, text="玩家状态", font=("Songti SC", 10, "bold")).pack(fill="x", padx=8, pady=(0, 2))
        self.players_frame = tk.Frame(players_outer, bg=LEGACY_SIDEBAR_COLOR, padx=8, pady=1)
        self.players_frame.pack(fill="x")
        self.player_card_images = {
            "normal": self.solid_image(270, 32, LEGACY_PLAYER_COLOR),
            "current": self.solid_image(270, 32, LEGACY_CURRENT_PLAYER_COLOR),
        }

        self.bind_all("<MouseWheel>", self.sidebar_mousewheel, add="+")
        self.bind_all("<Button-4>", self.sidebar_mousewheel, add="+")
        self.bind_all("<Button-5>", self.sidebar_mousewheel, add="+")

    @staticmethod
    def solid_image(width: int, height: int, color: str) -> tk.PhotoImage:
        image = tk.PhotoImage(width=width, height=height)
        image.put(color, to=(0, 0, width, height))
        return image

    @staticmethod
    def display_button(parent: tk.Widget, *, text: str | None = None, textvariable: tk.StringVar | None = None, font: tuple | None = None, centered: bool = False, width: int | None = None) -> tk.Button:
        """用 macOS 系统 Tk 能稳定绘制的原生按钮显示静态信息。"""
        return tk.Button(
            parent,
            text=text,
            textvariable=textvariable,
            font=font,
            command=lambda: None,
            takefocus=False,
            cursor="arrow",
            anchor="center" if centered else "w",
            width=width,
            padx=8,
            pady=3,
        )

    def sidebar_mousewheel(self, event: tk.Event) -> str | None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        target = None
        while widget is not None:
            if widget is self.log_entries_frame:
                target = "log"
                break
            if widget in (self.sidebar_content, self.sidebar_canvas):
                target = "sidebar"
                break
            widget = getattr(widget, "master", None)
        if target is None:
            return None
        if getattr(event, "num", None) == 4:
            amount = -1
        elif getattr(event, "num", None) == 5:
            amount = 1
        else:
            amount = -1 if event.delta > 0 else 1
        if target == "log" and len(self.log_messages) > self.log_visible_count:
            self.scroll_log("scroll", amount, "units")
        else:
            self.sidebar_canvas.yview_scroll(amount, "units")
        return "break"

    def scroll_log(self, *args: object) -> None:
        maximum = max(0, len(self.log_messages) - self.log_visible_count)
        if not args:
            return
        if args[0] == "moveto":
            self.log_offset = round(float(args[1]) * maximum)
        elif args[0] == "scroll":
            step = self.log_visible_count if len(args) > 2 and args[2] == "pages" else 1
            self.log_offset += int(args[1]) * step
        self.log_offset = max(0, min(self.log_offset, maximum))
        self.render_log()

    def render_log(self) -> None:
        for index, button in enumerate(self.log_entry_buttons):
            message_index = self.log_offset + index
            if message_index < len(self.log_messages):
                button.configure(text=self.log_messages[message_index])
                button.pack(pady=2)
            else:
                button.pack_forget()
        total = len(self.log_messages)
        if total:
            self.log_scrollbar.set(self.log_offset / total, min(1.0, (self.log_offset + self.log_visible_count) / total))
        else:
            self.log_scrollbar.set(0, 1)

    def refresh(self) -> None:
        state = self.game.state
        current = state.current()
        pending_text = f"  ·  待结算 {specialization_name(state.pending_specializations[0])}" if state.pending_specializations else ""
        self.status_var.set(f"第 {state.round_number} 轮  ·  {current.name} 行动  ·  贤者碎晶 {state.light_pool}{pending_text}")
        self.render_market()
        self.render_players()
        self.render_actions()
        if not self.ai_battle and state.current_player == 0 and not state.finished and state.pending_specializations and not self.specialization_prompt_scheduled and self.specialization_dialog is None:
            self.specialization_prompt_scheduled = True
            self.after_idle(self.prompt_specialization)
        if not self.ai_battle and state.current_player == 0 and not state.finished and not state.pending_specializations and self.discount_choice_pending and not self.discount_prompt_scheduled and self.discount_dialog is None:
            self.discount_prompt_scheduled = True
            self.after_idle(self.prompt_discount_choice)
        if not state.finished and (self.ai_battle or state.current_player != 0) and not self.ai_turn_scheduled:
            self.ai_turn_scheduled = True
            self.after(int(self.ai_interval * 1000), self.play_ai_turn)
        elif state.finished:
            winners = ", ".join(player.name for player in self.game.winners())
            self.status_var.set(f"对局结束  ·  获胜者：{winners}")
            if not self.end_dialog_shown:
                self.end_dialog_shown = True
                self.after_idle(self.show_end_dialog)

    def start_game_log(self) -> None:
        logs_dir = Path(__file__).resolve().parent.parent / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_name = f"RocoKingdomGemMaster_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
        self.game_log_path = logs_dir / log_name
        self.game_logger = logging.getLogger(f"magic_gems.game.{id(self)}")
        self.game_logger.setLevel(logging.INFO)
        self.game_logger.propagate = False
        self.game_log_handler = logging.FileHandler(self.game_log_path, encoding="utf-8")
        self.game_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.game_logger.addHandler(self.game_log_handler)

    def close_game_log(self) -> None:
        if hasattr(self, "game_log_handler"):
            self.game_logger.removeHandler(self.game_log_handler)
            self.game_log_handler.close()

    def show_end_dialog(self) -> None:
        if self.end_dialog is not None or not self.game.state.finished:
            return
        state = self.game.state
        winners = self.game.winners()
        winner_names = ", ".join(player.name for player in winners)
        result = "AI 对战结束" if self.ai_battle else ("你胜利了" if state.players[0] in winners else "你失败了")
        rounds = max(1, state.round_number - 1)

        dialog = tk.Toplevel(self)
        self.end_dialog = dialog
        dialog.title("对局结算")
        dialog.transient(self)
        dialog.resizable(False, False)
        self.display_button(dialog, text="对局结束", font=("Songti SC", 16, "bold")).pack(fill="x", padx=24, pady=(14, 4))
        self.display_button(dialog, text=f"{result}  ·  获胜玩家：{winner_names}  ·  {rounds}轮", font=("Songti SC", 11)).pack(fill="x", padx=24, pady=3)
        for player in state.players:
            self.display_button(dialog, text=f"{player.name}：{player.score}分  ·  购买{len(player.purchased)}张", font=("Songti SC", 10)).pack(fill="x", padx=24, pady=2)
        buttons = tk.Frame(dialog, pady=18)
        buttons.pack()
        tk.Button(buttons, text="重新开始", command=self.restart_from_end_dialog, padx=14, pady=6).pack(side="left", padx=6)
        tk.Button(buttons, text="关闭游戏", command=self.destroy, padx=14, pady=6).pack(side="left", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", self.destroy)
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()
        self.log(f"对局结束：{result}，获胜者：{winner_names}，消耗回合：{rounds}")

    def restart_from_end_dialog(self) -> None:
        if self.end_dialog is not None:
            self.end_dialog.grab_release()
            self.end_dialog.destroy()
            self.end_dialog = None
        self.restart()

    def render_market(self) -> None:
        state = self.game.state
        if not hasattr(self, "market_card_widgets"):
            self.card_images = {
                "normal": self.solid_image(self.CARD_WIDTH, self.CARD_HEIGHT, CARD_FACE_COLOR),
                "affordable": self.solid_image(self.CARD_WIDTH, self.CARD_HEIGHT, CARD_AFFORDABLE_COLOR),
                "selected": self.solid_image(self.CARD_WIDTH, self.CARD_HEIGHT, CARD_SELECTED_COLOR),
            }
            self.display_button(self.market_frame,centered=True, text="公共宠物市场", font=("Songti SC", 15, "bold")).pack(fill="x", pady=(0, 8))
            self.market_card_widgets: dict[int, list[tk.Button]] = {}
            for level in (1, 2, 3):
                row = tk.Frame(self.market_frame, bg=LEGACY_TABLETOP_COLOR)
                row.pack(fill="x", pady=(0, 10))
                centered_line = tk.Frame(row, bg=LEGACY_TABLETOP_COLOR)
                centered_line.pack(anchor="center")
                level_label = self.display_button(
                    centered_line,
                    text=f"{level}级市场",
                    font=("Songti SC", 10, "bold"),
                    centered=True,
                    width=10,
                )
                level_label.pack(side="left", padx=(0, 6))
                cards = tk.Frame(centered_line, bg=LEGACY_TABLETOP_COLOR)
                cards.pack(side="left")
                widgets = [
                    tk.Button(
                        cards,
                        image=self.card_images["normal"],
                        compound="center",
                        font=("Songti SC", 8),
                        justify="center",
                        wraplength=self.CARD_WIDTH - 8,
                        padx=1,
                        pady=1,
                    )
                    for _ in range(5)
                ]
                self.market_card_widgets[level] = widgets
            reserved = tk.Frame(self.market_frame, bg=LEGACY_TABLETOP_COLOR)
            reserved.pack(fill="x", pady=(12, 0))
            self.display_button(reserved, text="你的预购区", font=("Songti SC", 10, "bold")).pack(fill="x")
            reserved_cards = tk.Frame(reserved, bg=LEGACY_TABLETOP_COLOR)
            reserved_cards.pack(fill="x", pady=4)
            self.reserved_card_widgets = [
                tk.Button(reserved_cards, image=self.card_images["normal"], compound="center", font=("Songti SC", 8), justify="center", wraplength=self.CARD_WIDTH - 8, padx=1, pady=1)
                for _ in range(3)
            ]

        self.card_buttons.clear()
        for level in (1, 2, 3):
            cards = state.market.cards[level]
            while len(self.market_card_widgets[level]) < len(cards):
                parent = self.market_card_widgets[level][0].master
                widget = tk.Button(
                    parent,
                    image=self.card_images["normal"],
                    compound="center",
                    font=("Songti SC", 8),
                    justify="center",
                    wraplength=self.CARD_WIDTH - 8,
                    padx=1,
                    pady=1,
                )
                self.market_card_widgets[level].append(widget)
            for index, widget in enumerate(self.market_card_widgets[level]):
                if index < len(cards):
                    self.configure_card_button(widget, cards[index])
                    widget.pack(side="left", padx=2, pady=3)
                    self.card_buttons.append(widget)
                else:
                    widget.pack_forget()
        reserved_cards = state.players[0].reserved
        for index, widget in enumerate(self.reserved_card_widgets):
            if index < len(reserved_cards):
                self.configure_card_button(widget, reserved_cards[index])
                widget.pack(side="left", padx=3, pady=3)
                self.card_buttons.append(widget)
            else:
                widget.pack_forget()

    def configure_card_button(self, button: tk.Button, card: PetCard) -> None:
        attributes = "/".join(attribute.value for attribute in card.attributes)
        transformed = f"↓{name_for_card_id(card.transformed_from)}" if card.transformed_from else ""
        selected = self.selected_card is not None and card.card_id == self.selected_card.card_id
        can_buy = self.can_current_player_buy(card)
        card_action_enabled = (
            self.game.state.current_player == 0
            and not self.game.state.finished
            and not self.game.state.pending_specializations
            and self.resource_mode is None
            and self.discount_dialog is None
            and self.specialization_dialog is None
        )
        marker = "▶" if selected else "★" if can_buy else "·"
        compact_cost = "".join(f"{attribute.value}{amount}" for attribute, amount in card.cost.items()) or "无成本"
        text = f"{marker} {card.display_name}{transformed}\n{attributes} {card.effective_score}分\n{compact_cost}"
        button.configure(
            text=text,
            image=self.card_images["selected" if selected else "affordable" if can_buy else "normal"],
            command=lambda selected_card=card: self.select_card(selected_card),
            state="normal",
            cursor="hand2" if card_action_enabled else "arrow",
        )

    def can_current_player_buy(self, card: PetCard) -> bool:
        state = self.game.state
        if state.current_player != 0 or state.finished or state.pending_specializations or self.resource_mode is not None:
            return False
        player = state.current()
        dual_cards = player.dual_cards()
        if dual_cards:
            if self.discount_dialog is not None or self.discount_choice_pending or self.next_dual_choices is None:
                return False
            choices = self.next_dual_choices
        else:
            choices = []
        try:
            payment_for(player, card, list(choices))
        except RuleError:
            return False
        return True

    def render_players(self) -> None:
        if not hasattr(self, "player_display_rows"):
            self.player_display_rows: list[tk.Button] = []
            for _ in range(4):
                card = tk.Button(
                    self.players_frame,
                    image=self.player_card_images["normal"],
                    compound="center",
                    font=("Songti SC", 8),
                    justify="center",
                    command=lambda: None,
                    takefocus=False,
                    cursor="arrow",
                )
                card.pack(pady=2)
                self.player_display_rows.append(card)
        state = self.game.state
        for index, player in enumerate(state.players):
            current = index == state.current_player
            discounts = "".join(f"{attribute.value}{amount}" for attribute, amount in player.permanent_discounts.items() if amount) or "无"
            current_discount = ""
            if index == 0 and self.next_dual_choices:
                counts = Counter(self.next_dual_choices)
                current_discount = "本次折扣 " + " ".join(f"{attribute.value}{amount}" for attribute, amount in counts.items())
            resource_details = ""
            if index == 0:
                temporary = f"+临时{player.temporary_light}" if player.temporary_light else ""
                resource_details = " ".join(f"{attribute.value}{player.resources[attribute]}" for attribute in ATTRIBUTES) + f" 光{player.light}{temporary}"
            free_text = " 免购" if player.next_purchase_free else ""
            if player.next_purchase_score_doubled:
                free_text += " 下张分×2"
            if player.next_attack_immune:
                free_text += " 攻击免疫"
            specialization_items = []
            for attribute in ATTRIBUTES:
                count = min(single_attribute_count(player, attribute), 3)
                if count:
                    stage = "②" if count >= 3 else "①" if count >= 2 else ""
                    specialization_items.append(f"{attribute.value}{count}{stage}")
            specialization_progress = "".join(specialization_items) or "无"
            first_line = (
                f"{'▶' if current else ''}{player.name} {player.score}分  "
                f"资源{player.resource_count}/{player.resource_capacity}  购{len(player.purchased)}  预{len(player.reserved)}  法师{len(player.wizard_cards)}/10"
            )
            if index != 0:
                resource_details = " ".join(f"{attribute.value}{player.resources[attribute]}" for attribute in ATTRIBUTES) + f" 光{player.light}"
            detail = f"{resource_details}  折{discounts} 专{specialization_progress}{free_text}"
            if current_discount:
                detail += f"  {current_discount}"
            self.player_display_rows[index].configure(
                text=f"{first_line}\n{detail}",
                image=self.player_card_images["current" if current else "normal"],
            )

    def render_actions(self) -> None:
        if not hasattr(self, "resource_buttons"):
            self.display_button(self.resource_frame, text="选择资源方式", font=("Songti SC", 9, "bold")).pack(fill="x", pady=(0, 3))
            mode_row = tk.Frame(self.resource_frame, bg=LEGACY_SIDEBAR_COLOR)
            mode_row.pack(fill="x", pady=3)
            self.different_button = tk.Button(mode_row, text="三种各一枚", command=lambda: self.set_resource_mode("different"))
            self.different_button.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=2)
            self.same_button = tk.Button(mode_row, text="同种两枚", command=lambda: self.set_resource_mode("same"))
            self.same_button.pack(side="left", fill="x", expand=True, pady=2)
            attrs = tk.Frame(self.resource_frame, bg=LEGACY_SIDEBAR_COLOR)
            attrs.pack(fill="x", pady=3)
            self.resource_buttons: dict[Attribute, tk.Button] = {}
            self.resource_images = {
                attribute: (
                    self.solid_image(44, 34, colors[0]),
                    self.solid_image(44, 34, colors[1]),
                )
                for attribute, colors in self.RESOURCE_COLORS.items()
            }
            for index, attribute in enumerate(ATTRIBUTES):
                attrs.grid_columnconfigure(index, weight=1, uniform="attribute-button", minsize=52)
                button = tk.Button(
                    attrs,
                    image=self.resource_images[attribute][0],
                    compound="center",
                    command=lambda selected_attribute=attribute: self.choose_resource(selected_attribute),
                    font=("Songti SC", 10, "bold"),
                )
                button.grid(row=0, column=index, padx=2)
                self.resource_buttons[attribute] = button
            self.resource_status_image = self.solid_image(280, 30, LEGACY_RESOURCE_BACKGROUND)
            self.resource_status_button = tk.Button(self.resource_frame, image=self.resource_status_image, compound="center", text="", font=("Songti SC", 9), command=lambda: None, cursor="arrow", takefocus=False)
            self.resource_status_button.pack(pady=3)
            resource_actions = tk.Frame(self.resource_frame, bg=LEGACY_SIDEBAR_COLOR)
            resource_actions.pack(fill="x", pady=(0, 8))
            self.confirm_resource_button = tk.Button(resource_actions, text="确定获取", command=self.confirm_resources)
            self.confirm_resource_button.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=2)
            self.cancel_resource_button = tk.Button(resource_actions, text="取消", command=self.cancel_resource_selection)
            self.cancel_resource_button.pack(side="left", fill="x", expand=True, pady=2)

            self.display_button(self.action_frame, text="卡片行动", font=("Songti SC", 9, "bold")).pack(fill="x", pady=(0, 3))
            self.buy_button = tk.Button(self.action_frame, text="购买选中宠物", command=self.buy_selected)
            self.buy_button.pack(fill="x", pady=4)
            self.reserve_button = tk.Button(self.action_frame, text="预购选中宠物", command=self.reserve_selected)
            self.reserve_button.pack(fill="x", pady=4)
            self.cancel_card_button = tk.Button(self.action_frame, text="取消选择", command=self.cancel_card_selection)
            self.cancel_card_button.pack(fill="x", pady=4)

        state = self.game.state
        enabled = state.current_player == 0 and not state.finished and not state.pending_specializations and not self.ai_battle
        resource_enabled = enabled and self.selected_card is None and self.discount_dialog is None and self.specialization_dialog is None
        card_action_enabled = enabled and self.selected_card is not None and self.resource_mode is None and self.discount_dialog is None and self.specialization_dialog is None
        self.different_button.configure(relief="sunken" if self.resource_mode == "different" else "raised", state="normal" if resource_enabled else "disabled")
        self.same_button.configure(relief="sunken" if self.resource_mode == "same" else "raised", state="normal" if resource_enabled else "disabled")
        for attribute in ATTRIBUTES:
            available = resource_enabled and self.resource_mode is not None and state.resource_pool[attribute] > 0
            selected = attribute in self.resource_selection
            self.resource_buttons[attribute].configure(
                text=f"{'✓' if selected else ''}{attribute.value}{state.resource_pool[attribute]}",
                image=self.resource_images[attribute][1 if selected else 0],
                fg=LEGACY_RESOURCE_SELECTED_TEXT if selected else LEGACY_HEADER_COLOR,
                relief="sunken" if selected else "raised",
                state="normal",
                cursor="hand2" if available else "arrow",
            )
        mode_text = {"different": "三种各一枚", "same": "同种两枚"}.get(self.resource_mode, "未选择")
        selected_text = "、".join(attribute.value for attribute in self.resource_selection) or "无"
        self.resource_status_button.configure(text=f"当前：{mode_text}  |  已选：{selected_text}")
        confirm_enabled = resource_enabled and ((self.resource_mode == "different" and len(self.resource_selection) == 3) or (self.resource_mode == "same" and len(self.resource_selection) == 1))
        self.confirm_resource_button.configure(state="normal" if confirm_enabled else "disabled")
        self.cancel_resource_button.configure(state="normal" if resource_enabled and self.resource_mode is not None else "disabled")
        self.buy_button.configure(state="normal" if card_action_enabled else "disabled")
        self.reserve_button.configure(state="normal" if card_action_enabled else "disabled")
        self.cancel_card_button.configure(state="normal" if self.selected_card is not None else "disabled")

    def select_card(self, card: PetCard) -> None:
        if self.game.state.current_player != 0 or self.game.state.finished or self.game.state.pending_specializations or self.resource_mode is not None or self.discount_dialog is not None:
            return
        self.selected_card = card
        form = f" ↓{name_for_card_id(card.transformed_from)}" if card.transformed_from else ""
        self.selection_var.set(
            f"已选 {card.display_name}{form}  ·  {'/'.join(attribute.value for attribute in card.attributes)}  ·  "
            f"{card.cost_text() or '无成本'}  ·  {card.effective_score}分"
        )
        self.refresh()

    def cancel_card_selection(self) -> None:
        self.selected_card = None
        self.selection_var.set("尚未选择卡片")
        self.refresh()

    def set_resource_mode(self, mode: str) -> None:
        if self.selected_card is not None or self.game.state.current_player != 0 or self.game.state.finished or self.discount_dialog is not None:
            return
        self.resource_mode = mode
        self.resource_selection.clear()
        self.refresh()

    def choose_resource(self, attribute: Attribute) -> None:
        if self.resource_mode is None or self.game.state.current_player != 0 or self.game.state.finished or self.game.state.resource_pool[attribute] <= 0 or self.discount_dialog is not None:
            return
        if self.resource_mode == "same":
            self.resource_selection = [attribute]
            self.refresh()
            return
        if attribute in self.resource_selection:
            self.resource_selection.remove(attribute)
        elif len(self.resource_selection) < 3:
            self.resource_selection.append(attribute)
        self.refresh()

    def confirm_resources(self) -> None:
        if self.resource_mode == "different" and len(self.resource_selection) == 3:
            self.perform(Action("different", attributes=tuple(self.resource_selection)))
            return
        if self.resource_mode == "same" and len(self.resource_selection) == 1:
            self.perform(Action("same", attributes=(self.resource_selection[0],)))
            return
        messagebox.showinfo("资源选择", "请先选择符合当前方式的属性。")

    def cancel_resource_selection(self) -> None:
        self.resource_mode = None
        self.resource_selection.clear()
        self.refresh()

    def buy_selected(self) -> None:
        if self.selected_card is None or self.discount_dialog is not None:
            return
        if self.game.state.players[0].dual_cards():
            if self.next_dual_choices is None:
                self.discount_choice_pending = True
                self.prompt_discount_choice()
                return
            choices = self.next_dual_choices
        else:
            choices = []
        self.perform(Action("buy", card=self.selected_card, dual_choices=tuple(choices)))

    def reserve_selected(self) -> None:
        if self.selected_card is not None:
            self.perform(Action("reserve", card=self.selected_card))

    def prompt_discount_choice(self) -> None:
        dual_cards = self.game.state.players[0].dual_cards()
        if not dual_cards:
            self.discount_choice_pending = False
            return
        if self.discount_dialog is not None:
            return
        dialog = tk.Toplevel(self)
        self.discount_dialog = dialog
        dialog.title("选择双属性折扣")
        dialog.transient(self)
        dialog.resizable(False, False)
        self.display_button(dialog, text="点击每张宠物切换本次折扣属性", font=("Songti SC", 11, "bold")).pack(fill="x", padx=16, pady=10)
        choices = [card.attributes[0] for card in dual_cards]
        selectors: list[tk.Button] = []

        def toggle_choice(index: int) -> None:
            card = dual_cards[index]
            current = choices[index]
            choices[index] = card.attributes[1] if current == card.attributes[0] else card.attributes[0]
            selectors[index].configure(text=f"{card.display_name}  ·  当前折扣：{choices[index].value}系（点击切换）")

        for index, card in enumerate(dual_cards):
            selector = tk.Button(
                dialog,
                text=f"{card.display_name}  ·  当前折扣：{choices[index].value}系（点击切换）",
                command=lambda selected=index: toggle_choice(selected),
                padx=12,
                pady=6,
            )
            selector.pack(fill="x", padx=16, pady=3)
            selectors.append(selector)

        def confirm() -> None:
            self.next_dual_choices = list(choices)
            self.discount_choice_pending = False
            self.discount_dialog = None
            dialog.destroy()
            choice_text = "、".join(f"{card.display_name}->{choice.value}" for card, choice in zip(dual_cards, self.next_dual_choices))
            self.log(f"本次双属性折扣：{choice_text}")
            self.refresh()

        def close() -> None:
            self.discount_dialog = None
            self.discount_choice_pending = False
            self.next_dual_choices = None
            dialog.destroy()
            self.refresh()

        buttons = tk.Frame(dialog)
        buttons.pack(pady=12)
        tk.Button(buttons, text="确认选择", command=confirm, padx=12, pady=5).pack(side="left", padx=4)
        tk.Button(buttons, text="取消", command=close, padx=12, pady=5).pack(side="left", padx=4)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        self.discount_prompt_scheduled = False
        self.render_actions()

    def prompt_specialization(self) -> None:
        self.specialization_prompt_scheduled = False
        if not self.game.state.pending_specializations or self.specialization_dialog is not None:
            return
        effect = self.game.state.pending_specializations[0]
        cards = legal_card_targets(self.game.state, effect)
        players = legal_player_targets(self.game.state, effect)
        dialog = tk.Toplevel(self)
        self.specialization_dialog = dialog
        dialog.title("结算属性专精")
        dialog.transient(self)
        dialog.resizable(False, False)
        self.display_button(
            dialog,
            text=specialization_name(effect),
            font=("Songti SC", 16, "bold"),
        ).pack(fill="x", padx=16, pady=10)

        options = tk.Frame(dialog, padx=16, pady=8)
        options.pack(fill="both", expand=True)

        def settle(action: Action) -> None:
            self.specialization_dialog = None
            dialog.destroy()
            self.perform(action)

        if cards:
            self.display_button(options, text="选择一张公共市场宠物：").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
            for index, card in enumerate(cards):
                tk.Button(
                    options,
                    text=f"{card.display_name}  {card.level}级  {card.cost_text()}  →{card.effective_score}分",
                    width=24,
                    command=lambda selected=card: settle(Action("specialization", card=selected)),
                ).grid(row=1 + index // 3, column=index % 3, padx=3, pady=3, sticky="ew")
        elif players:
            self.display_button(options, text="选择目标玩家：").pack(fill="x", pady=(0, 6))
            for index in players:
                target = self.game.state.players[index]
                tk.Button(
                    options,
                    text=f"{target.name}  ·  {target.score}分  ·  资源{target.resource_count}  ·  已购{len(target.purchased)}",
                    command=lambda selected=index: settle(Action("specialization", target_player=selected)),
                ).pack(fill="x", pady=3)
        else:
            self.display_button(options, text="该效果无需选择目标。").pack(fill="x", pady=6)
            tk.Button(options, text="结算效果", command=lambda: settle(Action("specialization")), padx=14, pady=5).pack(pady=6)

        def close() -> None:
            self.specialization_dialog = None
            dialog.destroy()
            self.refresh()

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()

    def perform(self, action: Action) -> None:
        try:
            actor_index = self.game.state.current_player
            actor = self.game.state.current().name
            effect_messages = self.game.execute(action)
            self.log(f"{actor}：{self.action_text(action)}")
            for message in effect_messages:
                self.log(message)
            self.selected_card = None
            self.selection_var.set("尚未选择卡片")
            if action.kind in {"different", "same"}:
                self.resource_mode = None
            if actor_index == 0 and not self.ai_battle:
                self.next_dual_choices = None
                self.discount_choice_pending = bool(self.game.state.players[0].dual_cards()) and not self.game.state.pending_specializations
            self.resource_selection.clear()
            self.refresh()
        except (RuleError, ValueError) as error:
            card_text = action.card.display_name if action.card is not None else "无"
            choices_text = "、".join(attribute.value for attribute in action.dual_choices) or "无"
            self.game_logger.warning("操作无效：%s | 动作=%s 卡片=%s 双属性选择=%s", error, action.kind, card_text, choices_text)
            messagebox.showwarning("操作无效", str(error))

    def play_ai_turn(self) -> None:
        self.ai_turn_scheduled = False
        if self.game.state.finished or (not self.ai_battle and self.game.state.current_player == 0):
            return
        action = choose_action(self.game)
        self.perform(action)

    def action_text(self, action: Action) -> str:
        if action.kind == "buy":
            return f"购买 {action.card.display_name if action.card else ''}"
        if action.kind == "reserve":
            return f"预购 {action.card.display_name if action.card else ''}"
        if action.kind == "different":
            resources = "、".join(f"{attribute.value}1" for attribute in action.attributes)
            return f"获取资源：{resources}"
        if action.kind == "same":
            return f"获取资源：{action.attributes[0].value}2"
        if action.kind == "specialization":
            return "结算属性专精"
        return "跳过行动"

    def log(self, message: str) -> None:
        timestamped_message = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.log_messages.append(timestamped_message)
        self.log_offset = max(0, len(self.log_messages) - self.log_visible_count)
        self.render_log()
        self.game_logger.info(message)

    def restart(self) -> None:
        players = [Player(f"AI-{index}") for index in range(1, 5)] if self.ai_battle else [Player("你"), Player("AI-2"), Player("AI-3"), Player("AI-4")]
        self.game = Game(create_state(players, build_decks(self.seed), self.seed))
        self.selected_card = None
        self.next_dual_choices = None
        self.discount_choice_pending = False
        self.discount_prompt_scheduled = False
        self.specialization_dialog = None
        self.specialization_prompt_scheduled = False
        self.end_dialog = None
        self.end_dialog_shown = False
        self.ai_turn_scheduled = False
        self.close_game_log()
        self.start_game_log()
        self.selection_var.set("尚未选择卡片")
        self.log_messages.clear()
        self.log_offset = 0
        self.render_log()
        self.log(f"对局重新开始，{seed_description(self.seed, self.seed_mode)}")
        self.refresh()

    def destroy(self) -> None:
        self.close_game_log()
        super().destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="启动魔法宝石图形界面")
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int, help="使用指定的固定随机种子")
    seed_group.add_argument("--random-seed", action="store_true", help="每次启动时自动生成随机种子")
    args = parser.parse_args()
    if sys.version_info < (3, 11) or tk.TkVersion < 8.6:
        parser.error("图形界面需要 Python 3.11+ 和 Tk 8.6+；请换用符合要求的解释器")
    seed, seed_mode = select_seed(args.seed, args.random_seed)
    print("本局使用" + seed_description(seed, seed_mode))
    app = MagicGemsApp(seed, seed_mode=seed_mode)
    app.mainloop()


if __name__ == "__main__":
    main()
