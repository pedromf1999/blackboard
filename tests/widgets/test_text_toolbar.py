from beeref.items import BeeTextItem


def test_toolbar_offers_a_font_button(view):
    """Beside bold, so the two live together."""

    item = BeeTextItem('hello')
    view.scene.addItem(item)
    item.setSelected(True)
    toolbar = view.text_toolbar

    assert toolbar.font.icon().isNull() is False
    assert 'Ranade' in toolbar.font.toolTip()
    # Bold comes first, the font button right after it
    buttons = toolbar.findChildren(type(toolbar.bold))
    assert buttons.index(toolbar.font) == buttons.index(toolbar.bold) + 1
