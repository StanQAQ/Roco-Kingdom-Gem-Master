from __future__ import annotations

from .models import Attribute


# Qt 游戏、旧版 Tk 界面和动画演示共用调色板；新增界面色值应在此定义，避免散落在界面代码中。
TABLETOP_COLOR = "#3c3531"  # 游戏窗口桌面及木纹背景的主色。
PANEL_COLOR = "#f3eee1"  # 市场、面板和常规弹窗的浅色底。
TEXT_COLOR = "#3c3531"  # 界面通用文字颜色。
LOG_TEXT_COLOR = "#000000"  # 普通行动记录文字颜色；专精等特殊记录可覆盖此色。
PANEL_BORDER_COLOR = "#3c3531"  # 市场、面板、按钮等界面容器边线的颜色。
DECORATION_COLOR = "#be5003"  # 木桌纹理及标题页巴洛克花纹的主颜色；可独立于面板边线调整。
PLAYER_STATUS_COLOR = "#f3eee1"  # 普通玩家状态栏背景色。
PLAYER_CURRENT_COLOR = "#eec545"  # 当前行动玩家状态栏的高亮背景色。
HOVER_SURFACE_COLOR = "#fff1e4"  # 玩家悬停详情窗口的外层背景色。
HOVER_INSET_COLOR = "#f3eee1"  # 悬停详情窗口内嵌区域的背景色。
RESERVED_AREA_BACKGROUND = "#efefef"  # 预购区域及卡牌容器的灰色底。
CARD_CORNER_RADIUS = 7  # 卡牌圆角半径，单位为 Qt 逻辑像素。
PLAYER_HOVER_FONT_SIZE = 12  # 玩家状态悬停窗口中所有说明文字的统一字号，单位为 Qt 逻辑像素。
UI_FONT_FAMILIES = (  # 界面字体候选顺序：优先使用随程序打包的字体，再回退到中文别名。
    "KN Bobohei",
    "荆南波波黑",
)

# 卡牌及价格文字颜色；这些常量也用于动画卡面，保持移动前后的外观一致。
CARD_FACE_COLOR = "#fff6e8"  # 公共市场普通宠物卡的底色。
CARD_FACE_WARM_COLOR = "#fff5df"  # 购买、转移等动画浮层卡片的暖白底色。
CARD_FACE_CREAM_COLOR = "#fffaf0"  # 已购卡和卡牌价格数字的奶油白底色。
CARD_BORDER_COLOR = "#b8b8b8"  # 普通宠物卡及中性动画卡片边框。
CARD_SELECTED_COLOR = "#f4d484"  # 当前选中的宠物卡底色。
CARD_AFFORDABLE_COLOR = "#dceecf"  # 当前玩家可购买宠物卡的提示底色。
CARD_PRICE_TEXT_COLOR = "#fffaf0"  # 绘制在零碎图标上的价格数字填充色。
CARD_PRICE_OUTLINE_COLOR = "#43291d"  # 价格数字描边色，增强图标上的可读性。
CARD_NEUTRAL_BORDER_COLOR = "#d5cbbb"  # 普通已购买宠物卡的边框色。
CARD_DUAL_FACE_COLOR = "#fff1bf"  # 双属性卡及魔法师卡的金色系底色。
CARD_DUAL_BORDER_COLOR = "#d9a817"  # 双属性卡金色边框。
CARD_DUAL_GLOW_COLOR = "#efc84a"  # 双属性卡发光效果的颜色。

# 按钮、禁用控件和界面装饰颜色。
BUTTON_HOVER_COLOR = "#ffe8d3"  # 普通按钮鼠标悬停时的底色。
TURN_STATUS_BACKGROUND = "#eec545"  # 正常对局时顶部轮次与当前玩家状态标签的背景色。
BUTTON_PRESSED_COLOR = "#efc9a9"  # 普通按钮按下时的底色。
ACTION_BUTTON_BACKGROUND = TEXT_COLOR  # 确认、预购和取消等行动按钮可用时的深色底。
ACTION_BUTTON_TEXT_COLOR = PANEL_COLOR  # 深色行动按钮上的浅色文字。
BUTTON_DISABLED_COLOR = "#d2d0cc"  # 确认、预购和取消按钮不可用时的中性浅灰底色。
BUTTON_DISABLED_TEXT_COLOR = "#6e6862"  # 浅灰禁用按钮上的柔和深灰文字色。
BUTTON_DISABLED_BORDER_COLOR = "#b7b0a1"  # 不可用按钮的边框色。
CONTROL_DISABLED_FILL_COLOR = "#d2d0cc"  # 不可领取的公共资源按钮填充色。
CONTROL_DISABLED_TEXT_COLOR = "#8b8985"  # 不可领取的公共资源按钮文字色。
STATUS_BADGE_COLOR = "#eec545"  # 游戏顶部模式标签的背景色。
ORNAMENT_ACCENT_COLOR = "#eec545"  # 巴洛克边框及装饰花纹中的强调色。
ORNAMENT_INK_COLOR = "#2f1414"  # 标题页装饰边框的深色线条。
SPECIALIZATION_DUAL_GLOW_COLOR = "#4f8996"  # 同时带水、草专精效果卡牌的组合辉光色。
TABLETOP_TEXTURE_RGBA = (69, 135, 149, 46)  # 木桌背景纹理线的颜色及透明度（RGBA）。
PARCHMENT_FLECK_RGB = (69, 135, 149)  # 做旧牛皮纸细点纹理的蓝绿色基色（RGB）。
PARCHMENT_FLECK_ALPHA_BASE = 10  # 做旧牛皮纸细点纹理透明度的起始值。
PARCHMENT_FLECK_ALPHA_VARIATION = 7  # 细点透明度循环变化的档位数，形成轻微深浅差异。
TRANSPARENT_RGBA = (0, 0, 0, 0)  # 动画渐变的完全透明起始颜色（RGBA）。

# 标题页及菜单配色。
TITLE_TEXT_COLOR = "#ffffff"  # 标题页主标题及按钮选中文字的白色。
TITLE_SUBTITLE_COLOR = "#f0d9ae"  # 标题页副标题的浅金色。
TITLE_SHADOW_COLOR = "#3a281c"  # 标题文字投影的深棕色。

# 魔法师卡、认可提示和贤者碎晶相关颜色。
WIZARD_CARD_BORDER_COLOR = "#d2a83d"  # 魔法师卡及其认可提示框的金色边框。
WIZARD_CARD_TEXT_COLOR = TEXT_COLOR  # 魔法师卡文字色，沿用全局正文颜色。
WIZARD_NOTICE_BACKGROUND = "#fff4ce"  # 获得魔法师认可提示框的淡金色背景。
WIZARD_NOTICE_TEXT_COLOR = "#4a3017"  # 获得魔法师认可提示文字的深棕色。
SAGE_ACCENT_COLOR = "#bd903d"  # 贤者碎晶变化提示中的金色强调文字。
SAGE_TEXT_COLOR = "#9b742c"  # 玩家状态中贤者碎晶数量的文字色。

# 资源变化及卡牌受影响时显示的动画浮层配色。
RESOURCE_POPUP_BACKGROUND = "#ffffff"  # 普通资源变化提示框的白色背景。
RESOURCE_POPUP_TEXT_COLOR = "#333333"  # 普通资源变化提示框的文字色。
RESOURCE_POPUP_BORDER_COLOR = "#c8c8c8"  # 普通资源变化提示框的灰色边框。
SAGE_POPUP_BACKGROUND = "#fff1b8"  # 只显示贤者碎晶变化时的淡金色背景。
SAGE_POPUP_TEXT_COLOR = "#634b16"  # 贤者碎晶变化提示框的深金棕文字色。
SAGE_POPUP_BORDER_COLOR = "#d2aa4c"  # 贤者碎晶变化提示框的金色边框。
IMPACT_CARD_TEXT_COLOR = "#252525"  # 动画卡片上宠物属性、分数等内容的文字色。
IMPACT_CAPTION_BACKGROUND = "#fffaf0"  # 引燃、吞噬等动画说明标签的背景色。
SPECIALIZATION_NEUTRAL_COLOR = "#7f654e"  # 未指定属性时，卡牌效果记录的默认强调色。

# 回合提示颜色：自己的回合使用暖色提示，其他玩家的回合使用白色提示。
OWN_TURN_BACKGROUND = "#fff4cf"  # 自己回合提示框的背景色。
OWN_TURN_TEXT_COLOR = "#513817"  # 自己回合提示框的文字色。
OWN_TURN_BORDER_COLOR = "#c99b45"  # 自己回合提示框的金色边框。
OTHER_TURN_BACKGROUND = "#ffffff"  # 其他玩家回合提示框的白色背景。
OTHER_TURN_TEXT_COLOR = "#343434"  # 其他玩家回合提示框的深灰文字色。
OTHER_TURN_BORDER_COLOR = "#c8c8c8"  # 其他玩家回合提示框的灰色边框。
END_OVERLAY_RGBA = (35, 20, 19, 165)  # 游戏结束遮罩层的颜色及透明度（RGBA）。

# 旧版 Tk 界面的颜色单独保留，以免影响其与 Qt 界面不同的旧布局外观。
LEGACY_TABLETOP_COLOR = "#f4efe6"  # 旧版 Tk 主窗口及市场背景色。
LEGACY_HEADER_COLOR = "#263238"  # 旧版 Tk 顶部标题栏及未选中文字色。
LEGACY_SIDEBAR_COLOR = "#e8dfd1"  # 旧版 Tk 右侧栏及其内容区背景色。
LEGACY_LOG_BACKGROUND = "#f8f4ed"  # 旧版 Tk 行动记录区域背景色。
LEGACY_PLAYER_COLOR = "#f2ede6"  # 旧版 Tk 普通玩家状态卡背景色。
LEGACY_CURRENT_PLAYER_COLOR = "#e5e9d8"  # 旧版 Tk 当前玩家状态卡背景色。
LEGACY_RESOURCE_BACKGROUND = "#f7eee0"  # 旧版 Tk 资源状态区域背景色。
LEGACY_RESOURCE_SELECTED_TEXT = "#ffffff"  # 旧版 Tk 被选资源按钮上的文字色。


# 各属性颜色值依次为浅色背景和饱和强调色，分别用于底色及文字/边框。
RESOURCE_COLORS = {
    Attribute.WATER: ("#e2ecff", "#3e6fc6"),  # 水：浅蓝底色、蓝色强调色。
    Attribute.FIRE: ("#f9e0d7", "#c04e2c"),  # 火：浅橙底色、红橙强调色。
    Attribute.GRASS: ("#e4f1df", "#4f894c"),  # 草：浅绿底色、绿色强调色。
    Attribute.CUTE: ("#f8deea", "#c34c86"),  # 萌：浅粉底色、玫红强调色。
    Attribute.DARK: ("#f1dce4", "#91405f"),  # 恶：浅紫粉底色、深紫红强调色。
}

RESOURCE_SHARD_DIR = "属性零碎图标"  # 各属性资源零碎图片所在的媒体子目录。
ATTRIBUTE_ICON_DIR = "属性图标"  # 卡牌和玩家状态所用属性图标所在的媒体子目录。

RESOURCE_SHARD_FILES = {
    Attribute.WATER: "水系零碎.png",  # 水属性资源零碎图片文件名。
    Attribute.FIRE: "火系零碎.png",  # 火属性资源零碎图片文件名。
    Attribute.GRASS: "草系零碎.png",  # 草属性资源零碎图片文件名。
    Attribute.CUTE: "萌系零碎.png",  # 萌属性资源零碎图片文件名。
    Attribute.DARK: "恶系零碎.png",  # 恶属性资源零碎图片文件名。
}

ATTRIBUTE_ICON_FILES = {
    Attribute.WATER: "水系图标.png",  # 卡片和界面中的水属性标识图。
    Attribute.FIRE: "火系图标.png",  # 卡片和界面中的火属性标识图。
    Attribute.GRASS: "草系图标.png",  # 卡片和界面中的草属性标识图。
    Attribute.CUTE: "萌系图标.png",  # 卡片和界面中的萌属性标识图。
    Attribute.DARK: "恶系图标.png",  # 卡片和界面中的恶属性标识图。
}
