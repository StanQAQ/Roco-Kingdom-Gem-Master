"""Qt 6 desktop interface for Magic Gems."""
from __future__ import annotations

from datetime import datetime
from html import escape as html_escape
import logging
from pathlib import Path
import re
import sys

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QGraphicsDropShadowEffect,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit,
    QStyle, QStyleOptionButton, QStylePainter, QVBoxLayout, QWidget,
)

from .ai import choose_action
from .cards import build_decks
from .game import Action, Game
from .models import ATTRIBUTES, Attribute, PetCard, Player, SpecializationEffect
from .rules import RuleError, create_state, payment_for
from .seeding import seed_description, select_seed
from .specializations import STAGE_NAMES, legal_card_targets, legal_player_targets, single_attribute_count, specialization_name


class CardButton(QPushButton):
    """Uniform 3:4 portrait card widget."""

    def __init__(self, width: int = 84, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, round(width * 4 / 3))
        self.top_left = ""
        self.top_right = ""
        self.card_id = ""
        self.cost_items: list[tuple[str, int]] = []
        self.setStyleSheet(
            "QPushButton { text-align:center; padding:3px; background:#fff6e8; border:2px solid #b8b8b8; }"
            "QPushButton:hover { border-color:#6b8799; }"
        )

    def set_card_content(self, top_left: str, top_right: str, card_id: str, cost_items: list[tuple[str, int]]) -> None:
        self.top_left = top_left
        self.top_right = top_right
        self.card_id = card_id
        self.cost_items = cost_items
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        scale = self.height() / 84
        inset_x, inset_y = round(4 * scale), round(3 * scale)
        rect = self.rect().adjusted(inset_x, inset_y, -inset_x, -inset_y)

        def draw(text: str, x: int, y: int, width: int, height: int, size: float, bold: bool, align: Qt.AlignmentFlag) -> None:
            if not text:
                return
            font = QFont(QApplication.font())
            point_size = size * scale
            font.setBold(bold)
            while point_size > 4.2:
                font.setPointSizeF(point_size)
                if QFontMetricsF(font).horizontalAdvance(text) <= width - 2:
                    break
                point_size -= .3
            font.setPointSizeF(max(4.2, point_size))
            painter.setFont(font)
            painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
            painter.drawText(x, y, width, height, int(align | Qt.AlignmentFlag.AlignVCenter), text)

        left_width = round(rect.width() * .67)
        draw(self.top_left, rect.left(), rect.top() + round(scale), left_width, round(15 * scale), 8.5, False, Qt.AlignmentFlag.AlignLeft)
        draw(self.top_right, rect.left() + left_width, rect.top() + round(scale), rect.width() - left_width, round(15 * scale), 8.5, False, Qt.AlignmentFlag.AlignRight)
        draw(self.card_id, rect.left(), rect.top() + round(21 * scale), rect.width(), round(21 * scale), 10, True, Qt.AlignmentFlag.AlignHCenter)

        if not self.cost_items:
            draw("无成本", rect.left(), rect.top() + round(47 * scale), rect.width(), round(15 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
            return
        column_width = rect.width() / len(self.cost_items)
        for index, (attribute, amount) in enumerate(self.cost_items):
            x = round(rect.left() + index * column_width)
            width = round(column_width + 0.5)
            draw(attribute, x, rect.top() + round(48 * scale), width, round(13 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
            draw(str(amount), x, rect.top() + round(62 * scale), width, round(14 * scale), 8, True, Qt.AlignmentFlag.AlignHCenter)


def paint_resource_tile(widget: QWidget, text: str, fill: QColor, text_color: QColor) -> None:
    painter = QPainter(widget)
    painter.setPen(QColor("#9b9388"))
    painter.setBrush(fill)
    painter.drawRect(widget.rect().adjusted(0, 0, -1, -1))
    painter.setPen(text_color)
    painter.setFont(widget.font())
    painter.drawText(widget.rect(), Qt.AlignmentFlag.AlignCenter, text)


class ResourceButton(QPushButton):
    """Draw every resource button in the same rectangle across enabled states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(53, 36)
        font = QFont(self.font())
        font.setPixelSize(10)
        self.setFont(font)
        self.fill_color = QColor("#d2d0cc")
        self.text_color = QColor("#8b8985")

    def set_visual(self, fill: str, text_color: str) -> None:
        if self.fill_color.name() == fill and self.text_color.name() == text_color:
            return
        self.fill_color = QColor(fill)
        self.text_color = QColor(text_color)
        self.update()

    def paintEvent(self, _event) -> None:
        paint_resource_tile(self, self.text(), self.fill_color, self.text_color)


class LightResourceLabel(QLabel):
    """Non-interactive light pool indicator matching the resource buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(53, 36)
        font = QFont(self.font())
        font.setPixelSize(10)
        self.setFont(font)

    def paintEvent(self, _event) -> None:
        paint_resource_tile(self, self.text(), QColor("#f3e7bd"), QColor("#263238"))


class DotWidget(QWidget):
    """Colored resource marker, optionally with a remove control."""

    def __init__(self, color: str, remove=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = color
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self.dot_label = QLabel("●")
        self.dot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dot_label.setStyleSheet(f"color:{color};font-size:20px;")
        grid.addWidget(self.dot_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        if remove is not None:
            x = QPushButton("×")
            x.setFixedSize(16, 16)
            x.setStyleSheet("QPushButton { padding:0; min-height:0; border:0; color:#633f3b; background:transparent; font-size:13px; font-weight:bold; }")
            x.clicked.connect(remove)
            grid.addWidget(x, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

    def set_color(self, color: str) -> None:
        if color == self.color:
            return
        self.color = color
        self.dot_label.setStyleSheet(f"color:{color};font-size:20px;")


class DotStackWidget(QWidget):
    """Compact vertical resource stack with partially overlapping dots."""

    def __init__(self, color: str, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color = QColor(color)
        self.count = count
        self.setFixedSize(18, 70)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        for index in range(self.count):
            painter.drawEllipse(3, 2 + index * 6, 12, 12)


class OwnedCardView(CardButton):
    WIDTH = 52
    HEIGHT = round(WIDTH * 4 / 3)

    def __init__(self, card: PetCard, *, dual: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(self.WIDTH, parent)
        self.card = card
        attributes = "/".join(attribute.value for attribute in card.attributes)
        transformed = f" ↓{card.transformed_from}" if card.transformed_from else ""
        cost_items = [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)]
        self.set_card_content(attributes, str(card.score), f"{card.card_id}{transformed}", cost_items)
        self.setToolTip(f"{card.card_id}{transformed}\n{attributes} · {card.score}分")
        if dual:
            self.setStyleSheet("QPushButton { background:#fff1bf; border:3px solid #d9a817; padding:1px; }")
            glow = QGraphicsDropShadowEffect(self)
            glow.setBlurRadius(8)
            glow.setOffset(0, 0)
            glow.setColor(QColor("#efc84a"))
            self.setGraphicsEffect(glow)
        else:
            self.setStyleSheet("QPushButton { background:#fffaf0; border:1px solid #d5cbbb; padding:1px; }")


class DraggableDualCard(OwnedCardView):
    REVEAL_HEIGHT = 20

    def __init__(self, card: PetCard, board: QWidget, drop_handler, draggable: bool) -> None:
        super().__init__(card, dual=True, parent=board)
        self.board = board
        self.drop_handler = drop_handler
        self.draggable = draggable
        self.press_global: QPoint | None = None
        self.drag_offset = QPoint()
        self.dragging = False

    def mousePressEvent(self, event) -> None:
        if self.draggable and event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.drag_offset = self.press_global - self.mapToGlobal(QPoint(0, 0))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            if not self.dragging and (global_pos - self.press_global).manhattanLength() >= QApplication.startDragDistance():
                top_left = self.mapToGlobal(QPoint(0, 0))
                self.setParent(self.board)
                self.move(self.board.mapFromGlobal(top_left))
                self.show()
                self.raise_()
                self.grabMouse()
                self.dragging = True
            if self.dragging:
                self.move(self.board.mapFromGlobal(global_pos - self.drag_offset))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.press_global is not None and event.button() == Qt.MouseButton.LeftButton:
            if self.dragging:
                self.releaseMouse()
                self.drop_handler(self.card, event.globalPosition().toPoint())
            self.press_global = None
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MagicGemsQtApp(QMainWindow):
    WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
    CARD_WIDTH = 75
    RESOURCE_COLORS = {
        Attribute.WATER: ("#a6d4f5", "#2379b9"),
        Attribute.FIRE: ("#f4aba3", "#bf4640"),
        Attribute.GRASS: ("#b7dd9a", "#588e38"),
        Attribute.CUTE: ("#f0b7d4", "#bf5894"),
        Attribute.DARK: ("#c8ccd2", "#747b86"),
    }
    RESOURCE_NAMES = {
        Attribute.WATER: "水", Attribute.FIRE: "火", Attribute.GRASS: "草",
        Attribute.CUTE: "萌", Attribute.DARK: "恶",
    }

    def __init__(self, seed: int = 1, ai_battle: bool = False, interval: float = .5, seed_mode: str = "fixed") -> None:
        super().__init__()
        self.seed, self.seed_mode = seed, seed_mode
        self.ai_battle, self.ai_interval = ai_battle, max(0.0, interval)
        players = [Player(f"AI-{i}") for i in range(1, 5)] if ai_battle else [Player("你"), Player("AI-2"), Player("AI-3"), Player("AI-4")]
        self.game = Game(create_state(players, build_decks(seed), seed))
        self.selected_card: PetCard | None = None
        self.resource_selection: list[Attribute] = []
        self.resource_notice = ""
        self.market_slots: dict[int, dict[str, int]] = {level: {} for level in (1, 2, 3)}
        self.log_messages: list[tuple[str, str, bool]] = []
        self.dual_move_order: dict[str, int] = {}
        self.dual_move_sequence = 0
        self.ai_timer = QTimer(self)
        self.ai_timer.setSingleShot(True)
        self.ai_timer.timeout.connect(self.play_ai_turn)
        self.specialization_scheduled = False
        self.specialization_dialog: QDialog | None = None
        self.start_game_log()
        self.setWindowTitle(f"洛克王国：魔法宝石 · 种子 {seed}")
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setStyleSheet("QMainWindow, QWidget { background:#f4efe6; color:#263238; }")
        self.build_ui()
        self.refresh()
        self.log(f"对局开始，{seed_description(seed, seed_mode)}")

    def start_game_log(self) -> None:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        self.game_log_path = log_dir / f"magic_gems_{datetime.now():%Y%m%d_%H%M%S_%f}.log"
        self.game_logger = logging.getLogger(f"magic-gems-qt-{id(self)}")
        self.game_logger.setLevel(logging.INFO)
        self.game_logger.propagate = False
        self.game_log_handler = logging.FileHandler(self.game_log_path, encoding="utf-8")
        self.game_logger.addHandler(self.game_log_handler)

    @staticmethod
    def section(title: str, parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(parent)
        frame.setStyleSheet("QFrame { background:#e9e0d3; border:1px solid #c5b9aa; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(3)
        label = QLabel(title)
        label.setFixedHeight(18)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("font-weight:bold;background:transparent;border:0;")
        layout.addWidget(label)
        return frame, layout

    def build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#263238;border:0;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 2, 14, 2)
        title = QLabel("魔法宝石")
        title.setStyleSheet("color:white;font-size:20px;font-weight:bold;background:transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color:white;font-size:13px;background:transparent;")
        header_layout.addWidget(self.status_label)
        restart_button = QPushButton("重新开始")
        restart_button.clicked.connect(self.confirm_restart)
        header_layout.addWidget(restart_button)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(10)
        outer.addLayout(body, 1)

        left = QWidget()
        left.setFixedWidth(728)
        self.left_layout = QVBoxLayout(left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(7)
        body.addWidget(left)

        market, market_outer = self.section("公共宠物市场")
        self.market_layout = QVBoxLayout()
        self.market_layout.setContentsMargins(0, 0, 0, 0)
        self.market_layout.setSpacing(3)
        market_outer.addLayout(self.market_layout)
        self.left_layout.addWidget(market, 7)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(6)
        self.players_frame, self.players_layout = self.section("玩家状态（固定四人）")
        self.log_frame, self.log_layout = self.section("行动记录（全部操作）")
        self.reserved_frame, self.reserved_layout = self.section("预购卡牌")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setUndoRedoEnabled(False)
        self.log_view.setStyleSheet("background:#fffaf0;border:1px solid #c5bcae;")
        self.log_layout.addWidget(self.log_view, 1)
        lower_row.addWidget(self.players_frame, 3)
        lower_row.addWidget(self.log_frame, 3)
        lower_row.addWidget(self.reserved_frame, 1)
        self.left_layout.addLayout(lower_row, 3)

        right = QWidget()
        right.setFixedWidth(350)
        self.right_layout = QVBoxLayout(right)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(6)
        body.addWidget(right)

        summary = QWidget()
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(6)
        self.purchasing_power_frame = QFrame()
        self.purchasing_power_frame.setStyleSheet("QFrame { background:#e9e0d3; border:1px solid #c5b9aa; }")
        self.purchasing_power_layout = QVBoxLayout(self.purchasing_power_frame)
        self.purchasing_power_layout.setContentsMargins(5, 3, 5, 3)
        self.purchasing_power_layout.setSpacing(1)
        self.pool_resource_frame, self.pool_resource_layout = self.section("已有资源")
        self.purchased_frame, self.purchased_layout = self.section("已购买卡牌")
        self.purchasing_power_frame.setFixedHeight(70)
        self.pool_resource_frame.setFixedHeight(108)
        summary_layout.addWidget(self.purchasing_power_frame)
        summary_layout.addWidget(self.pool_resource_frame)
        summary_layout.addWidget(self.purchased_frame, 1)
        self.right_layout.addWidget(summary, 1)

        self.controls_frame, self.controls_layout = self.section("行动与公共资源")
        self.controls_layout.setSpacing(0)
        self.controls_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        title_item = self.controls_layout.takeAt(0)
        self.controls_title = title_item.widget() if title_item is not None else None
        if self.controls_title is not None:
            self.controls_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.controls_title.setGeometry(8, 6, 160, 18)
            title_spacer = QWidget(self.controls_frame)
            title_spacer.setFixedHeight(18)
            title_spacer.setStyleSheet("background:transparent;border:0;")
            self.controls_layout.insertWidget(0, title_spacer)
        self.controls_frame.setFixedHeight(258)
        self.right_layout.addWidget(self.controls_frame)

    @staticmethod
    def clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                MagicGemsQtApp.clear_layout(child_layout)

    @staticmethod
    def clear_section_body(layout) -> None:
        """Clear dynamic content while keeping the section heading in slot zero."""
        while layout.count() > 1:
            item = layout.takeAt(1)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
            elif child_layout is not None:
                MagicGemsQtApp.clear_layout(child_layout)

    def render_market(self) -> None:
        self.clear_layout(self.market_layout)
        self.sync_market_slots()
        self.market_buttons: dict[int, list[CardButton | None]] = {}
        state = self.game.state
        self.market_layout.addStretch(1)
        for level in (3, 2, 1):
            row = QHBoxLayout()
            row.setSpacing(5)
            row.setAlignment(Qt.AlignmentFlag.AlignLeft)
            label = QLabel(f"{level}级市场")
            label.setFixedWidth(82)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size:14px;font-weight:bold;background:transparent;border:0;")
            row.addWidget(label)
            buttons: list[CardButton | None] = []
            cards_by_slot = {
                self.market_slots[level][card.card_id]: card
                for card in state.market.cards[level]
            }
            for slot in range(5):
                card = cards_by_slot.get(slot)
                if card is None:
                    placeholder = QWidget()
                    placeholder.setFixedSize(self.CARD_WIDTH, round(self.CARD_WIDTH * 4 / 3))
                    placeholder.setStyleSheet("background:transparent;border:0;")
                    row.addWidget(placeholder)
                    buttons.append(None)
                    continue
                button = CardButton(self.CARD_WIDTH)
                button.clicked.connect(lambda _=False, c=card: self.select_card(c))
                row.addWidget(button)
                buttons.append(button)
            self.market_buttons[level] = buttons
            self.market_layout.addLayout(row)
            for slot, button in enumerate(buttons):
                card = cards_by_slot.get(slot)
                if button is not None and card is not None:
                    self.configure_card(button, card)
            self.market_layout.addStretch(1)

    def sync_market_slots(self) -> None:
        """Keep each market card in its existing visual slot across refreshes."""
        for level in (1, 2, 3):
            cards = self.game.state.market.cards[level]
            card_ids = {card.card_id for card in cards}
            previous = self.market_slots[level]
            released_slots = [slot for card_id, slot in previous.items() if card_id not in card_ids]
            current = {card_id: slot for card_id, slot in previous.items() if card_id in card_ids}
            occupied = set(current.values())
            free_slots = released_slots + [slot for slot in range(5) if slot not in occupied and slot not in released_slots]
            for card in cards:
                if card.card_id in current:
                    continue
                if not free_slots:
                    break
                current[card.card_id] = free_slots.pop(0)
            self.market_slots[level] = current

    def configure_card(self, button: CardButton, card: PetCard) -> None:
        marker = "▶" if card is self.selected_card else "★" if self.can_buy(card) else "·"
        transformed = f" ↓{card.transformed_from}" if card.transformed_from else ""
        attributes = "/".join(attribute.value for attribute in card.attributes)
        cost_items = [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)]
        shown_id = f"{marker} {card.card_id}{transformed}" if card is self.selected_card else f"{card.card_id}{transformed}"
        button.set_card_content(attributes, str(card.score), shown_id, cost_items)
        cost = " ".join(f"{attribute}{amount}" for attribute, amount in cost_items) or "无成本"
        button.setToolTip(f"{card.card_id}{transformed}\n{attributes} · {card.score}分\n费用：{cost}")
        background = "#f4d484" if card is self.selected_card else "#dceecf" if self.can_buy(card) else "#fff6e8"
        button.setStyleSheet(f"QPushButton {{ text-align:center; padding:2px; background:{background}; border:2px solid #b8b8b8; }} QPushButton:hover {{ border-color:#6b8799; }}")
        # QSS may change a QPushButton's size hint, so reapply the portrait bounds afterward.
        width = button.maximumWidth()
        button.setFixedSize(width, round(width * 4 / 3))

    def can_buy(self, card: PetCard) -> bool:
        state = self.game.state
        if state.current_player != 0 or state.finished or state.pending_specializations or self.resource_selection:
            return False
        try:
            payment_for(state.current(), card, self.dual_discount_choices(state.current()))
        except RuleError:
            return False
        return True

    @staticmethod
    def dual_discount_choices(player: Player) -> list[Attribute]:
        return [
            chosen if chosen in card.attributes else card.attributes[0]
            for card, chosen in player.purchased
            if card.is_dual
        ]

    def render_resource_zones(self) -> None:
        self.clear_layout(self.purchasing_power_layout)
        self.clear_section_body(self.pool_resource_layout)
        player = self.game.state.players[0]
        discounts = player.permanent_discounts
        for card, chosen in player.purchased:
            if card.is_dual:
                discounts[chosen if chosen in card.attributes else card.attributes[0]] += 1
        power_row = QHBoxLayout()
        power_row.setSpacing(2)
        for attribute in ATTRIBUTES:
            column = QVBoxLayout()
            name = QLabel(self.RESOURCE_NAMES[attribute])
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("background:transparent;border:0;font-size:11px;")
            resources = player.resources[attribute]
            discount = discounts[attribute]
            total = QLabel(f"{resources}+{discount}={resources + discount}")
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total.setStyleSheet(f"background:transparent;border:0;font-size:12px;font-weight:bold;color:{self.RESOURCE_COLORS[attribute][1]};")
            total.setToolTip(f"{self.RESOURCE_NAMES[attribute]}资源 {resources} + 折扣 {discount} = 购买力 {resources + discount}")
            column.addWidget(name)
            column.addWidget(total)
            power_row.addLayout(column, 1)
        self.purchasing_power_layout.addLayout(power_row)

        fixed_row = QHBoxLayout()
        fixed_row.setSpacing(2)
        for attribute in ATTRIBUTES:
            column = QVBoxLayout()
            name = QLabel(self.RESOURCE_NAMES[attribute])
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("background:transparent;border:0;font-size:11px;")
            column.addWidget(name)
            count = player.resources[attribute]
            column.setSpacing(0)
            column.addWidget(DotStackWidget(self.RESOURCE_COLORS[attribute][1], count), 0, Qt.AlignmentFlag.AlignHCenter)
            column.addStretch()
            fixed_row.addLayout(column, 1)
        self.pool_resource_layout.addLayout(fixed_row)

    def render_reserved(self) -> None:
        self.clear_section_body(self.reserved_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(4)
        for index, card in enumerate(self.game.state.players[0].reserved):
            button = CardButton(44)
            button.clicked.connect(lambda _=False, c=card: self.select_card(c))
            self.configure_card(button, card)
            grid.addWidget(button, index, 0, Qt.AlignmentFlag.AlignHCenter)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        scroll.setWidget(content)
        self.reserved_layout.addWidget(scroll, 1)

    def render_purchased(self) -> None:
        self.clear_section_body(self.purchased_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        columns_layout = QHBoxLayout(content)
        columns_layout.setContentsMargins(2, 2, 2, 2)
        columns_layout.setSpacing(3)

        singles = {attribute: [] for attribute in ATTRIBUTES}
        duals = {attribute: [] for attribute in ATTRIBUTES}
        player = self.game.state.players[0]
        for card, chosen in player.purchased:
            if card.is_dual:
                pile_attribute = chosen if chosen in card.attributes else card.attributes[0]
                if card.card_id not in self.dual_move_order:
                    self.dual_move_sequence += 1
                    self.dual_move_order[card.card_id] = self.dual_move_sequence
                duals[pile_attribute].append((self.dual_move_order[card.card_id], card))
            else:
                singles[card.attributes[0]].append(card)

        self.purchased_columns: dict[Attribute, QWidget] = {}
        draggable = self.game.state.current_player == 0 and not self.ai_battle and not self.game.state.finished and not self.game.state.pending_specializations
        for attribute in ATTRIBUTES:
            column = QFrame(content)
            column.setMinimumWidth(48)
            column.setStyleSheet("QFrame { background:#f5eee3; border:1px solid #d1c5b6; }")
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(2, 3, 2, 3)
            column_layout.setSpacing(2)
            column_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            name = QLabel(self.RESOURCE_NAMES[attribute])
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("background:transparent;border:0;font-weight:bold;")
            column_layout.addWidget(name)
            self.purchased_columns[attribute] = column
            duals[attribute].sort(key=lambda item: item[0])
            cards = [(card, False) for card in singles[attribute]] + [
                (card, True) for _order, card in duals[attribute]
            ]
            stack = QWidget(column)
            stack.setFixedWidth(56)
            stack_height = OwnedCardView.HEIGHT if cards else 1
            if cards:
                stack_height += (len(cards) - 1) * DraggableDualCard.REVEAL_HEIGHT
            stack.setFixedHeight(stack_height)
            for index, (card, is_dual) in enumerate(cards):
                card_view = (
                    DraggableDualCard(card, content, self.drop_dual_card, draggable)
                    if is_dual else OwnedCardView(card, parent=stack)
                )
                card_view.setParent(stack)
                card_view.move((stack.width() - card_view.width()) // 2, index * DraggableDualCard.REVEAL_HEIGHT)
                card_view.show()
                card_view.raise_()
            column_layout.addWidget(stack, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            columns_layout.addWidget(column, 1)
        scroll.setWidget(content)
        self.purchased_layout.addWidget(scroll, 1)

    def drop_dual_card(self, card: PetCard, global_pos: QPoint) -> None:
        board = next((column for column in self.purchased_columns.values() if column.geometry().contains(column.parentWidget().mapFromGlobal(global_pos))), None)
        if board is not None:
            target = next(attribute for attribute, column in self.purchased_columns.items() if column is board)
            if target in card.attributes:
                player = self.game.state.players[0]
                for index, (owned_card, _chosen) in enumerate(player.purchased):
                    if owned_card is card:
                        player.purchased[index] = (owned_card, target)
                        self.dual_move_sequence += 1
                        self.dual_move_order[card.card_id] = self.dual_move_sequence
                        self.log(f"{card.card_id} 双属性折扣吸附到 {target.value} 属性区")
                        break
        self.refresh()

    def render_controls(self) -> None:
        state = self.game.state
        if not hasattr(self, "resource_buttons"):
            self.controls_layout.addSpacing(35)
            self.hint_label = QLabel()
            self.hint_label.setWordWrap(False)
            self.hint_label.setFixedHeight(20)
            self.hint_label.setStyleSheet("background:transparent;border:0;color:#625a51;font-size:10px;")
            self.controls_layout.addWidget(self.hint_label)

            self.controls_layout.addSpacing(19)
            selected_frame = QFrame()
            selected_frame.setFixedHeight(32)
            selected_frame.setStyleSheet("QFrame { background:#f5eee3; border:1px solid #d1c5b6; }")
            selected_row = QHBoxLayout(selected_frame)
            selected_row.setContentsMargins(4, 0, 3, 0)
            selected_row.setSpacing(1)
            selected_title = QLabel("本回合选中资源")
            selected_title.setFixedWidth(96)
            selected_title.setStyleSheet("background:transparent;border:0;font-size:11px;")
            selected_row.addWidget(selected_title)
            self.selection_markers = []
            for index in range(3):
                marker = DotWidget("#766f66", lambda _=False, i=index: self.cancel_resource(i))
                marker.setFixedSize(24, 26)
                marker.hide()
                selected_row.addWidget(marker)
                self.selection_markers.append(marker)
            self.selection_empty_label = QLabel("—")
            self.selection_empty_label.setStyleSheet("background:transparent;border:0;color:#766f66;")
            selected_row.addWidget(self.selection_empty_label)
            selected_row.addStretch()
            self.controls_layout.addWidget(selected_frame)

            self.controls_layout.addSpacing(19)
            public_row = QHBoxLayout()
            public_row.setSpacing(3)
            public_row.setContentsMargins(0, 0, 0, 0)
            self.resource_buttons = {}
            for attribute in ATTRIBUTES:
                button = ResourceButton()
                button.clicked.connect(lambda _=False, a=attribute: self.choose_resource(a))
                public_row.addWidget(button)
                self.resource_buttons[attribute] = button
            self.light_count_label = LightResourceLabel()
            self.light_count_label.setToolTip("公共光系灵碎剩余数量；预购公共市场卡牌时获得。")
            public_row.addWidget(self.light_count_label)
            self.controls_layout.addLayout(public_row)

            self.controls_layout.addSpacing(19)
            card_actions = QHBoxLayout()
            card_actions.setSpacing(0)
            self.confirm_button = QPushButton("确认")
            self.confirm_button.clicked.connect(self.confirm_current_action)
            self.reserve_button = QPushButton("预购")
            self.reserve_button.clicked.connect(self.reserve_selected)
            self.cancel_button = QPushButton("取消")
            self.cancel_button.clicked.connect(self.cancel_current_selection)
            action_style = (
                "QPushButton { background:#f7f6f2; color:#263238; border:1px solid #b8b3ab; padding:0; }"
                "QPushButton:disabled { background:#d2d0cc; color:#8b8985; border:1px solid #b8b3ab; padding:0; }"
            )
            for button, width in ((self.confirm_button, 111), (self.reserve_button, 112), (self.cancel_button, 111)):
                button.setFixedSize(width, 27)
                button.setStyleSheet(action_style)
                card_actions.addWidget(button)
            self.controls_layout.addLayout(card_actions)

        action_enabled = state.current_player == 0 and not state.finished and not self.ai_battle and not state.pending_specializations
        hint_text = self.resource_notice or "三种不同属性各1枚，或同属性2枚（资源池≥4）；选好后确认。"
        if self.hint_label.text() != hint_text:
            self.hint_label.setText(hint_text)
        self.selection_empty_label.setVisible(not self.resource_selection)
        for index, marker in enumerate(self.selection_markers):
            if index < len(self.resource_selection):
                attribute = self.resource_selection[index]
                marker.set_color(self.RESOURCE_COLORS[attribute][1])
                if not marker.isVisible():
                    marker.show()
            else:
                if marker.isVisible():
                    marker.hide()

        selection_complete = (
            (len(self.resource_selection) == 2 and len(set(self.resource_selection)) == 1)
            or len(self.resource_selection) == 3
        )
        for attribute, button in self.resource_buttons.items():
            count = state.resource_pool[attribute]
            button_enabled = action_enabled and self.selected_card is None and count > 0 and not selection_complete
            selected = attribute in self.resource_selection
            fill = self.RESOURCE_COLORS[attribute][1 if selected else 0] if button_enabled else "#d2d0cc"
            text_color = "#fffaf0" if button_enabled and selected else "#263238" if button_enabled else "#8b8985"
            button_text = f"● {attribute.value} {count}"
            if button.text() != button_text:
                button.setText(button_text)
            if button.isEnabled() != button_enabled:
                button.setEnabled(button_enabled)
            button.set_visual(fill, text_color)
        light_text = f"● 光 {state.light_pool}"
        if self.light_count_label.text() != light_text:
            self.light_count_label.setText(light_text)

        can_action = action_enabled and self.selected_card is not None and not self.resource_selection
        can_confirm_resource = action_enabled and bool(self.resource_selection) and self.resource_selection_is_valid()
        confirm_enabled = can_confirm_resource or (can_action and self.can_buy(self.selected_card))
        reserve_enabled = can_action
        cancel_enabled = action_enabled and (bool(self.resource_selection) or self.selected_card is not None)
        if self.confirm_button.isEnabled() != confirm_enabled:
            self.confirm_button.setEnabled(confirm_enabled)
        if self.reserve_button.isEnabled() != reserve_enabled:
            self.reserve_button.setEnabled(reserve_enabled)
        if self.cancel_button.isEnabled() != cancel_enabled:
            self.cancel_button.setEnabled(cancel_enabled)

    def render_players(self) -> None:
        self.clear_section_body(self.players_layout)
        state = self.game.state
        for index, player in enumerate(state.players):
            discount_counts = player.permanent_discounts
            for card, chosen in player.purchased:
                if card.is_dual:
                    discount_counts[chosen if chosen in card.attributes else card.attributes[0]] += 1
            discounts = "".join(f"{attribute.value}{n}" for attribute, n in discount_counts.items() if n) or "无"
            progress = "".join(f"{attribute.value}{min(single_attribute_count(player, attribute), 3)}" for attribute in ATTRIBUTES if single_attribute_count(player, attribute)) or "无"
            text = (
                f"{'▶ ' if index == state.current_player else ''}{player.name}　{player.score}分　R{player.resource_count}/{player.resource_capacity}　购{len(player.purchased)}预{len(player.reserved)}\n"
                f"{' '.join(f'{attribute.value}{player.resources[attribute]}' for attribute in ATTRIBUTES)}　"
                f"光{player.light}{f'+{player.temporary_light}' if player.temporary_light else ''}　折{discounts}　专{progress}"
            )
            label = QLabel(text)
            label.setFixedHeight(39)
            label.setWordWrap(True)
            label.setStyleSheet("background:#fffaf0;border:1px solid #c8bcae;padding:1px;font-size:10px;")
            self.players_layout.addWidget(label)

    def refresh(self) -> None:
        state = self.game.state
        self.status_label.setText(f"种子 {self.seed}　·　第 {state.round_number} 轮　·　当前玩家：{state.current().name}")
        self.render_market()
        self.render_resource_zones()
        self.render_reserved()
        self.render_purchased()
        self.render_controls()
        self.render_players()
        if state.pending_specializations:
            owner = state.pending_specializations[0].player_index
            if owner == 0 and not self.ai_battle and not self.specialization_scheduled:
                self.specialization_scheduled = True
                QTimer.singleShot(0, self.prompt_specialization)
            elif not state.finished:
                self.ai_timer.start(round(self.ai_interval * 1000))
        elif not state.finished and (self.ai_battle or state.current_player != 0):
            self.ai_timer.start(round(self.ai_interval * 1000))
        else:
            self.ai_timer.stop()

    def select_card(self, card: PetCard) -> None:
        if self.resource_selection or self.game.state.current_player != 0 or self.game.state.finished or self.game.state.pending_specializations or self.ai_battle:
            return
        if self.selected_card is card:
            self.selected_card = None
        elif self.selected_card is None:
            self.selected_card = card
        else:
            return
        self.refresh()

    def cancel_card_selection(self) -> None:
        self.selected_card = None
        self.refresh()

    def confirm_current_action(self) -> None:
        if self.resource_selection:
            self.confirm_resources()
        elif self.selected_card is not None:
            self.buy_selected()

    def cancel_current_selection(self) -> None:
        if self.resource_selection:
            self.cancel_resource_selection()
        elif self.selected_card is not None:
            self.cancel_card_selection()

    def choose_resource(self, attribute: Attribute) -> None:
        state = self.game.state
        if (
            self.selected_card is not None
            or state.current_player != 0
            or state.finished
            or state.pending_specializations
            or self.ai_battle
            or state.resource_pool[attribute] <= 0
        ):
            return
        player = state.current()
        self.resource_notice = ""
        if not self.resource_selection:
            self.resource_selection.append(attribute)
        elif len(self.resource_selection) == 1:
            first = self.resource_selection[0]
            if attribute == first:
                if state.resource_pool[attribute] < 4:
                    self.resource_notice = f"{attribute.value}资源池不足4枚，不能领取同种两枚。"
                elif player.resource_count + 2 > player.resource_capacity:
                    self.resource_notice = "资源容量不足，不能领取两枚资源。"
                else:
                    self.resource_selection.append(attribute)
            elif player.resource_count + 3 > player.resource_capacity:
                self.resource_notice = "资源容量不足，不能领取三种不同资源。"
            else:
                self.resource_selection.append(attribute)
        elif len(self.resource_selection) == 2:
            if len(set(self.resource_selection)) == 1:
                self.resource_notice = "已选同种两枚；请确认领取，或点圆点旁的 × 撤销。"
            elif attribute in self.resource_selection:
                self.resource_notice = "要领取三种不同资源，请选择尚未选过的属性；也可点资源圆点旁的 × 撤销。"
            elif player.resource_count + 3 > player.resource_capacity:
                self.resource_notice = "资源容量不足，不能领取三种不同资源。"
            else:
                self.resource_selection.append(attribute)
        else:
            self.resource_notice = "选择已完整；请确认领取，或点圆点旁的 × 修改。"
        self.render_controls()

    def cancel_resource(self, index: int) -> None:
        if 0 <= index < len(self.resource_selection):
            self.resource_selection.pop(index)
            self.resource_notice = ""
        self.render_controls()

    def cancel_resource_selection(self) -> None:
        self.resource_selection.clear()
        self.resource_notice = ""
        self.render_controls()

    def resource_selection_is_valid(self) -> bool:
        if len(self.resource_selection) == 2 and len(set(self.resource_selection)) == 1:
            attribute = self.resource_selection[0]
            return self.game.state.resource_pool[attribute] >= 4
        return len(self.resource_selection) == 3 and len(set(self.resource_selection)) == 3

    def confirm_resources(self) -> None:
        if not self.resource_selection_is_valid():
            self.resource_notice = "资源选择不完整或不符合规则，请调整后再确认。"
            self.render_controls()
            return
        if len(self.resource_selection) == 2:
            self.perform(Action("same", attributes=(self.resource_selection[0],)))
        else:
            self.perform(Action("different", attributes=tuple(self.resource_selection)))

    def buy_selected(self) -> None:
        if self.selected_card is None:
            return
        choices = self.dual_discount_choices(self.game.state.players[0])
        self.perform(Action("buy", card=self.selected_card, dual_choices=tuple(choices)))

    def reserve_selected(self) -> None:
        if self.selected_card is not None:
            self.perform(Action("reserve", card=self.selected_card))

    def prompt_specialization(self) -> None:
        self.specialization_scheduled = False
        if not self.game.state.pending_specializations:
            return
        effect = self.game.state.pending_specializations[0]
        if effect.player_index != 0 or self.ai_battle:
            self.ai_timer.start(round(self.ai_interval * 1000))
            return
        cards = legal_card_targets(self.game.state, effect)
        players = legal_player_targets(self.game.state, effect)
        dialog = QDialog(self)
        self.specialization_dialog = dialog
        dialog.setWindowTitle("结算属性专精")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(specialization_name(effect)))
        if cards:
            for card in cards:
                button = QPushButton(f"{card.card_id}　{card.level}级　{card.cost_text()} → {card.score}分")
                button.clicked.connect(lambda _=False, c=card: self.settle_specialization(dialog, Action("specialization", card=c)))
                layout.addWidget(button)
        elif players:
            for index in players:
                player = self.game.state.players[index]
                button = QPushButton(f"{player.name} · {player.score}分 · 资源{player.resource_count}")
                button.clicked.connect(lambda _=False, i=index: self.settle_specialization(dialog, Action("specialization", target_player=i)))
                layout.addWidget(button)
        else:
            button = QPushButton("结算效果")
            button.clicked.connect(lambda: self.settle_specialization(dialog, Action("specialization")))
            layout.addWidget(button)
        dialog.finished.connect(lambda: setattr(self, "specialization_dialog", None))
        dialog.exec()

    def settle_specialization(self, dialog: QDialog, action: Action) -> None:
        dialog.accept()
        self.perform(action)

    @staticmethod
    def action_text(action: Action) -> str:
        if action.kind == "buy": return f"购买 {action.card.card_id if action.card else ''}"
        if action.kind == "reserve": return f"预购 {action.card.card_id if action.card else ''}"
        if action.kind == "different": return "获取资源：" + "、".join(f"{a.value}1" for a in action.attributes)
        if action.kind == "same": return f"获取资源：{action.attributes[0].value}2"
        if action.kind == "specialization": return "结算属性专精"
        return action.kind

    @staticmethod
    def format_specialization_record(
        effect: SpecializationEffect,
        player_name: str,
        message: str,
    ) -> str:
        attribute, stage = effect.attribute, effect.stage
        effect_name = STAGE_NAMES[(attribute, stage)]
        result = message.partition("：")[2] or message

        if "没有" in result and "效果失效" in result:
            outcome = "没有符合条件的目标，效果未生效！"
        elif attribute == Attribute.WATER and stage == 1:
            match = re.search(r"([^ ]+) 的(.+?)系成本 -1", result)
            outcome = f"{match.group(1)}的{match.group(2)}系费用降低了1！" if match else "目标宠物的费用降低了！"
        elif attribute == Attribute.WATER and stage == 2:
            outcome = f"{player_name}下一次购买的费用减免了！"
        elif attribute == Attribute.FIRE and stage == 1:
            match = re.search(r"资源上限提高到\s*(\d+)", result)
            outcome = f"{player_name}的资源上限提高到{match.group(1)}了！" if match else f"{player_name}的资源上限提高了！"
        elif attribute == Attribute.FIRE and stage == 2:
            match = re.search(r"烧掉市场\s*(\d+)\s*张", result)
            outcome = f"公共市场中{match.group(1)}张宠物卡被烧毁并重新补充了！" if match else "公共市场的宠物卡被烧毁并重新补充了！"
        elif attribute == Attribute.GRASS and stage == 1:
            match = re.search(r"([^ ]+) 的分数 \+1", result)
            outcome = f"{match.group(1)}的分数提高了1分！" if match else "目标宠物的分数提高了1分！"
        elif attribute == Attribute.GRASS and stage == 2:
            match = re.search(r"获得\s*(\d+)\s*枚临时光系灵碎", result)
            outcome = f"{player_name}获得了{match.group(1)}枚临时光系灵碎！" if match else f"{player_name}获得了临时光系灵碎！"
        elif attribute == Attribute.CUTE and stage == 1:
            match = re.search(r"([^ ]+) 萌化为 (.+?) 数值模板并移入 (\d+) 级市场", result)
            outcome = f"{match.group(1)}萌化为{match.group(2)}的数值并移入{match.group(3)}级市场了！" if match else "目标宠物已萌化并移入低一级市场！"
        elif attribute == Attribute.CUTE and stage == 2:
            details = result.strip()
            outcome = f"所有玩家符合条件的已购宠物都萌化了（{details}）！" if "没有可萌化" not in details else "所有玩家都没有可萌化的已购宠物，效果未生效！"
        elif attribute == Attribute.DARK and stage == 1:
            match = re.search(r"(.+?) 从 (.+?) 偷取 1 枚(.+?)系灵碎", result)
            outcome = f"{match.group(1)}从{match.group(2)}偷取了1枚{match.group(3)}系灵碎！" if match else "没有可偷取的灵碎，效果未生效！"
        elif attribute == Attribute.DARK and stage == 2:
            match = re.search(r"(.+?) 从 (.+?) 偷走 (.+)", result)
            outcome = f"{match.group(1)}从{match.group(2)}夺取了宠物{match.group(3)}！" if match else "没有可夺取的宠物，效果未生效！"
        else:
            outcome = f"{result.rstrip('。！')}！"

        return f"【{effect_name}】玩家{player_name}触发了{attribute.value}系专精阶段{stage}，{outcome}"

    def perform(self, action: Action) -> None:
        try:
            actor_player = self.game.state.current()
            actor = actor_player.name
            specialization_effect = (
                self.game.state.pending_specializations[0]
                if action.kind == "specialization" and self.game.state.pending_specializations
                else None
            )
            specialization_attribute = specialization_effect.attribute if specialization_effect else None
            previous_duals = actor_player.dual_cards()
            messages = self.game.execute(action)
            if action.kind == "buy":
                for old_card, selected_attribute in zip(previous_duals, action.dual_choices):
                    if selected_attribute in old_card.attributes:
                        for index, (owned, _chosen) in enumerate(actor_player.purchased):
                            if owned is old_card:
                                actor_player.purchased[index] = (owned, selected_attribute)
                                break
                if action.card is not None and action.card.is_dual:
                    for index, (owned, _chosen) in enumerate(actor_player.purchased):
                        if owned is action.card:
                            initial_attribute = action.card.attributes[0]
                            actor_player.purchased[index] = (owned, initial_attribute)
                            break
            if action.kind == "specialization" and specialization_effect is not None:
                result = messages[0] if messages else "效果未生效"
                record = self.format_specialization_record(specialization_effect, actor, result)
                self.log(record, specialization_attribute, bold=True)
            else:
                self.log(f"{actor}：{self.action_text(action)}")
                for message in messages:
                    if action.kind == "buy" and "触发" in message and "系专精" in message:
                        continue
                    self.log(message)
            self.selected_card = None
            self.resource_selection.clear()
            self.resource_notice = ""
            self.refresh()
            if self.game.state.finished:
                QMessageBox.information(self, "对局结束", "胜者：" + "、".join(player.name for player in self.game.winners()))
        except (RuleError, ValueError) as error:
            self.game_logger.warning("操作无效：%s", error)
            QMessageBox.warning(self, "操作无效", str(error))

    def play_ai_turn(self) -> None:
        if self.game.state.finished or (not self.ai_battle and self.game.state.current_player == 0):
            return
        self.perform(choose_action(self.game))

    def log(self, message: str, attribute: Attribute | None = None, *, bold: bool = False) -> None:
        timestamped = f"[{datetime.now():%H:%M:%S}] {message}"
        color = self.RESOURCE_COLORS[attribute][1] if attribute is not None else "#263238"
        self.log_messages.insert(0, (timestamped, color, bold))
        contents = "<br>".join(
            f'<span style="color:{entry_color}">{"<b>" if entry_bold else ""}{html_escape(entry)}{"</b>" if entry_bold else ""}</span>'
            for entry, entry_color, entry_bold in self.log_messages
        )
        self.log_view.setHtml(f'<html><body style="margin:2px">{contents}</body></html>')
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.log_view.setTextCursor(cursor)
        self.log_view.verticalScrollBar().setValue(0)
        self.game_logger.info(message)

    def restart(self) -> None:
        players = [Player(f"AI-{i}") for i in range(1, 5)] if self.ai_battle else [Player("你"), Player("AI-2"), Player("AI-3"), Player("AI-4")]
        self.game = Game(create_state(players, build_decks(self.seed), self.seed))
        self.dual_move_order.clear()
        self.dual_move_sequence = 0
        self.selected_card = None
        self.resource_selection.clear()
        self.resource_notice = ""
        self.log_messages.clear()
        self.log_view.clear()
        self.game_logger.removeHandler(self.game_log_handler)
        self.game_log_handler.close()
        self.start_game_log()
        self.log(f"对局重新开始，{seed_description(self.seed, self.seed_mode)}")
        self.refresh()

    def confirm_restart(self) -> None:
        answer = QMessageBox.question(self, "重新开始", "当前对局将结束并使用相同种子重新开局，继续吗？")
        if answer == QMessageBox.StandardButton.Yes:
            self.restart()

    def closeEvent(self, event) -> None:
        self.ai_timer.stop()
        self.game_logger.removeHandler(self.game_log_handler)
        self.game_log_handler.close()
        super().closeEvent(event)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="启动 Qt6 图形界面")
    seed_group = parser.add_mutually_exclusive_group()
    seed_group.add_argument("--seed", type=int)
    seed_group.add_argument("--random-seed", action="store_true")
    args = parser.parse_args()
    seed, mode = select_seed(args.seed, args.random_seed, default_random=True)
    app = QApplication(sys.argv)
    window = MagicGemsQtApp(seed, seed_mode=mode)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
