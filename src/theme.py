from __future__ import annotations

from .models import Attribute


# Core tabletop palette. Keep these values centralized so the Qt view and any
# future preview/export code stay visually consistent.
TABLETOP_COLOR = "#6e2828"
PANEL_COLOR = "#ffdcbc"
TEXT_COLOR = "#983432"
ORNAMENT_COLOR = "#458795"
PLAYER_STATUS_COLOR = "#f3c9ab"
PLAYER_CURRENT_COLOR = "#d1e6e6"
HOVER_SURFACE_COLOR = "#fff1e4"
HOVER_INSET_COLOR = "#f3c9ab"
RESERVED_AREA_BACKGROUND = "#efefef"
CARD_CORNER_RADIUS = 7
UI_FONT_FAMILIES = (
    "KN Bobohei",
    "荆南波波黑",
)


# (soft surface, saturated accent), chosen to follow each resource shard.
RESOURCE_COLORS = {
    Attribute.WATER: ("#e2ecff", "#3e6fc6"),
    Attribute.FIRE: ("#f9e0d7", "#c04e2c"),
    Attribute.GRASS: ("#e4f1df", "#4f894c"),
    Attribute.CUTE: ("#f8deea", "#c34c86"),
    Attribute.DARK: ("#f1dce4", "#91405f"),
}

RESOURCE_SHARD_DIR = "属性零碎图标"
ATTRIBUTE_ICON_DIR = "属性图标"

RESOURCE_SHARD_FILES = {
    Attribute.WATER: "水系零碎.png",
    Attribute.FIRE: "火系零碎.png",
    Attribute.GRASS: "草系零碎.png",
    Attribute.CUTE: "萌系零碎.png",
    Attribute.DARK: "恶系零碎.png",
}

ATTRIBUTE_ICON_FILES = {
    Attribute.WATER: "水系图标.png",
    Attribute.FIRE: "火系图标.png",
    Attribute.GRASS: "草系图标.png",
    Attribute.CUTE: "萌系图标.png",
    Attribute.DARK: "恶系图标.png",
}
