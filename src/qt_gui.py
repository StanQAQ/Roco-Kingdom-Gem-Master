"""Qt 6 desktop interface for Magic Gems."""
from __future__ import annotations

from datetime import datetime
from html import escape as html_escape
from io import BytesIO
import copy
import logging
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, Property, QPauseAnimation, QRect, Signal, Qt, QParallelAnimationGroup, QPropertyAnimation,
    QSequentialAnimationGroup, QTimer,
)
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetricsF,
    QPainter, QPainterPath, QPalette, QPen, QPixmap, QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QScrollBar, QTextEdit,
    QStackedWidget, QStyle, QStyleOptionButton, QStylePainter, QVBoxLayout, QWidget,
)

from .ai import choose_action
from .cards import build_decks
from .game import Action, Game
from .models import ATTRIBUTES, Attribute, PetCard, Player, SpecializationEffect
from .rules import RuleError, create_state, payment_for
from .seeding import seed_description, select_seed
from .specializations import STAGE_NAMES, legal_card_targets, legal_player_targets, single_attribute_count, specialization_name
from .theme import (
    ATTRIBUTE_ICON_DIR, ATTRIBUTE_ICON_FILES, CARD_CORNER_RADIUS,
    HOVER_INSET_COLOR, HOVER_SURFACE_COLOR, ORNAMENT_COLOR, PANEL_COLOR,
    PLAYER_CURRENT_COLOR, PLAYER_STATUS_COLOR, RESERVED_AREA_BACKGROUND,
    SERIF_FONT_FAMILIES, TABLETOP_COLOR, TEXT_COLOR,
    RESOURCE_COLORS as ATTRIBUTE_COLORS,
    RESOURCE_SHARD_DIR, RESOURCE_SHARD_FILES,
)


_RESOURCE_SHARD_PIXMAPS: dict[tuple[Attribute, int, float], QPixmap] = {}
_SAGE_SHARD_PIXMAPS: dict[tuple[int, float], QPixmap] = {}
_ATTRIBUTE_ICON_PIXMAPS: dict[tuple[Attribute, int, float], QPixmap] = {}
_RESOURCE_SHARD_SOURCES: dict[Attribute, QPixmap] = {}
_SAGE_SHARD_SOURCE: QPixmap | None = None
_ATTRIBUTE_ICON_SOURCES: dict[Attribute, QPixmap] = {}


def preferred_serif_family() -> str:
    """Use Source Han Serif when installed, with a native serif fallback."""
    installed = {family.casefold(): family for family in QFontDatabase.families()}
    return next(
        (installed[name.casefold()] for name in SERIF_FONT_FAMILIES if name.casefold() in installed),
        SERIF_FONT_FAMILIES[0],
    )


def resource_shard_pixmap(attribute: Attribute, size: int, device_pixel_ratio: float = 1.0) -> QPixmap:
    device_pixel_ratio = max(1.0, float(device_pixel_ratio))
    key = (attribute, size, device_pixel_ratio)
    if key not in _RESOURCE_SHARD_PIXMAPS:
        if attribute not in _RESOURCE_SHARD_SOURCES:
            image_path = (
                Path(__file__).resolve().parent.parent
                / "media" / RESOURCE_SHARD_DIR / RESOURCE_SHARD_FILES[attribute]
            )
            _RESOURCE_SHARD_SOURCES[attribute] = QPixmap(str(image_path))
        source = _RESOURCE_SHARD_SOURCES[attribute]
        pixel_size = round(size * device_pixel_ratio)
        pixmap = source.scaled(
            pixel_size,
            pixel_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ) if not source.isNull() else QPixmap()
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(device_pixel_ratio)
        _RESOURCE_SHARD_PIXMAPS[key] = pixmap
    return _RESOURCE_SHARD_PIXMAPS[key]


def sage_shard_pixmap(size: int, device_pixel_ratio: float = 1.0) -> QPixmap:
    global _SAGE_SHARD_SOURCE
    device_pixel_ratio = max(1.0, float(device_pixel_ratio))
    key = (size, device_pixel_ratio)
    if key not in _SAGE_SHARD_PIXMAPS:
        if _SAGE_SHARD_SOURCE is None:
            image_path = (
                Path(__file__).resolve().parent.parent
                / "media" / RESOURCE_SHARD_DIR / "贤者零碎.png"
            )
            _SAGE_SHARD_SOURCE = QPixmap(str(image_path))
        source = _SAGE_SHARD_SOURCE
        pixel_size = round(size * device_pixel_ratio)
        pixmap = source.scaled(
            pixel_size,
            pixel_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ) if not source.isNull() else QPixmap()
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(device_pixel_ratio)
        _SAGE_SHARD_PIXMAPS[key] = pixmap
    return _SAGE_SHARD_PIXMAPS[key]


def attribute_icon_pixmap(
    attribute: Attribute,
    size: int,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    device_pixel_ratio = max(1.0, float(device_pixel_ratio))
    key = (attribute, size, device_pixel_ratio)
    if key not in _ATTRIBUTE_ICON_PIXMAPS:
        if attribute not in _ATTRIBUTE_ICON_SOURCES:
            image_path = (
                Path(__file__).resolve().parent.parent
                / "media" / ATTRIBUTE_ICON_DIR / ATTRIBUTE_ICON_FILES[attribute]
            )
            _ATTRIBUTE_ICON_SOURCES[attribute] = QPixmap(str(image_path))
        source = _ATTRIBUTE_ICON_SOURCES[attribute]
        pixel_size = round(size * device_pixel_ratio)
        _ATTRIBUTE_ICON_PIXMAPS[key] = source.scaled(
            pixel_size,
            pixel_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ) if not source.isNull() else QPixmap()
        if not _ATTRIBUTE_ICON_PIXMAPS[key].isNull():
            _ATTRIBUTE_ICON_PIXMAPS[key].setDevicePixelRatio(device_pixel_ratio)
    return _ATTRIBUTE_ICON_PIXMAPS[key]


class CardButton(QPushButton):
    """Uniform 3:4 portrait card widget."""

    STYLE_REFERENCE_HEIGHT = 100
    TOP_INFO_Y = 1
    TOP_INFO_HEIGHT = 15
    CARD_ID_Y = 21
    PRICE_SHARD_Y = 64
    SHOW_TOP_INFO = True
    impactTintChanged = Signal(QColor)
    impactContentOpacityChanged = Signal(float)

    def __init__(self, width: int = 84, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, round(width * 4 / 3))
        self._card_style: dict[str, object] | None = None
        self._last_card_style_metrics: tuple[object, ...] | None = None
        self._card_glow_color: QColor | None = None
        self._card_glow_base_radius = 0
        self.top_left = ""
        self.top_right = ""
        self.card_id = ""
        self.display_card_id = ""
        self.cost_items: list[tuple[str, int]] = []
        self._impact_tint = QColor(0, 0, 0, 0)
        self._impact_content_opacity = 1.0
        self.set_card_style(
            background="#fff6e8",
            border_color="#b8b8b8",
            border_width=2,
            padding=3,
            hover_border_color="#6b8799",
        )

    def set_card_style(
        self,
        *,
        background: str,
        border_color: str,
        border_width: int = 2,
        padding: int = 2,
        text_color: str | None = None,
        hover_border_color: str | None = None,
        object_name: str | None = None,
    ) -> None:
        """Set card chrome using the same proportional scale as its contents."""
        self._card_style = {
            "background": background,
            "border_color": border_color,
            "border_width": border_width,
            "padding": padding,
            "text_color": text_color,
            "hover_border_color": hover_border_color,
            "object_name": object_name,
        }
        self._apply_card_style()

    def _apply_card_style(self) -> None:
        if self._card_style is None:
            return
        scale = self.height() / self.STYLE_REFERENCE_HEIGHT
        border_width = max(1, int(self._card_style["border_width"] * scale))
        padding = max(0, int(self._card_style["padding"] * scale))
        radius = max(1, round(CARD_CORNER_RADIUS * scale))
        signature = (
            border_width,
            padding,
            radius,
            self._card_style["background"],
            self._card_style["border_color"],
            self._card_style["text_color"],
            self._card_style["hover_border_color"],
            self._card_style["object_name"],
        )
        if signature == self._last_card_style_metrics:
            return
        self._last_card_style_metrics = signature
        selector = "QPushButton"
        if self._card_style["object_name"]:
            selector += f"#{self._card_style['object_name']}"
        text_color = self._card_style["text_color"]
        color_rule = f" color:{text_color};" if text_color else ""
        stylesheet = (
            f"{selector} {{ text-align:center;{color_rule} "
            f"padding:{padding}px; background:{self._card_style['background']}; "
            f"border:{border_width}px solid {self._card_style['border_color']}; "
            f"border-radius:{radius}px; }}"
        )
        hover_color = self._card_style["hover_border_color"]
        if hover_color:
            stylesheet += f"{selector}:hover {{ border-color:{hover_color}; }}"
        self.setStyleSheet(stylesheet)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Cards are resized during move/scale animations as well as in piles.
        # Refresh only when rounded stylesheet metrics actually change.
        self._apply_card_style()
        self._apply_card_glow()

    def set_card_glow(self, color: str, base_blur_radius: float = 8) -> None:
        self._card_glow_color = QColor(color)
        self._card_glow_base_radius = base_blur_radius
        effect = self.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(self)
            effect.setOffset(0, 0)
            self.setGraphicsEffect(effect)
        effect.setColor(self._card_glow_color)
        self._apply_card_glow()

    def _apply_card_glow(self) -> None:
        if self._card_glow_color is None:
            return
        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(
                max(1, self._card_glow_base_radius * self.height() / self.STYLE_REFERENCE_HEIGHT)
            )

    def set_card_content(self, top_left: str, top_right: str, card_id: str, cost_items: list[tuple[str, int]]) -> None:
        self.top_left = top_left
        self.top_right = top_right
        self.card_id = card_id
        self.display_card_id = card_id
        self.cost_items = cost_items
        self.update()

    @Property(QColor, notify=impactTintChanged)
    def impactTint(self) -> QColor:
        return QColor(self._impact_tint)

    @impactTint.setter
    def impactTint(self, color: QColor) -> None:
        if self._impact_tint == color:
            return
        self._impact_tint = QColor(color)
        self.impactTintChanged.emit(self._impact_tint)
        self.update()

    @Property(float, notify=impactContentOpacityChanged)
    def impactContentOpacity(self) -> float:
        return self._impact_content_opacity

    @impactContentOpacity.setter
    def impactContentOpacity(self, opacity: float) -> None:
        opacity = max(0.0, min(1.0, float(opacity)))
        if self._impact_content_opacity == opacity:
            return
        self._impact_content_opacity = opacity
        self.impactContentOpacityChanged.emit(opacity)
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

        def draw(text: str, x: int, y: int, width: int, height: int, size: float, bold: bool, align: Qt.AlignmentFlag, *, heavy: bool = False) -> None:
            if not text:
                return
            font = QFont(QApplication.font())
            point_size = size * scale
            font.setBold(bold)
            if heavy:
                font.setWeight(QFont.Weight.Black)
            minimum_point_size = max(1.0, 4.2 * self.height() / self.STYLE_REFERENCE_HEIGHT)
            while point_size > minimum_point_size:
                font.setPointSizeF(point_size)
                if QFontMetricsF(font).horizontalAdvance(text) <= width - 2:
                    break
                point_size -= .3
            font.setPointSizeF(max(minimum_point_size, point_size))
            painter.setFont(font)
            painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
            painter.drawText(x, y, width, height, int(align | Qt.AlignmentFlag.AlignVCenter), text)

        painter.save()
        painter.setOpacity(self._impact_content_opacity)
        left_width = round(rect.width() * .67)
        if self.SHOW_TOP_INFO:
            attribute_by_name = {attribute.value: attribute for attribute in ATTRIBUTES}
            top_parts = self.top_left.split("/")
            top_attributes = [attribute_by_name.get(part) for part in top_parts]
            if top_attributes and all(attribute is not None for attribute in top_attributes):
                icon_gap = max(1, round(2 * scale))
                info_height = round(self.TOP_INFO_HEIGHT * scale)
                icon_size = max(
                    1,
                    min(
                        round(15 * scale),
                        info_height,
                        (left_width - icon_gap * (len(top_attributes) - 1)) // len(top_attributes),
                    ),
                )
                icons = [
                    attribute_icon_pixmap(attribute, icon_size, self.devicePixelRatioF())
                    for attribute in top_attributes
                ]
                if all(not icon.isNull() for icon in icons):
                    icon_y = rect.top() + round(self.TOP_INFO_Y * scale) + (info_height - icon_size) // 2
                    icon_x = rect.left()
                    for icon in icons:
                        painter.save()
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                        painter.drawPixmap(icon_x, icon_y, icon)
                        painter.restore()
                        icon_x += icon_size + icon_gap
                else:
                    draw(
                        self.top_left, rect.left(), rect.top() + round(self.TOP_INFO_Y * scale),
                        left_width, info_height, 8.5, False, Qt.AlignmentFlag.AlignLeft,
                    )
            else:
                draw(
                    self.top_left, rect.left(), rect.top() + round(self.TOP_INFO_Y * scale),
                    left_width, round(self.TOP_INFO_HEIGHT * scale), 8.5, False,
                    Qt.AlignmentFlag.AlignLeft,
                )
            draw(
                self.top_right, rect.left() + left_width, rect.top() + round(self.TOP_INFO_Y * scale),
                rect.width() - left_width, round(self.TOP_INFO_HEIGHT * scale), 10.5, True,
                Qt.AlignmentFlag.AlignRight, heavy=True,
            )
        draw(
            self.display_card_id, rect.left(), rect.top() + round(self.CARD_ID_Y * scale),
            rect.width(), round(21 * scale), 10, True, Qt.AlignmentFlag.AlignHCenter,
        )

        if not self.cost_items:
            draw("无成本", rect.left(), rect.top() + round(47 * scale), rect.width(), round(15 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
        else:
            column_width = rect.width() / len(self.cost_items)
            for index, (attribute, amount) in enumerate(self.cost_items):
                x = round(rect.left() + index * column_width)
                width = round(column_width + 0.5)
                cost_attribute = next((item for item in ATTRIBUTES if item.value == attribute), None)
                amount_on_shard = False
                if cost_attribute is None:
                    draw(attribute, x, rect.top() + round(48 * scale), width, round(13 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
                elif self.top_left == "魔法师":
                    column_pixels = max(1, round(width))
                    icon_size = max(1, min(round(13 * scale), column_pixels))
                    icon = attribute_icon_pixmap(cost_attribute, icon_size, self.devicePixelRatioF())
                    if icon.isNull():
                        draw(attribute, x, rect.top() + round(48 * scale), width, round(13 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
                    else:
                        painter.save()
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                        icon_x = x + (width - icon_size) // 2
                        icon_y = rect.top() + round(48 * scale) + (round(13 * scale) - icon_size) // 2
                        painter.drawPixmap(icon_x, icon_y, icon)
                        painter.restore()
                    draw(str(amount), x, rect.top() + round(62 * scale), width, round(14 * scale), 9, True, Qt.AlignmentFlag.AlignHCenter)
                else:
                    # Keep the shard at its established size. The larger price
                    # numeral is fitted independently to the available column.
                    column_pixels = max(1, round(width))
                    icon_size = max(1, min(round(13 * scale), column_pixels))
                    icon = resource_shard_pixmap(cost_attribute, icon_size, self.devicePixelRatioF())
                    if icon.isNull():
                        draw(attribute, x, rect.top() + round(48 * scale), width, round(13 * scale), 7.5, False, Qt.AlignmentFlag.AlignHCenter)
                    else:
                        painter.save()
                        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                        icon_x = x + (width - icon_size) // 2
                        icon_y = rect.top() + round(self.PRICE_SHARD_Y * scale) + (round(13 * scale) - icon_size) // 2
                        painter.drawPixmap(icon_x, icon_y, icon)
                        number = str(amount)
                        number_font = QFont(QApplication.font())
                        number_font.setBold(True)
                        # Keep the quantity on its shard. Fit the glyph to the
                        # actual icon bounds instead of moving it below on
                        # narrow cards or multi-attribute prices.
                        pixel_size = max(1, round(icon_size * 1.0))
                        number_font.setPixelSize(pixel_size)
                        metrics = QFontMetricsF(number_font)
                        text_width_limit = max(1, column_pixels - 3)
                        while pixel_size > 1 and metrics.horizontalAdvance(number) > text_width_limit:
                            pixel_size -= 1
                            number_font.setPixelSize(pixel_size)
                            metrics = QFontMetricsF(number_font)
                        number_path = QPainterPath()
                        number_x = icon_x + (icon_size - metrics.horizontalAdvance(number)) / 2
                        number_y = icon_y + (icon_size - metrics.height()) / 2 + metrics.ascent()
                        number_path.addText(number_x, number_y, number_font, number)
                        outline = QPen(QColor("#43291d"), max(0.35, 0.8 * scale))
                        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                        painter.strokePath(number_path, outline)
                        painter.fillPath(number_path, QColor("#fffaf0"))
                        painter.restore()
                        amount_on_shard = True
                if not amount_on_shard:
                    draw(str(amount), x, rect.top() + round(62 * scale), width, round(14 * scale), 9, True, Qt.AlignmentFlag.AlignHCenter)
        painter.restore()

        if self._impact_tint.alpha():
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            rounded = QPainterPath()
            rounded.addRoundedRect(
                self.rect().adjusted(0, 0, -1, -1),
                CARD_CORNER_RADIUS * self.height() / self.STYLE_REFERENCE_HEIGHT,
                CARD_CORNER_RADIUS * self.height() / self.STYLE_REFERENCE_HEIGHT,
            )
            painter.setClipPath(rounded)
            painter.fillPath(rounded, self._impact_tint)
            painter.restore()


class WoodTableWidget(QWidget):
    """Paint the burgundy tabletop with a restrained teal wood-grain pattern."""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(TABLETOP_COLOR))

        # Fine, low-contrast grain keeps the background textured without
        # competing with the cards or making text harder to read.
        for index, y in enumerate(range(10, self.height(), 24)):
            color = QColor(ORNAMENT_COLOR)
            color.setAlpha(22 if index % 2 else 30)
            painter.setPen(QPen(color, 1))
            path = QPainterPath()
            path.moveTo(0, y)
            x = 0
            while x < self.width():
                drift = math.sin((index + 1) * (x + 19) / 173) * 2.2
                path.cubicTo(x + 32, y - 2 + drift, x + 66, y + 2 - drift, x + 100, y + drift)
                x += 100
            painter.drawPath(path)

        painter.setPen(QPen(QColor(69, 135, 149, 46), 1))
        for knot_x, knot_y in ((self.width() * .18, self.height() * .28), (self.width() * .79, self.height() * .73)):
            painter.drawEllipse(round(knot_x), round(knot_y), 28, 7)
            painter.drawEllipse(round(knot_x + 5), round(knot_y + 2), 17, 3)


class AgedParchmentFrame(QFrame):
    """A warm panel with a subtle teal ornamental print."""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(0, 0, -1, -1)
        painter.setBrush(QColor(PANEL_COLOR))
        painter.setPen(QPen(QColor(ORNAMENT_COLOR), 2))
        painter.drawRect(area)

        # Deterministic, very faint flecks give the panels a printed finish.
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(160):
            x = (index * 73 + 29) % max(1, self.width())
            y = (index * 47 + 13) % max(1, self.height())
            shade = QColor(69, 135, 149, 10 + index % 7)
            painter.setBrush(shade)
            painter.drawEllipse(x, y, 1 + index % 2, 1 + (index // 3) % 2)


class BaroqueTitlePage(QWidget):
    """Title screen backing with a hand-drawn, antique baroque border."""

    @staticmethod
    def draw_corner(painter: QPainter, x: int, y: int, flip_x: int, flip_y: int) -> None:
        painter.save()
        painter.translate(x, y)
        painter.scale(flip_x, flip_y)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ornament_pen = QPen(QColor(ORNAMENT_COLOR), 5)
        ornament_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        ornament_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(ornament_pen)
        flourish = QPainterPath()
        flourish.moveTo(4, 94)
        flourish.cubicTo(35, 93, 25, 64, 50, 51)
        flourish.cubicTo(72, 40, 99, 56, 90, 77)
        flourish.cubicTo(82, 96, 56, 85, 65, 69)
        flourish.cubicTo(71, 59, 84, 64, 80, 73)
        flourish.moveTo(48, 52)
        flourish.cubicTo(42, 28, 62, 16, 92, 18)
        flourish.cubicTo(81, 37, 72, 45, 51, 54)
        flourish.moveTo(48, 53)
        flourish.cubicTo(23, 49, 17, 29, 23, 9)
        flourish.cubicTo(42, 20, 49, 31, 51, 52)
        flourish.moveTo(50, 55)
        flourish.cubicTo(36, 78, 17, 81, 7, 70)
        painter.drawPath(flourish)
        painter.setPen(QPen(QColor("#83b3bc"), 1.5))
        painter.drawEllipse(43, 45, 14, 14)
        painter.drawEllipse(5, 91, 8, 8)
        painter.drawEllipse(89, 14, 8, 8)
        painter.restore()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(TABLETOP_COLOR))
        for inset, color, width in ((12, ORNAMENT_COLOR, 2), (20, "#3f1b1b", 3), (26, "#83b3bc", 1)):
            painter.setPen(QPen(QColor(color), width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))
        self.draw_corner(painter, 27, 27, 1, 1)
        self.draw_corner(painter, self.width() - 27, 27, -1, 1)
        self.draw_corner(painter, 27, self.height() - 27, 1, -1)
        self.draw_corner(painter, self.width() - 27, self.height() - 27, -1, -1)
        painter.setPen(QPen(QColor(131, 179, 188, 105), 1))
        for x in range(145, self.width() - 145, 90):
            painter.drawEllipse(x, 21, 3, 3)
            painter.drawEllipse(x, self.height() - 24, 3, 3)


class SoundEffects:
    """Small synthesized UI sounds, played through each platform's audio backend."""

    SAMPLE_RATE = 22050

    def __init__(self) -> None:
        self._coin_wav = self._make_wav(((880, 1250, 0.055), (1360, 1980, 0.075)))
        self._click_wav = self._make_wav(((1850, 1250, 0.028),))
        self._player = self._find_player()

    @classmethod
    def _make_wav(cls, notes: tuple[tuple[float, float, float], ...]) -> bytes:
        pcm = bytearray()
        for note_index, (start_frequency, end_frequency, duration) in enumerate(notes):
            sample_count = int(cls.SAMPLE_RATE * duration)
            phase = 0.0
            for index in range(sample_count):
                progress = index / max(1, sample_count - 1)
                frequency = start_frequency + (end_frequency - start_frequency) * progress
                phase += 2 * math.pi * frequency / cls.SAMPLE_RATE
                attack = min(1.0, progress * 45)
                decay = (1.0 - progress) ** 1.8
                envelope = attack * decay
                metallic = math.sin(phase) + .28 * math.sin(phase * 2.76)
                sample = int(max(-1.0, min(1.0, metallic * envelope * .32)) * 32767)
                pcm.extend(struct.pack("<h", sample))
            if note_index + 1 < len(notes):
                pcm.extend(b"\x00\x00" * int(cls.SAMPLE_RATE * .012))
        stream = BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(cls.SAMPLE_RATE)
            wav.writeframes(pcm)
        return stream.getvalue()

    @staticmethod
    def _find_player() -> list[str] | None:
        if sys.platform == "darwin" and Path("/usr/bin/afplay").exists():
            return ["/usr/bin/afplay"]
        for candidate in ("pw-play", "paplay", "aplay"):
            executable = shutil.which(candidate)
            if executable:
                return [executable, "-q"] if candidate == "aplay" else [executable]
        return None

    @staticmethod
    def _remove_when_finished(process: subprocess.Popen, path: str) -> None:
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    def play(self, sound: str) -> None:
        is_coin = sound == "coin"
        if sys.platform == "win32":
            try:
                import winsound

                sequence = ((940, 48), (1420, 58), (1900, 78)) if is_coin else ((1680, 26),)
                threading.Thread(
                    target=lambda: [winsound.Beep(frequency, duration) for frequency, duration in sequence],
                    daemon=True,
                ).start()
                return
            except (ImportError, RuntimeError):
                pass

        if self._player:
            wav_data = self._coin_wav if is_coin else self._click_wav
            sound_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as sound_file:
                    sound_file.write(wav_data)
                    sound_path = sound_file.name
                process = subprocess.Popen(
                    [*self._player, sound_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                threading.Thread(
                    target=self._remove_when_finished,
                    args=(process, sound_path),
                    daemon=True,
                ).start()
                return
            except OSError:
                if sound_path is not None:
                    try:
                        Path(sound_path).unlink(missing_ok=True)
                    except OSError:
                        pass

        QApplication.beep()
        if is_coin:
            QTimer.singleShot(70, QApplication.beep)
            QTimer.singleShot(140, QApplication.beep)


def paint_resource_tile(
    widget: QWidget,
    text: str,
    fill: QColor,
    text_color: QColor,
    attribute: Attribute | None = None,
    icon_pixmap: QPixmap | None = None,
) -> None:
    painter = QPainter(widget)
    painter.setPen(QColor(ORNAMENT_COLOR))
    painter.setBrush(fill)
    painter.drawRect(widget.rect().adjusted(0, 0, -1, -1))
    painter.setPen(text_color)
    painter.setFont(widget.font())
    if attribute is None and icon_pixmap is None:
        painter.drawText(widget.rect(), Qt.AlignmentFlag.AlignCenter, text)
        return

    icon_size = min(20, widget.height() - 8)
    pixmap = (
        resource_shard_pixmap(attribute, icon_size, widget.devicePixelRatioF())
        if attribute is not None else icon_pixmap
    )
    if pixmap is None:
        painter.drawText(widget.rect(), Qt.AlignmentFlag.AlignCenter, text)
        return
    icon_width = icon_size if attribute is not None else round(pixmap.deviceIndependentSize().width())
    text_width = round(QFontMetricsF(widget.font()).horizontalAdvance(text))
    content_width = icon_width + 3 + text_width
    left = max(2, (widget.width() - content_width) // 2)
    icon_y = (widget.height() - icon_size) // 2
    if not pixmap.isNull():
        painter.save()
        if not widget.isEnabled():
            painter.setOpacity(.42)
        painter.drawPixmap(left, icon_y, pixmap)
        painter.restore()
    else:
        painter.drawText(QRect(left, 0, icon_size, widget.height()), Qt.AlignmentFlag.AlignCenter, "●")
    painter.setPen(text_color)
    painter.drawText(
        QRect(left + icon_width + 3, 0, widget.width() - left - icon_width - 3, widget.height()),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        text,
    )


class ResourceButton(QPushButton):
    """Draw every resource button in the same rectangle across enabled states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(53, 36)
        self.attribute: Attribute | None = None
        font = QFont(self.font())
        font.setPixelSize(10)
        self.setFont(font)
        self.fill_color = QColor("#d2d0cc")
        self.text_color = QColor("#8b8985")

    def set_resource(self, attribute: Attribute, count: int) -> None:
        self.attribute = attribute
        self.setText(str(count))
        self.update()

    def set_visual(self, fill: str, text_color: str) -> None:
        if self.fill_color.name() == fill and self.text_color.name() == text_color:
            return
        self.fill_color = QColor(fill)
        self.text_color = QColor(text_color)
        self.update()

    def paintEvent(self, _event) -> None:
        paint_resource_tile(self, self.text(), self.fill_color, self.text_color, self.attribute)


class LightResourceLabel(QLabel):
    """Non-interactive light pool indicator matching the resource buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(53, 36)
        font = QFont(self.font())
        font.setPixelSize(10)
        self.setFont(font)

    def paintEvent(self, _event) -> None:
        paint_resource_tile(
            self,
            self.text(),
            QColor("#f3e7bd"),
            QColor(TEXT_COLOR),
            icon_pixmap=sage_shard_pixmap(min(20, self.height() - 8), self.devicePixelRatioF()),
        )


class DotWidget(QWidget):
    """Resource shard marker that can be clicked to remove a selection."""

    def __init__(self, attribute: Attribute | None, on_clicked=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.attribute = attribute
        self.on_clicked = on_clicked
        self.dot_label = QLabel()
        self.dot_label.setFixedSize(20, 20)
        self.dot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dot_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_attribute(attribute)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.dot_label, 0, Qt.AlignmentFlag.AlignCenter)
        if on_clicked is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if (
            self.on_clicked is not None
            and self.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.on_clicked()
            event.accept()
            return
        super().mousePressEvent(event)

    def set_attribute(self, attribute: Attribute | None) -> None:
        if attribute == self.attribute and self.dot_label.pixmap() is not None:
            return
        self.attribute = attribute
        pixmap = resource_shard_pixmap(attribute, 20, self.dot_label.devicePixelRatioF()) if attribute is not None else QPixmap()
        self.dot_label.setPixmap(pixmap)
        if pixmap.isNull() and attribute is not None:
            self.dot_label.setText("●")
            self.dot_label.setStyleSheet(f"color:{ATTRIBUTE_COLORS[attribute][1]};font-size:17px;")
        else:
            self.dot_label.setText("")
            self.dot_label.setStyleSheet("background:transparent;border:0;")


class DotStackWidget(QWidget):
    """Compact vertical stack of partially overlapping resource shards."""

    def __init__(self, attribute: Attribute, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.attribute = attribute
        self.count = count
        self.setFixedSize(18, 70)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        pixmap = resource_shard_pixmap(self.attribute, 16, self.devicePixelRatioF())
        for index in range(self.count):
            y = index * 6
            if not pixmap.isNull():
                painter.drawPixmap(1, y, pixmap)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(ATTRIBUTE_COLORS[self.attribute][1]))
                painter.drawEllipse(3, y + 2, 12, 12)


def specialization_glow_color(card: PetCard) -> str | None:
    water = Attribute.WATER in card.specialization_glows
    grass = Attribute.GRASS in card.specialization_glows
    if water and grass:
        return "#4f8996"
    if water:
        return ATTRIBUTE_COLORS[Attribute.WATER][1]
    if grass:
        return ATTRIBUTE_COLORS[Attribute.GRASS][1]
    return None


def apply_specialization_glow(widget: QWidget, card: PetCard) -> None:
    color = specialization_glow_color(card)
    if color is None:
        return
    if isinstance(widget, CardButton):
        widget.set_card_glow(color)
        return
    glow = QGraphicsDropShadowEffect(widget)
    glow.setBlurRadius(max(1, 8 * widget.height() / CardButton.STYLE_REFERENCE_HEIGHT))
    glow.setOffset(0, 0)
    glow.setColor(QColor(color))
    widget.setGraphicsEffect(glow)


class OwnedCardView(CardButton):
    WIDTH = 52
    HEIGHT = round(WIDTH * 4 / 3)
    # The exposed strip includes the attribute/score row but ends before the ID row.
    REVEAL_HEIGHT = 16

    def __init__(
        self,
        card: PetCard,
        *,
        dual: bool = False,
        parent: QWidget | None = None,
        width: int | None = None,
    ) -> None:
        card_width = self.WIDTH if width is None else width
        super().__init__(card_width, parent)
        self.card = card
        attributes = "/".join(attribute.value for attribute in card.attributes)
        transformed = f" ↓{card.transformed_from}" if card.transformed_from else ""
        cost_items = [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)]
        self.set_card_content(attributes, str(card.effective_score), f"{card.card_id}{transformed}", cost_items)
        self.card_id = card.card_id
        glow_color = specialization_glow_color(card)
        if dual:
            self.set_card_style(
                background="#fff1bf",
                border_color="#d9a817",
                border_width=3,
                padding=1,
            )
            self.set_card_glow("#efc84a")
        else:
            border_color = glow_color or "#d5cbbb"
            self.set_card_style(
                background="#fffaf0",
                border_color=border_color,
                border_width=2,
                padding=1,
            )
        apply_specialization_glow(self, card)


class WizardCardView(CardButton):
    WIDTH, HEIGHT = 60, 80
    CARD_ID_Y = 6
    SHOW_TOP_INFO = False

    def __init__(self, wizard, parent: QWidget | None = None, *, width: int | None = None) -> None:
        card_width = self.WIDTH if width is None else width
        super().__init__(card_width, parent)
        self.wizard = wizard
        requirements = [(attribute.value, amount) for attribute, amount in wizard.requirements]
        self.set_card_content("魔法师", f"+{wizard.score}", wizard.name, requirements)
        self.set_card_style(
            background="#fff1bf",
            border_color="#d2a83d",
            border_width=2,
            padding=2,
            text_color=TEXT_COLOR,
            hover_border_color="#a77914",
        )


class DraggableDualCard(OwnedCardView):
    def __init__(self, card: PetCard, board: QWidget, drop_handler, draggable: bool) -> None:
        super().__init__(card, dual=True, parent=board)
        self.board = board
        self.drop_handler = drop_handler
        self.draggable = draggable
        self.press_global: QPoint | None = None
        self.drag_offset = QPoint()
        self.dragging = False

    def mousePressEvent(self, event) -> None:
        if (
            self.draggable
            and not getattr(self.window(), "interaction_locked", False)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.press_global = event.globalPosition().toPoint()
            self.drag_offset = self.press_global - self.mapToGlobal(QPoint(0, 0))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.press_global is not None and getattr(self.window(), "interaction_locked", False):
            if self.dragging:
                self.releaseMouse()
            self.press_global = None
            self.dragging = False
            event.accept()
            return
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


class PlayerStatusHoverCard(QFrame):
    """A parchment-themed in-game detail card shown beside a player row."""

    PARCHMENT_COLOR = PANEL_COLOR
    BORDER_COLOR = ORNAMENT_COLOR

    def __init__(self, parent: QWidget) -> None:
        # Keep this as a child overlay, not a native Qt.ToolTip window. Native
        # tooltips get platform-specific slide/fade effects and opaque corners.
        super().__init__(parent)
        self.setObjectName("playerStatusHoverCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        self.setMinimumWidth(300)
        self.setMaximumWidth(430)
        self.setStyleSheet(
            f"QFrame#playerStatusHoverCard {{ background:transparent; color:{TEXT_COLOR}; border:0; }}"
            f"QFrame#playerHoverHeader {{ background:{TEXT_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; }}"
            f"QLabel#playerHoverName {{ color:{PANEL_COLOR}; font-size:14px; font-weight:bold; background:transparent; border:0; }}"
            f"QLabel#playerHoverScore {{ color:{PANEL_COLOR}; font-size:14px; font-weight:bold; background:transparent; border:0; }}"
            f"QFrame#playerHoverResources {{ background:{HOVER_SURFACE_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; }}"
            f"QFrame#playerHoverInfo {{ background:{HOVER_SURFACE_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; }}"
            f"QLabel#playerHoverSection {{ color:{TEXT_COLOR}; font-size:9px; font-weight:bold; background:transparent; border:0; }}"
            f"QLabel#playerHoverDetail {{ color:{TEXT_COLOR}; font-size:10px; background:transparent; border:0; }}"
            f"QLabel#playerHoverStatus {{ color:{TEXT_COLOR}; background:{HOVER_SURFACE_COLOR}; border:1px solid {ORNAMENT_COLOR}; "
            f"border-radius:{CARD_CORNER_RADIUS}px; padding:3px 6px; font-size:10px; }}"
            f"QFrame#playerHoverCardsFrame {{ background:{HOVER_INSET_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; }}"
            f"QWidget#playerHoverCardsContent {{ background:{HOVER_SURFACE_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:0; }}"
            "QWidget#playerHoverCardStack { background:transparent; border:0; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(7, 7, 7, 7)
        outer.setSpacing(5)

        header = QFrame()
        header.setObjectName("playerHoverHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(5)
        self.name_label = QLabel()
        self.name_label.setObjectName("playerHoverName")
        header_layout.addWidget(self.name_label, 1)
        self.score_label = QLabel()
        self.score_label.setObjectName("playerHoverScore")
        header_layout.addWidget(self.score_label)
        outer.addWidget(header)

        resources = QFrame()
        self.resources_frame = resources
        resources.setObjectName("playerHoverResources")
        resources_layout = QVBoxLayout(resources)
        resources_layout.setContentsMargins(6, 3, 6, 4)
        resources_layout.setSpacing(1)
        resource_heading = QHBoxLayout()
        resource_heading.setContentsMargins(0, 0, 0, 0)
        resource_heading.addWidget(self._section_label("持有灵碎"))
        self.capacity_label = QLabel()
        self.capacity_label.setObjectName("playerHoverSection")
        resource_heading.addStretch(1)
        resource_heading.addWidget(self.capacity_label)
        resources_layout.addLayout(resource_heading)

        token_row = QHBoxLayout()
        token_row.setContentsMargins(0, 0, 0, 0)
        token_row.setSpacing(3)
        self.resource_counts: dict[Attribute, QLabel] = {}
        for attribute in ATTRIBUTES:
            token = QWidget()
            token.setStyleSheet("background:transparent;border:0;")
            token_layout = QHBoxLayout(token)
            token_layout.setContentsMargins(0, 0, 0, 0)
            token_layout.setSpacing(1)
            icon = QLabel()
            icon.setFixedSize(18, 18)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = resource_shard_pixmap(attribute, 18, self.devicePixelRatioF())
            if not pixmap.isNull():
                icon.setPixmap(pixmap)
            else:
                icon.setText("●")
                icon.setStyleSheet(f"color:{ATTRIBUTE_COLORS[attribute][1]};border:0;")
            count = QLabel("0")
            count.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count.setStyleSheet(
                f"color:{ATTRIBUTE_COLORS[attribute][1]};font-size:10px;font-weight:bold;"
                "background:transparent;border:0;"
            )
            self.resource_counts[attribute] = count
            token_layout.addWidget(icon)
            token_layout.addWidget(count)
            token_row.addWidget(token)

        sage_token = QWidget()
        sage_token.setStyleSheet("background:transparent;border:0;")
        sage_layout = QHBoxLayout(sage_token)
        sage_layout.setContentsMargins(0, 0, 0, 0)
        sage_layout.setSpacing(1)
        sage_icon = QLabel()
        sage_icon.setFixedSize(18, 18)
        sage_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sage_pixmap = sage_shard_pixmap(18, self.devicePixelRatioF())
        if not sage_pixmap.isNull():
            sage_icon.setPixmap(sage_pixmap)
        self.sage_count = QLabel("0")
        self.sage_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sage_count.setStyleSheet(
            "color:#9b742c;font-size:10px;font-weight:bold;background:transparent;border:0;"
        )
        sage_layout.addWidget(sage_icon)
        sage_layout.addWidget(self.sage_count)
        token_row.addWidget(sage_token)
        token_row.addStretch(1)
        resources_layout.addLayout(token_row)
        outer.addWidget(resources)

        info = QFrame()
        self.info_frame = info
        info.setObjectName("playerHoverInfo")
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(3, 0, 3, 0)
        info_layout.setSpacing(8)
        self.wizard_label = self._detail_label()
        info_layout.addWidget(self._section_label("魔法师卡"))
        info_layout.addWidget(self.wizard_label)
        info_layout.addStretch(1)
        outer.addWidget(info)

        self.status_label = QLabel()
        self.status_label.setObjectName("playerHoverStatus")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        cards_frame = QFrame()
        self.cards_frame = cards_frame
        cards_frame.setObjectName("playerHoverCardsFrame")
        cards_layout = QVBoxLayout(cards_frame)
        cards_layout.setContentsMargins(5, 4, 5, 5)
        cards_layout.setSpacing(3)
        self.cards_title = self._section_label("已购买卡牌")
        cards_layout.addWidget(self.cards_title)
        self.cards_content = QWidget(cards_frame)
        self.cards_content.setObjectName("playerHoverCardsContent")
        self.cards_columns_layout = QHBoxLayout(self.cards_content)
        self.cards_columns_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_columns_layout.setSpacing(3)
        cards_layout.addWidget(self.cards_content)
        outer.addWidget(cards_frame)
        self.purchased_card_views: list[OwnedCardView] = []
        self.purchased_columns: dict[Attribute, QFrame] = {}
        self.purchased_piles: dict[Attribute, QWidget] = {}
        self.purchased_attribute_icons: dict[Attribute, QLabel] = {}
        self._purchased_signature: tuple | None = None
        self._purchased_layout_width: int | None = None

        # Decode the five hover-only attribute icons while the game window is
        # being initialized, rather than on the first opponent hover.
        for attribute in ATTRIBUTES:
            attribute_icon_pixmap(attribute, 22, self.devicePixelRatioF())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)
        painter.fillPath(path, QColor(self.PARCHMENT_COLOR))
        painter.setPen(QPen(QColor(self.BORDER_COLOR), 2))
        painter.drawPath(path)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("playerHoverSection")
        return label

    @staticmethod
    def _detail_label() -> QLabel:
        label = QLabel()
        label.setObjectName("playerHoverDetail")
        return label

    @staticmethod
    def purchased_cards_signature(player: Player) -> tuple[tuple[object, ...], ...]:
        """Fields that affect how the player's owned cards are drawn and piled."""
        return tuple(
            (
                card.card_id,
                card.level,
                tuple(attribute.value for attribute in card.attributes),
                tuple((attribute.value, card.cost.get(attribute, 0)) for attribute in ATTRIBUTES),
                card.score,
                card.score_multiplier,
                card.transformed_from,
                tuple(sorted(attribute.value for attribute in card.specialization_glows)),
                chosen_attribute.value if chosen_attribute is not None else None,
            )
            for card, chosen_attribute in player.purchased
        )

    def set_player_details(
        self,
        player: Player,
        status: str,
        is_self: bool,
    ) -> bool:
        self.name_label.setText(player.name)
        self.score_label.setText(f"{player.score}分")
        self.resources_frame.setVisible(not is_self)
        self.info_frame.setVisible(not is_self)
        self.cards_frame.setVisible(not is_self)
        self.capacity_label.setText(f"{player.resource_count}/{player.resource_capacity}")
        for attribute, label in self.resource_counts.items():
            label.setText(str(player.resources[attribute]))
        self.sage_count.setText(str(player.light + player.temporary_light))
        self.wizard_label.setText(f"{len(player.wizard_cards)} 张")
        self.status_label.setText(f"当前效果：{status or '暂无'}")
        if not is_self:
            self.cards_title.setText(f"已购买宠物卡　{len(player.purchased)}")
            signature = self.purchased_cards_signature(player)
            if signature == self._purchased_signature and self.width() == self._purchased_layout_width:
                self.status_label.setVisible(True)
                return False
            self._purchased_signature = signature
            self._purchased_layout_width = self.width()
            while self.cards_columns_layout.count():
                item = self.cards_columns_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.deleteLater()
            self.purchased_card_views = []
            self.purchased_columns = {}
            self.purchased_piles = {}
            self.purchased_attribute_icons = {}
            card_width = min(52, max(20, (self.width() - 90) // len(ATTRIBUTES)))
            card_height = round(card_width * 4 / 3)
            reveal_height = max(10, round(OwnedCardView.REVEAL_HEIGHT * card_width / OwnedCardView.WIDTH))
            singles = {attribute: [] for attribute in ATTRIBUTES}
            duals = {attribute: [] for attribute in ATTRIBUTES}
            for card, chosen_attribute in player.purchased:
                if card.is_dual:
                    pile_attribute = (
                        chosen_attribute
                        if chosen_attribute in card.attributes
                        else card.attributes[0]
                    )
                    duals[pile_attribute].append(card)
                else:
                    singles[card.attributes[0]].append(card)

            tallest_pile = 0
            self.cards_columns_layout.addStretch(1)
            for attribute in ATTRIBUTES:
                column = QFrame(self.cards_content)
                column.setObjectName("playerHoverPurchasedColumn")
                # Keep the five piles compact instead of stretching empty
                # attribute columns across the entire hover panel.
                column.setFixedWidth(card_width + 10)
                column.setStyleSheet(
                    f"QFrame#playerHoverPurchasedColumn {{ background:{PANEL_COLOR}; "
                    f"border:1px solid {ORNAMENT_COLOR}; }}"
                )
                column_layout = QVBoxLayout(column)
                column_layout.setContentsMargins(2, 3, 2, 3)
                column_layout.setSpacing(2)
                column_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                icon = QLabel()
                icon.setFixedSize(22, 22)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setStyleSheet("background:transparent;border:0;padding:0;")
                pixmap = attribute_icon_pixmap(attribute, 22, self.cards_content.devicePixelRatioF())
                if not pixmap.isNull():
                    icon.setPixmap(pixmap)
                else:
                    icon.setText(attribute.value)
                column_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
                self.purchased_attribute_icons[attribute] = icon
                self.purchased_columns[attribute] = column
                self.cards_columns_layout.addWidget(column)

                cards = [(card, False) for card in singles[attribute]] + [
                    (card, True) for card in duals[attribute]
                ]
                stack_height = card_height + (len(cards) - 1) * reveal_height if cards else 0
                tallest_pile = max(tallest_pile, stack_height)
                if cards:
                    stack = QWidget(column)
                    stack.setObjectName("playerHoverCardStack")
                    stack.setFixedWidth(card_width + 4)
                    stack.setFixedHeight(stack_height)
                    for index, (card, is_dual) in enumerate(cards):
                        card_view = OwnedCardView(
                            card,
                            dual=is_dual,
                            parent=stack,
                            width=card_width,
                        )
                        card_view.setProperty("pileAttribute", attribute.value)
                        card_view.setProperty("stackIndex", index)
                        card_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                        card_view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                        card_view.move((stack.width() - card_view.width()) // 2, index * reveal_height)
                        card_view.show()
                        card_view.raise_()
                        self.purchased_card_views.append(card_view)
                    column_layout.addWidget(
                        stack,
                        0,
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    )
                    self.purchased_piles[attribute] = stack
            self.cards_columns_layout.addStretch(1)
            # The hover card grows with its tallest attribute pile. No scroll
            # viewport may clip the lower cards: every purchased card remains
            # visible in this compact, overlapped stack.
            cards_content_height = max(64, tallest_pile + 38)
            self.cards_content.setMinimumHeight(cards_content_height)
            self.cards_content.setMaximumHeight(cards_content_height)
            self.cards_content.updateGeometry()
            self.cards_frame.updateGeometry()
        self.status_label.setVisible(True)
        return not is_self


class MagicGemsQtApp(QMainWindow):
    WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
    CARD_WIDTH = 75
    SINGLE_PLAYER_OPPONENTS = {
        "simple": ("米米", "米莎", "米蒂"),
        "hard": ("可丽希亚", "菲尔特", "拉普"),
    }
    RESOURCE_COLORS = ATTRIBUTE_COLORS
    RESOURCE_NAMES = {
        Attribute.WATER: "水", Attribute.FIRE: "火", Attribute.GRASS: "草",
        Attribute.CUTE: "萌", Attribute.DARK: "恶",
    }

    def __init__(self, seed: int = 1, ai_battle: bool = False, interval: float = .5, seed_mode: str = "fixed") -> None:
        super().__init__()
        self.ui_font_family = preferred_serif_family()
        app = QApplication.instance()
        if app is not None:
            app_font = QFont(self.ui_font_family)
            app_font.setStyleHint(QFont.StyleHint.Serif)
            app.setFont(app_font)
        self.seed, self.seed_mode = seed, seed_mode
        self.ai_battle, self.ai_interval = ai_battle, max(0.0, interval)
        self.ai_difficulty = "hard"
        self.game = Game(create_state(self.create_players(), build_decks(seed), seed))
        self.displayed_turn_key = (
            self.game.state.round_number,
            self.game.state.current_player,
        )
        self.selected_card: PetCard | None = None
        self.resource_selection: list[Attribute] = []
        self.resource_notice = ""
        self.market_slots: dict[int, dict[str, int]] = {level: {} for level in (1, 2, 3)}
        self.market_slot_widgets: dict[int, list[QWidget]] = {}
        self.deferred_market_card_ids: set[str] = set()
        self.market_refill_without_animation = False
        self.deferred_reserved_card_ids: set[str] = set()
        self.deferred_purchased_card_ids: set[str] = set()
        self.log_messages: list[tuple[str, str, bool]] = []
        self.dual_move_order: dict[str, int] = {}
        self.dual_move_sequence = 0
        self.sound_effects = SoundEffects()
        self.ai_timer = QTimer(self)
        self.ai_timer.setSingleShot(True)
        self.ai_timer.timeout.connect(self.play_ai_turn)
        self.specialization_scheduled = False
        self.specialization_retry_timer = QTimer(self)
        self.specialization_retry_timer.setSingleShot(True)
        self.specialization_retry_timer.setInterval(100)
        self.specialization_retry_timer.timeout.connect(self.schedule_specialization_prompt)
        self.specialization_dialog: QDialog | None = None
        self.wizard_animation_queue = []
        self.wizard_animation_running = False
        self.wizard_animation_overlay: WizardCardView | None = None
        self.wizard_animation_notice: QLabel | None = None
        self.wizard_animation: QSequentialAnimationGroup | None = None
        self.impact_animation_queue: list[dict] = []
        self.impact_animation_running = False
        self.impact_animation_overlay: QWidget | None = None
        self.impact_animation_overlays: list[QWidget] = []
        self.impact_animation: QSequentialAnimationGroup | QParallelAnimationGroup | None = None
        self.interaction_locked = False
        self.turn_banner_pending = False
        self.turn_animation_running = False
        self.turn_animation_overlay: QLabel | None = None
        self.turn_animation: QSequentialAnimationGroup | None = None
        self.turn_banner_text = "你的回合！"
        self.last_announced_turn: tuple[int, int] | None = None
        self.player_status_labels: dict[int, QWidget] = {}
        self.player_status_heading_labels: dict[int, QLabel] = {}
        self.player_status_effect_labels: dict[int, QLabel] = {}
        self.end_dialog_shown = False
        self.end_dialog_pending = False
        self.end_overlay: QWidget | None = None
        self.setWindowTitle("洛克王国：魔法宝石")
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)
        self.setStyleSheet(
            f"QMainWindow {{ background:{TABLETOP_COLOR}; color:{TEXT_COLOR}; }}"
            f"QWidget {{ color:{TEXT_COLOR}; font-family:'{self.ui_font_family}'; }}"
        )
        self.start_game_log()
        self.pages = QStackedWidget(self)
        self.setCentralWidget(self.pages)
        self.title_page = self.build_title_page()
        self.pages.addWidget(self.title_page)
        self.difficulty_page = self.build_difficulty_page()
        self.pages.addWidget(self.difficulty_page)
        self.game_page = WoodTableWidget()
        self.game_page.setObjectName("gamePage")
        self.pages.addWidget(self.game_page)
        self.build_ui(self.game_page)
        self.player_hover_card = PlayerStatusHoverCard(self)
        self.player_hover_card.installEventFilter(self)
        # Child widgets become visible with the main window unless explicitly
        # hidden. The hover card must appear only after entering a player row.
        self.player_hover_card.hide()
        self.player_hover_hide_timer = QTimer(self)
        self.player_hover_hide_timer.setSingleShot(True)
        self.player_hover_hide_timer.setInterval(180)
        self.player_hover_hide_timer.timeout.connect(self.hide_player_status_hover)
        self.player_hover_anchor: QWidget | None = None
        self.game_started = self.ai_battle
        self.pages.setCurrentWidget(self.game_page if self.ai_battle else self.title_page)
        self.refresh()
        if self.ai_battle:
            self.log(f"对局开始，{seed_description(seed, seed_mode)}")
            self.enqueue_turn_banner()

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
    def section(
        title: str,
        parent: QWidget | None = None,
        help_callback=None,
        parchment: bool = False,
    ) -> tuple[QFrame, QVBoxLayout]:
        frame = AgedParchmentFrame(parent) if parchment else QFrame(parent)
        if parchment:
            frame.setStyleSheet("QFrame { background:transparent; border:0; }")
        else:
            frame.setStyleSheet(f"QFrame {{ background:{PANEL_COLOR}; border:1px solid {ORNAMENT_COLOR}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(3)
        label = QLabel(title)
        label.setFixedHeight(18)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("font-weight:bold;background:transparent;border:0;")
        if help_callback is None:
            layout.addWidget(label)
        else:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(4)
            header.addWidget(label)
            header.addStretch(1)
            help_button = QPushButton("?")
            help_button.setObjectName("specializationHelpButton")
            help_button.setFixedSize(24, 24)
            help_button.setToolTip("查看属性专精规则")
            help_button.setStyleSheet(
                f"QPushButton {{ padding:0; border:1px solid {ORNAMENT_COLOR}; border-radius:12px; "
                f"background:{PANEL_COLOR}; color:{TEXT_COLOR}; font-weight:bold; font-size:15px; }}"
                f"QPushButton:hover {{ background:#ffe8d3; border-color:{TEXT_COLOR}; }}"
            )
            help_button.clicked.connect(help_callback)
            header.addWidget(help_button)
            layout.addLayout(header)
        return frame, layout

    def build_title_page(self) -> QWidget:
        page = BaroqueTitlePage()
        page.setObjectName("titlePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(92, 76, 92, 76)
        layout.setSpacing(0)
        layout.addStretch(2)

        title = QLabel("洛克王国：魔法宝石")
        title.setObjectName("gameTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#ffffff;background:transparent;border:0;")
        retro_family = self.ui_font_family
        title_font = QFont(retro_family)
        title_font.setPointSize(54)
        title_font.setBold(True)
        title_font.setStyleHint(QFont.StyleHint.Serif)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        title.setFont(title_font)
        title_shadow = QGraphicsDropShadowEffect(title)
        title_shadow.setBlurRadius(5)
        title_shadow.setOffset(1, 2)
        title_shadow.setColor(QColor("#3a281c"))
        title.setGraphicsEffect(title_shadow)
        layout.addWidget(title)

        subtitle = QLabel("—— 经典策略桌游 · 四人对战 ——")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#f0d9ae;background:transparent;border:0;font-size:15px;font-weight:bold;letter-spacing:2px;")
        subtitle_font = QFont(retro_family)
        subtitle_font.setPointSize(15)
        subtitle.setFont(subtitle_font)
        layout.addSpacing(12)
        layout.addWidget(subtitle)
        layout.addSpacing(68)

        button_font = QFont(retro_family)
        button_font.setPointSize(15)
        button_font.setBold(True)
        options = (
            ("单人模式", "titleSinglePlayerButton", self.start_single_player),
            ("规则介绍", "titleRulesButton", self.show_game_rules),
            ("退出游戏", "titleQuitButton", self.close),
        )
        for label, object_name, callback in options:
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.setFixedSize(350, 44)
            button.setFont(button_font)
            button.setStyleSheet(
                f"QPushButton {{ color:{TEXT_COLOR}; border:2px solid {ORNAMENT_COLOR}; padding:3px 16px; "
                f"background:{PANEL_COLOR}; }}"
                f"QPushButton:hover {{ color:{TEXT_COLOR}; border-color:#83b3bc; background:#ffe8d3; }}"
                "QPushButton:pressed { background:#efc9a9; }"
            )
            button.clicked.connect(callback)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addSpacing(12)

        layout.addStretch(3)
        return page

    def build_difficulty_page(self) -> QWidget:
        page = BaroqueTitlePage()
        page.setObjectName("difficultyPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(92, 76, 92, 76)
        layout.setSpacing(0)
        layout.addStretch(2)

        title = QLabel("选择对手难度")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#ffffff;background:transparent;border:0;font-size:38px;font-weight:bold;")
        difficulty_font = QFont(self.ui_font_family)
        difficulty_font.setPointSize(15)
        difficulty_font.setBold(True)
        difficulty_font.setStyleHint(QFont.StyleHint.Serif)
        layout.addWidget(title)
        subtitle = QLabel("选择单人模式的 AI 策略水平")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#f0d9ae;background:transparent;border:0;font-size:15px;font-weight:bold;")
        layout.addSpacing(16)
        layout.addWidget(subtitle)
        layout.addSpacing(52)

        options = (
            ("简单模式", "difficultySimpleButton", "simple"),
            ("困难模式","difficultyHardButton", "hard"),
        )
        for label, object_name, difficulty in options:
            button = QPushButton(f"{label}")
            button.setObjectName(object_name)
            button.setFixedSize(470, 48)
            button.setFont(difficulty_font)
            button.setStyleSheet(
                f"QPushButton {{ color:{TEXT_COLOR}; border:2px solid {ORNAMENT_COLOR}; padding:3px 16px; "
                f"background:{PANEL_COLOR}; }}"
                f"QPushButton:hover {{ color:{TEXT_COLOR}; border-color:#83b3bc; background:#ffe8d3; }}"
                "QPushButton:pressed { background:#efc9a9; }"
            )
            button.clicked.connect(lambda _checked=False, mode=difficulty: self.start_game_with_difficulty(mode))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
            layout.addSpacing(12)

        back = QPushButton("返回")
        back.setObjectName("difficultyBackButton")
        back.setFixedSize(160, 40)
        back.setFont(difficulty_font)
        back.setStyleSheet(
            f"QPushButton {{ color:{TEXT_COLOR}; border:1px solid {ORNAMENT_COLOR}; padding:3px 12px; background:{PANEL_COLOR}; }}"
            "QPushButton:hover { background:#ffe8d3; }"
        )
        back.clicked.connect(lambda: self.pages.setCurrentWidget(self.title_page))
        layout.addSpacing(8)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(3)
        return page

    def start_single_player(self) -> None:
        self.pages.setCurrentWidget(self.difficulty_page)

    def create_players(self) -> list[Player]:
        if self.ai_battle:
            return [Player(f"AI-{index}") for index in range(1, 5)]
        opponents = self.SINGLE_PLAYER_OPPONENTS[self.ai_difficulty]
        return [Player("你"), *(Player(name) for name in opponents)]

    def apply_single_player_opponent_names(self) -> None:
        if self.ai_battle:
            return
        for player, name in zip(
            self.game.state.players[1:], self.SINGLE_PLAYER_OPPONENTS[self.ai_difficulty]
        ):
            player.name = name
        self.render_players()

    def current_mode_text(self) -> str:
        if self.ai_battle:
            return "四 AI 对战模式"
        difficulty = "简单" if self.ai_difficulty == "simple" else "困难"
        return f"单人 · {difficulty}模式"

    def start_game_with_difficulty(self, difficulty: str) -> None:
        self.ai_difficulty = "simple" if difficulty == "simple" else "hard"
        self.apply_single_player_opponent_names()
        self.mode_label.setText(self.current_mode_text())
        self.pages.setCurrentWidget(self.game_page)
        if not self.game_started:
            self.game_started = True
            self.log(f"单人模式：{'简单' if self.ai_difficulty == 'simple' else '困难'}")
            self.log(f"对局开始，{seed_description(self.seed, self.seed_mode)}")
            self.enqueue_turn_banner()

    def show_game_rules(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("游戏规则介绍")
        dialog.resize(650, 560)
        dialog.setStyleSheet(f"QDialog {{ background:{PANEL_COLOR}; color:{TEXT_COLOR}; }}")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        heading = QLabel("游戏规则")
        heading.setStyleSheet(f"font-size:18px;font-weight:bold;background:transparent;border:0;color:{TEXT_COLOR};")
        layout.addWidget(heading)

        rules = (
            "每回合选择一项行动：领取资源、购买宠物，或预购一张市场宠物。",
            "领取资源：拿取三种不同属性各1枚，或同一种属性2枚；第二种方式要求资源池该属性至少剩4枚。",
            "购买宠物：支付卡牌费用。已购宠物提供永久属性折扣和卡面分数；贤者零碎可替代任意属性。",
            "预购宠物：从市场保留一张卡并获得1枚贤者零碎；预购区最多3张，之后仍需花费行动购买。",
            "属性专精：拥有2张同属性单属性宠物触发阶段一，达到3张触发阶段二；双属性宠物不计入专精。",
            "魔法师卡：公开卡只在玩家行动及待结算专精全部结束后检查；符合条件自动获得，每张加3分。",
            "胜利：任一玩家达到18分后立即结算；若公共市场全部耗尽，则完成本轮后结算。",
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 8, 4)
        content_layout.setSpacing(9)
        for text in rules:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"background:{PANEL_COLOR};color:{TEXT_COLOR};border:1px solid {ORNAMENT_COLOR};padding:8px;font-size:12px;"
            )
            content_layout.addWidget(label)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        specialization_button = QPushButton("查看属性专精细则")
        specialization_button.clicked.connect(self.show_specialization_rules)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(specialization_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        dialog.exec()

    def show_specialization_rules(self) -> None:
        """Show the current in-game specialization rules in a scrollable dialog."""
        if self.interaction_locked:
            return
        rules = (
            (
                Attribute.WATER,
                "泡沫幻影",
                "选择公共市场中的一张宠物卡，将其当前最高的一项资源费用 -1；若有多项并列最高，随机降低其中一项。市场没有宠物时效果失效。",
                "免费捕捉",
                "下一次购买宠物不需要支付任何资源。效果在完成下一次购买后消耗。",
            ),
            (
                Attribute.FIRE,
                "引燃",
                "随机选一名有预购卡或已购宠物的对手。若其有预购卡，随机烧掉一张并放回对应等级牌库；对手已因预购获得的贤者零碎保留。若其没有预购卡，则从其最低等级的已购宠物中随机烧掉一张，该卡移出本局并扣除对应分数。自己不会成为目标；没有符合条件的对手时效果失效。",
                "阳火增辉",
                "下一张购买的宠物分数翻倍，仅影响这一张卡。",
            ),
            (
                Attribute.GRASS,
                "根吸收",
                "选择公共市场中的一张宠物卡，使该卡分数 +1。之后购买这张卡时会保留增加的分数；市场没有宠物时效果失效。",
                "汲取",
                "获得临时贤者零碎，数量为其他玩家所拥有的单属性草系宠物总数 +1。临时零碎用于购买后消耗，不会退回公共贤者零碎池。",
            ),
            (
                Attribute.CUTE,
                "撒娇",
                "获得一次攻击免疫。下一次受到其他玩家的恶系阶段一或阶段二攻击时，免疫该次攻击并消耗此效果。",
                "甜心续航",
                "对每一名其他玩家，分别随机选择其一张已购二级或三级宠物，将其降为属性组合相同的低一级形态，并按新卡面更新费用和分数；一级宠物不受影响。没有可降级宠物的玩家跳过。",
            ),
            (
                Attribute.DARK,
                "吞噬",
                "选择一名持有水、火、草、萌或恶系普通灵碎的其他玩家，随机夺取其一种普通灵碎 1 枚。若自己已达到资源上限，或没有可选目标，则无法发动；受撒娇免疫时攻击无效并消耗免疫。",
                "恶魔契约",
                "选择已购宠物数量最多的其他玩家之一（并列时可选其中一人），随机夺取其一张已购宠物并加入自己的已购区，卡牌分数从对方转给自己；受撒娇免疫时攻击无效并消耗免疫。",
            ),
        )

        dialog = QDialog(self)
        dialog.setObjectName("specializationRulesDialog")
        dialog.setWindowTitle("属性专精规则")
        dialog.resize(690, 640)
        dialog.setStyleSheet(f"QDialog {{ background:{PANEL_COLOR}; color:{TEXT_COLOR}; }}")
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        intro = QLabel(
            "专精触发条件：每拥有 2 张同属性单属性宠物，触发该属性阶段一；达到 3 张时触发阶段二。"
            "双属性宠物的两种属性都不计入专精数量。每个阶段每名玩家一局只触发一次。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"background:{PANEL_COLOR};color:{TEXT_COLOR};border:1px solid {ORNAMENT_COLOR};padding:8px;font-size:11px;"
        )
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 6, 2)
        content_layout.setSpacing(7)

        for attribute, stage_one_name, stage_one_text, stage_two_name, stage_two_text in rules:
            color = self.RESOURCE_COLORS[attribute][1]
            panel = QFrame()
            panel.setObjectName("specializationRulePanel")
            panel.setStyleSheet(
                f"QFrame#specializationRulePanel {{ background:{PANEL_COLOR}; color:{TEXT_COLOR}; border:1px solid {ORNAMENT_COLOR}; border-radius:4px; }}"
            )
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(9, 6, 9, 7)
            panel_layout.setSpacing(4)
            heading = QLabel(f"{attribute.value}系专精")
            heading.setStyleSheet(f"color:{color};font-weight:bold;font-size:13px;background:transparent;border:0;")
            panel_layout.addWidget(heading)
            for stage, name, description in (
                ("阶段一", stage_one_name, stage_one_text),
                ("阶段二", stage_two_name, stage_two_text),
            ):
                detail = QLabel(
                    f"<b>{stage} · {html_escape(name)}</b><br>{html_escape(description)}"
                )
                detail.setWordWrap(True)
                detail.setTextFormat(Qt.TextFormat.RichText)
                detail.setStyleSheet("font-size:10px;background:transparent;border:0;")
                panel_layout.addWidget(detail)
            content_layout.addWidget(panel)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        close_button = QPushButton("关闭")
        close_button.setFixedWidth(88)
        close_button.clicked.connect(dialog.accept)
        outer.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def build_ui(self, root: QWidget | None = None) -> None:
        if root is None:
            root = WoodTableWidget()
            if self.centralWidget() is not root:
                self.setCentralWidget(root)
        root.setObjectName("gamePage")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background:{PANEL_COLOR};border:1px solid {ORNAMENT_COLOR};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 2, 14, 2)
        title = QLabel("魔法宝石")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(32)
        title.setStyleSheet(
            f"color:{PANEL_COLOR};font-size:18px;font-weight:bold;background:{TEXT_COLOR};"
            f"border:1px solid {ORNAMENT_COLOR};border-radius:4px;padding:2px 10px;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumWidth(225)
        self.status_label.setFixedHeight(30)
        self.status_label.setStyleSheet(
            f"color:{TEXT_COLOR};font-size:12px;font-weight:bold;background:#ffe8d3;"
            f"border:1px solid {ORNAMENT_COLOR};border-radius:4px;padding:2px 8px;"
        )
        header_layout.addWidget(self.status_label)
        self.mode_label = QLabel(self.current_mode_text())
        self.mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_label.setMinimumWidth(132)
        self.mode_label.setFixedHeight(30)
        self.mode_label.setStyleSheet(
            f"color:{TEXT_COLOR}; background:#cfe5e6; border:1px solid {ORNAMENT_COLOR}; "
            "border-radius:4px; padding:2px 8px; font-size:11px; font-weight:bold;"
        )
        header_layout.addWidget(self.mode_label)
        self.restart_button = QPushButton("重新开始")
        self.restart_button.setFixedSize(92, 30)
        self.restart_button.setStyleSheet(
            f"QPushButton {{ color:{PANEL_COLOR}; background:{TEXT_COLOR}; border:1px solid {ORNAMENT_COLOR}; "
            "border-radius:4px; padding:3px 8px; font-weight:bold; }"
            "QPushButton:hover { background:#ad514b; border-color:#83b3bc; }"
            "QPushButton:pressed { background:#6e2828; }"
            "QPushButton:disabled { color:#f1d5c1; background:#b88782; border-color:#b7b0a1; }"
        )
        self.restart_button.clicked.connect(self.confirm_restart)
        header_layout.addWidget(self.restart_button)
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

        market, market_outer = self.section(
            "公共市场", help_callback=self.show_specialization_rules, parchment=True
        )
        self.market_layout = QVBoxLayout()
        self.market_layout.setContentsMargins(0, 0, 0, 0)
        self.market_layout.setSpacing(3)
        market_outer.addLayout(self.market_layout)
        self.left_layout.addWidget(market, 7)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(6)
        self.players_frame, self.players_layout = self.section("玩家状态")
        self.log_frame, self.log_layout = self.section("行动记录")
        self.reserved_frame, self.reserved_layout = self.section("预购卡牌")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setUndoRedoEnabled(False)
        self.log_view.setStyleSheet(
            f"background:{RESERVED_AREA_BACKGROUND};color:{TEXT_COLOR};border:1px solid {ORNAMENT_COLOR};"
        )
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
        self.purchasing_power_frame.setStyleSheet(
            f"QFrame {{ background:{PANEL_COLOR}; border:1px solid {ORNAMENT_COLOR}; }}"
        )
        self.purchasing_power_layout = QVBoxLayout(self.purchasing_power_frame)
        self.purchasing_power_layout.setContentsMargins(5, 3, 5, 3)
        self.purchasing_power_layout.setSpacing(1)
        self.pool_resource_frame, self.pool_resource_layout = self.section("已有资源")
        self.pool_resource_title = self.pool_resource_layout.itemAt(0).widget()
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
        wizard_row = QHBoxLayout()
        wizard_row.setSpacing(5)
        wizard_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        wizard_label = QLabel("魔法师")
        wizard_label.setFixedWidth(82)
        wizard_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wizard_label.setStyleSheet("font-size:14px;font-weight:bold;background:transparent;border:0;")
        wizard_row.addWidget(wizard_label)
        self.wizard_market_views = []
        for wizard in state.wizard_market[:3]:
            card_view = WizardCardView(wizard)
            self.wizard_market_views.append(card_view)
            wizard_row.addWidget(card_view)
        for _ in range(3 - len(self.wizard_market_views)):
            placeholder = QWidget()
            placeholder.setFixedSize(WizardCardView.WIDTH, WizardCardView.HEIGHT)
            placeholder.setStyleSheet("background:transparent;border:0;")
            wizard_row.addWidget(placeholder)
        self.market_layout.addLayout(wizard_row)
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
                if card.card_id not in self.deferred_market_card_ids
            }
            slot_widgets: list[QWidget] = []
            for slot in range(max(5, len(state.market.cards[level]))):
                card = cards_by_slot.get(slot)
                if card is None:
                    placeholder = QWidget()
                    placeholder.setFixedSize(self.CARD_WIDTH, round(self.CARD_WIDTH * 4 / 3))
                    placeholder.setStyleSheet("background:transparent;border:0;")
                    row.addWidget(placeholder)
                    slot_widgets.append(placeholder)
                    buttons.append(None)
                    continue
                button = CardButton(self.CARD_WIDTH)
                button.clicked.connect(lambda _=False, c=card: self.select_card(c))
                row.addWidget(button)
                slot_widgets.append(button)
                buttons.append(button)
            self.market_buttons[level] = buttons
            self.market_slot_widgets[level] = slot_widgets
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
            slot_count = max(5, len(cards))
            free_slots = released_slots + [slot for slot in range(slot_count) if slot not in occupied and slot not in released_slots]
            for card in cards:
                if card.card_id in current:
                    continue
                if not free_slots:
                    break
                current[card.card_id] = free_slots.pop(0)
            self.market_slots[level] = current

    def configure_card(self, button: CardButton, card: PetCard) -> None:
        can_afford = self.can_player_afford_card(card)
        transformed = f" ↓{card.transformed_from}" if card.transformed_from else ""
        attributes = "/".join(attribute.value for attribute in card.attributes)
        cost_items = [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)]
        shown_id = f"▶ {card.card_id}{transformed}" if card is self.selected_card else f"{card.card_id}{transformed}"
        button.set_card_content(attributes, str(card.effective_score), shown_id, cost_items)
        button.card_id = card.card_id
        background = "#f4d484" if card is self.selected_card else "#dceecf" if can_afford else "#fff6e8"
        border_color = specialization_glow_color(card) or "#b8b8b8"
        text_color = TEXT_COLOR
        button.set_card_style(
            background=background,
            border_color=border_color,
            border_width=2,
            padding=2,
            text_color=text_color,
            hover_border_color="#6b8799",
        )
        palette = button.palette()
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(text_color))
        button.setPalette(palette)
        # QSS may change a QPushButton's size hint, so reapply the portrait bounds afterward.
        width = button.maximumWidth()
        button.setFixedSize(width, round(width * 4 / 3))
        apply_specialization_glow(button, card)

    def can_player_afford_card(self, card: PetCard) -> bool:
        """Whether the human player can afford a card, independent of turn order."""
        player = self.game.state.players[0]
        try:
            payment_for(player, card, self.dual_discount_choices(player))
        except RuleError:
            return False
        return True

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

    def attribute_icon_label(self, attribute: Attribute, size: int = 22) -> QLabel:
        label = QLabel()
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background:transparent;border:0;padding:0;")
        pixmap = attribute_icon_pixmap(attribute, size, self.devicePixelRatioF())
        if pixmap.isNull():
            label.setText(attribute.value)
        else:
            label.setPixmap(pixmap)
        return label

    def render_resource_zones(self) -> None:
        self.clear_layout(self.purchasing_power_layout)
        self.clear_section_body(self.pool_resource_layout)
        player = self.game.state.players[0]
        light_total = player.light + player.temporary_light
        self.pool_resource_title.setText(
            f"已有资源：{player.resource_count}/{player.resource_capacity}　贤者碎晶{light_total}"
        )
        discounts = player.permanent_discounts
        for card, chosen in player.purchased:
            if card.is_dual:
                discounts[chosen if chosen in card.attributes else card.attributes[0]] += 1
        power_row = QHBoxLayout()
        power_row.setSpacing(2)
        for attribute in ATTRIBUTES:
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addStretch(1)
            name = self.attribute_icon_label(attribute)
            name.setFixedSize(22, 26)
            name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            resources = player.resources[attribute]
            discount = discounts[attribute]
            total = QLabel(f"{resources}+{discount}={resources + discount}")
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            total.setStyleSheet(f"background:transparent;border:0;font-size:12px;font-weight:bold;color:{self.RESOURCE_COLORS[attribute][1]};")
            column.addWidget(name, 0, Qt.AlignmentFlag.AlignHCenter)
            column.addWidget(total)
            column.addStretch(1)
            power_row.addLayout(column, 1)
        self.purchasing_power_layout.addLayout(power_row)

        fixed_row = QHBoxLayout()
        fixed_row.setSpacing(2)
        for attribute in ATTRIBUTES:
            column = QVBoxLayout()
            name = QLabel("")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("background:transparent;border:0;font-size:11px;")
            name.setFixedHeight(14)
            column.addWidget(name)
            count = player.resources[attribute]
            column.setSpacing(0)
            column.addWidget(DotStackWidget(attribute, count), 0, Qt.AlignmentFlag.AlignHCenter)
            column.addStretch()
            fixed_row.addLayout(column, 1)
        self.pool_resource_layout.addLayout(fixed_row)

    def render_reserved(self) -> None:
        self.clear_section_body(self.reserved_layout)
        self.reserved_buttons: list[CardButton] = []
        self.reserved_card_views: dict[str, CardButton] = {}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("reservedCardsContent")
        content.setStyleSheet(f"QWidget#reservedCardsContent {{ background:{RESERVED_AREA_BACKGROUND}; }}")
        self.reserved_cards_content = content
        grid = QGridLayout(content)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setSpacing(4)
        for index, card in enumerate(self.game.state.players[0].reserved):
            button = CardButton(44)
            button.clicked.connect(lambda _=False, c=card: self.select_card(c))
            self.configure_card(button, card)
            if card.card_id in self.deferred_reserved_card_ids:
                hidden = QGraphicsOpacityEffect(button)
                hidden.setOpacity(0.0)
                button.setGraphicsEffect(hidden)
            grid.addWidget(button, index, 0, Qt.AlignmentFlag.AlignHCenter)
            self.reserved_buttons.append(button)
            self.reserved_card_views[card.card_id] = button
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        scroll.setWidget(content)
        self.reserved_layout.addWidget(scroll, 1)
        scroll.show()

    def render_purchased(self) -> None:
        self.clear_section_body(self.purchased_layout)
        player = self.game.state.players[0]
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        wizard_header = QLabel(f"魔法师卡 {len(player.wizard_cards)}")
        wizard_header.setStyleSheet("background:transparent;border:0;font-size:10px;font-weight:bold;")
        container_layout.addWidget(wizard_header)
        wizard_scroll = QScrollArea()
        wizard_scroll.setObjectName("ownedWizardScroll")
        wizard_scroll.setWidgetResizable(True)
        wizard_card_width = 44
        wizard_scroll.setFixedHeight(80)
        wizard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        wizard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        wizard_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wizard_content = QWidget()
        wizard_row = QHBoxLayout(wizard_content)
        wizard_row.setContentsMargins(2, 0, 2, 0)
        wizard_row.setSpacing(3)
        self.owned_wizard_views: list[WizardCardView] = []
        for wizard in player.wizard_cards:
            wizard_view = WizardCardView(wizard, width=wizard_card_width)
            self.owned_wizard_views.append(wizard_view)
            wizard_row.addWidget(wizard_view)
        wizard_row.addStretch()
        wizard_scroll.setWidget(wizard_content)
        self.owned_wizard_scroll = wizard_scroll
        container_layout.addWidget(wizard_scroll)

        singles = {attribute: [] for attribute in ATTRIBUTES}
        duals = {attribute: [] for attribute in ATTRIBUTES}
        for card, chosen in player.purchased:
            if card.is_dual:
                pile_attribute = chosen if chosen in card.attributes else card.attributes[0]
                if card.card_id not in self.dual_move_order:
                    self.dual_move_sequence += 1
                    self.dual_move_order[card.card_id] = self.dual_move_sequence
                duals[pile_attribute].append((self.dual_move_order[card.card_id], card))
            else:
                singles[card.attributes[0]].append(card)

        purchased_board = QWidget()
        board_layout = QHBoxLayout(purchased_board)
        board_layout.setContentsMargins(2, 2, 2, 2)
        board_layout.setSpacing(3)
        self.purchased_board = purchased_board
        self.purchased_columns: dict[Attribute, QFrame] = {}
        self.purchased_column_scrolls: dict[Attribute, QScrollArea] = {}
        self.purchased_attribute_icons: dict[Attribute, QLabel] = {}
        self.purchased_card_views: dict[str, OwnedCardView] = {}
        draggable = (
            not self.interaction_locked
            and self.game.state.current_player == 0
            and not self.ai_battle
            and not self.game.state.finished
            and not self.game.state.pending_specializations
        )
        for attribute in ATTRIBUTES:
            # The icon and its card pile share one stationary column frame.
            # Only the inner pile viewport scrolls, leaving the icon attached
            # to its property column at all times.
            column = QFrame(purchased_board)
            column.setMinimumWidth(48)
            column.setStyleSheet(f"QFrame {{ background:{PANEL_COLOR}; border:1px solid {ORNAMENT_COLOR}; }}")
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(2, 3, 2, 3)
            column_layout.setSpacing(2)
            column_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            self.purchased_columns[attribute] = column
            name = self.attribute_icon_label(attribute)
            column_layout.addWidget(name, 0, Qt.AlignmentFlag.AlignHCenter)
            self.purchased_attribute_icons[attribute] = name

            duals[attribute].sort(key=lambda item: item[0])
            cards = [(card, False) for card in singles[attribute]] + [
                (card, True) for _order, card in duals[attribute]
            ]
            stack = QWidget()
            stack.setFixedWidth(56)
            stack_height = OwnedCardView.HEIGHT if cards else 1
            if cards:
                stack_height += (len(cards) - 1) * OwnedCardView.REVEAL_HEIGHT
            stack.setFixedHeight(stack_height)
            for index, (card, is_dual) in enumerate(cards):
                card_view = (
                    # During a drag, lift only the card to the game-page layer.
                    # Keeping the drag layer outside the scroll content prevents
                    # the purchased-column header/icons from moving with it.
                    DraggableDualCard(card, self.game_page, self.drop_dual_card, draggable)
                    if is_dual else OwnedCardView(card, parent=stack)
                )
                card_view.setParent(stack)
                card_view.move((stack.width() - card_view.width()) // 2, index * OwnedCardView.REVEAL_HEIGHT)
                if card.card_id in self.deferred_purchased_card_ids:
                    hidden = QGraphicsOpacityEffect(card_view)
                    hidden.setOpacity(0.0)
                    card_view.setGraphicsEffect(hidden)
                card_view.show()
                card_view.raise_()
                self.purchased_card_views[card.card_id] = card_view
            pile_content = QWidget()
            pile_layout = QHBoxLayout(pile_content)
            pile_layout.setContentsMargins(0, 0, 0, 0)
            pile_layout.addStretch(1)
            pile_layout.addWidget(stack, 0, Qt.AlignmentFlag.AlignTop)
            pile_layout.addStretch(1)
            pile_content.setMinimumHeight(stack_height)

            pile_scroll = QScrollArea(column)
            pile_scroll.setWidgetResizable(True)
            pile_scroll.setFrameShape(QFrame.Shape.NoFrame)
            pile_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            pile_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            pile_scroll.setWidget(pile_content)
            self.purchased_column_scrolls[attribute] = pile_scroll
            column_layout.addWidget(pile_scroll, 1)
            board_layout.addWidget(column, 1)

        shared_scrollbar = QScrollBar(Qt.Orientation.Vertical, purchased_board)
        shared_scrollbar.setObjectName("purchasedCardScrollBar")
        shared_scrollbar.setRange(0, 0)
        shared_scrollbar.hide()
        board_layout.addWidget(shared_scrollbar)
        self.purchased_scrollbar = shared_scrollbar

        scroll_state = {"syncing": False}
        column_scrollbars = [
            area.verticalScrollBar() for area in self.purchased_column_scrolls.values()
        ]

        def sync_scroll_values(value: int) -> None:
            if scroll_state["syncing"]:
                return
            scroll_state["syncing"] = True
            bounded_value = max(0, min(value, shared_scrollbar.maximum()))
            if shared_scrollbar.value() != bounded_value:
                shared_scrollbar.setValue(bounded_value)
            for scrollbar in column_scrollbars:
                scrollbar.setValue(min(bounded_value, scrollbar.maximum()))
            scroll_state["syncing"] = False

        def sync_from_column(value: int) -> None:
            if not scroll_state["syncing"]:
                sync_scroll_values(value)

        def update_shared_scroll_range(_minimum: int = 0, _maximum: int = 0) -> None:
            if getattr(self, "purchased_board", None) is not purchased_board:
                return
            if scroll_state["syncing"]:
                return
            scroll_state["syncing"] = True
            maximum = max((bar.maximum() for bar in column_scrollbars), default=0)
            shared_scrollbar.setRange(0, maximum)
            shared_scrollbar.setPageStep(
                max((bar.pageStep() for bar in column_scrollbars), default=1)
            )
            shared_scrollbar.setVisible(maximum > 0)
            value = min(shared_scrollbar.value(), maximum)
            shared_scrollbar.setValue(value)
            for scrollbar in column_scrollbars:
                scrollbar.setValue(min(value, scrollbar.maximum()))
            scroll_state["syncing"] = False

        shared_scrollbar.valueChanged.connect(sync_scroll_values)
        for scrollbar in column_scrollbars:
            scrollbar.valueChanged.connect(sync_from_column)
            scrollbar.rangeChanged.connect(update_shared_scroll_range)
        QTimer.singleShot(0, update_shared_scroll_range)

        container_layout.addWidget(purchased_board, 1)
        self.purchased_layout.addWidget(container, 1)
        container.show()

    def ensure_purchased_card_visible(self, card_view: QWidget) -> None:
        for attribute, column in self.purchased_columns.items():
            if column.isAncestorOf(card_view):
                self.purchased_column_scrolls[attribute].ensureWidgetVisible(card_view, 2, 2)
                return

    def drop_dual_card(self, card: PetCard, global_pos: QPoint) -> None:
        if self.interaction_locked:
            return
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
            self.hint_label.setStyleSheet(f"background:transparent;border:0;color:{TEXT_COLOR};font-size:10px;")
            self.controls_layout.addWidget(self.hint_label)

            self.controls_layout.addSpacing(19)
            selected_frame = QFrame()
            selected_frame.setFixedHeight(32)
            selected_frame.setStyleSheet(
                f"QFrame {{ background:{RESERVED_AREA_BACKGROUND}; border:1px solid {ORNAMENT_COLOR}; }}"
            )
            self.selected_resource_frame = selected_frame
            selected_row = QHBoxLayout(selected_frame)
            selected_row.setContentsMargins(4, 0, 3, 0)
            selected_row.setSpacing(1)
            selected_title = QLabel("本回合选中资源")
            selected_title.setFixedWidth(96)
            selected_title.setStyleSheet("background:transparent;border:0;font-size:11px;")
            selected_row.addWidget(selected_title)
            self.selection_markers = []
            for index in range(3):
                marker = DotWidget(None, lambda i=index: self.cancel_resource(i))
                marker.setFixedSize(24, 26)
                marker.hide()
                selected_row.addWidget(marker)
                self.selection_markers.append(marker)
            self.selection_empty_label = QLabel("—")
            self.selection_empty_label.setStyleSheet(f"background:transparent;border:0;color:{TEXT_COLOR};")
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
            self.light_count_label.setToolTip("公共贤者零碎剩余数量；预购公共市场卡牌时获得。")
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
                f"QPushButton {{ background:{PANEL_COLOR}; color:{TEXT_COLOR}; border:1px solid {ORNAMENT_COLOR}; padding:0; }}"
                "QPushButton:disabled { background:#e8cbbc; color:#b88782; border:1px solid #b7b0a1; padding:0; }"
            )
            for button, width in ((self.confirm_button, 111), (self.reserve_button, 112), (self.cancel_button, 111)):
                button.setFixedSize(width, 27)
                button.setStyleSheet(action_style)
                card_actions.addWidget(button)
            self.controls_layout.addLayout(card_actions)

        action_enabled = (
            not self.interaction_locked
            and state.current_player == 0
            and not state.finished
            and not self.ai_battle
            and not state.pending_specializations
        )
        hint_text = self.resource_notice or "选3种各1枚或同种2枚（池≥4）；点击已选资源可取消。"
        if self.hint_label.text() != hint_text:
            self.hint_label.setText(hint_text)
        self.selection_empty_label.setVisible(not self.resource_selection)
        for index, marker in enumerate(self.selection_markers):
            if index < len(self.resource_selection):
                attribute = self.resource_selection[index]
                marker.set_attribute(attribute)
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
            text_color = "#fffaf0" if button_enabled and selected else TEXT_COLOR if button_enabled else "#8b8985"
            button.set_resource(attribute, count)
            if button.isEnabled() != button_enabled:
                button.setEnabled(button_enabled)
            button.set_visual(fill, text_color)
        light_text = str(state.light_pool)
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
        state = self.game.state
        displayed_current_player = getattr(
            self, "displayed_turn_key", (state.round_number, state.current_player)
        )[1]

        def refresh_row(index: int, frame: QWidget, heading: QLabel, effect_label: QLabel) -> None:
            player = state.players[index]
            is_current = index == displayed_current_player
            row_background = PLAYER_CURRENT_COLOR if is_current else PLAYER_STATUS_COLOR
            border_width = 2 if is_current else 1
            frame.setStyleSheet(
                f"QFrame#playerStatusRow {{ background:{row_background};border:{border_width}px solid {ORNAMENT_COLOR};border-radius:{CARD_CORNER_RADIUS}px; }}"
                f"QFrame#playerStatusRow:hover {{ background:{PLAYER_CURRENT_COLOR};border-color:{TEXT_COLOR}; }}"
            )
            heading.setText(
                f"{'▶ ' if is_current else ''}{player.name}　{player.score}分"
            )
            effects = self.current_player_effects(player)
            effect_text = "、".join(effects) if effects else "无"
            effect_label.setText(f"当前效果：{effect_text}")

        expected_indexes = set(range(len(state.players)))
        if (
            set(self.player_status_labels) == expected_indexes
            and set(self.player_status_heading_labels) == expected_indexes
            and set(self.player_status_effect_labels) == expected_indexes
        ):
            for index in range(len(state.players)):
                refresh_row(
                    index,
                    self.player_status_labels[index],
                    self.player_status_heading_labels[index],
                    self.player_status_effect_labels[index],
                )
            return

        # Only construct these rows once. Keeping their widgets stable means
        # updating the active turn won't invalidate an open hover-card anchor.
        self.clear_section_body(self.players_layout)
        self.player_status_labels = {}
        self.player_status_heading_labels = {}
        self.player_status_effect_labels = {}
        for index, player in enumerate(state.players):
            frame = QFrame()
            frame.setFixedHeight(25)
            frame.setObjectName("playerStatusRow")
            frame.setProperty("playerStatusIndex", index)
            frame.installEventFilter(self)
            frame_layout = QHBoxLayout(frame)
            frame_layout.setContentsMargins(4, 1, 4, 1)
            frame_layout.setSpacing(4)

            heading = QLabel()
            heading.setFixedHeight(21)
            heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            heading.setStyleSheet("background:transparent;border:0;font-size:11px;")
            frame_layout.addWidget(heading, 1)

            effect_label = QLabel()
            effect_label.setObjectName("playerStatusEffect")
            effect_label.setFixedHeight(21)
            effect_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            effect_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            effect_label.setStyleSheet(
                f"color:{TEXT_COLOR};background:transparent;border:0;font-size:9px;"
            )
            frame_layout.addWidget(effect_label)

            self.players_layout.addWidget(frame)
            self.player_status_labels[index] = frame
            self.player_status_heading_labels[index] = heading
            self.player_status_effect_labels[index] = effect_label
            refresh_row(index, frame, heading, effect_label)

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if watched is getattr(self, "player_hover_card", None):
            if event_type == QEvent.Type.Enter:
                self.player_hover_hide_timer.stop()
            elif event_type == QEvent.Type.Leave:
                self.player_hover_hide_timer.start()
            return super().eventFilter(watched, event)

        if isinstance(watched, QWidget) and watched.property("playerStatusIndex") is not None:
            if event_type == QEvent.Type.Enter:
                self.player_hover_hide_timer.stop()
                self.show_player_status_hover(
                    self.player_status_labels.get(
                        int(watched.property("playerStatusIndex")), watched
                    ),
                    int(watched.property("playerStatusIndex")),
                )
            elif event_type == QEvent.Type.Leave:
                self.player_hover_hide_timer.start()
        return super().eventFilter(watched, event)

    @staticmethod
    def current_player_effects(player: Player) -> list[str]:
        effects = []
        if player.next_purchase_free:
            effects.append("下张免付费")
        if player.next_purchase_score_doubled:
            effects.append("下张分数翻倍")
        if player.next_attack_immune:
            effects.append("攻击免疫")
        return effects

    def show_player_status_hover(self, anchor: QWidget, player_index: int) -> None:
        if not 0 <= player_index < len(self.game.state.players):
            return
        player = self.game.state.players[player_index]
        available = self.rect().adjusted(4, 4, -4, -4)
        self.player_hover_card.setFixedWidth(max(1, anchor.width()))
        self.player_hover_card.setMaximumHeight(max(1, available.height()))
        statuses = self.current_player_effects(player)
        self.player_hover_card.set_player_details(
            player,
            "、".join(statuses) if statuses else "无",
            player_index == 0,
        )
        # Finish all nested geometry calculations before measuring or showing
        # the popup. This is intentionally done on every opening: a hidden
        # QWidget can retain stale size hints even when its data was cached.
        self.player_hover_card.ensurePolished()
        self.player_hover_card.cards_content.ensurePolished()
        for column in self.player_hover_card.purchased_columns.values():
            column.ensurePolished()
            if column.layout() is not None:
                column.layout().activate()
        for card_view in self.player_hover_card.purchased_card_views:
            card_view.ensurePolished()
        if self.player_hover_card.cards_columns_layout is not None:
            self.player_hover_card.cards_columns_layout.activate()
        if self.player_hover_card.cards_content.layout() is not None:
            self.player_hover_card.cards_content.layout().activate()
        if self.player_hover_card.cards_frame.layout() is not None:
            self.player_hover_card.cards_frame.layout().activate()
        if self.player_hover_card.layout() is not None:
            self.player_hover_card.layout().activate()
        self.player_hover_card.adjustSize()
        if self.player_hover_card.layout() is not None:
            self.player_hover_card.layout().activate()
        anchor_top_left = anchor.mapTo(self, QPoint(0, 0))
        popup_size = self.player_hover_card.size()
        x = anchor_top_left.x()
        # Pin the detail card to the status row's left edge and let it open
        # upward from the row, so it never follows the cursor or jumps between
        # the row frame and its text label.
        y = anchor_top_left.y() + anchor.height() - popup_size.height()
        if y < available.top():
            below_y = anchor_top_left.y()
            if below_y + popup_size.height() - 1 <= available.bottom():
                y = below_y
        x = min(max(x, available.left()), available.right() - popup_size.width() + 1)
        y = min(max(y, available.top()), available.bottom() - popup_size.height() + 1)
        self.player_hover_card.setGeometry(x, y, popup_size.width(), popup_size.height())
        self.player_hover_card.show()
        self.player_hover_card.raise_()
        self.player_hover_anchor = anchor

    def hide_player_status_hover(self) -> None:
        self.player_hover_hide_timer.stop()
        self.player_hover_card.hide()
        self.player_hover_anchor = None

    def refresh_open_player_status_hover(self) -> None:
        """Keep an open player detail card synchronized with the game state."""
        anchor = self.player_hover_anchor
        if anchor is None or self.player_hover_card.isHidden():
            return
        player_index = anchor.property("playerStatusIndex")
        if player_index is None:
            return
        player_index = int(player_index)
        if self.player_status_labels.get(player_index) is not anchor:
            return
        # Reuse the normal layout path so changed card piles can grow/shrink the
        # popup and its position remains aligned to the same status row.
        self.show_player_status_hover(anchor, player_index)

    def refresh(self) -> None:
        state = self.game.state
        turn_key = (state.round_number, state.current_player)
        waiting_for_turn_banner = (
            self.game_started
            and not state.finished
            and turn_key != self.last_announced_turn
        ) or self.turn_banner_pending
        if state.finished or not waiting_for_turn_banner:
            self.displayed_turn_key = turn_key
            self.update_turn_status_bar()
        self.render_market()
        self.render_resource_zones()
        self.render_reserved()
        self.render_purchased()
        self.render_controls()
        self.render_players()
        self.refresh_open_player_status_hover()
        if state.pending_specializations:
            owner = state.pending_specializations[0].player_index
            if owner == 0 and not self.ai_battle and not self.specialization_scheduled:
                self.schedule_specialization_prompt()
            elif not state.finished:
                self.ai_timer.start(round(self.ai_interval * 1000))
        elif not state.finished and (self.ai_battle or state.current_player != 0):
            self.ai_timer.start(round(self.ai_interval * 1000))
        else:
            self.ai_timer.stop()

    def update_turn_status_bar(self) -> None:
        """Update only the header turn indicator; leave player hover UI untouched."""
        state = self.game.state
        if state.finished:
            winners = "、".join(player.name for player in self.game.winners())
            self.status_label.setText(
                f"第 {state.round_number} 轮　·　对局结束！胜者：{winners}"
            )
            self.status_label.setStyleSheet(
                f"color:{PANEL_COLOR};font-size:12px;font-weight:bold;background:{TEXT_COLOR};"
                f"border:1px solid {ORNAMENT_COLOR};border-radius:4px;padding:2px 8px;"
            )
        else:
            self.status_label.setText(
                f"第 {state.round_number} 轮　·　当前玩家：{state.current().name}"
            )
            self.status_label.setStyleSheet(
                f"color:{TEXT_COLOR};font-size:12px;font-weight:bold;background:#ffe8d3;"
                f"border:1px solid {ORNAMENT_COLOR};border-radius:4px;padding:2px 8px;"
            )

    def select_card(self, card: PetCard) -> None:
        if self.interaction_locked or self.resource_selection or self.game.state.current_player != 0 or self.game.state.finished or self.game.state.pending_specializations or self.ai_battle:
            return
        if self.selected_card is card:
            self.selected_card = None
        else:
            # Selecting another market/reserved card switches the pending
            # choice directly; clicking the selected card again clears it.
            self.selected_card = card
        self.sound_effects.play("click")
        self.refresh()

    def cancel_card_selection(self) -> None:
        if self.interaction_locked:
            return
        self.selected_card = None
        self.refresh()

    def confirm_current_action(self) -> None:
        if self.interaction_locked:
            return
        if self.resource_selection:
            self.confirm_resources()
        elif self.selected_card is not None:
            self.buy_selected()

    def cancel_current_selection(self) -> None:
        if self.interaction_locked:
            return
        if self.resource_selection:
            self.cancel_resource_selection()
        elif self.selected_card is not None:
            self.cancel_card_selection()

    def choose_resource(self, attribute: Attribute) -> None:
        state = self.game.state
        if (
            self.interaction_locked
            or self.selected_card is not None
            or state.current_player != 0
            or state.finished
            or state.pending_specializations
            or self.ai_battle
            or state.resource_pool[attribute] <= 0
        ):
            return
        player = state.current()
        previous_selection = tuple(self.resource_selection)
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
                self.resource_notice = "已选同种两枚；点击上方对应资源可取消，或确认领取。"
            elif attribute in self.resource_selection:
                self.resource_notice = "要领取三种不同资源，请选尚未选择的属性；点击上方已选资源可取消。"
            elif player.resource_count + 3 > player.resource_capacity:
                self.resource_notice = "资源容量不足，不能领取三种不同资源。"
            else:
                self.resource_selection.append(attribute)
        else:
            self.resource_notice = "选择已完整；点击上方对应资源可取消，或确认领取。"
        if tuple(self.resource_selection) != previous_selection:
            self.sound_effects.play("click")
        self.render_controls()

    def cancel_resource(self, index: int) -> None:
        if self.interaction_locked:
            return
        if 0 <= index < len(self.resource_selection):
            self.resource_selection.pop(index)
            self.resource_notice = ""
        self.render_controls()

    def cancel_resource_selection(self) -> None:
        if self.interaction_locked:
            return
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

    def schedule_specialization_prompt(self) -> None:
        if self.specialization_scheduled:
            return
        self.specialization_scheduled = True
        QTimer.singleShot(0, self.prompt_specialization)

    def prompt_specialization(self) -> None:
        self.specialization_scheduled = False
        self.specialization_retry_timer.stop()
        if not self.game.state.pending_specializations:
            return
        if self.has_active_animations():
            # refresh() can request the prompt just before purchase animations
            # are queued. Do not lose that one-shot request: retry after the
            # animation pipeline has had time to drain.
            self.specialization_retry_timer.start()
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
        dialog.setStyleSheet(f"QDialog {{ background:{PANEL_COLOR}; color:{TEXT_COLOR}; }}")
        if cards:
            dialog.resize(650, 580)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(QLabel(specialization_name(effect)))
        if cards:
            intro = QLabel("选择目标卡牌；卡面下方显示本次专精将造成的变化，悬停可查看详细结果。")
            intro.setWordWrap(True)
            intro.setStyleSheet(f"background:transparent;border:0;color:{TEXT_COLOR};font-size:11px;")
            layout.addWidget(intro)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            market = QWidget()
            market_layout = QVBoxLayout(market)
            market_layout.setContentsMargins(2, 2, 8, 2)
            market_layout.setSpacing(8)
            for level in (3, 2, 1):
                level_cards = [card for card in cards if card.level == level]
                cards_by_slot = {
                    self.market_slots[level].get(card.card_id, slot): card
                    for slot, card in enumerate(self.game.state.market.cards[level])
                    if card in level_cards
                }
                slot_count = max(5, len(self.game.state.market.cards[level]))
                row = QHBoxLayout()
                row.setSpacing(5)
                row.setAlignment(Qt.AlignmentFlag.AlignLeft)
                label = QLabel(f"{level}级市场")
                label.setFixedWidth(82)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("font-size:14px;font-weight:bold;background:transparent;border:0;")
                row.addWidget(label)

                preview_row = QHBoxLayout()
                preview_row.setSpacing(5)
                preview_label = QLabel("")
                preview_label.setFixedWidth(82)
                preview_row.addWidget(preview_label)
                for slot in range(slot_count):
                    card = cards_by_slot.get(slot)
                    if card is None:
                        placeholder = QWidget()
                        placeholder.setFixedSize(self.CARD_WIDTH, round(self.CARD_WIDTH * 4 / 3))
                        placeholder.setStyleSheet("background:transparent;border:0;")
                        row.addWidget(placeholder)
                        preview_placeholder = QWidget()
                        preview_placeholder.setFixedSize(self.CARD_WIDTH, 38)
                        preview_placeholder.setStyleSheet("background:transparent;border:0;")
                        preview_row.addWidget(preview_placeholder)
                        continue
                    button = CardButton(self.CARD_WIDTH)
                    self.configure_card(button, card)
                    button.clicked.connect(
                        lambda _=False, c=card: self.settle_specialization(
                            dialog, Action("specialization", card=c)
                        )
                    )
                    row.addWidget(button)

                    preview = self.specialization_card_preview(effect, card)
                    preview_label = QLabel(preview)
                    preview_label.setFixedWidth(self.CARD_WIDTH)
                    preview_label.setMinimumHeight(38)
                    preview_label.setWordWrap(True)
                    preview_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                    accent = self.RESOURCE_COLORS[effect.attribute][1]
                    preview_label.setStyleSheet(
                        f"color:{accent};background:transparent;border:0;font-size:10px;font-weight:bold;"
                    )
                    preview_row.addWidget(preview_label)
                row.addStretch(1)
                preview_row.addStretch(1)
                market_layout.addLayout(row)
                market_layout.addLayout(preview_row)
            market_layout.addStretch(1)
            scroll.setWidget(market)
            layout.addWidget(scroll, 1)
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
        dialog.finished.connect(self.specialization_dialog_finished)
        dialog.exec()

    @staticmethod
    def specialization_card_preview(effect: SpecializationEffect, card: PetCard) -> str:
        if effect.attribute == Attribute.GRASS and effect.stage == 1:
            return f"分数 {card.effective_score}→{card.effective_score + 1}"
        if effect.attribute == Attribute.WATER and effect.stage == 1 and card.cost:
            highest = max(card.cost.values())
            changes = []
            for attribute in ATTRIBUTES:
                amount = card.cost.get(attribute, 0)
                if amount == highest:
                    after = f"{amount - 1}"
                    if amount == 1:
                        after += "(移除)"
                    changes.append(f"{attribute.value}{amount}→{after}")
            prefix = "最高费用随机其一：" if len(changes) > 1 else "费用："
            return prefix + " / ".join(changes)
        return "无可预览变化"

    def settle_specialization(self, dialog: QDialog, action: Action) -> None:
        # A stale interaction lock can survive an animation transition. Clear
        # it when no animation is actually active, otherwise keep the modal
        # open so the pending specialization is not stranded if perform()
        # rejects the action.
        if self.interaction_locked and not self.has_active_animations():
            self.sync_interaction_lock()
        if self.perform(action):
            dialog.accept()

    def specialization_dialog_finished(self) -> None:
        self.specialization_dialog = None
        if self.game.state.pending_specializations and not self.specialization_scheduled:
            # Closing the window (for example with Esc or the title-bar close
            # control) must not leave a mandatory effect pending with no way
            # to resolve it.
            self.schedule_specialization_prompt()

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
            reserved = re.search(r"烧掉了(.+?)预购的(.+?)，归还至(\d+)级牌库；(.+?)保留预购获得的贤者零碎", result)
            purchased = re.search(r"烧掉了(.+?)最低等级的(.+?)，该卡移出对局，(.+?)失去(\d+)分", result)
            if reserved:
                outcome = f"随机烧掉了{reserved.group(1)}预购的{reserved.group(2)}，归还至{reserved.group(3)}级牌库，预购贤者零碎保留！"
            elif purchased:
                outcome = f"没有预购卡，随机烧掉了{purchased.group(1)}最低等级的{purchased.group(2)}并移出对局，失去{purchased.group(4)}分！"
            else:
                outcome = "没有可烧掉的对手卡牌，效果未生效！"
        elif attribute == Attribute.FIRE and stage == 2:
            outcome = f"{player_name}下一张购买的宠物分数翻倍了！"
        elif attribute == Attribute.GRASS and stage == 1:
            match = re.search(r"([^ ]+) 的分数 \+1", result)
            outcome = f"{match.group(1)}的分数提高了1分！" if match else "目标宠物的分数提高了1分！"
        elif attribute == Attribute.GRASS and stage == 2:
            match = re.search(r"获得\s*(\d+)\s*枚临时贤者零碎", result)
            outcome = f"{player_name}获得了{match.group(1)}枚临时贤者零碎！" if match else f"{player_name}获得了临时贤者零碎！"
        elif attribute == Attribute.CUTE and stage == 1:
            outcome = f"{player_name}获得一次攻击免疫，下次遭受其他玩家攻击时免疫了！"
        elif attribute == Attribute.CUTE and stage == 2:
            details = result.strip()
            outcome = f"除{player_name}外，其他玩家的随机二/三级宠物被萌化并降低了分数（{details}）！" if "其他玩家没有" not in details else "其他玩家没有可萌化的二级或三级宠物，效果未生效！"
        elif attribute == Attribute.DARK and stage == 1:
            blocked = re.search(r"(.+?)触发撒娇，免疫了来自(.+?)的攻击", result)
            match = re.search(r"(.+?) 从 (.+?) 偷取 1 枚(.+?)系灵碎", result)
            if blocked:
                outcome = f"{blocked.group(1)}触发撒娇并免疫了{blocked.group(2)}的攻击！"
            else:
                outcome = f"{match.group(1)}从{match.group(2)}偷取了1枚{match.group(3)}系灵碎！" if match else "没有可偷取的灵碎，效果未生效！"
        elif attribute == Attribute.DARK and stage == 2:
            blocked = re.search(r"(.+?)触发撒娇，免疫了来自(.+?)的攻击", result)
            match = re.search(r"(.+?) 从 (.+?) 偷走 (.+)", result)
            if blocked:
                outcome = f"{blocked.group(1)}触发撒娇并免疫了{blocked.group(2)}的攻击！"
            else:
                outcome = f"{match.group(1)}从{match.group(2)}夺取了宠物{match.group(3)}！" if match else "没有可夺取的宠物，效果未生效！"
        else:
            outcome = f"{result.rstrip('。！')}！"

        return f"【{effect_name}】玩家{player_name}触发了{attribute.value}系专精阶段{stage}，{outcome}"

    def widget_rect_in_window(self, widget: QWidget | None) -> QRect:
        if widget is None or not widget.isVisible():
            return QRect()
        return QRect(widget.mapTo(self, QPoint(0, 0)), widget.size())

    @staticmethod
    def card_signature(card: PetCard) -> tuple:
        return (
            card.level,
            card.effective_score,
            tuple((attribute, card.cost.get(attribute, 0)) for attribute in ATTRIBUTES),
            card.transformed_from,
            tuple(sorted(attribute.value for attribute in card.specialization_glows)),
        )

    @staticmethod
    def state_card_locations(state) -> tuple[dict[str, tuple[int | None, str]], dict[str, PetCard]]:
        locations: dict[str, tuple[int | None, str]] = {}
        cards: dict[str, PetCard] = {}
        for level in (1, 2, 3):
            for card in state.market.cards[level]:
                locations[card.card_id] = (None, "market")
                cards[card.card_id] = copy.deepcopy(card)
        for player_index, player in enumerate(state.players):
            for card in player.reserved:
                locations[card.card_id] = (player_index, "reserved")
                cards[card.card_id] = copy.deepcopy(card)
            for card, _chosen_attribute in player.purchased:
                locations[card.card_id] = (player_index, "purchased")
                cards[card.card_id] = copy.deepcopy(card)
        return locations, cards

    def capture_impact_snapshot(self) -> dict:
        state = self.game.state
        locations, cards = self.state_card_locations(state)
        card_origins = {}
        for widget in self.findChildren(CardButton):
            if widget.card_id and widget.card_id not in card_origins:
                rect = self.widget_rect_in_window(widget)
                if rect.isValid() and rect.width() > 0 and rect.height() > 0:
                    card_origins[widget.card_id] = rect
        player_origins = {
            index: self.widget_rect_in_window(label)
            for index, label in self.player_status_labels.items()
        }
        resources = {
            index: {
                **{attribute: player.resources[attribute] for attribute in ATTRIBUTES},
                "光": player.light + player.temporary_light,
            }
            for index, player in enumerate(state.players)
        }
        return {
            "locations": locations,
            "cards": cards,
            "resources": resources,
            "card_origins": card_origins,
            "player_origins": player_origins,
            "current_player": state.current_player,
        }

    def card_zone_target(self, player_index: int, zone: str, anchors: dict[int, QRect]) -> QRect:
        if player_index == 0:
            target_widget = self.reserved_frame if zone == "reserved" else self.purchased_frame
            target = self.widget_rect_in_window(target_widget)
            if target.isValid():
                return QRect(target.center().x() - 36, target.center().y() - 48, 72, 96)
        origin = anchors.get(player_index, QRect())
        if origin.isValid():
            if player_index != 0 and zone == "reserved":
                target_height = min(36, max(1, origin.height() - 2))
                target_width = round(target_height * 3 / 4)
                return QRect(
                    origin.right() - target_width - 3,
                    origin.center().y() - target_height // 2,
                    target_width,
                    target_height,
                )
            return QRect(origin.center().x() - 36, origin.center().y() - 48, 72, 96)
        return QRect(self.rect().center().x() - 36, self.rect().center().y() - 48, 72, 96)

    def resolve_card_acquisition_targets(self, events: list[dict]) -> None:
        """Resolve acquisition landings against the currently rendered UI."""
        for event in events:
            if event.get("kind") == "reserve-acquire":
                player_index = event.get("player_index")
                if player_index == 0:
                    target_widget = self.reserved_card_views.get(event["card_id"])
                    target = self.widget_rect_in_window(target_widget)
                else:
                    continue
            elif event.get("zone") == "purchased" and event.get("kind") in ("market-purchase", "acquire"):
                if event.get("player_index") != 0:
                    continue
                target_widget = self.purchased_card_views.get(event["card_id"])
                if target_widget is not None:
                    self.ensure_purchased_card_visible(target_widget)
                target = self.widget_rect_in_window(target_widget)
            else:
                continue
            if target.isValid() and target.width() > 0 and target.height() > 0:
                event["target"] = target

    def build_impact_events(
        self,
        before: dict,
        action: Action,
        messages: list[str],
        specialization_effect: SpecializationEffect | None,
    ) -> list[dict]:
        state = self.game.state
        after_locations, after_cards = self.state_card_locations(state)
        events: list[dict] = []

        for player_index, player in enumerate(state.players):
            previous = before["resources"][player_index]
            current = {
                **{attribute: player.resources[attribute] for attribute in ATTRIBUTES},
                "光": player.light + player.temporary_light,
            }
            changes = []
            color = "#bd903d"
            for attribute in ATTRIBUTES:
                delta = current[attribute] - previous[attribute]
                if delta:
                    sign = "+" if delta > 0 else "−"
                    changes.append(f"{attribute.value}{sign}{abs(delta)}")
                    if len(changes) == 1:
                        color = self.RESOURCE_COLORS[attribute][1]
            light_delta = current["光"] - previous["光"]
            if light_delta:
                sign = "+" if light_delta > 0 else "−"
                changes.append(f"贤者{sign}{abs(light_delta)}")
            if changes:
                events.append({
                    "kind": "resource-status",
                    "player_index": player_index,
                    "text": "　".join(changes),
                    "color": color,
                    "start": before["player_origins"].get(player_index, QRect()),
                })

        burned_id = None
        burned_owner = None
        if specialization_effect and specialization_effect.attribute == Attribute.FIRE and specialization_effect.stage == 1:
            result = (messages[0].partition("：")[2] or messages[0]) if messages else ""
            match = re.search(r"烧掉了(.+?)预购的([^，]+)", result)
            if not match:
                match = re.search(r"烧掉了(.+?)最低等级的([^，]+)", result)
            if match:
                burned_owner, burned_id = match.group(1), match.group(2)

        all_card_ids = set(before["locations"]) | set(after_locations)
        for card_id in sorted(all_card_ids):
            old_location = before["locations"].get(card_id)
            new_location = after_locations.get(card_id)
            old_card = before["cards"].get(card_id)
            new_card = after_cards.get(card_id)
            card = new_card or old_card
            if card is None:
                continue

            if card_id == burned_id:
                owner_index = next(
                    (index for index, player in enumerate(state.players) if player.name == burned_owner),
                    old_location[0] if old_location else None,
                )
                source = before["card_origins"].get(card_id)
                if owner_index not in (None, 0):
                    source = before["player_origins"].get(owner_index) or source
                elif source is None and owner_index is not None:
                    source = before["player_origins"].get(owner_index)
                events.append({
                    "kind": "burn" if owner_index == 0 else "burn-in-place",
                    "card": copy.deepcopy(old_card or card),
                    "card_id": card_id,
                    "player_index": owner_index,
                    "text": f"{burned_owner}的{card_id}被引燃了",
                    "color": self.RESOURCE_COLORS[Attribute.FIRE][1],
                    "start": source or QRect(),
                })
                continue

            if old_location == new_location:
                if old_card is None or new_card is None or self.card_signature(old_card) == self.card_signature(new_card):
                    continue
                kind = "changed"
                color = (
                    self.RESOURCE_COLORS[specialization_effect.attribute][1]
                    if specialization_effect else "#7f654e"
                )
                text = f"{card_id}受到影响"
                if old_location and old_location[1] == "market" and specialization_effect:
                    # Water/grass stage-one effects alter a market card in place.
                    # Let the updated card and its glow show immediately instead
                    # of covering it with a floating, fading card overlay.
                    if specialization_effect.attribute in (Attribute.WATER, Attribute.GRASS):
                        continue
                    kind = "market-change"
                elif old_location and old_location[1] == "purchased":
                    text = f"{card_id}形态改变"
                source = before["card_origins"].get(card_id)
                if source is None and old_location and old_location[0] is not None:
                    source = before["player_origins"].get(old_location[0])
                events.append({
                    "kind": kind,
                    "card": copy.deepcopy(new_card),
                    "card_id": card_id,
                    "text": text,
                    "color": color,
                    "start": source or QRect(),
                })
                continue

            if old_location is None or new_location is None:
                continue
            old_player, old_zone = old_location
            new_player, new_zone = new_location
            if old_player is not None and new_player is None:
                continue
            if old_player == new_player and old_zone == new_zone:
                continue

            source = before["card_origins"].get(card_id)
            if source is None and old_player is not None:
                source = before["player_origins"].get(old_player)
            if old_player is not None and new_player is not None and old_player != new_player:
                if (
                    specialization_effect
                    and specialization_effect.attribute == Attribute.DARK
                    and specialization_effect.stage == 2
                    and old_zone == "purchased"
                ):
                    kind = "center-impact" if old_player == 0 else "status-impact"
                else:
                    kind = "transfer"
                text = (
                    f"{state.players[old_player].name}的{card_id}被吞噬了"
                    if kind in ("center-impact", "status-impact")
                    else f"{state.players[new_player].name}获得{card_id}"
                )
                if kind == "status-impact":
                    source = before["player_origins"].get(old_player) or source
            elif (
                action.kind == "buy"
                and old_player is None
                and old_zone == "market"
                and new_player is not None
                and new_zone == "purchased"
            ):
                kind = "market-purchase"
                text = f"{state.players[new_player].name}购买{card_id}"
            elif (
                action.kind == "reserve"
                and old_player is None
                and old_zone == "market"
                and new_player is not None
                and new_zone == "reserved"
            ):
                kind = "reserve-acquire"
                text = f"{state.players[new_player].name}预购{card_id}"
            elif new_player is not None:
                kind = "acquire"
                text = f"{state.players[new_player].name}获得{card_id}"
            else:
                continue
            target = self.card_zone_target(new_player, new_zone, before["player_origins"])
            events.append({
                "kind": kind,
                "card": copy.deepcopy(old_card if kind in ("center-impact", "status-impact") else card),
                "card_id": card_id,
                "player_index": new_player,
                "affected_player_index": old_player if kind == "status-impact" else None,
                "zone": new_zone,
                "source_zone": old_zone,
                "text": text,
                "color": (
                    "#bd903d" if kind in ("acquire", "reserve-acquire")
                    else self.RESOURCE_COLORS[Attribute.DARK][1]
                ),
                "start": source or QRect(),
                "target": target,
            })
        return events

    def enqueue_impact_animations(self, events: list[dict]) -> None:
        # Start purchase animations before other feedback: the source market
        # card has already been removed by refresh(), so its overlay must take
        # over the exact source position without a visible gap.
        landing_events = [
            event for event in events
            if event.get("kind") == "market-purchase"
            or (
                event.get("player_index") == 0
                and event.get("zone") == "purchased"
                and event.get("kind") == "acquire"
            )
        ]
        other_events = [event for event in events if event not in landing_events]
        self.impact_animation_queue.extend((*landing_events, *other_events))
        self.sync_interaction_lock()
        self.play_next_impact_animation()

    def has_active_animations(self) -> bool:
        return bool(
            self.impact_animation_running
            or self.impact_animation_queue
            or self.wizard_animation_running
            or self.wizard_animation_queue
            or self.turn_animation_running
            or self.turn_banner_pending
        )

    def sync_interaction_lock(self) -> None:
        locked = self.has_active_animations()
        if self.interaction_locked == locked:
            return
        self.interaction_locked = locked
        for marker in getattr(self, "selection_markers", []):
            marker.setEnabled(not locked)
        restart_button = getattr(self, "restart_button", None)
        if restart_button is not None:
            restart_button.setEnabled(not locked)
        for button in self.findChildren(QPushButton, "specializationHelpButton"):
            button.setEnabled(not locked)
        for card in self.findChildren(DraggableDualCard):
            card.draggable = (
                not locked
                and self.game.state.current_player == 0
                and not self.ai_battle
                and not self.game.state.finished
                and not self.game.state.pending_specializations
            )
        if hasattr(self, "resource_buttons"):
            self.render_controls()

    def play_resource_card_animation(self, resource_event: dict, card_event: dict) -> None:
        """Animate resource feedback alongside a card landing or purchase exit."""
        resource_overlay = self.create_resource_impact_overlay(resource_event)
        resource_width = min(300, max(96, len(resource_event["text"]) * 16 + 20))
        resource_start = resource_event.get("start", QRect())
        if not resource_start.isValid():
            resource_start = QRect(self.rect().center().x() - 48, self.rect().center().y(), 96, 32)
        resource_start = QRect(
            resource_start.center().x() - resource_width // 2,
            resource_start.center().y() - 16,
            resource_width,
            32,
        )
        resource_end = QRect(
            resource_start.x(), resource_start.y() - 24,
            resource_start.width(), resource_start.height(),
        )

        card: PetCard = card_event["card"]
        card_overlay = CardButton(76, self)
        card_overlay.set_card_content(
            "/".join(attribute.value for attribute in card.attributes),
            str(card.effective_score),
            card.card_id,
            [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)],
        )
        card_overlay.setMinimumSize(1, 1)
        card_overlay.setMaximumSize(1000, 1000)
        card_overlay.set_card_style(
            background="#fff5df",
            border_color="#b8b8b8",
            border_width=2,
            padding=4,
        )
        card_start = card_event.get("start", QRect())
        if not card_start.isValid() or card_start.width() <= 0 or card_start.height() <= 0:
            center = self.rect().center()
            card_start = QRect(center.x() - 38, center.y() + 135, 76, 100)
        card_target = card_event.get("target", QRect())
        if not card_target.isValid():
            center = self.rect().center()
            target_width = 44 if card_event.get("player_index") == 0 else 72
            target_height = round(target_width * 4 / 3)
            card_target = QRect(
                center.x() - target_width // 2,
                center.y() - target_height // 2,
                target_width,
                target_height,
            )
        is_ai_market_purchase = (
            card_event.get("kind") == "market-purchase"
            and card_event.get("player_index") != 0
        )
        # Preserve the source card's exact top-left position when it already
        # has a card-sized rect. Re-centering an odd/even-sized QRect can move
        # it by one pixel because QRect.center() is integer-based.
        if card_start.width() > 160 or card_start.height() > 120:
            card_start = QRect(
                card_start.center().x() - 38,
                card_start.center().y() - 50,
                76,
                100,
            )
        if is_ai_market_purchase:
            card_target = QRect(
                card_start.x(),
                card_start.y() - 58,
                card_start.width(),
                card_start.height(),
            )

        resource_opacity = QGraphicsOpacityEffect(resource_overlay)
        resource_overlay.setGraphicsEffect(resource_opacity)
        card_opacity = None
        if is_ai_market_purchase:
            card_opacity = QGraphicsOpacityEffect(card_overlay)
            card_overlay.setGraphicsEffect(card_opacity)
        if card_event.get("zone") == "reserved":
            card_overlay.setProperty("reservedCardId", card_event["card_id"])
        elif card_event.get("zone") == "purchased" and card_event.get("player_index") == 0:
            card_overlay.setProperty("purchasedCardId", card_event["card_id"])
        resource_overlay.setGeometry(resource_start)
        card_overlay.setGeometry(card_start)
        resource_overlay.show()
        resource_overlay.raise_()
        card_overlay.show()
        card_overlay.raise_()
        self.keep_turn_banner_on_top()
        self.impact_animation_overlays = [resource_overlay, card_overlay]
        self.impact_animation_overlay = card_overlay

        group = QParallelAnimationGroup(self)
        resource_group = QParallelAnimationGroup(group)
        resource_move = QPropertyAnimation(resource_overlay, b"geometry", resource_group)
        resource_move.setDuration(640)
        resource_move.setStartValue(resource_start)
        resource_move.setEndValue(resource_end)
        resource_fade = QPropertyAnimation(resource_opacity, b"opacity", resource_group)
        resource_fade.setDuration(640)
        resource_fade.setStartValue(1.0)
        resource_fade.setEndValue(0.0)
        resource_group.addAnimation(resource_move)
        resource_group.addAnimation(resource_fade)

        card_group = QParallelAnimationGroup(group)
        card_move = QPropertyAnimation(card_overlay, b"geometry", card_group)
        card_move.setDuration(620 if is_ai_market_purchase else 640)
        card_move.setStartValue(card_start)
        card_move.setEndValue(card_target)
        card_move.setEasingCurve(
            QEasingCurve.Type.OutCubic if is_ai_market_purchase else QEasingCurve.Type.Linear
        )
        card_group.addAnimation(card_move)
        if card_opacity is not None:
            card_fade = QPropertyAnimation(card_opacity, b"opacity", card_group)
            card_fade.setDuration(620)
            card_fade.setStartValue(1.0)
            card_fade.setEndValue(0.0)
            card_group.addAnimation(card_fade)

        group.addAnimation(resource_group)
        group.addAnimation(card_group)
        group.finished.connect(
            lambda overlays=self.impact_animation_overlays.copy(): self.finish_impact_animation(overlays)
        )
        self.impact_animation = group
        group.start()

    @staticmethod
    def impact_card_style(event: dict) -> str:
        kind = event["kind"]
        destructive = kind in ("burn", "burn-in-place", "center-impact", "status-impact")
        background = "#fff5df"
        foreground = "#252525"
        border = "#b8b8b8"
        border_width = 4 if kind in ("burn", "burn-in-place", "status-impact") else 2
        return (
            "QPushButton { "
            f"color:{foreground}; background:{background}; "
            f"border:{border_width}px solid {border}; padding:4px; border-radius:{CARD_CORNER_RADIUS}px; "
            "}"
        )

    def recolor_impact_card(
        self,
        overlay: CardButton,
        event: dict,
        caption: QLabel | None,
    ) -> None:
        if caption is not None:
            caption.show()
            caption.raise_()
        self.keep_turn_banner_on_top()

    @staticmethod
    def clear_impact_card_content(overlay: CardButton) -> None:
        overlay.top_left = ""
        overlay.top_right = ""
        overlay.display_card_id = ""
        overlay.cost_items = []
        overlay.update()

    def create_resource_impact_overlay(self, event: dict) -> QFrame:
        """Build a resource-change popup from shard icons and signed counts."""
        overlay = QFrame(self)
        overlay.setObjectName("resourceImpactOverlay")
        overlay.setStyleSheet(self.resource_impact_style(event))
        row = QHBoxLayout(overlay)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(7)
        row.addStretch(1)
        for change in event.get("text", "").split():
            attribute = next(
                (item for item in ATTRIBUTES if change.startswith(item.value)),
                None,
            )
            if attribute is not None:
                resource_name = attribute.value
                pixmap = resource_shard_pixmap(attribute, 16, self.devicePixelRatioF())
                color = self.RESOURCE_COLORS[attribute][1]
            else:
                resource_name = "贤者"
                pixmap = sage_shard_pixmap(16, self.devicePixelRatioF())
                color = "#bd903d"

            token = QWidget(overlay)
            token.setStyleSheet("background:transparent;border:0;padding:0;")
            token_row = QHBoxLayout(token)
            token_row.setContentsMargins(0, 0, 0, 0)
            token_row.setSpacing(2)
            icon = QLabel(token)
            icon.setFixedSize(16, 16)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet("background:transparent;border:0;padding:0;")
            if not pixmap.isNull():
                icon.setPixmap(pixmap)
            delta = QLabel(change[len(resource_name):], token)
            delta.setStyleSheet(
                f"background:transparent;border:0;padding:0;color:{color};font-size:13px;font-weight:bold;"
            )
            token_row.addWidget(icon)
            token_row.addWidget(delta)
            row.addWidget(token)
        row.addStretch(1)
        return overlay

    @staticmethod
    def resource_impact_style(event: dict) -> str:
        changes = event.get("text", "").split()
        light_only = bool(changes) and all(change.startswith("贤者") for change in changes)
        background, foreground, border = (
            ("#fff1b8", "#634b16", "#d2aa4c")
            if light_only
            else ("#ffffff", "#333333", "#c8c8c8")
        )
        return (
            "QFrame#resourceImpactOverlay { "
            f"color:{foreground}; background:{background}; border:1px solid {border}; "
            "border-radius:6px; }"
        )

    def play_next_impact_animation(self) -> None:
        if self.impact_animation_running or self.wizard_animation_running:
            return
        if self.turn_animation_running and not (
            self.impact_animation_queue
            and self.impact_animation_queue[0].get("kind") == "market-refill"
        ):
            return
        if not self.impact_animation_queue:
            if self.wizard_animation_queue:
                self.play_next_wizard_animation()
                return
            if self.turn_banner_pending:
                self.play_turn_banner()
                if self.deferred_market_card_ids:
                    if self.market_refill_without_animation:
                        self.deferred_market_card_ids.clear()
                        self.render_market()
                        self.keep_turn_banner_on_top()
                    else:
                        # refresh() has just rebuilt the market rows. Wait for Qt
                        # to place their new slot widgets before reading geometry.
                        QTimer.singleShot(0, self.start_deferred_market_refill)
                self.market_refill_without_animation = False
                return
            if self.turn_animation_running:
                return
            if (
                self.game.state.pending_specializations
                and self.game.state.pending_specializations[0].player_index == 0
                and not self.ai_battle
            ):
                self.schedule_specialization_prompt()
            elif self.end_dialog_pending:
                self.show_end_dialog()
            return

        event = self.impact_animation_queue.pop(0)
        if event.get("kind") == "market-purchase" and event.get("player_index") != 0:
            resource_event = next(
                (
                    queued for queued in self.impact_animation_queue
                    if queued.get("kind") == "resource-status"
                    and queued.get("player_index") == event.get("player_index")
                ),
                None,
            )
            if resource_event is not None:
                self.impact_animation_queue.remove(resource_event)
                self.impact_animation_running = True
                self.play_resource_card_animation(resource_event, event)
                return
        if (
            event["kind"] == "resource-status"
            and "贤者+1" in event["text"]
            and self.impact_animation_queue
            and self.impact_animation_queue[0]["kind"] == "reserve-acquire"
        ):
            card_event = self.impact_animation_queue.pop(0)
            self.impact_animation_running = True
            self.play_resource_card_animation(event, card_event)
            return
        if (
            event.get("player_index") == 0
            and event.get("zone") == "purchased"
            and event.get("kind") in ("market-purchase", "acquire")
        ):
            resource_event = next(
                (
                    queued for queued in self.impact_animation_queue
                    if queued.get("kind") == "resource-status"
                    and queued.get("player_index") == 0
                ),
                None,
            )
            if resource_event is not None:
                self.impact_animation_queue.remove(resource_event)
                self.impact_animation_running = True
                self.play_resource_card_animation(resource_event, event)
                return
        self.impact_animation_running = True
        center = self.rect().center()
        start = event.get("start", QRect())
        status_row = QRect()
        if event.get("kind") in ("burn-in-place", "status-impact") and not start.isValid():
            affected_index = event.get("affected_player_index", event.get("player_index"))
            status_widget = self.player_status_labels.get(affected_index)
            if status_widget is not None:
                start = self.widget_rect_in_window(status_widget)
        if not start.isValid() or start.width() <= 0 or start.height() <= 0:
            start = QRect(center.x() - 38, center.y() + 135, 76, 100)

        if event["kind"] == "resource-status":
            overlay: QWidget = self.create_resource_impact_overlay(event)
            width = min(300, max(96, len(event["text"]) * 16 + 20))
            start = QRect(start.center().x() - width // 2, start.center().y() - 16, width, 32)
            target = QRect(start.x(), start.y() - 24, start.width(), start.height())
            rise = target
        else:
            card: PetCard = event["card"]
            overlay = CardButton(76, self)
            overlay.set_card_content(
                "/".join(attribute.value for attribute in card.attributes),
                str(card.effective_score),
                card.card_id,
                [(attribute.value, card.cost[attribute]) for attribute in ATTRIBUTES if card.cost.get(attribute)],
            )
            overlay.setMinimumSize(1, 1)
            overlay.setMaximumSize(1000, 1000)
            overlay.set_card_style(
                background="#fff5df",
                border_color="#b8b8b8",
                border_width=4 if event["kind"] in ("burn", "burn-in-place", "status-impact") else 2,
                padding=4,
                text_color="#252525",
            )
            if event["kind"] in ("acquire", "reserve-acquire", "transfer"):
                target = event.get("target", QRect(center.x() - 38, center.y() - 50, 76, 100))
                if (
                    event.get("player_index") == 0
                    and (
                        event["kind"] == "reserve-acquire"
                        or (event["kind"] == "acquire" and event.get("zone") == "purchased")
                    )
                ):
                    rise = target
                else:
                    target = QRect(target.center().x() - 38, target.center().y() - 50, 76, 100)
                    rise = QRect(target.x(), target.y() - 55, target.width(), target.height())
            elif event["kind"] == "market-purchase":
                if event.get("player_index") == 0 and event.get("zone") == "purchased":
                    target = event.get("target", QRect())
                    if not target.isValid():
                        target = QRect(start.x(), start.y() - 58, start.width(), start.height())
                else:
                    target = QRect(start.x(), start.y() - 58, start.width(), start.height())
                rise = target
            elif event["kind"] == "market-refill":
                target = event["target"]
                rise = target
            elif event["kind"] in ("burn", "center-impact"):
                width, height, rise_distance = 190, 254, 180
                target = QRect(center.x() - width // 2, center.y() - height // 2, width, height)
                rise = QRect(target.x(), target.y() - rise_distance, target.width(), target.height())
            else:
                target = QRect(start.x(), start.y() - 58, start.width(), start.height())
                rise = target
            status_impact = event["kind"] in ("burn-in-place", "status-impact")
            if status_impact:
                status_row = QRect(start)
                width, height = 24, 32
                y = status_row.center().y() - (height - 1) // 2
                target = QRect(status_row.right() - width - 6, y, width, height)
                start = QRect(target)
                rise = target
            elif start.width() > 160 or start.height() > 120:
                start = QRect(start.center().x() - 38, start.center().y() - 50, 76, 100)
            elif event["kind"] not in (
                "acquire", "reserve-acquire", "transfer", "burn", "burn-in-place", "center-impact",
                "status-impact", "market-refill", "market-purchase"
            ):
                target = QRect(start.x(), start.y() - 58, start.width(), start.height())
                rise = target

        impact_caption: QLabel | None = None
        caption_opacity: QGraphicsOpacityEffect | None = None
        caption_start = QRect()
        caption_rise = QRect()
        if event["kind"] in ("burn", "center-impact") and event.get("text"):
            impact_caption = QLabel(event["text"], self)
            impact_caption.setObjectName("specializationImpactCaption")
            caption_font = QFont(QApplication.font())
            caption_font.setBold(True)
            status_impact = event["kind"] in ("burn-in-place", "status-impact")
            caption_font.setPointSize(11 if status_impact else 15)
            impact_caption.setFont(caption_font)
            if status_impact:
                caption_height = max(22, status_row.height() - 8)
                max_caption_width = max(80, status_row.width() - target.width() - 20)
                caption_width = min(
                    max_caption_width,
                    max(100, math.ceil(QFontMetricsF(caption_font).horizontalAdvance(event["text"])) + 12),
                )
                caption_x = status_row.x() + 6
                caption_y = status_row.y() + (status_row.height() - caption_height) // 2
            else:
                caption_width = min(
                    self.width() - 24,
                    max(220, math.ceil(QFontMetricsF(caption_font).horizontalAdvance(event["text"])) + 24),
                )
                caption_height = 40
                caption_x = min(
                    self.width() - caption_width - 12,
                    max(12, target.center().x() - caption_width // 2),
                )
                caption_y = max(8, target.y() - caption_height - 10)
            caption_start = QRect(caption_x, caption_y, caption_width, caption_height)
            caption_rise = caption_start.translated(0, rise.y() - target.y())
            impact_caption.setGeometry(caption_start)
            impact_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            impact_caption.setStyleSheet(
                "QLabel#specializationImpactCaption { "
                f"color:{event['color']}; background:#fffaf0; border:2px solid {event['color']}; "
                "border-radius:6px; padding:3px 8px; font-weight:bold; }"
            )
            caption_opacity = QGraphicsOpacityEffect(impact_caption)
            caption_opacity.setOpacity(1.0)
            impact_caption.setGraphicsEffect(caption_opacity)
            impact_caption.hide()

        overlay.setGeometry(start)
        opacity = QGraphicsOpacityEffect(overlay)
        opacity.setOpacity(1.0)
        overlay.setGraphicsEffect(opacity)
        overlay.show()
        overlay.raise_()
        self.keep_turn_banner_on_top()
        if event.get("kind") == "reserve-acquire":
            overlay.setProperty("reservedCardId", event["card_id"])
        elif (
            event.get("player_index") == 0
            and event.get("zone") == "purchased"
            and event.get("kind") in ("market-purchase", "acquire")
        ):
            overlay.setProperty("purchasedCardId", event["card_id"])
        self.impact_animation_overlay = overlay
        self.impact_animation_overlays = [overlay]
        if impact_caption is not None:
            self.impact_animation_overlays.append(impact_caption)

        group = QSequentialAnimationGroup(self)
        if event.get("kind") in ("burn", "center-impact"):
            enlarge = QPropertyAnimation(overlay, b"geometry", group)
            enlarge.setDuration(380)
            enlarge.setStartValue(start)
            enlarge.setEndValue(target)
            enlarge.finished.connect(
                lambda card_overlay=overlay, impact_event=event, caption=impact_caption:
                self.recolor_impact_card(card_overlay, impact_event, caption)
            )
            group.addAnimation(enlarge)
            recolor_group = QParallelAnimationGroup(group)
            recolor = QPropertyAnimation(overlay, b"impactTint", recolor_group)
            recolor.setDuration(420)
            recolor.setStartValue(QColor(0, 0, 0, 0))
            recolor.setEndValue(QColor(event["color"]))
            content_fade = QPropertyAnimation(overlay, b"impactContentOpacity", recolor_group)
            content_fade.setDuration(420)
            content_fade.setStartValue(1.0)
            content_fade.setEndValue(0.0)
            content_fade.finished.connect(
                lambda card_overlay=overlay: self.clear_impact_card_content(card_overlay)
            )
            recolor_group.addAnimation(recolor)
            recolor_group.addAnimation(content_fade)
            group.addAnimation(recolor_group)
            group.addPause(160)
        elif event["kind"] in ("burn-in-place", "status-impact"):
            recolor_pause = QPauseAnimation(180, group)
            recolor_pause.finished.connect(
                lambda card_overlay=overlay, impact_event=event, caption=impact_caption:
                self.recolor_impact_card(card_overlay, impact_event, caption)
            )
            group.addAnimation(recolor_pause)
            recolor_group = QParallelAnimationGroup(group)
            recolor = QPropertyAnimation(overlay, b"impactTint", recolor_group)
            recolor.setDuration(420)
            recolor.setStartValue(QColor(0, 0, 0, 0))
            recolor.setEndValue(QColor(event["color"]))
            content_fade = QPropertyAnimation(overlay, b"impactContentOpacity", recolor_group)
            content_fade.setDuration(420)
            content_fade.setStartValue(1.0)
            content_fade.setEndValue(0.0)
            content_fade.finished.connect(
                lambda card_overlay=overlay: self.clear_impact_card_content(card_overlay)
            )
            recolor_group.addAnimation(recolor)
            recolor_group.addAnimation(content_fade)
            group.addAnimation(recolor_group)
            group.addPause(160)
        if event["kind"] in ("burn", "burn-in-place", "center-impact", "status-impact"):
            fade_group = QParallelAnimationGroup(group)
            rise_animation = QPropertyAnimation(overlay, b"geometry", fade_group)
            rise_animation.setDuration(560)
            rise_animation.setStartValue(target)
            rise_animation.setEndValue(rise)
            opacity_animation = QPropertyAnimation(opacity, b"opacity", fade_group)
            opacity_animation.setDuration(560)
            opacity_animation.setStartValue(1.0)
            opacity_animation.setEndValue(0.0)
            fade_group.addAnimation(rise_animation)
            fade_group.addAnimation(opacity_animation)
            if impact_caption is not None and caption_opacity is not None:
                caption_move = QPropertyAnimation(impact_caption, b"geometry", fade_group)
                caption_move.setDuration(560)
                caption_move.setStartValue(caption_start)
                caption_move.setEndValue(caption_rise)
                caption_fade = QPropertyAnimation(caption_opacity, b"opacity", fade_group)
                caption_fade.setDuration(560)
                caption_fade.setStartValue(1.0)
                caption_fade.setEndValue(0.0)
                fade_group.addAnimation(caption_move)
                fade_group.addAnimation(caption_fade)
            group.addAnimation(fade_group)
        elif event["kind"] == "market-refill":
            drop = QPropertyAnimation(overlay, b"geometry", group)
            drop.setDuration(380)
            drop.setStartValue(start)
            drop.setEndValue(target)
            drop.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(drop)
            overlay.setProperty("marketRefillCardId", event["card_id"])
        elif (
            event.get("player_index") == 0
            and (
                (event["kind"] == "reserve-acquire" and event.get("zone") == "reserved")
                or (event["kind"] in ("market-purchase", "acquire") and event.get("zone") == "purchased")
            )
        ):
            move_to_card_slot = QPropertyAnimation(overlay, b"geometry", group)
            move_to_card_slot.setDuration(640)
            move_to_card_slot.setStartValue(start)
            move_to_card_slot.setEndValue(target)
            move_to_card_slot.setEasingCurve(QEasingCurve.Type.Linear)
            group.addAnimation(move_to_card_slot)
        elif event["kind"] == "market-purchase":
            exit_group = QParallelAnimationGroup(group)
            rise = QPropertyAnimation(overlay, b"geometry", exit_group)
            rise.setDuration(620)
            rise.setStartValue(start)
            rise.setEndValue(target)
            rise.setEasingCurve(QEasingCurve.Type.OutCubic)
            fade = QPropertyAnimation(opacity, b"opacity", exit_group)
            fade.setDuration(620)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            exit_group.addAnimation(rise)
            exit_group.addAnimation(fade)
            group.addAnimation(exit_group)
        elif event["kind"] in ("resource-status", "changed", "market-change"):
            float_group = QParallelAnimationGroup(group)
            duration = 640 if event["kind"] == "resource-status" else 620
            movement = QPropertyAnimation(overlay, b"geometry", float_group)
            movement.setDuration(duration)
            movement.setStartValue(start)
            movement.setEndValue(target)
            fade = QPropertyAnimation(opacity, b"opacity", float_group)
            fade.setDuration(duration)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            float_group.addAnimation(movement)
            float_group.addAnimation(fade)
            group.addAnimation(float_group)
        else:
            movement = QPropertyAnimation(overlay, b"geometry", group)
            movement.setDuration(430)
            movement.setStartValue(start)
            movement.setEndValue(target)
            group.addAnimation(movement)
            group.addPause(100)
            fade = QPropertyAnimation(opacity, b"opacity", group)
            fade.setDuration(260)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            group.addAnimation(fade)
        group.finished.connect(
            lambda animated_widgets=self.impact_animation_overlays.copy():
            self.finish_impact_animation(animated_widgets)
        )
        self.impact_animation = group
        group.start()

    def finish_impact_animation(self, overlays: QWidget | list[QWidget]) -> None:
        animated_overlays = overlays if isinstance(overlays, list) else [overlays]
        market_refill_card_ids = [
            str(card_id)
            for overlay in animated_overlays
            if (card_id := overlay.property("marketRefillCardId"))
        ]
        reserved_card_ids = [
            str(card_id)
            for overlay in animated_overlays
            if (card_id := overlay.property("reservedCardId"))
        ]
        purchased_card_ids = [
            str(card_id)
            for overlay in animated_overlays
            if (card_id := overlay.property("purchasedCardId"))
        ]
        if self.impact_animation_overlay in animated_overlays:
            self.impact_animation_overlay = None
        self.impact_animation_overlays = []
        # Clear the state machine before rebuilding widgets. If a redraw raises,
        # the pending effect must not remain blocked behind a stale animation
        # flag or interaction lock.
        self.impact_animation_running = False
        self.impact_animation = None
        try:
            for overlay in animated_overlays:
                overlay.deleteLater()
            if market_refill_card_ids:
                self.deferred_market_card_ids.difference_update(market_refill_card_ids)
                self.render_market()
            if reserved_card_ids:
                self.deferred_reserved_card_ids.difference_update(reserved_card_ids)
                self.render_reserved()
            if purchased_card_ids:
                self.deferred_purchased_card_ids.difference_update(purchased_card_ids)
                self.render_purchased()
                for card_id in purchased_card_ids:
                    target_widget = self.purchased_card_views.get(card_id)
                    if target_widget is not None:
                        self.ensure_purchased_card_visible(target_widget)
        finally:
            try:
                self.sync_interaction_lock()
            finally:
                self.play_next_impact_animation()

    def start_deferred_market_refill(self) -> None:
        self.reveal_deferred_market_cards()
        self.play_next_impact_animation()

    def reveal_deferred_market_cards(self) -> None:
        if not self.deferred_market_card_ids:
            return
        pending_ids = set(self.deferred_market_card_ids)
        refill_events: list[dict] = []
        for level in (3, 2, 1):
            for card in self.game.state.market.cards[level]:
                if card.card_id not in pending_ids:
                    continue
                slot = self.market_slots[level].get(card.card_id)
                slot_widgets = self.market_slot_widgets.get(level, [])
                if slot is None or slot >= len(slot_widgets):
                    continue
                target_widget = slot_widgets[slot]
                target_top_left = target_widget.mapTo(self, QPoint(0, 0))
                target = QRect(
                    target_top_left.x(), target_top_left.y(),
                    target_widget.width(), target_widget.height(),
                )
                start = target.translated(0, -min(28, target.height() // 3))
                refill_events.append({
                    "kind": "market-refill",
                    "card": copy.deepcopy(card),
                    "card_id": card.card_id,
                    "color": "#b8b8b8",
                    "start": start,
                    "target": target,
                })
        self.impact_animation_queue.extend(refill_events)
        unanimated_ids = pending_ids - {event["card_id"] for event in refill_events}
        if unanimated_ids:
            self.deferred_market_card_ids.difference_update(unanimated_ids)
            self.render_market()

    def perform(self, action: Action) -> bool:
        if self.interaction_locked or self.has_active_animations():
            return False
        try:
            actor_player = self.game.state.current()
            actor = actor_player.name
            impact_snapshot = self.capture_impact_snapshot()
            specialization_effect = (
                self.game.state.pending_specializations[0]
                if action.kind == "specialization" and self.game.state.pending_specializations
                else None
            )
            specialization_attribute = specialization_effect.attribute if specialization_effect else None
            previous_duals = actor_player.dual_cards()
            previous_wizards = tuple(actor_player.wizard_cards)
            messages = self.game.execute(action)
            old_market_ids = {
                card_id
                for card_id, location in impact_snapshot["locations"].items()
                if location == (None, "market")
            }
            new_market_ids = {
                card.card_id
                for level in (1, 2, 3)
                for card in self.game.state.market.cards[level]
            }
            # Any cards replenished by this turn's rotation should enter on the
            # next player's turn, regardless of whether they were bought or reserved.
            self.deferred_market_card_ids.update(new_market_ids - old_market_ids)
            previous_reserved_ids = {
                card_id
                for card_id, location in impact_snapshot["locations"].items()
                if location == (0, "reserved")
            }
            current_reserved_ids = {
                card.card_id for card in self.game.state.players[0].reserved
            }
            self.deferred_reserved_card_ids.update(current_reserved_ids - previous_reserved_ids)
            previous_purchased_ids = {
                card_id
                for card_id, location in impact_snapshot["locations"].items()
                if location == (0, "purchased")
            }
            current_purchased_ids = {
                card.card_id for card, _chosen in self.game.state.players[0].purchased
            }
            self.deferred_purchased_card_ids.update(current_purchased_ids - previous_purchased_ids)
            turn_started = (
                not self.game.state.finished
                and impact_snapshot["current_player"] != self.game.state.current_player
            )
            if turn_started:
                # Water/grass specialization does not move a market card; show
                # the next turn's refill without a card flight.
                self.market_refill_without_animation = bool(
                    specialization_effect
                    and specialization_effect.attribute in (Attribute.WATER, Attribute.GRASS)
                )
            if actor_player is self.game.state.players[0] and not self.ai_battle and action.kind in (
                "buy", "reserve", "same", "different"
            ):
                self.sound_effects.play("coin")
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
                followup_messages = messages[1:]
            else:
                was_reserved_purchase = (
                    action.kind == "buy"
                    and action.card is not None
                    and impact_snapshot["locations"].get(action.card.card_id)
                    == (impact_snapshot["current_player"], "reserved")
                )
                if was_reserved_purchase:
                    self.log(f"{actor}购买了预购的{action.card.card_id}卡")
                else:
                    self.log(f"{actor}：{self.action_text(action)}")
                followup_messages = [
                    message for message in messages
                    if not (action.kind == "buy" and "触发" in message and "系专精" in message)
                ]
            for message in followup_messages:
                wizard_match = re.fullmatch(r"获得魔法师卡【(.+)】（\+(\d+)分）", message)
                if wizard_match:
                    self.log(
                        f"{actor}获得了魔法师【{wizard_match.group(1)}】的认可，"
                        f"获得了{wizard_match.group(2)}分奖励",
                        color=TEXT_COLOR,
                    )
                else:
                    self.log(message, color=TEXT_COLOR)
            acquired_wizards = [wizard for wizard in actor_player.wizard_cards if wizard not in previous_wizards]
            impact_events = self.build_impact_events(
                impact_snapshot, action, messages, specialization_effect
            )
            self.selected_card = None
            self.resource_selection.clear()
            self.resource_notice = ""
            self.refresh()
            self.resolve_card_acquisition_targets(impact_events)
            self.enqueue_impact_animations(impact_events)
            for wizard in acquired_wizards:
                self.enqueue_wizard_animation(wizard, actor)
            if turn_started:
                self.enqueue_turn_banner()
            if self.game.state.finished:
                self.end_dialog_pending = True
                self.play_next_impact_animation()
        except (RuleError, ValueError) as error:
            self.game_logger.warning("操作无效：%s", error)
            QMessageBox.warning(self, "操作无效", str(error))
            return False
        return True

    def enqueue_wizard_animation(self, wizard, player_name: str) -> None:
        self.wizard_animation_queue.append((wizard, player_name))
        self.sync_interaction_lock()
        self.play_next_wizard_animation()

    def play_next_wizard_animation(self) -> None:
        if self.wizard_animation_running or self.impact_animation_running or self.turn_animation_running:
            return
        if not self.wizard_animation_queue:
            self.play_next_impact_animation()
            return

        wizard, player_name = self.wizard_animation_queue.pop(0)
        self.wizard_animation_running = True
        overlay = WizardCardView(wizard, self, width=70)
        overlay.setObjectName("wizardAcquisitionOverlay")
        overlay.set_card_style(
            background="#fff1bf",
            border_color="#d2a83d",
            border_width=4,
            padding=4,
            text_color="#493516",
            object_name="wizardAcquisitionOverlay",
        )
        overlay.setMinimumSize(1, 1)
        overlay.setMaximumSize(1000, 1000)

        center = self.rect().center()
        start_rect = QRect(center.x() - 35, center.y() - 46, 70, 93)
        final_rect = QRect(center.x() - 120, center.y() - 160, 240, 320)
        overlay.setGeometry(start_rect)
        opacity = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(opacity)
        overlay.show()
        overlay.raise_()
        self.wizard_animation_overlay = overlay

        notice = QLabel(f"{player_name}获得了【{wizard.name}】的认可！", self)
        notice.setObjectName("wizardApprovalNotice")
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        notice.setStyleSheet(
            "QLabel#wizardApprovalNotice { color:#4a3017; background:#fff4ce; "
            "border:2px solid #d2a83d; border-radius:6px; padding:5px 12px; "
            "font-size:16px; font-weight:bold; }"
        )
        notice.setGeometry(center.x() - 235, final_rect.top() - 48, 470, 38)
        notice_opacity = QGraphicsOpacityEffect(notice)
        notice.setGraphicsEffect(notice_opacity)
        notice.show()
        notice.raise_()
        self.wizard_animation_notice = notice

        group = QSequentialAnimationGroup(self)
        appear = QParallelAnimationGroup(group)
        geometry_animation = QPropertyAnimation(overlay, b"geometry", appear)
        geometry_animation.setDuration(360)
        geometry_animation.setStartValue(start_rect)
        geometry_animation.setEndValue(final_rect)
        opacity_animation = QPropertyAnimation(opacity, b"opacity", appear)
        opacity_animation.setDuration(360)
        opacity_animation.setStartValue(0.25)
        opacity_animation.setEndValue(1.0)
        notice_appear = QPropertyAnimation(notice_opacity, b"opacity", appear)
        notice_appear.setDuration(360)
        notice_appear.setStartValue(0.0)
        notice_appear.setEndValue(1.0)
        appear.addAnimation(geometry_animation)
        appear.addAnimation(opacity_animation)
        appear.addAnimation(notice_appear)
        group.addAnimation(appear)
        group.addPause(550)
        fade_group = QParallelAnimationGroup(group)
        for effect in (opacity, notice_opacity):
            fade = QPropertyAnimation(effect, b"opacity", fade_group)
            fade.setDuration(300)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            fade_group.addAnimation(fade)
        group.addAnimation(fade_group)
        group.finished.connect(lambda card_overlay=overlay: self.finish_wizard_animation(card_overlay))
        self.wizard_animation = group
        group.start()

    def finish_wizard_animation(self, overlay: WizardCardView) -> None:
        overlay.deleteLater()
        if self.wizard_animation_notice is not None:
            self.wizard_animation_notice.deleteLater()
            self.wizard_animation_notice = None
        if self.wizard_animation_overlay is overlay:
            self.wizard_animation_overlay = None
        self.wizard_animation_running = False
        self.wizard_animation = None
        self.play_next_impact_animation()
        self.sync_interaction_lock()

    def enqueue_turn_banner(self) -> None:
        state = self.game.state
        if not self.game_started or state.finished:
            return
        turn_key = (state.round_number, state.current_player)
        if self.last_announced_turn == turn_key:
            return
        self.last_announced_turn = turn_key
        self.turn_banner_text = (
            "你的回合！"
            if state.current_player == 0 and not self.ai_battle
            else f"{state.current().name} 的回合！"
        )
        self.turn_banner_pending = True
        self.sync_interaction_lock()
        self.play_next_impact_animation()

    def keep_turn_banner_on_top(self) -> None:
        banner = self.turn_animation_overlay
        if banner is not None and banner.isVisible():
            banner.raise_()

    def play_turn_banner(self) -> None:
        if self.turn_animation_running or not self.turn_banner_pending:
            return
        self.turn_banner_pending = False
        self.turn_animation_running = True
        state = self.game.state
        self.displayed_turn_key = (state.round_number, state.current_player)
        self.render_players()
        self.update_turn_status_bar()
        center = self.rect().center()
        notice = QLabel(self.turn_banner_text, self)
        notice.setObjectName("turnNoticeOverlay")
        notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not self.ai_battle and self.game.state.current_player == 0:
            notice.setStyleSheet(
                "QLabel#turnNoticeOverlay { color:#513817; background:#fff4cf; "
                "border:3px solid #c99b45; border-radius:12px; padding:8px 18px; "
                "font-size:28px; font-weight:bold; }"
            )
        else:
            notice.setStyleSheet(
                "QLabel#turnNoticeOverlay { color:#343434; background:#ffffff; "
                "border:2px solid #c8c8c8; border-radius:8px; padding:8px 18px; "
                "font-size:28px; font-weight:bold; }"
            )
        start_rect = QRect(center.x() - 115, center.y() - 30, 230, 60)
        full_rect = QRect(center.x() - 165, center.y() - 38, 330, 76)
        rise_rect = QRect(full_rect.x(), full_rect.y() - 28, full_rect.width(), full_rect.height())
        notice.setGeometry(start_rect)
        opacity = QGraphicsOpacityEffect(notice)
        notice.setGraphicsEffect(opacity)
        notice.show()
        notice.raise_()
        self.turn_animation_overlay = notice

        group = QSequentialAnimationGroup(self)
        appear = QParallelAnimationGroup(group)
        grow = QPropertyAnimation(notice, b"geometry", appear)
        grow.setDuration(220)
        grow.setStartValue(start_rect)
        grow.setEndValue(full_rect)
        fade_in = QPropertyAnimation(opacity, b"opacity", appear)
        fade_in.setDuration(220)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        appear.addAnimation(grow)
        appear.addAnimation(fade_in)
        group.addAnimation(appear)
        group.addPause(650)
        fade_out = QParallelAnimationGroup(group)
        rise = QPropertyAnimation(notice, b"geometry", fade_out)
        rise.setDuration(420)
        rise.setStartValue(full_rect)
        rise.setEndValue(rise_rect)
        fade = QPropertyAnimation(opacity, b"opacity", fade_out)
        fade.setDuration(420)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade_out.addAnimation(rise)
        fade_out.addAnimation(fade)
        group.addAnimation(fade_out)
        group.finished.connect(self.finish_turn_banner)
        self.turn_animation = group
        group.start()

    def finish_turn_banner(self) -> None:
        if self.turn_animation_overlay is not None:
            self.turn_animation_overlay.deleteLater()
            self.turn_animation_overlay = None
        self.turn_animation_running = False
        self.turn_animation = None
        self.play_next_impact_animation()
        self.sync_interaction_lock()

    def show_end_dialog(self) -> None:
        if self.end_dialog_shown or not self.game.state.finished:
            return
        self.end_dialog_pending = False
        self.end_dialog_shown = True
        winners = self.game.winners()
        winner_names = "、".join(player.name for player in winners)
        winner_scores = "　·　".join(f"{player.name} {player.score}分" for player in winners)

        overlay = QWidget(self.game_page)
        overlay.setObjectName("endGameOverlay")
        overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        overlay.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        overlay.setGeometry(self.game_page.rect())
        overlay.setStyleSheet(
            "QWidget#endGameOverlay { background:rgba(35, 20, 19, 165); }"
            f"QFrame#endGamePanel {{ background:{PANEL_COLOR}; border:3px solid {ORNAMENT_COLOR}; "
            f"border-radius:{CARD_CORNER_RADIUS + 5}px; }}"
            f"QLabel#endGameTitle {{ color:{PANEL_COLOR}; background:{TEXT_COLOR}; "
            f"border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; "
            "font-size:22px; font-weight:bold; padding:8px; }"
            f"QLabel#endGameWinner {{ color:{TEXT_COLOR}; background:transparent; border:0; "
            "font-size:20px; font-weight:bold; }"
            f"QLabel#endGameScore {{ color:{TEXT_COLOR}; background:{HOVER_SURFACE_COLOR}; "
            f"border:1px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; "
            "font-size:13px; padding:8px; }"
            f"QPushButton#endGameButton {{ color:{TEXT_COLOR}; background:{HOVER_SURFACE_COLOR}; "
            f"border:2px solid {ORNAMENT_COLOR}; border-radius:{CARD_CORNER_RADIUS}px; "
            "font-size:13px; font-weight:bold; padding:7px 16px; }"
            f"QPushButton#endGameButton:hover {{ background:{PLAYER_CURRENT_COLOR}; }}"
        )
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(18, 18, 18, 18)
        overlay_layout.addStretch(1)
        panel = QFrame(overlay)
        panel.setObjectName("endGamePanel")
        panel.setFixedWidth(440)
        panel.setMinimumHeight(240)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(14)

        title = QLabel("对局结束")
        title.setObjectName("endGameTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(title)
        winner = QLabel(f"{winner_names} 获胜！")
        winner.setObjectName("endGameWinner")
        winner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        winner.setWordWrap(True)
        panel_layout.addWidget(winner)
        score = QLabel(winner_scores)
        score.setObjectName("endGameScore")
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score.setWordWrap(True)
        panel_layout.addWidget(score)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        continue_button = QPushButton("返回战局")
        continue_button.setObjectName("endGameButton")
        continue_button.clicked.connect(self.dismiss_end_dialog)
        restart_button = QPushButton("重新开始")
        restart_button.setObjectName("endGameButton")
        restart_button.clicked.connect(self.restart)
        buttons.addWidget(continue_button)
        buttons.addWidget(restart_button)
        panel_layout.addLayout(buttons)

        overlay_layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        overlay_layout.addStretch(1)
        panel_layout.activate()
        overlay_layout.activate()
        self.end_overlay = overlay
        overlay.show()
        overlay.raise_()

    def dismiss_end_dialog(self) -> None:
        if self.end_overlay is not None:
            self.end_overlay.hide()
            self.end_overlay.deleteLater()
            self.end_overlay = None

    def play_ai_turn(self) -> None:
        if self.has_active_animations():
            self.ai_timer.start(max(100, round(self.ai_interval * 1000)))
            return
        if self.game.state.finished or (not self.ai_battle and self.game.state.current_player == 0):
            return
        self.perform(choose_action(self.game, difficulty=self.ai_difficulty))

    def log(
        self,
        message: str,
        attribute: Attribute | None = None,
        *,
        bold: bool = False,
        color: str | None = None,
    ) -> None:
        timestamped = f"[{datetime.now():%H:%M:%S}] {message}"
        entry_color = (
            color
            if color is not None
            else self.RESOURCE_COLORS[attribute][1]
            if attribute is not None
            else "#000000"
        )
        self.log_messages.insert(0, (timestamped, entry_color, bold))
        contents = "<br>".join(
            f'<span style="color:{logged_color}">{"<b>" if entry_bold else ""}{html_escape(entry)}{"</b>" if entry_bold else ""}</span>'
            for entry, logged_color, entry_bold in self.log_messages
        )
        self.log_view.setHtml(f'<html><body style="margin:2px">{contents}</body></html>')
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.log_view.setTextCursor(cursor)
        self.log_view.verticalScrollBar().setValue(0)
        self.game_logger.info(message)

    def restart(self) -> None:
        self.ai_timer.stop()
        self.specialization_retry_timer.stop()
        if self.turn_animation is not None:
            self.turn_animation.stop()
            self.turn_animation.deleteLater()
            self.turn_animation = None
        if self.turn_animation_overlay is not None:
            self.turn_animation_overlay.deleteLater()
            self.turn_animation_overlay = None
        self.turn_banner_pending = False
        self.turn_animation_running = False
        self.last_announced_turn = None
        if self.impact_animation is not None:
            self.impact_animation.stop()
            self.impact_animation.deleteLater()
            self.impact_animation = None
        overlays_to_remove = list(self.impact_animation_overlays)
        if self.impact_animation_overlay is not None and self.impact_animation_overlay not in overlays_to_remove:
            overlays_to_remove.append(self.impact_animation_overlay)
        for overlay in overlays_to_remove:
            overlay.deleteLater()
        self.impact_animation_overlays.clear()
        self.impact_animation_overlay = None
        self.impact_animation_queue.clear()
        self.impact_animation_running = False
        if self.wizard_animation is not None:
            self.wizard_animation.stop()
            self.wizard_animation.deleteLater()
            self.wizard_animation = None
        if self.wizard_animation_overlay is not None:
            self.wizard_animation_overlay.deleteLater()
            self.wizard_animation_overlay = None
        if self.wizard_animation_notice is not None:
            self.wizard_animation_notice.deleteLater()
            self.wizard_animation_notice = None
        self.wizard_animation_queue.clear()
        self.wizard_animation_running = False
        self.dismiss_end_dialog()
        self.end_dialog_pending = False
        self.end_dialog_shown = False
        self.specialization_scheduled = False
        self.deferred_market_card_ids.clear()
        self.market_refill_without_animation = False
        self.deferred_reserved_card_ids.clear()
        self.deferred_purchased_card_ids.clear()
        self.game = Game(create_state(self.create_players(), build_decks(self.seed), self.seed))
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
        self.enqueue_turn_banner()

    def confirm_restart(self) -> None:
        if self.interaction_locked:
            return
        answer = QMessageBox.question(self, "重新开始", "当前对局将结束并使用相同种子重新开局，继续吗？")
        if answer == QMessageBox.StandardButton.Yes:
            self.restart()

    def closeEvent(self, event) -> None:
        self.ai_timer.stop()
        if self.turn_animation is not None:
            self.turn_animation.stop()
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
