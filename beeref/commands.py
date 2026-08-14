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

from PyQt6 import QtCore, QtGui


class InsertItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, position=None, ignore_first_redo=False):
        super().__init__('Insert items')
        self.scene = scene
        self.items = items
        self.position = position
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        self.scene.deselect_all_items()
        if self.position:
            self.old_positions = []
            rect = self.scene.itemsBoundingRect(items=self.items)
            for item in self.items:
                self.old_positions.append(item.pos())
                item.setPos(item.pos() + self.position - rect.center())
        for item in self.items:
            self.scene.addItem(item)
            item.setSelected(True)
            item.bring_to_front()

    def undo(self):
        self.scene.deselect_all_items()
        for item in self.items:
            self.scene.removeItem(item)
        if self.position:
            for item, pos in zip(self.items, self.old_positions):
                item.setPos(pos)


class DeleteItems(QtGui.QUndoCommand):
    def __init__(self, scene, items):
        super().__init__('Delete items')
        self.scene = scene
        self.items = items

    def redo(self):
        for item in self.items:
            self.scene.removeItem(item)

    def undo(self):
        self.scene.deselect_all_items()
        for item in self.items:
            item.setSelected(True)
            self.scene.addItem(item)


class MoveItemsBy(QtGui.QUndoCommand):

    def __init__(self, items, delta, ignore_first_redo=False):
        super().__init__('Move items')
        self.items = items
        self.delta = delta
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.moveBy(self.delta.x(), self.delta.y())

    def undo(self):
        for item in self.items:
            item.moveBy(-self.delta.x(), -self.delta.y())


class ScaleItemsBy(QtGui.QUndoCommand):
    """Scale items by a given factor around the given anchor."""

    def __init__(self, items, factor, anchor, ignore_first_redo=False):
        super().__init__('Scale items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.factor = factor
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setScale(item.scale() * self.factor,
                          item.mapFromScene(self.anchor))

    def undo(self):
        for item in self.items:
            item.setScale(item.scale() / self.factor,
                          item.mapFromScene(self.anchor))


class RotateItemsBy(QtGui.QUndoCommand):
    """Rotate items by a given delta around the given anchor."""

    def __init__(self, items, delta, anchor, ignore_first_redo=False):
        super().__init__('Rotate items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.delta = delta
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setRotation(
                item.rotation() + self.delta * item.flip(),
                item.mapFromScene(self.anchor))

    def undo(self):
        for item in self.items:
            item.setRotation(item.rotation() - self.delta * item.flip(),
                             item.mapFromScene(self.anchor))


class NormalizeItems(QtGui.QUndoCommand):

    def __init__(self, items, scale_factors):
        super().__init__('Normalize items')
        self.items = items
        self.scale_factors = scale_factors

    def redo(self):
        self.old_scale_factors = []
        for item, factor in zip(self.items, self.scale_factors):
            self.old_scale_factors.append(item.scale())
            item.setScale(item.scale() * factor, item.center)

    def undo(self):
        for item, factor in zip(self.items, self.old_scale_factors):
            item.setScale(factor, item.center)


class FlipItems(QtGui.QUndoCommand):

    def __init__(self, items, anchor, vertical):
        super().__init__('Flip items')
        self.items = items
        self.anchor = anchor
        self.vertical = vertical

    def redo(self):
        for item in self.items:
            item.do_flip(self.vertical, item.mapFromScene(self.anchor))

    def undo(self):
        self.redo()


class ResetScale(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Scale')
        self.items = items

    def redo(self):
        self.old_scale_factors = []
        for item in self.items:
            self.old_scale_factors.append(item.scale())
            item.setScale(1, anchor=item.center)

    def undo(self):
        for item, scale_factor in zip(self.items, self.old_scale_factors):
            item.setScale(scale_factor, anchor=item.center)


class ResetRotation(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Rotation')
        self.items = items

    def redo(self):
        self.old_rotations = []
        for item in self.items:
            self.old_rotations.append(item.rotation())
            item.setRotation(0, anchor=item.center)

    def undo(self):
        for item, rotation in zip(self.items, self.old_rotations):
            item.setRotation(rotation, anchor=item.center)


class ResetFlip(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Flip')
        self.items = items

    def redo(self):
        self.old_flips = []
        for item in self.items:
            self.old_flips.append(item.flip())
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, flip in zip(self.items, self.old_flips):
            if flip == -1:
                item.do_flip(anchor=item.center)


class ResetCrop(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Crop')
        self.items = [item for item in items if item.is_image]

    def redo(self):
        self.old_crops = []
        for item in self.items:
            self.old_crops.append(item.crop)
            item.reset_crop()

    def undo(self):
        for item, crop in zip(self.items, self.old_crops):
            item.crop = crop


class ResetTransforms(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset All Transformations')
        self.items = items

    def redo(self):
        self.old_values = []
        for item in self.items:
            values = {
                'scale': item.scale(),
                'rotation': item.rotation(),
                'flip': item.flip(),
            }
            if item.is_image:
                values['crop'] = item.crop
                item.reset_crop()
            self.old_values.append(values)

            item.setScale(1, anchor=item.center)
            item.setRotation(0, anchor=item.center)
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, old in zip(self.items, self.old_values):
            item.setScale(old['scale'], anchor=item.center)
            item.setRotation(old['rotation'], anchor=item.center)
            if old['flip'] == -1:
                item.do_flip(anchor=item.center)
            if item.is_image:
                item.crop = old['crop']


class ArrangeItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, positions):
        super().__init__('Arrange items')
        self.scene = scene
        self.items = items
        self.positions = positions

    def redo(self):
        self.old_positions = []
        for item, pos in zip(self.items, self.positions):
            self.old_positions.append(item.pos())
            orig_topleft = item.mapToScene(QtCore.QPointF(0, 0))
            rect_topleft = self.scene.itemsBoundingRect(
                items=[item]).topLeft()
            item.setPos(pos + orig_topleft - rect_topleft)

    def undo(self):
        for item, pos in zip(self.items, self.old_positions):
            item.setPos(pos)


class CropItem(QtGui.QUndoCommand):
    def __init__(self, item, crop):
        super().__init__('Crop item')
        self.item = item
        self.crop = crop

    def redo(self):
        self.old_crop = self.item.crop
        self.item.crop = self.crop

    def undo(self):
        self.item.crop = self.old_crop


class GroupItems(QtGui.QUndoCommand):
    """Put the given items into a new group."""

    def __init__(self, scene, items, group):
        super().__init__('Group items')
        self.scene = scene
        self.items = list(items)
        self.group = group
        # Positions are relative to the parent, so they need restoring
        # when the items are taken out of the group again
        self.old_parents = [item.parentItem() for item in self.items]
        self.old_positions = [item.pos() for item in self.items]

        # Grouping items that are already in a group creates a group
        # inside that one, rather than pulling them out of it
        parents = set(self.old_parents)
        parent = parents.pop() if len(parents) == 1 else None
        self.parent_group = (
            parent if getattr(parent, 'TYPE', None) == 'group' else None)

    def restore_parent_state(self):
        """Put the surrounding group back the way it was."""

        if self.parent_group is None:
            self.scene.deselect_all_items()
            return
        self.scene.refit_group(self.parent_group)
        self.parent_group.set_children_interactive(
            self.parent_group is self.scene.active_group)
        # Not deselect_all_items(), which would close the parent group
        self.scene.clearSelection()

    def redo(self):
        if self.parent_group is None:
            self.scene.addItem(self.group)
        else:
            self.group.setParentItem(self.parent_group)
        self.group.setPos(0, 0)
        self.group.setZValue(
            min(item.zValue() for item in self.items) - self.scene.Z_STEP)
        for item in self.items:
            # Keep the items where they appear on screen, whatever the
            # surrounding group is doing
            scene_pos = item.scenePos()
            item.setParentItem(self.group)
            item.setPos(self.group.mapFromScene(scene_pos))
        self.group.fit_to_children()
        self.group.set_children_interactive(False)
        self.restore_parent_state()
        self.group.setSelected(True)

    def undo(self):
        self.group.set_children_interactive(True)
        for item, parent, pos in zip(
                self.items, self.old_parents, self.old_positions):
            item.setParentItem(parent)
            if item.scene() is None:
                self.scene.addItem(item)
            item.setPos(pos)
        if self.group.scene() is not None:
            self.group.setParentItem(None)
            self.scene.removeItem(self.group)
        self.restore_parent_state()
        for item in self.items:
            item.setSelected(True)


class UngroupItems(QtGui.QUndoCommand):
    """Dissolve the given groups, keeping their items."""

    def __init__(self, scene, groups):
        super().__init__('Ungroup items')
        self.scene = scene
        self.groups = list(groups)
        self.children = [group.bee_children() for group in self.groups]
        self.positions = [[item.pos() for item in children]
                          for children in self.children]

    def redo(self):
        self.scene.deselect_all_items()
        for group, children in zip(self.groups, self.children):
            group.set_children_interactive(True)
            for item in children:
                # Keep the item where it appears on screen
                scene_pos = item.scenePos()
                item.setParentItem(group.parentItem())
                if item.parentItem() is None:
                    self.scene.addItem(item)
                    item.setPos(scene_pos)
                item.setSelected(True)
            self.scene.removeItem(group)

    def undo(self):
        for group, children, positions in zip(
                self.groups, self.children, self.positions):
            self.scene.addItem(group)
            for item, pos in zip(children, positions):
                item.setParentItem(group)
                item.setPos(pos)
            group.fit_to_children()
            group.set_children_interactive(False)
        self.scene.deselect_all_items()
        for group in self.groups:
            group.setSelected(True)


class RenameItem(QtGui.QUndoCommand):
    """Rename an item from the layers panel."""

    def __init__(self, item, name):
        super().__init__('Rename item')
        self.item = item
        self.name = name or None
        self.old_name = item.name

    def set_name(self, name):
        self.item.name = name
        if hasattr(self.item, 'touch'):
            self.item.touch()

    def redo(self):
        self.set_name(self.name)

    def undo(self):
        self.set_name(self.old_name)


class ReorderItems(QtGui.QUndoCommand):
    """Set new z values, for reordering from the layers panel."""

    def __init__(self, items, z_values):
        super().__init__('Reorder items')
        self.items = list(items)
        self.z_values = list(z_values)
        self.old_z_values = [item.zValue() for item in self.items]

    def redo(self):
        for item, z in zip(self.items, self.z_values):
            item.setZValue(z)

    def undo(self):
        for item, z in zip(self.items, self.old_z_values):
            item.setZValue(z)


class MoveToGroup(QtGui.QUndoCommand):
    """Move items into a group, or out of their current one.

    This is what happens when items are dragged onto a group's box, or
    dragged out of it. ``group`` of ``None`` means "not in any group".
    """

    def __init__(self, scene, items, group):
        super().__init__('Move items to group')
        self.scene = scene
        self.items = list(items)
        self.group = group
        self.old_parents = [item.parentItem() for item in self.items]
        self.old_positions = [item.pos() for item in self.items]

    def reparent(self, item, group):
        """Re-parent the item, keeping it where it appears on screen."""

        scene_pos = item.scenePos()
        item.setParentItem(group)
        if group is None:
            if item.scene() is None:
                self.scene.addItem(item)
            item.setPos(scene_pos)
        else:
            item.setPos(group.mapFromScene(scene_pos))

    def refit(self, groups):
        for group in groups:
            if group is not None and group.scene() is not None:
                self.scene.refit_group(group)
                group.touch()
                if group is not self.scene.active_group:
                    group.set_children_interactive(False)

    def redo(self):
        for item in self.items:
            self.reparent(item, self.group)
        self.refit(set(self.old_parents) | {self.group})
        if self.group is not None:
            self.scene.clearSelection()
            self.group.setSelected(True)

    def undo(self):
        for item, parent, pos in zip(
                self.items, self.old_parents, self.old_positions):
            self.reparent(item, parent)
            item.setPos(pos)
        self.refit(set(self.old_parents) | {self.group})


class ChangeGroupBoxColor(QtGui.QUndoCommand):
    """Change the colour of the box behind grouped items."""

    def __init__(self, groups, color):
        super().__init__('Change group colour')
        self.groups = list(groups)
        self.color = color
        self.old_colors = [group.box_color for group in self.groups]

    def redo(self):
        for group in self.groups:
            group.box_color = self.color
            group.touch()

    def undo(self):
        for group, color in zip(self.groups, self.old_colors):
            group.box_color = color
            group.touch()


class ChangeText(QtGui.QUndoCommand):
    """Change the contents of a text item.

    Texts are handled as html so that formatting is preserved.
    """

    def __init__(self, item, new_text, old_text):
        super().__init__('Change text')
        self.item = item
        self.new_text = new_text
        self.old_text = old_text

    def redo(self):
        self.item.setHtml(self.new_text)

    def undo(self):
        self.item.setHtml(self.old_text)


class ChangeTextFormat(QtGui.QUndoCommand):
    """Change the formatting of text items.

    Since Qt's char formats are applied to the document directly, we
    store the whole html of each item before and after the change.
    """

    def __init__(self, items, new_htmls, old_htmls):
        super().__init__('Change text format')
        self.items = list(items)
        self.new_htmls = new_htmls
        self.old_htmls = old_htmls

    def redo(self):
        for item, html in zip(self.items, self.new_htmls):
            item.setHtml(html)

    def undo(self):
        for item, html in zip(self.items, self.old_htmls):
            item.setHtml(html)


class ChangeTextBoxColor(QtGui.QUndoCommand):
    """Change the colour of the box drawn behind text items."""

    def __init__(self, items, color):
        super().__init__('Change text box colour')
        self.items = list(items)
        self.color = color
        self.old_colors = [item.box_color for item in self.items]

    def set_color(self, item, color):
        item.box_color = color
        # The text colour comes from the box, so it changes along with it
        item.apply_text_font()

    def redo(self):
        for item in self.items:
            self.set_color(item, self.color)

    def undo(self):
        for item, color in zip(self.items, self.old_colors):
            self.set_color(item, color)


class ChangeOpacity(QtGui.QUndoCommand):
    """Change opacity on images."""

    def __init__(self, items, opacity, ignore_first_redo=False):
        super().__init__('Change Opacity')
        self.ignore_first_redo = ignore_first_redo
        self.items = list(filter(lambda item: item.is_image, items))
        self.opacity = opacity
        self.old_opacities = [item.opacity() for item in items]

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        for item in self.items:
            item.setOpacity(self.opacity)

    def undo(self):
        for item, opacity in zip(self.items, self.old_opacities):
            item.setOpacity(opacity)


class ToggleGrayscale(QtGui.QUndoCommand):
    """Toggle grayscale mode on images."""

    def __init__(self, items, grayscale):
        super().__init__('Toggle Grayscale')
        self.items = list(filter(lambda item: item.is_image, items))
        self.grayscale = grayscale
        self.old_grayscales = [item.grayscale for item in items]

    def redo(self):
        for item in self.items:
            item.grayscale = self.grayscale

    def undo(self):
        for item, grayscale in zip(self.items, self.old_grayscales):
            item.grayscale = grayscale
