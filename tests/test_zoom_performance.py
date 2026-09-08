"""What a zoom frame is allowed to spend its time on.

Measured on a real board of 238 items: a single turn of the wheel is
eased out over about a dozen frames sixteen milliseconds apart, so a
frame that costs eleven has no room to spare and drops some.
"""

from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui

from beeref.items import BeePixmapItem, BeeTextItem


def board(view, items=40):
    for i in range(items):
        img = QtGui.QImage(40, 30, QtGui.QImage.Format.Format_RGB32)
        img.fill(QtGui.QColor(90, 140, 190))
        item = BeePixmapItem(img)
        view.scene.addItem(item)
        item.setPos(i * 50, (i % 7) * 40)
    return view.scene


def test_the_bounding_box_is_asked_for_once_when_zooming(view):
    """It walks every item on the board, and a smooth zoom lands here
    on every frame of every step. It used to be worked out four times
    a frame: twice in get_zoom_size and twice in recalc_scene_rect."""

    board(view)
    with patch.object(type(view.scene), 'itemsBoundingRect',
                      wraps=view.scene.itemsBoundingRect) as walked:
        view.zoom(120, QtCore.QPointF(100, 100))

    assert walked.call_count <= 2


def test_recalc_scene_rect_walks_the_items_once(view):
    board(view)
    with patch.object(type(view.scene), 'itemsBoundingRect',
                      wraps=view.scene.itemsBoundingRect) as walked:
        view.recalc_scene_rect()

    assert walked.call_count == 1


def test_get_zoom_size_walks_the_items_once(view):
    board(view)
    with patch.object(type(view.scene), 'itemsBoundingRect',
                      wraps=view.scene.itemsBoundingRect) as walked:
        view.get_zoom_size(max)

    assert walked.call_count == 1


def test_the_bounding_box_is_the_one_it_always_was(view):
    """Mapping each item's box in one step gives what taking its four
    corners one at a time gave."""

    board(view)
    item = list(view.scene.items_by_type('pixmap'))[0]
    item.setRotation(37)
    item.setScale(2.5)

    corners = item.corners_scene_coords
    left = min(c.x() for c in corners)
    right = max(c.x() for c in corners)
    top = min(c.y() for c in corners)
    bottom = max(c.y() for c in corners)
    whole = view.scene.itemsBoundingRect(items=[item])

    assert round(whole.left(), 6) == round(left, 6)
    assert round(whole.top(), 6) == round(top, 6)
    assert round(whole.right(), 6) == round(right, 6)
    assert round(whole.bottom(), 6) == round(bottom, 6)


def test_it_still_leaves_the_selection_handles_out(view):
    """Which is why the scene has its own instead of Qt's."""

    item = BeeTextItem(text='Hello')
    view.scene.addItem(item)
    item.setSelected(True)
    whole = view.scene.itemsBoundingRect()

    assert whole.width() == item.width
    assert whole.height() == item.height


def test_an_empty_board_has_no_bounding_box(view):
    assert view.scene.itemsBoundingRect() == QtCore.QRectF(0, 0, 0, 0)


def test_the_grid_is_put_down_as_filled_rectangles(view, settings):
    """A pixel wide, on whole pixels. The line rasteriser cost half
    again as much for a result that cannot be told apart."""

    view.show_grid = True
    settings.setValue('View/grid_style', 'lines')
    painter = MagicMock()
    with patch('PyQt6.QtWidgets.QGraphicsView.drawBackground'):
        view.drawBackground(painter, QtCore.QRectF(0, 0, 500, 500))

    assert painter.fillRect.called
    painter.drawLines.assert_not_called()


def test_every_grid_line_is_one_whole_pixel(view, settings):
    view.resize(400, 300)
    view.show_grid = True
    settings.setValue('View/grid_style', 'lines')
    painter = MagicMock()
    with patch('PyQt6.QtWidgets.QGraphicsView.drawBackground'):
        view.drawBackground(painter, QtCore.QRectF(0, 0, 500, 500))

    for call in painter.fillRect.call_args_list:
        rect = call[0][0]
        assert isinstance(rect, QtCore.QRect)
        assert 1 in (rect.width(), rect.height())


def test_the_grid_is_drawn_on_the_screen_not_the_board(view, settings):
    """In device coordinates: a line landing on a fractional pixel is
    spread over its neighbours, so a one-pixel line came out two
    pixels of half strength at some zooms."""

    view.resize(400, 300)
    view.show_grid = True
    settings.setValue('View/grid_style', 'lines')
    view.setTransform(QtGui.QTransform.fromScale(3.7, 3.7))
    painter = MagicMock()
    with patch('PyQt6.QtWidgets.QGraphicsView.drawBackground'):
        view.drawBackground(painter, QtCore.QRectF(0, 0, 500, 500))

    for call in painter.fillRect.call_args_list:
        rect = call[0][0]
        assert rect.x() == int(rect.x())
        assert rect.y() == int(rect.y())


def test_words_are_drawn_at_the_size_they_are_seen_at(view):
    """Text is rasterised at the size the font asks for, not at the
    size it ends up. A group's title is sized from the box holding it,
    and on a real board that reached the eight thousand point cap and
    arrived four pixels tall: sixteen milliseconds a frame, for a title
    nobody could read."""

    from beeref.items import text_at_screen_size

    painter = MagicMock()
    painter.combinedTransform.return_value = QtGui.QTransform.fromScale(
        0.0005, 0.0005)
    room = QtCore.QRectF(0, 0, 216191, 23212)

    smaller, size = text_at_screen_size(painter, room, 8000)

    painter.save.assert_called_once()
    painter.scale.assert_called_once()
    assert round(size, 1) == 4.0
    assert round(smaller.width()) == 108


def test_a_title_at_its_own_size_is_left_alone(view):
    """Scaling up a rasterised letter is worse than asking for a big
    one, so this only ever makes them smaller."""

    from beeref.items import text_at_screen_size

    painter = MagicMock()
    painter.combinedTransform.return_value = QtGui.QTransform.fromScale(3, 3)
    room = QtCore.QRectF(0, 0, 100, 40)

    same, size = text_at_screen_size(painter, room, 12)

    assert same == room
    assert size == 12
    painter.scale.assert_not_called()
    # Still saved, because the caller restores either way
    painter.save.assert_called_once()


def test_the_painter_is_left_as_it_was_found(view):
    """However the words are drawn, what comes after must not inherit
    a scaled painter."""

    from beeref.items import BeeGroupItem

    item = BeeTextItem(text='Hello')
    view.scene.addItem(item)
    item.setSelected(True)
    view.on_action_group_items()
    group = list(view.scene.items_by_type('group'))[0]
    group.title = 'Chapter One'

    picture = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(picture)
    painter.scale(0.01, 0.01)
    before = painter.transform()
    group.paint_header(painter)
    after = painter.transform()
    painter.end()

    assert isinstance(group, BeeGroupItem)
    assert after == before


def test_a_captions_painter_is_left_as_it_was_found(view):
    img = QtGui.QImage(300, 200, QtGui.QImage.Format.Format_RGB32)
    img.fill(QtGui.QColor(70, 120, 190))
    item = BeePixmapItem(img)
    view.scene.addItem(item)
    item.caption = 'A caption'

    picture = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(picture)
    painter.scale(0.01, 0.01)
    before = painter.transform()
    item.paint_caption(painter)
    after = painter.transform()
    painter.end()

    assert after == before


def test_a_turn_of_the_wheel_takes_a_share_of_what_is_left(view):
    """A frame arriving on time behaves exactly as it always did."""

    on_time = view.ZOOM_INTERVAL / 1000
    assert round(view.zoom_share(on_time), 6) == view.ZOOM_SMOOTHING


def test_a_late_frame_makes_up_for_being_late(view):
    """Two intervals' worth of waiting covers two intervals' worth of
    the zoom, so the board arrives when it should."""

    interval = view.ZOOM_INTERVAL / 1000
    one = view.zoom_share(interval)
    two = view.zoom_share(interval * 2)

    assert two > one
    assert round(two, 6) == round(1 - (1 - one) ** 2, 6)


def test_catching_up_has_a_limit(view):
    """Coming back to a window that was buried must not finish the zoom
    in a single jump."""

    huge = view.zoom_share(60)
    capped = view.zoom_share(
        view.ZOOM_INTERVAL / 1000 * view.ZOOM_MAX_CATCHUP)

    assert huge == capped
    assert huge < 1


def test_no_time_passing_moves_nothing(view):
    assert view.zoom_share(0) == 0


def settle_ms(view, frame_ms):
    """How long a wheel notch takes to arrive, at this frame cost."""

    view.pending_zoom = 120.0
    elapsed = frame_ms / 1000
    waited = 0
    while abs(view.pending_zoom) > view.ZOOM_REMAINDER and waited < 4000:
        view.pending_zoom -= view.pending_zoom * view.zoom_share(elapsed)
        waited += frame_ms
    return waited


def test_the_zoom_arrives_when_it_should_however_busy_the_board(view):
    """It used to take a fixed number of frames, so a board whose
    frames cost three times as much took three times as long to stop --
    which is what made zooming out on a full board feel floaty."""

    quick = settle_ms(view, 4)
    slow = settle_ms(view, 45)

    assert quick < 400
    assert slow < quick * 1.5


def test_a_clock_reading_zero_still_zooms(view):
    """The moment a zoom started is a clock reading, and a clock can
    read zero. Treating that as 'not started yet' left the zoom sitting
    still for as long as the wheel was turned."""

    from PyQt6 import QtGui as _QtGui

    img = _QtGui.QImage(30, 30, _QtGui.QImage.Format.Format_RGB32)
    img.fill(_QtGui.QColor('red'))
    view.scene.addItem(BeePixmapItem(img))

    clock = [0.0]
    with patch('beeref.view.time.monotonic', side_effect=lambda: clock[0]):
        view.smooth_zoom(120, QtCore.QPointF(50, 50))
        assert view.last_zoom_step == 0.0
        clock[0] += view.ZOOM_INTERVAL / 1000
        before = view.get_scale()
        view.step_zoom()

    assert view.pending_zoom < 120
    assert view.get_scale() > before
