# BV Ref — personal fork of BeeRef

## What this is

This repo is a fork of [BeeRef](https://github.com/rbreu/beeref) (reference image
viewer, Python + PyQt6, GPL-3), being customised for personal use under the name
**BV Ref**. Upstream version at fork point: `0.3.4.dev0` (branch `main`, after the
v0.3.3 release).

The owner is a product/industrial designer, not a professional Python developer.
Explain what you are changing and why in plain terms, and prefer clear code over
clever code. Assume the app itself is the test: after each change it must still
launch and behave normally.

## Environment

- Windows, PowerShell.
- Python 3.11 in a virtualenv at `.venv` (the system Python is 3.14, which BeeRef
  does **not** support — never install into it).
- Already installed editable: `pip install -e .`
- Activate with `.venv\Scripts\activate`, then run the app with `beeref`.
  The terminal stays busy while the app runs; errors and log output appear there.
- Repo path contains spaces (`...\Desktop\BV Ref\beeref`). If PyInstaller ever
  misbehaves, that is the first suspect.

## Git

- Work happens on the branch **`bvref`**. It is already created and checked out.
  `main` holds the untouched upstream code — do not commit to it.
- Commit after each feature that works, with a short descriptive message.
  Do not batch several unrelated features into one commit.
- If a change breaks the app and cannot be fixed quickly, revert rather than
  layering fixes on top.

## Codebase map

- `beeref/__main__.py` — application entry point, main window, menu bar assembly.
- `beeref/view.py` — `BeeGraphicsView`: zoom, panning, mouse/keyboard handling.
- `beeref/scene.py` — `BeeGraphicsScene`: the canvas, selection, z-ordering.
- `beeref/items.py` — item classes (`BeePixmapItem` for images, the text item),
  including transform handles, crop, opacity, grayscale.
- `beeref/actions/` — declarative definitions of menu entries, shortcuts and
  their callbacks. Most new commands are registered here.
- `beeref/fileio/` — reading and writing `.bee` files. These are SQLite
  databases; images live in an `sqlar` table, item properties in JSON.
- `beeref/config/` — settings system and the settings dialog.
- `beeref/assets/` — icons and images.
- `BeeRef.spec` — PyInstaller build spec (executable name and icon).

Checks available: `pytest --cov .` for tests, `flake8 .` for style. Run them
before committing; existing tests must keep passing.

## Planned features, in intended order

Do these one at a time. Confirm each works and is committed before starting
the next. Ask before making changes that go beyond the feature at hand.

### 1. Rename to BV Ref
Application name, organisation name, window title, about box, icon, and the
PyInstaller spec. Renaming the organisation/app also moves the settings folder,
which is desirable: it keeps this fork's config separate from the stock BeeRef
install that is still in use.

### 2. Background colour setting
A configurable canvas background colour, exposed in the existing settings
dialog alongside the other appearance options.

### 3. Zoom-aware background grid
A guide grid drawn behind the items, via `drawBackground()` on the scene.
Spacing should adapt to the zoom level (e.g. step through 10 / 50 / 100 px) so
the grid never becomes a dense mess or disappears. Needs a toggle, and ideally
configurable colour and spacing.

### 4. Text search with F3
Search across all text items in the scene. Matches should be selected and the
view centred on them, with F3 cycling through results. Existing keyboard
shortcut configuration must be respected — do not hardcode past the settings
system if the project has a mechanism for it.

### 5. Coloured box behind text
A per-item background/fill colour for text items, with a UI to pick it. This is
the first feature that stores a new property in the `.bee` file — see the file
format warning below.

### 6. Clickable web links in text
URLs inside text items should open in the system browser on **Ctrl + left
click**. Plain URL detection is enough; opening should go through
`QDesktopServices.openUrl`. Must not interfere with normal click-to-select or
with text edit mode.

### 7. Text highlighting
**Open question — ask before implementing.** If highlighting applies to a whole
text item, it is the same mechanism as feature 5. If it must apply to selected
words within a note, the text items have to move from plain text to rich text,
which changes how text is stored in the `.bee` file and requires formatting UI.
Clarify which is wanted, and state the cost of the rich-text version.

### 8. Grouping with Ctrl+G
BeeRef has no concept of groups. This touches selection, the custom transform
logic (scaling/rotating/flipping is handled by BeeRef itself, not delegated to
Qt), undo/redo, copy/paste, delete, and the file format. Plan it explicitly
before writing code, and present the plan first.

### 9. Layers / hierarchy panel with Ctrl+J
A dockable side panel listing scene items in stacking order, with drag-and-drop
reordering that writes back to z-values, kept in sync with canvas selection.
Groups must appear as nodes in this tree, so it depends on feature 8. Items
currently have no name property — one will likely need to be added.

## Constraints

- **File format.** Once new item properties are stored, `.bee` files written by
  this fork may not open correctly in stock BeeRef. Prefer additive changes that
  degrade gracefully (unknown keys ignored on load, sensible defaults on save).
  Warn explicitly whenever a change affects on-disk compatibility.
- **Licence.** GPL-3. Fine for private use; only redistribution triggers the
  obligation to publish modified source.
- Keep the diff against upstream as small and readable as reasonable, so that
  pulling future upstream releases stays possible.
- Do not add dependencies without asking first.
