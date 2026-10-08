import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPropertyAnimation, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from src.game import Action
from src.models import Attribute, PetCard, SpecializationEffect, WizardCard
from src.qt_gui import CardButton, MagicGemsQtApp, OwnedCardView, WizardCardView
from src.theme import (
    CARD_CORNER_RADIUS, HOVER_SURFACE_COLOR, PANEL_COLOR, PLAYER_CURRENT_COLOR, TEXT_COLOR,
    RESERVED_AREA_BACKGROUND,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def game_window(tmp_path, monkeypatch, qapp):
    monkeypatch.chdir(tmp_path)
    window = MagicGemsQtApp(seed=7)
    yield window
    window.ai_timer.stop()
    for animation_name in ("impact_animation", "wizard_animation", "turn_animation"):
        animation = getattr(window, animation_name, None)
        if animation is not None:
            animation.stop()
    window.game_log_handler.close()
    window.game_logger.removeHandler(window.game_log_handler)
    window.close()


def test_settlement_clears_stale_lock_and_applies_effect(game_window):
    window = game_window
    window.game.state.pending_specializations = [
        SpecializationEffect(0, Attribute.CUTE, 1)
    ]
    dialog = QDialog()
    dialog.show()

    # Reproduce the stranded state: the lock is set, but no animation remains.
    window.interaction_locked = True
    window.settle_specialization(dialog, Action("specialization"))

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not window.game.state.pending_specializations
    assert window.game.state.players[0].next_attack_immune
    assert window.game.state.current_player == 1
    assert any("撒娇" in message for message, _color, _bold in window.log_messages)


def test_action_log_uses_black_for_normal_entries_and_preserves_effect_colors(game_window):
    window = game_window
    window.log("普通操作记录")
    normal_entry = window.log_messages[0]
    assert normal_entry[1] == "#000000"
    assert not normal_entry[2]

    window.log("水系专精效果", Attribute.WATER, bold=True)
    specialization_entry = window.log_messages[0]
    assert specialization_entry[1] == window.RESOURCE_COLORS[Attribute.WATER][1]
    assert specialization_entry[2]

    window.log("魔法师效果记录", color=TEXT_COLOR)
    effect_entry = window.log_messages[0]
    assert effect_entry[1] == TEXT_COLOR


def test_game_end_uses_in_game_overlay(game_window):
    window = game_window
    window.game.state.players[0].score = 18
    window.game.state.finished = True

    window.show_end_dialog()

    overlay = window.end_overlay
    assert overlay is not None
    assert overlay.parentWidget() is window
    assert not overlay.isHidden()
    winner_label = overlay.findChild(QLabel, "endGameWinner")
    assert winner_label is not None
    assert window.game.state.players[0].name in winner_label.text()


def test_player_hover_card_is_hidden_until_a_player_row_is_hovered(game_window):
    window = game_window
    window.show()
    QApplication.processEvents()

    assert window.player_hover_card.isHidden()

    anchor = window.player_status_labels[1]
    window.show_player_status_hover(anchor, 1)
    assert not window.player_hover_card.isHidden()


def test_card_selection_switches_between_market_and_reserved_and_toggles(game_window):
    window = game_window
    market_card = next(
        card
        for level in (3, 2, 1)
        for card in window.game.state.market.cards[level]
    )
    reserved_card = PetCard(
        "TEST-RESERVED", 1, (Attribute.WATER,), {Attribute.FIRE: 1}, 1
    )
    window.game.state.players[0].reserved.append(reserved_card)
    window.refresh()

    window.select_card(market_card)
    assert window.selected_card is market_card
    market_button = next(
        button for level in (3, 2, 1)
        for button in window.market_buttons[level]
        if button is not None and button.card_id == market_card.card_id
    )
    assert f"border-radius:{CARD_CORNER_RADIUS}px" in market_button.styleSheet()

    window.select_card(reserved_card)
    assert window.selected_card is reserved_card

    window.select_card(reserved_card)
    assert window.selected_card is None

    window.select_card(reserved_card)
    window.select_card(market_card)
    assert window.selected_card is market_card


def test_reserved_log_and_selected_resources_share_background(game_window):
    window = game_window
    assert f"background:{RESERVED_AREA_BACKGROUND}" in window.reserved_cards_content.styleSheet()
    assert f"background:{RESERVED_AREA_BACKGROUND}" in window.log_view.styleSheet()
    assert f"background:{RESERVED_AREA_BACKGROUND}" in window.selected_resource_frame.styleSheet()


@pytest.mark.parametrize(
    ("difficulty", "opponent_names"),
    [
        ("simple", ["米米", "米莎", "米蒂"]),
        ("hard", ["可丽希亚", "菲尔特", "拉普"]),
    ],
)
def test_single_player_names_follow_difficulty_and_restart(game_window, difficulty, opponent_names):
    game_window.start_game_with_difficulty(difficulty)

    expected_names = ["你", *opponent_names]
    assert [player.name for player in game_window.game.state.players] == expected_names
    assert all(
        name in game_window.player_status_labels[index].findChild(QLabel).text()
        for index, name in enumerate(expected_names)
    )

    game_window.restart()

    assert [player.name for player in game_window.game.state.players] == expected_names


def test_self_player_hover_only_shows_name_score_and_effects(game_window):
    window = game_window
    player = window.game.state.players[0]
    player.resources[Attribute.WATER] = 2
    player.light = 1
    player.temporary_light = 1
    player.next_purchase_free = True
    player.next_purchase_score_doubled = True
    player.next_attack_immune = True

    window.render_players()

    frame = window.player_status_labels[0]
    assert PLAYER_CURRENT_COLOR in frame.styleSheet()
    assert f"border-radius:{CARD_CORNER_RADIUS}px" in frame.styleSheet()
    heading = frame.findChild(QLabel)
    assert heading is not None
    assert player.name in heading.text()
    assert f"{player.score}分" in heading.text()
    assert "资源" not in heading.text()
    assert "购买" not in heading.text()
    assert not heading.toolTip()
    effect_label = frame.findChild(QLabel, "playerStatusEffect")
    assert effect_label is not None
    assert effect_label.text() == "当前效果：下张免付费、下张分数翻倍、攻击免疫"

    window.show_player_status_hover(frame, 0)
    hover_card = window.player_hover_card
    assert hover_card.name_label.text() == player.name
    assert hover_card.score_label.text() == f"{player.score}分"
    assert "攻击免疫" in hover_card.status_label.text()
    assert hover_card.resources_frame.isHidden()
    assert hover_card.info_frame.isHidden()
    assert hover_card.cards_frame.isHidden()
    assert hover_card.width() == frame.width()
    assert hover_card.PARCHMENT_COLOR == PANEL_COLOR
    assert HOVER_SURFACE_COLOR in hover_card.styleSheet()
    assert not hover_card.isWindow()
    assert hover_card.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_other_player_hover_shows_resources_wizards_effects_and_purchased_cards(game_window):
    window = game_window
    player = window.game.state.players[1]
    player.resources[Attribute.WATER] = 2
    player.light = 1
    player.wizard_cards.append(WizardCard("认可", ((Attribute.WATER, 3),)))
    player.purchased.append((
        PetCard("OPP-01", 1, (Attribute.WATER,), {Attribute.FIRE: 1}, 1),
        None,
    ))
    player.purchased.append((
        PetCard("OPP-G1", 1, (Attribute.GRASS,), {Attribute.WATER: 1}, 1),
        None,
    ))
    dual_card = PetCard(
        "OPP-DG", 2, (Attribute.GRASS, Attribute.CUTE), {Attribute.WATER: 2}, 2
    )
    player.purchased.append((dual_card, Attribute.GRASS))
    player.next_purchase_free = True
    window.render_players()

    frame = window.player_status_labels[1]
    window.show_player_status_hover(frame, 1)
    hover_card = window.player_hover_card

    assert hover_card.name_label.text() == player.name
    assert hover_card.score_label.text() == f"{player.score}分"
    assert not hover_card.resources_frame.isHidden()
    assert hover_card.resource_counts[Attribute.WATER].text() == "2"
    assert hover_card.sage_count.text() == "1"
    assert hover_card.wizard_label.text() == "1 张"
    assert "下张免付费" in hover_card.status_label.text()
    assert hover_card.cards_title.text() == "已购买宠物卡　3"
    assert set(hover_card.purchased_columns) == set(Attribute)
    assert set(hover_card.purchased_piles) == {Attribute.WATER, Attribute.GRASS}
    column_widths = {column.width() for column in hover_card.purchased_columns.values()}
    assert len(column_widths) == 1
    assert next(iter(column_widths)) == hover_card.purchased_card_views[0].width() + 10
    first_column = hover_card.purchased_columns[Attribute.WATER].geometry()
    last_column = hover_card.purchased_columns[Attribute.DARK].geometry()
    left_space = first_column.x()
    right_space = hover_card.cards_content.width() - last_column.x() - last_column.width()
    assert abs(left_space - right_space) <= 1
    hover_styles = hover_card.styleSheet()
    assert "QFrame#playerHoverCardsFrame" in hover_styles
    assert f"border-radius:{CARD_CORNER_RADIUS}px" in hover_styles
    assert "QWidget#playerHoverCardsContent" in hover_styles
    assert "border-radius:0" in hover_styles
    assert [view.card_id for view in hover_card.purchased_card_views] == [
        "OPP-01", "OPP-G1", "OPP-DG"
    ]
    assert all(
        f"border-radius:{round(CARD_CORNER_RADIUS * view.height() / CardButton.STYLE_REFERENCE_HEIGHT)}px"
        in view.styleSheet()
        for view in hover_card.purchased_card_views
    )
    grass_pile = [
        view for view in hover_card.purchased_card_views
        if view.property("pileAttribute") == Attribute.GRASS.value
    ]
    assert [view.card_id for view in grass_pile] == ["OPP-G1", "OPP-DG"]
    assert [view.property("stackIndex") for view in grass_pile] == [0, 1]
    grass_stack = hover_card.purchased_piles[Attribute.GRASS]
    assert grass_stack.objectName() == "playerHoverCardStack"
    assert "QWidget#playerHoverCardStack { background:transparent; border:0; }" in hover_card.styleSheet()
    assert all(view.geometry().bottom() < grass_stack.height() for view in grass_pile)
    assert hover_card.cards_content.height() >= grass_stack.height() + 38
    assert hover_card.width() == frame.width()


def test_other_player_hover_reuses_unchanged_card_views_and_refreshes_after_purchase(game_window):
    window = game_window
    player = window.game.state.players[1]
    player.purchased.append((
        PetCard("HOVER-CACHE-01", 1, (Attribute.WATER,), {Attribute.FIRE: 1}, 1),
        None,
    ))
    window.render_players()
    frame = window.player_status_labels[1]

    window.show_player_status_hover(frame, 1)
    hover_card = window.player_hover_card
    initial_views = tuple(hover_card.purchased_card_views)
    assert len(initial_views) == 1

    window.show_player_status_hover(frame, 1)
    assert len(hover_card.purchased_card_views) == 1
    assert hover_card.purchased_card_views[0] is initial_views[0]

    player.purchased.append((
        PetCard("HOVER-CACHE-02", 1, (Attribute.FIRE,), {Attribute.WATER: 1}, 1),
        None,
    ))
    player.resources[Attribute.WATER] = 3
    window.refresh()
    assert not hover_card.isHidden()
    assert window.player_hover_anchor is frame
    assert len(hover_card.purchased_card_views) == 2
    assert hover_card.purchased_card_views[0] is not initial_views[0]
    assert hover_card.resource_counts[Attribute.WATER].text() == "3"

    updated_views = tuple(hover_card.purchased_card_views)
    player.resources[Attribute.WATER] = 4
    window.refresh()
    assert hover_card.resource_counts[Attribute.WATER].text() == "4"
    assert tuple(hover_card.purchased_card_views) == updated_views


def test_owned_wizard_cards_are_smaller_and_scroll_horizontally(game_window):
    window = game_window
    window.start_game_with_difficulty("hard")
    window.ai_timer.stop()
    player = window.game.state.players[0]
    player.wizard_cards = [
        WizardCard(
            f"贤者{index}", ((Attribute.WATER, 3), (Attribute.GRASS, 2))
        )
        for index in range(16)
    ]
    window.refresh()
    window.show()
    QTest.qWait(40)

    scroll = window.owned_wizard_scroll
    assert scroll.height() == 80
    assert scroll.horizontalScrollBar().maximum() > 0
    assert scroll.verticalScrollBar().maximum() == 0
    assert len(window.owned_wizard_views) == 16
    assert window.owned_wizard_views[0].size().width() == 44
    assert window.owned_wizard_views[0].height() == 59
    assert window.owned_wizard_views[0].geometry().bottom() < scroll.viewport().height()


def test_hovering_player_status_opens_in_game_detail_card(game_window):
    window = game_window
    window.start_game_with_difficulty("hard")
    window.show()
    QTest.qWait(30)

    frame = window.player_status_labels[0]
    QTest.mouseMove(frame, QPoint(5, max(2, frame.height() // 2)))
    QTest.qWait(240)

    assert window.player_hover_card.isVisible()
    assert window.player_hover_card.name_label.text() == window.game.state.players[0].name
    assert window.player_hover_card.width() == frame.width()
    frame_top_left = frame.mapTo(window, QPoint(0, 0))
    assert window.player_hover_card.x() == frame_top_left.x()
    assert window.player_hover_card.geometry().bottom() == frame_top_left.y() + frame.height() - 1


def test_dragging_purchased_dual_card_does_not_move_attribute_icon(game_window):
    window = game_window
    window.start_game_with_difficulty("hard")
    window.ai_timer.stop()
    if window.turn_animation is not None:
        window.turn_animation.stop()
    window.turn_animation_running = False
    window.turn_banner_pending = False
    window.interaction_locked = False
    dual_card = PetCard(
        "DRAG-DUAL", 1, (Attribute.GRASS, Attribute.CUTE), {Attribute.WATER: 1}, 1
    )
    window.game.state.players[0].purchased.append((dual_card, Attribute.GRASS))
    window.refresh()
    window.show()
    QTest.qWait(30)

    card_view = window.purchased_card_views[dual_card.card_id]
    icon = window.purchased_attribute_icons[Attribute.GRASS]
    icon_position = icon.mapToGlobal(QPoint(0, 0))
    assert card_view.board is window.game_page

    QTest.mousePress(card_view, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(card_view, QPoint(42, 2), delay=30)

    assert card_view.parentWidget() is window.game_page
    assert icon.mapToGlobal(QPoint(0, 0)) == icon_position

    QTest.mouseRelease(card_view, Qt.MouseButton.LeftButton, pos=QPoint(42, 2))


def test_purchased_attribute_icons_stay_fixed_when_card_piles_scroll(game_window):
    window = game_window
    window.start_game_with_difficulty("hard")
    window.ai_timer.stop()
    if window.turn_animation is not None:
        window.turn_animation.stop()
    window.turn_animation_running = False
    window.turn_banner_pending = False
    window.interaction_locked = False
    window.game.state.players[0].purchased = [
        (
            PetCard(
                f"SCROLL-{index}", 1, (Attribute.WATER,), {Attribute.FIRE: 1}, 1
            ),
            None,
        )
        for index in range(25)
    ]
    window.refresh()
    window.show()
    QTest.qWait(40)

    scroll_bar = window.purchased_scrollbar
    assert scroll_bar.maximum() > 0
    column = window.purchased_columns[Attribute.WATER]
    header_icon = window.purchased_attribute_icons[Attribute.WATER]
    last_card = window.purchased_card_views["SCROLL-24"]
    header_before = header_icon.mapToGlobal(QPoint(0, 0))
    column_before = column.mapToGlobal(QPoint(0, 0))
    card_before = last_card.mapToGlobal(QPoint(0, 0))
    icon_center_x = header_icon.mapToGlobal(QPoint(header_icon.width() // 2, 0)).x()
    column_center_x = column.mapToGlobal(QPoint(column.width() // 2, 0)).x()
    assert abs(icon_center_x - column_center_x) <= 2

    scroll_bar.setValue(scroll_bar.maximum())
    QTest.qWait(20)

    assert header_icon.mapToGlobal(QPoint(0, 0)) == header_before
    assert column.mapToGlobal(QPoint(0, 0)) == column_before
    assert last_card.mapToGlobal(QPoint(0, 0)).y() < card_before.y()


def test_other_player_hover_panel_loads_all_cards_on_first_show(game_window):
    window = game_window
    window.start_game_with_difficulty("hard")
    player = window.game.state.players[1]
    player.purchased = [
        (
            PetCard(
                f"HOVER-{index}", 1, (Attribute.FIRE,), {Attribute.WATER: 1}, 1
            ),
            None,
        )
        for index in range(15)
    ]
    window.show()
    QTest.qWait(30)

    anchor = window.player_status_labels[1]
    window.show_player_status_hover(anchor, 1)

    popup = window.player_hover_card
    assert popup.height() < window.height()
    assert popup.y() >= 4
    assert popup.geometry().bottom() <= window.rect().bottom() - 4
    fire_stack = popup.purchased_piles[Attribute.FIRE]
    assert fire_stack.height() == (
        popup.purchased_card_views[0].height() + 14 * 16
    )
    assert all(
        view.geometry().bottom() < fire_stack.height()
        for view in popup.purchased_card_views
    )
    assert popup.cards_content.height() >= fire_stack.height() + 38
    fire_icon = popup.purchased_attribute_icons[Attribute.FIRE]
    fire_icon_position = fire_icon.mapToGlobal(QPoint(0, 0))
    first_pile_card = popup.purchased_card_views[0]
    card_position = first_pile_card.mapToGlobal(QPoint(0, 0))
    fire_scroll.verticalScrollBar().setValue(fire_scroll.verticalScrollBar().maximum())
    QTest.qWait(20)
    assert fire_icon.mapToGlobal(QPoint(0, 0)) == fire_icon_position
    assert first_pile_card.mapToGlobal(QPoint(0, 0)).y() < card_position.y()


def test_settlement_keeps_dialog_open_when_animation_is_active(game_window):
    window = game_window
    window.game.state.pending_specializations = [
        SpecializationEffect(0, Attribute.CUTE, 1)
    ]
    dialog = QDialog()
    dialog.show()

    # A real active-animation flag must still block the action, but not dismiss
    # the only dialog that can resolve the pending specialization.
    window.turn_banner_pending = True
    window.interaction_locked = True
    window.settle_specialization(dialog, Action("specialization"))

    assert dialog.isVisible()
    assert window.game.state.pending_specializations == [
        SpecializationEffect(0, Attribute.CUTE, 1)
    ]
    assert not window.game.state.players[0].next_attack_immune


def test_specialization_prompt_retries_after_purchase_animation(game_window, monkeypatch):
    window = game_window
    window.game.state.pending_specializations = [
        SpecializationEffect(0, Attribute.WATER, 1)
    ]
    opened = []

    def fake_exec(dialog):
        opened.append(dialog.windowTitle())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    window.impact_animation_running = True
    window.schedule_specialization_prompt()

    # The first prompt attempt is expected to wait while the purchase card is
    # still moving. Once it finishes, the retry must open the settlement UI.
    QTest.qWait(180)
    assert opened == []
    assert window.specialization_retry_timer.isActive()

    window.impact_animation_running = False
    window.sync_interaction_lock()
    QTest.qWait(180)

    assert opened == ["结算属性专精"]
    assert window.game.state.pending_specializations
    assert not window.specialization_retry_timer.isActive()


def test_impact_animation_cleanup_survives_purchased_area_redraw_error(game_window, monkeypatch):
    window = game_window
    window.game.state.pending_specializations = [
        SpecializationEffect(0, Attribute.WATER, 1)
    ]
    window.impact_animation_running = True
    window.interaction_locked = True
    overlay = QLabel(window)
    overlay.setProperty("purchasedCardId", "PURCHASED-TEST")
    scheduled = []
    monkeypatch.setattr(
        window,
        "render_purchased",
        lambda: (_ for _ in ()).throw(RuntimeError("redraw failed")),
    )
    monkeypatch.setattr(window, "play_next_impact_animation", lambda: scheduled.append(True))

    with pytest.raises(RuntimeError, match="redraw failed"):
        window.finish_impact_animation([overlay])

    assert not window.impact_animation_running
    assert window.impact_animation is None
    assert not window.interaction_locked
    assert scheduled == [True]


def test_fully_discounted_purchase_still_animates_and_releases_interaction_lock(game_window):
    window = game_window
    card = PetCard("FREE-TEST", 1, (Attribute.FIRE,), {Attribute.FIRE: 1}, 1)
    event = {
        "kind": "market-purchase",
        "card": card,
        "card_id": card.card_id,
        "player_index": 0,
        "zone": "purchased",
        "color": "#bd903d",
        "start": QRect(100, 100, 76, 100),
        "target": QRect(320, 260, 52, 69),
    }

    # Fully discounted purchases have no resource-status event to pair with
    # the card's market-to-hand animation.
    window.enqueue_impact_animations([event])

    assert window.impact_animation_running
    assert window.impact_animation is not None
    assert window.impact_animation_overlay.property("purchasedCardId") == card.card_id
    assert window.interaction_locked

    QTest.qWait(700)

    assert not window.impact_animation_running
    assert window.impact_animation is None
    assert not window.interaction_locked


@pytest.mark.parametrize("kind", ["market-purchase", "reserve-acquire", "acquire", "transfer"])
def test_ordinary_card_movement_uses_neutral_thin_border(game_window, kind):
    style = game_window.impact_card_style({"kind": kind, "color": "#bd903d"})

    assert "border:2px solid #b8b8b8" in style
    assert "#bd903d" not in style


def test_card_moving_with_resource_feedback_has_no_colored_border(game_window):
    card = PetCard("MOVE-TEST", 1, (Attribute.WATER,), {Attribute.FIRE: 1}, 1)
    card_event = {
        "kind": "market-purchase",
        "card": card,
        "card_id": card.card_id,
        "player_index": 0,
        "zone": "purchased",
        "color": "#bd903d",
        "start": QRect(100, 100, 76, 100),
        "target": QRect(300, 300, 52, 69),
    }
    resource_event = {
        "kind": "resource-status",
        "player_index": 0,
        "text": "火−1",
        "color": "#dd4a28",
        "start": QRect(100, 100, 40, 20),
    }

    game_window.play_resource_card_animation(resource_event, card_event)

    overlay = game_window.impact_animation_overlay
    assert "border:2px solid #b8b8b8" in overlay.styleSheet()
    assert "#bd903d" not in overlay.styleSheet()
    assert game_window.impact_animation is not None


def test_dismissing_specialization_dialog_reopens_pending_effect(game_window, monkeypatch):
    window = game_window
    window.game.state.pending_specializations = [
        SpecializationEffect(0, Attribute.CUTE, 1)
    ]
    scheduled = []
    monkeypatch.setattr(window, "schedule_specialization_prompt", lambda: scheduled.append(True))
    dialog = QDialog()
    dialog.finished.connect(window.specialization_dialog_finished)

    dialog.reject()

    assert scheduled == [True]
    assert window.specialization_dialog is None
    assert window.game.state.pending_specializations


def test_existing_resources_heading_shows_capacity_and_total_light(game_window):
    player = game_window.game.state.players[0]
    player.resources[Attribute.WATER] = 2
    player.resources[Attribute.GRASS] = 1
    player.light = 1
    player.temporary_light = 1

    game_window.render_resource_zones()

    assert game_window.pool_resource_title.text() == "已有资源：5/10　贤者碎晶2"


def test_owned_card_stack_exposes_attribute_and_score_but_not_card_id():
    scale = OwnedCardView.HEIGHT / 84
    card_rect_top = round(3 * scale)
    top_info_bottom = (
        card_rect_top
        + round(CardButton.TOP_INFO_Y * scale)
        + round(CardButton.TOP_INFO_HEIGHT * scale)
    )
    card_id_top = card_rect_top + round(CardButton.CARD_ID_Y * scale)

    assert top_info_bottom <= OwnedCardView.REVEAL_HEIGHT < card_id_top


def test_wizard_card_hides_header_but_keeps_requirement_icons(qapp):
    wizard = WizardCard("测试魔法师", ((Attribute.WATER, 4), (Attribute.GRASS, 3)))
    view = WizardCardView(wizard)

    assert view.top_left == "魔法师"
    assert view.top_right == "+3"
    assert not view.SHOW_TOP_INFO
    assert view.CARD_ID_Y < CardButton.CARD_ID_Y
    assert [(attribute, amount) for attribute, amount in view.cost_items] == [
        (Attribute.WATER.value, 4),
        (Attribute.GRASS.value, 3),
    ]
    assert not view.grab().isNull()


@pytest.mark.parametrize("attribute", [Attribute.WATER, Attribute.GRASS])
def test_water_and_grass_specializations_update_market_card_without_fade_event(game_window, attribute):
    card = game_window.game.state.market.cards[1][0]
    before = game_window.capture_impact_snapshot()
    if attribute == Attribute.WATER:
        card.cost = dict(card.cost)
        card.cost[Attribute.FIRE] = card.cost.get(Attribute.FIRE, 0) + 1
    else:
        card.score += 1
    card.specialization_glows.add(attribute)

    events = game_window.build_impact_events(
        before,
        Action("specialization"),
        [],
        SpecializationEffect(0, attribute, 1),
    )

    assert not any(event.get("card_id") == card.card_id for event in events)
    game_window.enqueue_impact_animations(events)
    assert game_window.impact_animation is None
    assert not game_window.impact_animation_running


@pytest.mark.parametrize("attribute", [Attribute.WATER, Attribute.GRASS])
@pytest.mark.parametrize("level", [1, 3])
def test_water_and_grass_specializations_replenish_without_card_animation(game_window, qapp, attribute, level):
    window = game_window
    state = window.game.state
    state.market.cards[level].pop()
    previous_ids = {card.card_id for card in state.market.cards[level]}
    target_card = state.market.cards[1][0]
    window.pages.setCurrentWidget(window.game_page)
    window.show()
    window.game_started = True
    window.refresh()
    qapp.processEvents()
    state.pending_specializations = [SpecializationEffect(0, attribute, 1)]

    assert window.perform(Action("specialization", card=target_card))

    assert state.current_player == 1
    assert window.turn_animation_running
    qapp.processEvents()
    assert not window.impact_animation_running
    assert window.impact_animation_overlay is None
    assert not window.deferred_market_card_ids
    refill_id = next(card.card_id for card in state.market.cards[level] if card.card_id not in previous_ids)
    slot = window.market_slots[level][refill_id]
    slot_widget = window.market_slot_widgets[level][slot]
    assert isinstance(slot_widget, CardButton)
    assert slot_widget.card_id == refill_id


@pytest.mark.parametrize("attribute", [Attribute.WATER, Attribute.GRASS])
def test_water_and_grass_stage_two_do_not_animate_market_refill(game_window, qapp, attribute):
    window = game_window
    state = window.game.state
    state.market.cards[3].pop()
    window.pages.setCurrentWidget(window.game_page)
    window.show()
    window.game_started = True
    window.refresh()
    qapp.processEvents()
    state.pending_specializations = [SpecializationEffect(0, attribute, 2)]

    assert window.perform(Action("specialization"))
    window.ai_timer.stop()
    QTest.qWait(750)

    assert window.turn_animation_running
    assert not window.impact_animation_running
    assert window.impact_animation_overlay is None
    assert not window.deferred_market_card_ids
    assert not window.impact_animation_queue


def test_deferred_market_refill_drops_into_its_slot(game_window, qapp):
    window = game_window
    window.pages.setCurrentWidget(window.game_page)
    window.show()
    window.game_started = True
    card = window.game.state.market.cards[3][0]
    window.deferred_market_card_ids.add(card.card_id)
    window.render_market()
    qapp.processEvents()

    window.enqueue_turn_banner()

    assert window.turn_animation_running
    qapp.processEvents()
    assert window.impact_animation_running
    slot = window.market_slots[3][card.card_id]
    slot_widget = window.market_slot_widgets[3][slot]
    expected_target = QRect(slot_widget.mapTo(window, QPoint(0, 0)), slot_widget.size())
    movement = window.impact_animation.animationAt(0)
    assert movement.endValue() == expected_target
    assert 0 < expected_target.y() - movement.startValue().y() <= 28


@pytest.mark.parametrize(
    ("kind", "color"),
    [
        ("burn", "#bf4640"),
        ("burn-in-place", "#bf4640"),
        ("center-impact", "#747b86"),
        ("status-impact", "#747b86"),
    ],
)
def test_fire_and_dark_impact_move_then_tint_text_then_fade(game_window, kind, color):
    event = {
        "kind": kind,
        "color": color,
        "card": PetCard("TEST", 1, (Attribute.FIRE,), {Attribute.FIRE: 1}, 1),
        "card_id": "TEST",
        "player_index": 1,
        "affected_player_index": 1,
        "text": "AI-2的TEST被引燃了" if color == "#bf4640" else "AI-2的TEST被吞噬了",
        "start": QRect(100, 100, 52, 69),
    }
    style = game_window.impact_card_style(event)
    assert "background:#fff5df" in style

    game_window.impact_animation_queue = [event]
    game_window.play_next_impact_animation()
    overlay = game_window.impact_animation_overlay
    expected_scale = overlay.height() / CardButton.STYLE_REFERENCE_HEIGHT
    expected_border = max(
        1,
        int((4 if kind in ("burn", "burn-in-place", "status-impact") else 2) * expected_scale),
    )
    assert f"border:{expected_border}px solid #b8b8b8" in overlay.styleSheet()
    assert f"border-radius:{round(CARD_CORNER_RADIUS * expected_scale)}px" in overlay.styleSheet()
    assert overlay.display_card_id == "TEST"
    assert overlay.graphicsEffect().opacity() >= 0.95

    QTest.qWait(550)

    animation_groups = [game_window.impact_animation]
    fade_animations = []
    while animation_groups:
        group = animation_groups.pop()
        for index in range(group.animationCount()):
            animation = group.animationAt(index)
            if isinstance(animation, QPropertyAnimation):
                if animation.propertyName() == b"opacity":
                    fade_animations.append(animation)
            elif hasattr(animation, "animationCount"):
                animation_groups.append(animation)

    assert fade_animations
    assert any(animation.endValue() == 0.0 for animation in fade_animations)
    expected_scale = overlay.height() / CardButton.STYLE_REFERENCE_HEIGHT
    expected_border = max(
        1,
        int((4 if kind in ("burn", "burn-in-place", "status-impact") else 2) * expected_scale),
    )
    assert f"border:{expected_border}px solid #b8b8b8" in overlay.styleSheet()
    assert f"border-radius:{round(CARD_CORNER_RADIUS * expected_scale)}px" in overlay.styleSheet()
    assert overlay.display_card_id == "TEST"
    assert 0.0 < overlay.impactContentOpacity < 1.0
    assert 0 < overlay.impactTint.alpha() < 255
    if kind in ("burn-in-place", "status-impact"):
        assert overlay.geometry().center().y() == event["start"].center().y()
        assert overlay.geometry().x() == event["start"].right() - overlay.width() - 6
    captions = game_window.findChildren(QLabel, "specializationImpactCaption")
    if kind in ("burn-in-place", "status-impact"):
        assert not any(caption.text() == event["text"] for caption in captions)
    else:
        assert any(caption.text() == event["text"] and not caption.isHidden() for caption in captions)


def test_dark_stage_two_opponent_card_impact_uses_victims_status_bar(game_window):
    state = game_window.game.state
    victim = state.players[1]
    taken = PetCard("DARK-TEST", 2, (Attribute.DARK,), {Attribute.DARK: 2}, 3)
    victim.purchased.append((taken, None))
    game_window.refresh()
    before = game_window.capture_impact_snapshot()

    victim.purchased.remove((taken, None))
    state.players[0].purchased.append((taken, None))
    game_window.refresh()
    events = game_window.build_impact_events(
        before,
        Action("specialization"),
        [],
        SpecializationEffect(0, Attribute.DARK, 2),
    )

    impact = next(event for event in events if event["card_id"] == "DARK-TEST")
    assert impact["kind"] == "status-impact"
    assert impact["affected_player_index"] == 1
    assert impact["start"] == before["player_origins"][1]
    assert impact["text"] == f"{victim.name}的DARK-TEST被吞噬了"


def test_opponent_impact_resolves_status_bar_when_snapshot_has_no_position(game_window, qapp):
    game_window.pages.setCurrentWidget(game_window.game_page)
    game_window.show()
    qapp.processEvents()
    status_bar = game_window.player_status_labels[2]
    status_rect = game_window.widget_rect_in_window(status_bar)
    event = {
        "kind": "status-impact",
        "color": "#747b86",
        "card": PetCard("DARK-EMPTY", 2, (Attribute.DARK,), {Attribute.DARK: 2}, 3),
        "card_id": "DARK-EMPTY",
        "player_index": 0,
        "affected_player_index": 2,
        "text": "AI-3的DARK-EMPTY被吞噬了",
        "start": QRect(),
    }

    game_window.impact_animation_queue = [event]
    game_window.play_next_impact_animation()

    overlay = game_window.impact_animation_overlay
    assert overlay.geometry().x() == status_rect.right() - overlay.width() - 6
    assert overlay.geometry().center().y() == status_rect.center().y()


def test_fire_stage_one_opponent_card_impact_uses_victims_status_bar(game_window):
    state = game_window.game.state
    victim = state.players[1]
    burned = PetCard("FIRE-TEST", 1, (Attribute.FIRE,), {Attribute.FIRE: 1}, 1)
    victim.reserved.append(burned)
    game_window.refresh()
    before = game_window.capture_impact_snapshot()

    victim.reserved.remove(burned)
    state.market.cards[1].append(burned)
    game_window.refresh()
    events = game_window.build_impact_events(
        before,
        Action("specialization"),
        [f"烧掉了{victim.name}预购的FIRE-TEST，归还至1级牌库；{victim.name}保留预购获得的贤者碎晶"],
        SpecializationEffect(0, Attribute.FIRE, 1),
    )

    impact = next(event for event in events if event["card_id"] == "FIRE-TEST")
    assert impact["kind"] == "burn-in-place"
    assert impact["player_index"] == 1
    assert impact["start"] == before["player_origins"][1]
    assert impact["text"] == f"{victim.name}的FIRE-TEST被引燃了"
