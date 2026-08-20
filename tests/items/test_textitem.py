from unittest.mock import patch, MagicMock

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
import pytest

from beeref.items import BeeTextItem, BeePixmapItem, item_registry


def test_in_items_registry():
    assert item_registry['text'] == BeeTextItem


@patch('beeref.selection.SelectableMixin.init_selectable')
def test_init(selectable_mock, qapp):
    item = BeeTextItem('foo bar')
    assert item.save_id is None
    assert item.width
    assert item.height
    assert item.scale() == 1
    assert item.toPlainText() == 'foo bar'
    assert item.is_editable is True
    assert item.edit_mode is False
    assert item.is_image is False
    selectable_mock.assert_called_once()


def test_sample_color_at(qapp, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    assert item.sample_color_at(QtCore.QPointF(2.0, 2.0)) is None


def test_set_pos_center(qapp):
    item = BeeTextItem('foo bar')
    with patch.object(item, 'bounding_rect_unselected',
                      return_value=QtCore.QRectF(0, 0, 200, 100)):
        item.set_pos_center(QtCore.QPointF(0, 0))
        assert item.pos().x() == -100
        assert item.pos().y() == -50


def test_set_pos_center_when_scaled(qapp):
    item = BeeTextItem('foo bar')
    item.setScale(2)
    with patch.object(item, 'bounding_rect_unselected',
                      return_value=QtCore.QRectF(0, 0, 200, 100)):
        item.set_pos_center(QtCore.QPointF(0, 0))
        assert item.pos().x() == -200
        assert item.pos().y() == -100


def test_set_pos_center_when_rotated(qapp):
    item = BeeTextItem('foo bar')
    item.setRotation(90)
    with patch.object(item, 'bounding_rect_unselected',
                      return_value=QtCore.QRectF(0, 0, 200, 100)):
        item.set_pos_center(QtCore.QPointF(0, 0))
        assert item.pos().x() == 50
        assert item.pos().y() == -100


def test_get_extra_save_data(qapp):
    item = BeeTextItem('foo bar')
    data = item.get_extra_save_data()
    assert data['text'] == 'foo bar'
    assert data['box_color'] == (0, 0, 0, 255)
    assert 'foo bar' in data['html']


def test_text_colour_follows_the_box_colour(qapp):
    item = BeeTextItem('foo bar')
    on_black = item.defaultTextColor()

    item.box_color = QtGui.QColor(245, 225, 90, 255)
    on_yellow = item.defaultTextColor()
    # Light box gets dark text, dark box gets light text
    assert on_black.lightness() > 127
    assert on_yellow.lightness() < 127


def test_text_colour_accounts_for_a_translucent_box(qapp):
    """A see-through box shows the canvas, which is what text sits on."""

    item = BeeTextItem('foo bar')
    item.box_color = QtGui.QColor(255, 255, 255, 0)
    # Fully transparent over the dark canvas, so the text stays light
    assert item.defaultTextColor().lightness() > 127


def test_get_extra_save_data_with_box_color(qapp):
    item = BeeTextItem('foo bar')
    item.box_color = QtGui.QColor(255, 0, 0, 100)
    assert item.get_extra_save_data()['box_color'] == (255, 0, 0, 100)


def test_init_from_html_and_box_color(qapp):
    item = BeeTextItem(text='plain',
                       html='<p>rich <b>text</b></p>',
                       box_color=(255, 0, 0, 100))
    assert item.toPlainText() == 'rich text'
    assert item.box_color == QtGui.QColor(255, 0, 0, 100)


def test_init_falls_back_to_plain_text(qapp):
    item = BeeTextItem(text='plain')
    assert item.toPlainText() == 'plain'
    assert item.box_color == QtGui.QColor(0, 0, 0, 255)


@pytest.mark.parametrize(
    'text,index,expected',
    [
        ('see https://example.com/page now', 10,
         'https://example.com/page'),
        # First and last character of the url still count as a hit
        ('see https://example.com now', 4, 'https://example.com'),
        ('see https://example.com now', 22, 'https://example.com'),
        # www urls get a scheme added
        ('go to www.qt.io today', 10, 'http://www.qt.io'),
        # Sentence punctuation is not part of the address
        ('see https://example.com, ok', 10, 'https://example.com'),
        ('see (https://example.com) ok', 10, 'https://example.com'),
        # Not urls
        ('just some plain text', 6, None),
        ('see https://example.com now', 25, None),
        ('an email foo@example.com here', 12, None),
    ])
def test_get_url_at_cursor_pos(qapp, text, index, expected):
    item = BeeTextItem(text)
    assert item.get_url_at_cursor_pos(index) == expected


def test_get_url_at_cursor_pos_on_second_line(qapp):
    item = BeeTextItem('first line\nsee https://example.com here')
    index = item.toPlainText().index('example')
    assert item.get_url_at_cursor_pos(index) == 'https://example.com'


@patch('PyQt6.QtGui.QDesktopServices.openUrl')
def test_mouse_press_ctrl_click_opens_url(open_mock, qapp):
    item = BeeTextItem('see https://example.com now')
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
    with patch.object(item, 'get_url_at', return_value='https://example.com'):
        item.mousePressEvent(event)
    open_mock.assert_called_once()
    assert open_mock.call_args[0][0].toString() == 'https://example.com'
    event.accept.assert_called_once()


@patch('beeref.selection.SelectableMixin.mousePressEvent')
@patch('PyQt6.QtGui.QDesktopServices.openUrl')
def test_mouse_press_ctrl_click_without_url_selects_as_usual(
        open_mock, super_mock, qapp):
    item = BeeTextItem('just some plain text')
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.ControlModifier
    with patch.object(item, 'get_url_at', return_value=None):
        item.mousePressEvent(event)
    open_mock.assert_not_called()
    super_mock.assert_called_once()


@patch('beeref.selection.SelectableMixin.mousePressEvent')
@patch('PyQt6.QtGui.QDesktopServices.openUrl')
def test_mouse_press_without_ctrl_does_not_open_url(
        open_mock, super_mock, qapp):
    item = BeeTextItem('see https://example.com now')
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    item.mousePressEvent(event)
    open_mock.assert_not_called()
    super_mock.assert_called_once()


def test_apply_char_format_applies_to_whole_text(qapp):
    item = BeeTextItem('foo bar')
    charformat = QtGui.QTextCharFormat()
    charformat.setForeground(QtGui.QColor(255, 0, 0))
    item.apply_char_format(charformat)
    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    assert cursor.charFormat().foreground().color() == QtGui.QColor(255, 0, 0)


def test_apply_char_format_applies_to_selection_only(qapp):
    item = BeeTextItem('foo bar')
    cursor = item.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(3, QtGui.QTextCursor.MoveMode.KeepAnchor)
    item.setTextCursor(cursor)
    charformat = QtGui.QTextCharFormat()
    charformat.setForeground(QtGui.QColor(255, 0, 0))
    item.apply_char_format(charformat)

    check = item.textCursor()
    check.setPosition(2)
    assert check.charFormat().foreground().color() == QtGui.QColor(255, 0, 0)
    check.setPosition(6)
    assert check.charFormat().foreground().color() != QtGui.QColor(255, 0, 0)


def test_create_copy_keeps_formatting(qapp):
    item = BeeTextItem('foo bar')
    item.box_color = QtGui.QColor(255, 0, 0, 100)
    charformat = QtGui.QTextCharFormat()
    charformat.setFontWeight(QtGui.QFont.Weight.Bold)
    charformat.setBackground(QtGui.QColor(0, 255, 0))
    item.apply_char_format(charformat)

    copy = item.create_copy()
    assert copy.toPlainText() == 'foo bar'
    assert copy.box_color == QtGui.QColor(255, 0, 0, 100)
    cursor = copy.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    assert cursor.charFormat().fontWeight() == QtGui.QFont.Weight.Bold
    assert cursor.charFormat().background().color() == QtGui.QColor(0, 255, 0)


def test_stored_text_colour_follows_the_box(qapp):
    """An old note with its own text colour is brought into line."""

    old_html = (
        '<html><body><p><span style=" color:#00ff00;">'
        'green text</span></p></body></html>')
    item = BeeTextItem(html=old_html)

    cursor = item.textCursor()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    assert cursor.charFormat().foreground().color() == (
        item.defaultTextColor())


@patch('beeref.items.BeeTextItem.boundingRect')
def test_contains_when_inside_bounds(brect_mock, qapp):
    brect_mock.return_value = QtCore.QRectF(20, 30, 50, 50)
    item = BeeTextItem('foo bar')
    item.contains(QtCore.QPointF(33, 45)) is True
    brect_mock.assert_called_once_with()


@patch('beeref.items.BeeTextItem.boundingRect')
def test_contains_when_outside_bounds(brect_mock, qapp):
    brect_mock.return_value = QtCore.QRectF(20, 30, 50, 50)
    item = BeeTextItem('foo bar')
    item.contains(QtCore.QPointF(19, 29)) is False
    brect_mock.assert_called_once_with()


@patch('PyQt6.QtWidgets.QGraphicsTextItem.paint')
def test_paint(paint_mock, qapp):
    item = BeeTextItem('foo bar')
    item.paint_selectable = MagicMock()
    painter = MagicMock()
    option = MagicMock()
    item.paint(painter, option, 'widget')
    item.paint_selectable.assert_called_once()
    painter.drawRoundedRect.assert_called_once()
    assert option.state == QtWidgets.QStyle.StateFlag.State_Enabled
    paint_mock.assert_called_once_with(painter, option, 'widget')


def test_has_selection_outline_when_not_selected(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(False)
    item.has_selection_outline() is False


def test_has_selection_outline_when_selected(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(True)
    item.has_selection_outline() is True


def test_has_selection_handles_when_not_selected(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(False)
    item2 = BeeTextItem('baz')
    view.scene.addItem(item2)
    item2.setSelected(False)
    item.has_selection_handles() is False


def test_has_selection_handles_when_selected_single(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(True)
    item2 = BeeTextItem('baz')
    view.scene.addItem(item2)
    item2.setSelected(False)
    item.has_selection_handles() is True


def test_has_selection_handles_when_selected_multi(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.setSelected(True)
    item2 = BeeTextItem('baz')
    view.scene.addItem(item2)
    item2.setSelected(True)
    item.has_selection_handles() is False


def test_has_selection_handles_when_selected_single_and_edit_mode(view):
    item = BeeTextItem('foo bar')
    item.edit_mode = False
    view.scene.addItem(item)
    item.setSelected(True)
    item2 = BeeTextItem('baz')
    view.scene.addItem(item2)
    item2.setSelected(False)
    item.has_selection_handles() is False


def test_selection_action_items(qapp):
    item = BeeTextItem('foo bar')
    assert item.selection_action_items() == [item]


def test_update_from_data(qapp):
    item = BeeTextItem('foo bar')
    item.update_from_data(
        save_id=3,
        x=11,
        y=22,
        z=1.2,
        scale=2.5,
        rotation=45,
        flip=-1)
    assert item.save_id == 3
    assert item.pos() == QtCore.QPointF(11, 22)
    assert item.zValue() == 1.2
    assert item.rotation() == 45
    assert item.flip() == -1


def test_update_from_data_keeps_flip(qapp):
    item = BeeTextItem('foo bar')
    item.do_flip()
    item.update_from_data(flip=-1)
    assert item.flip() == -1


def test_update_from_data_keeps_unset_values(qapp):
    item = BeeTextItem('foo bar')
    item.setScale(3)
    item.update_from_data(rotation=45)
    assert item.scale() == 3
    assert item.flip() == 1


def test_create_from_data(qapp):
    item = BeeTextItem.create_from_data(data={'text': 'hello world'})
    item.toPlainText() == 'hello world'


def test_create_copy(qapp):
    item = BeeTextItem('foo bar')
    item.setPos(20, 30)
    item.setRotation(33)
    item.do_flip()
    item.setZValue(0.5)
    item.setScale(2.2)

    copy = item.create_copy()
    assert copy.toPlainText() == 'foo bar'
    assert copy.pos() == QtCore.QPointF(20, 30)
    assert copy.rotation() == 33
    assert copy.flip() == -1
    assert copy.zValue() == 0.5
    assert copy.scale() == 2.2


def test_enter_edit_mode(view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    item.enter_edit_mode()
    assert item.edit_mode is True
    assert view.scene.edit_item == item
    flags = item.textInteractionFlags()
    assert flags == Qt.TextInteractionFlag.TextEditorInteraction


@patch('PyQt6.QtGui.QTextCursor')
@patch('beeref.items.BeeTextItem.setTextCursor')
def test_exit_edit_mode(setcursor_mock, cursor_mock, view):
    item = BeeTextItem('foo bar')
    item.edit_mode = True
    item.old_text = 'old'
    view.scene.addItem(item)
    view.scene.edit_item = item
    item.exit_edit_mode()
    assert item.edit_mode is False
    assert view.scene.edit_item is None
    flags = item.textInteractionFlags()
    assert flags == Qt.TextInteractionFlag.NoTextInteraction
    cursor_mock.assert_called_once_with(item.document())
    setcursor_mock.assert_called_once_with(cursor_mock.return_value)
    assert view.scene.edit_item is None


def test_exit_edit_mode_when_text_empty(view):
    item = BeeTextItem(' \r\n\t')
    item.edit_mode = True
    item.old_text = 'old'
    view.scene.addItem(item)
    view.scene.edit_item = item
    item.exit_edit_mode()
    assert item.edit_mode is False
    assert view.scene.edit_item is None
    flags = item.textInteractionFlags()
    assert flags == Qt.TextInteractionFlag.NoTextInteraction
    assert item.scene() is None
    assert view.scene.items() == []
    assert view.scene.edit_item is None


@patch('PyQt6.QtGui.QTextCursor')
@patch('beeref.items.BeeTextItem.setTextCursor')
def test_exit_edit_mode_when_commit_false(setcursor_mock, cursor_mock, view):
    item = BeeTextItem('foo bar')
    item.edit_mode = True
    item.old_text = 'old'
    view.scene.addItem(item)
    view.scene.edit_item = item
    item.exit_edit_mode(commit=False)
    assert item.edit_mode is False
    assert view.scene.edit_item is None
    flags = item.textInteractionFlags()
    assert flags == Qt.TextInteractionFlag.NoTextInteraction
    cursor_mock.assert_called_once_with(item.document())
    setcursor_mock.assert_called_once_with(cursor_mock.return_value)
    assert view.scene.edit_item is None
    assert item.toPlainText() == 'old'


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_any_key(exit_mock, key_press_mock, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_T
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    item.keyPressEvent(event)
    key_press_mock.assert_called_once_with(event)
    exit_mock.assert_not_called()
    assert view.scene.edit_item == item


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_shift_return(exit_mock, key_press_mock, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_Return
    event.modifiers.return_value = Qt.KeyboardModifier.ShiftModifier
    item.keyPressEvent(event)
    key_press_mock.assert_called_once_with(event)
    exit_mock.assert_not_called()
    assert view.scene.edit_item == item


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_shift_enter(exit_mock, key_press_mock, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_Enter
    event.modifiers.return_value = Qt.KeyboardModifier.ShiftModifier
    item.keyPressEvent(event)
    key_press_mock.assert_called_once_with(event)
    exit_mock.assert_not_called()
    assert view.scene.edit_item == item


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_return_keeps_editing(exit_mock, key_press_mock,
                                              view):
    """Enter makes a new paragraph rather than ending the edit."""

    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_Return
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    item.keyPressEvent(event)
    key_press_mock.assert_called_once_with(event)
    exit_mock.assert_not_called()
    assert view.scene.edit_item == item


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_enter_keeps_editing(exit_mock, key_press_mock, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_Enter
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    item.keyPressEvent(event)
    key_press_mock.assert_called_once_with(event)
    exit_mock.assert_not_called()
    assert view.scene.edit_item == item


@patch('PyQt6.QtWidgets.QGraphicsTextItem.keyPressEvent')
@patch('beeref.items.BeeTextItem.exit_edit_mode')
def test_key_press_event_escape(exit_mock, key_press_mock, view):
    item = BeeTextItem('foo bar')
    view.scene.addItem(item)
    view.scene.edit_item = item
    event = MagicMock()
    event.key.return_value = Qt.Key.Key_Escape
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    item.keyPressEvent(event)
    key_press_mock.assert_not_called()
    exit_mock.assert_called_once_with(commit=False)


def test_item_to_mimedata(qapp):
    mimedata = QtCore.QMimeData()
    item = BeeTextItem('foo bar')
    item.add_to_mimedata(mimedata)
    assert mimedata.text() == 'foo bar'


def test_corner_radius_grows_with_the_text(view):
    """Scaling the text has to scale the rounding with it."""

    item = BeeTextItem('scale me')
    view.scene.addItem(item)
    item.setSelected(True)
    before = item.corner_radius()

    for _ in range(5):
        view.on_action_size_increase()

    assert item.corner_radius() > before


def test_corner_radius_shrinks_with_the_text(view):
    item = BeeTextItem('scale me')
    view.scene.addItem(item)
    item.setSelected(True)
    before = item.corner_radius()

    for _ in range(5):
        view.on_action_size_decrease()

    assert item.corner_radius() < before


def test_text_margin_grows_with_the_text(view):
    """The gap around the text has to keep its weight.

    Qt's margin is a fixed four pixels, so making the text bigger with
    the toolbar used to leave the gap behind and the text crept towards
    the edge of its box. Scaling the item already scaled the gap, so the
    two ways of making text bigger disagreed.
    """

    item = BeeTextItem('Title')
    view.scene.addItem(item)
    item.setSelected(True)

    def weight():
        return item.document().documentMargin() / item.text_line_height()

    before = weight()
    for _ in range(8):
        view.on_action_size_increase()

    assert item.document().documentMargin() > 4
    assert weight() == pytest.approx(before)


def test_corner_radius_is_proportional_to_the_text(view):
    item = BeeTextItem('proportions')
    view.scene.addItem(item)
    assert item.corner_radius() == pytest.approx(
        item.one_line_height() * item.CORNER_RADIUS_FRACTION)


def test_corner_radius_ignores_how_big_the_box_is(view):
    """A note with many lines must not get bigger corners.

    The rounding used to follow the box, so adding lines grew the
    corners until they cut into the text written in them.
    """

    one_line = BeeTextItem('A short note')
    view.scene.addItem(one_line)
    many_lines = BeeTextItem('\n'.join(['A short note'] * 20))
    view.scene.addItem(many_lines)

    tall = QtWidgets.QGraphicsTextItem.boundingRect(many_lines).height()
    short = QtWidgets.QGraphicsTextItem.boundingRect(one_line).height()
    assert tall > short * 5, 'the taller box needs to be clearly taller'
    assert many_lines.corner_radius() == one_line.corner_radius()


def test_corner_radius_keeps_its_proportion_across_sizes(view):
    """Big text and small text must look like the same shape."""

    small = BeeTextItem('same words')
    view.scene.addItem(small)
    big = BeeTextItem('same words')
    view.scene.addItem(big)
    big.setSelected(True)
    for _ in range(8):
        view.on_action_size_increase()

    def proportion(item):
        return item.corner_radius() / item.one_line_height()

    assert big.text_line_height() > small.text_line_height()
    assert proportion(big) == pytest.approx(proportion(small))


def test_corner_radius_never_swallows_a_small_box(view):
    """One big character gives a box barely larger than its own text."""

    item = BeeTextItem('W')
    view.scene.addItem(item)
    item.setSelected(True)
    for _ in range(8):
        view.on_action_size_increase()

    rect = QtWidgets.QGraphicsTextItem.boundingRect(item)
    shorter = min(rect.width(), rect.height())
    assert item.corner_radius() < shorter / 2


def test_corner_radius_keeps_its_weight_as_text_grows(view):
    """Big text must not round the box towards a capsule.

    Going by the bare line height, the corners crept from a third of the
    box towards half of it as the text was scaled up with the toolbar.
    """

    item = BeeTextItem('Title')
    view.scene.addItem(item)
    item.setSelected(True)

    def weight():
        rect = QtWidgets.QGraphicsTextItem.boundingRect(item)
        return item.corner_radius() / rect.height()

    before = weight()
    for _ in range(8):
        view.on_action_size_increase()

    assert weight() == pytest.approx(before, abs=0.02)


def test_wrap_width_rewraps_the_text(view):
    """Narrowing the box makes the text taller, not squashed."""

    item = BeeTextItem('one two three four five six seven eight nine ten')
    view.scene.addItem(item)
    wide = QtWidgets.QGraphicsTextItem.boundingRect(item)

    item.set_wrap_width(wide.width() / 3)
    narrow = QtWidgets.QGraphicsTextItem.boundingRect(item)

    assert narrow.width() < wide.width()
    assert narrow.height() > wide.height()
    # Rewrapping is not stretching: the letters keep their shape
    assert item.stretch == (1, 1)


def test_wrap_width_never_cuts_a_word_in_half(view):
    item = BeeTextItem('antidisestablishmentarianism')
    view.scene.addItem(item)
    item.set_wrap_width(item.MIN_WRAP_WIDTH)

    option = item.document().defaultTextOption()
    assert option.wrapMode() == QtGui.QTextOption.WrapMode.WordWrap
    # The long word hangs over the edge rather than being broken up
    assert item.toPlainText() == 'antidisestablishmentarianism'


def test_wrap_width_has_a_minimum(view):
    item = BeeTextItem('some text')
    view.scene.addItem(item)
    item.set_wrap_width(1)
    assert item.textWidth() == item.MIN_WRAP_WIDTH


def test_wrap_width_is_saved_and_restored(view):
    item = BeeTextItem('a fair amount of words here')
    view.scene.addItem(item)
    item.set_wrap_width(120)

    data = item.get_extra_save_data()
    assert data['text_width'] == 120

    restored = BeeTextItem(**data)
    assert restored.textWidth() == 120


def test_untouched_text_saves_no_width(view):
    """Boards that never used this stay exactly as they were."""

    item = BeeTextItem('plain')
    view.scene.addItem(item)
    assert 'text_width' not in item.get_extra_save_data()


def test_copy_keeps_the_wrap_width(view):
    item = BeeTextItem('wrapped text here')
    view.scene.addItem(item)
    item.set_wrap_width(90)
    assert item.create_copy().textWidth() == 90


def test_text_items_offer_no_vertical_edge_handles(view):
    item = BeeTextItem('foo')
    view.scene.addItem(item)
    assert [edge['vertical'] for edge in item.get_edge_bounds()] == [
        False, False]


def test_images_still_stretch_from_every_edge(view, imgfilename3x3):
    item = BeePixmapItem(QtGui.QImage(imgfilename3x3))
    view.scene.addItem(item)
    assert item.reflows_text() is False
    assert len(item.get_edge_bounds()) == 4


def press_key(item, key, modifier=Qt.KeyboardModifier.NoModifier, text=''):
    event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, modifier, text)
    item.keyPressEvent(event)


def test_enter_adds_a_paragraph_to_the_text(view):
    """Enter types a new paragraph instead of ending the edit."""

    item = BeeTextItem('first line')
    view.scene.addItem(item)
    item.enter_edit_mode()
    cursor = item.textCursor()
    cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
    item.setTextCursor(cursor)

    press_key(item, Qt.Key.Key_Return, text='\r')
    press_key(item, Qt.Key.Key_A, text='a')

    assert item.toPlainText().splitlines() == ['first line', 'a']
    assert item.edit_mode is True
    assert view.scene.edit_item is item


def test_escape_still_discards_the_edit(view):
    item = BeeTextItem('keep me')
    view.scene.addItem(item)
    item.enter_edit_mode()
    cursor = item.textCursor()
    cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
    item.setTextCursor(cursor)
    press_key(item, Qt.Key.Key_X, text='x')

    press_key(item, Qt.Key.Key_Escape)
    assert item.toPlainText() == 'keep me'
    assert item.edit_mode is False


def test_clicking_outside_ends_the_edit(view):
    """Which is the only way out now that Enter types a paragraph."""

    view.resize(800, 600)
    item = BeeTextItem('some text')
    view.scene.addItem(item)
    item.setPos(0, 0)
    view.on_action_fit_scene()
    item.enter_edit_mode()
    assert view.scene.edit_item is item

    empty = view.mapFromScene(item.mapToScene(QtCore.QPointF(-400, -400)))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, empty)

    assert item.edit_mode is False
    assert view.scene.edit_item is None


# A QTextTable belongs to its document, and a Python name for one can
# outlive the C++ object -- when the document is replaced, or simply at
# teardown. Qt then crashes wherever the collector happens to get to it,
# which is rarely the test that caused it. These helpers read what is
# needed and keep no table.

def shape(item):
    table = item.current_table()
    return (table.rows(), table.columns())


def widths(item):
    return item.column_widths(item.current_table())


def cell_background(item, row, column):
    return item.current_table().cellAt(row, column).format(
        ).toTableCellFormat().background().color()


def test_insert_table_makes_a_table_with_widths(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table()

    assert shape(item) == (item.TABLE_ROWS, item.TABLE_COLUMNS)
    assert widths(item) == [item.TABLE_COLUMN_WIDTH] * item.TABLE_COLUMNS
    # The cursor waits in the first cell, ready to type
    assert item.current_cell().row() == 0
    assert item.current_cell().column() == 0


def test_insert_table_row_and_column(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 2)

    item.insert_table_row()
    assert shape(item) == (3, 2)
    item.insert_table_column()
    assert shape(item) == (3, 3)
    # The new column gets a width like the others, rather than being
    # sized by whatever happens to be typed into it
    assert widths(item) == [item.TABLE_COLUMN_WIDTH] * 3


def test_remove_table_row_keeps_the_cursor_in_the_table(view):
    """Otherwise a second row could not be removed after the first."""

    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(3, 3)

    item.remove_table_row()
    assert item.current_table() is not None
    item.remove_table_row()
    assert shape(item) == (1, 3)


def test_last_row_and_column_are_kept(view):
    """Removing them would leave a table that is not there at all."""

    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(1, 1)

    item.remove_table_row()
    item.remove_table_column()
    assert shape(item) == (1, 1)


def test_cell_colour_keeps_the_words_readable(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 2)
    item.textCursor().insertText('hello')

    white = QtGui.QColor(255, 255, 255)
    item.apply_cell_color(white)
    assert cell_background(item, 0, 0) == white

    # White cell, so the words in it have to be dark
    cursor = item.current_table().cellAt(0, 0).firstCursorPosition()
    cursor.movePosition(QtGui.QTextCursor.MoveOperation.Right,
                        QtGui.QTextCursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().foreground().color() == item.text_color_over(
        white)


def boundaries(item):
    table = item.tables()[0]
    columns, rows = item.table_boundaries(table)
    del table
    return columns, rows


def test_grip_found_on_a_column_boundary(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 3)
    columns, rows = boundaries(item)

    index, x = columns[0]
    point = QtCore.QPointF(x, rows[0][1] - 5)
    assert item.table_grip_at(point) == ('column', 0, index)

    # Well inside a cell, away from every boundary, nothing is grabbed
    assert item.table_grip_at(QtCore.QPointF(x - 30, rows[0][1] - 12)) is None


def test_grip_found_on_a_row_boundary(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 3)
    columns, rows = boundaries(item)

    index, y = rows[0]
    point = QtCore.QPointF(columns[0][1] - 30, y)
    assert item.table_grip_at(point) == ('row', 0, index)


def test_dragging_a_column_boundary_widens_it(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 3)
    columns, rows = boundaries(item)
    index, x = columns[0]
    start = QtCore.QPointF(x, rows[0][1] - 5)
    before = item.column_widths(item.tables()[0])

    item.start_table_drag(('column', 0, index), start)
    item.drag_table_boundary(QtCore.QPointF(x + 40, start.y()))

    after = item.column_widths(item.tables()[0])
    assert after[0] == before[0] + 40
    # Only the column being dragged changes
    assert after[1:] == before[1:]


def test_a_column_cannot_be_dragged_away_to_nothing(view):
    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(2, 2)
    columns, rows = boundaries(item)
    index, x = columns[0]
    start = QtCore.QPointF(x, rows[0][1] - 5)

    item.start_table_drag(('column', 0, index), start)
    item.drag_table_boundary(QtCore.QPointF(x - 500, start.y()))

    assert item.column_widths(item.tables()[0])[0] == item.TABLE_MIN_WIDTH


def test_dragging_a_row_boundary_makes_it_taller(view):
    """Qt sizes rows to their contents, so the padding is the handle."""

    item = BeeTextItem('')
    view.scene.addItem(item)
    item.insert_table(3, 2)
    columns, rows = boundaries(item)
    index, y = rows[0]
    start = QtCore.QPointF(columns[0][1] - 30, y)
    before = item.boundingRect().height()

    item.start_table_drag(('row', 0, index), start)
    item.drag_table_boundary(QtCore.QPointF(start.x(), y + 30))

    assert item.row_extra_height(item.tables()[0], 0) == 30
    assert item.boundingRect().height() > before
