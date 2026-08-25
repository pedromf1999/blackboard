from PyQt6 import QtCore

from beeref.assets import BeeAssets


def colours_in(icon):
    image = icon.pixmap(QtCore.QSize(48, 48)).toImage()
    return {(image.pixelColor(x, y).red(),
             image.pixelColor(x, y).green(),
             image.pixelColor(x, y).blue())
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 200}


def test_the_colour_icon_keeps_its_colours(qapp):
    """It is coloured on purpose; repainting would flatten it."""

    kept = colours_in(BeeAssets().color_icon('color'))

    assert (255, 21, 161) in kept
    assert (21, 131, 255) in kept
    assert (0, 207, 45) in kept
    assert len(kept) > 50


def test_line_art_is_still_repainted(qapp):
    """Everything else is black line art, drawn to suit a dark window."""

    repainted = colours_in(BeeAssets().tool_icon('color'))
    assert len(repainted) < 10


def test_the_two_ways_of_loading_are_kept_apart(qapp):
    """Caching by name alone would hand back whichever came first."""

    assets = BeeAssets()
    plain = assets.tool_icon('color')
    coloured = assets.color_icon('color')
    assert plain.cacheKey() != coloured.cacheKey()
    # And asking again gives the same one back, not a fresh render
    assert assets.color_icon('color').cacheKey() == coloured.cacheKey()


def test_the_colour_buttons_use_it(view):
    from beeref import commands
    from beeref.items import BeeDrawItem, BeeGroupItem, BeeTextItem

    note = BeeTextItem('note')
    view.scene.addItem(note)
    drawing = BeeDrawItem(points=[(0, 0), (100, 0)])
    view.scene.addItem(drawing)
    group = BeeGroupItem(box_color=(10, 20, 30, 200))
    commands.GroupItems(view.scene, [note], group).redo()

    wanted = colours_in(BeeAssets().color_icon('color'))
    for button in (view.text_toolbar.box_color,
                   view.draw_item_toolbar.color,
                   view.group_toolbar.color):
        assert colours_in(button.icon()) == wanted


def test_the_highlighter_keeps_its_own_icon(view):
    """Two identical icons side by side would say nothing."""

    assert colours_in(view.text_toolbar.highlight.icon()) != colours_in(
        view.text_toolbar.box_color.icon())


def filled_share(icon):
    """How much of its square an icon's drawing actually covers."""

    image = icon.pixmap(QtCore.QSize(64, 64)).toImage()
    drawn = [(x, y) for x in range(image.width())
             for y in range(image.height())
             if image.pixelColor(x, y).alpha() > 20]
    xs = [x for x, _ in drawn]
    ys = [y for _, y in drawn]
    return (max(max(xs) - min(xs), max(ys) - min(ys)) + 1) / image.width()


def test_the_lock_icons_are_drawn_as_big_as_their_neighbours(qapp):
    """They came with wide margins baked in and looked shrunken.

    Nothing scales an icon down; the drawing simply sat in the middle of
    its square with room to spare, so the fix is in the artwork and this
    is what would let it come back.
    """

    reference = filled_share(BeeAssets().tool_icon('ungroup'))
    for name in ('lock', 'unlock'):
        assert filled_share(BeeAssets().tool_icon(name)) > reference - 0.1
