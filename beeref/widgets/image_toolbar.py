# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

"""The buttons for the selected images."""

import logging

from beeref.widgets.pinned_toolbar import PinnedToolBar


logger = logging.getLogger(__name__)


class ImageToolBar(PinnedToolBar):
    """Crop and contour, beside the picture they act on.

    Cropping was reachable only through a menu or a shortcut, which is
    a long way to go for something aimed at one particular picture.
    """

    def __init__(self, parent, view):
        super().__init__(parent, view)

        self.crop = self.add_button(
            'crop', 'Crop this image (Shift+C)', view.on_action_crop)
        self.caption = self.add_button(
            'text', 'Write a caption', view.on_action_image_caption)
        # Stays pressed while the image has one, so the button says
        # what a press would do
        self.outline = self.add_button(
            'outline', 'Outline (Shift+O)', view.on_action_image_outline)
        self.outline.setCheckable(True)
        # One button, two jobs: while a caption is being written it
        # colours the caption, because that is what the colour on
        # screen is at that moment
        self.writing_caption = False
        self.color = self.add_button(
            'color', 'Outline colour', self.on_color, keep_colors=True)
        # The same pair of icons as everywhere else: one makes what is
        # selected bigger, the other smaller -- letters, line or contour
        self.thinner = self.add_button(
            'smaller', 'Thinner outline',
            view.on_action_size_decrease, repeat=True)
        self.thicker = self.add_button(
            'bigger', 'Thicker outline',
            view.on_action_size_increase, repeat=True)

        self.adjustSize()

    def on_color(self):
        """Colour the caption if one is being written, else the outline."""

        if self.writing_caption:
            self.view.on_action_image_caption_color()
        else:
            self.view.on_action_image_outline_color()

    def update_state(self, items):
        """Show what these buttons can do to the images selected."""

        # Cropping is one picture at a time; it has its own mode, with
        # handles that belong to a single image
        self.crop.setEnabled(len(items) == 1)
        self.caption.setEnabled(len(items) == 1)
        self.writing_caption = any(item.caption_editing for item in items)
        outlined = [item for item in items if item.has_outline()]
        self.outline.setChecked(len(outlined) == len(items))
        self.color.setToolTip(
            'Caption colour' if self.writing_caption else 'Outline colour')
        self.color.setEnabled(bool(outlined) or self.writing_caption)
        for button in (self.thinner, self.thicker):
            button.setEnabled(bool(outlined))
