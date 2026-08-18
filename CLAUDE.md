# Blackboard — personal fork of BeeRef

## What this is

This repo is a fork of [BeeRef](https://github.com/rbreu/beeref) (reference image
viewer, Python + PyQt6, GPL-3), being customised for personal use under the name
**Blackboard**. Upstream version at fork point: `0.3.4.dev0` (branch `main`, after the
v0.3.3 release).

The owner is a product/industrial designer, not a professional Python developer.
Explain what you are changing and why in plain terms, and prefer clear code over
clever code. Assume the app itself is the test: after each change it must still
launch and behave normally.

## Environment

- Windows, PowerShell.
- Python 3.11 in a virtualenv at `.venv`. `pyproject.toml` requires
  `>=3.9,<3.13`, so the system Python (3.13 on this machine) will **not** work —
  never install into it. Rebuild the venv with `py -3.11 -m venv .venv`.
- Already installed editable: `pip install -e . -r requirements\dev.txt`
- Activate with `.venv\Scripts\activate`, then run the app with `beeref`, or
  `python -m beeref` if an Application Control policy blocks the venv's exe.
  The terminal stays busy while the app runs; errors and log output appear there.
- Repo path contains spaces (`...\Desktop\Blackboard\BV Ref\beeref`). If
  PyInstaller ever misbehaves, that is the first suspect.
- A venv copied from another machine does not work — `pyvenv.cfg` holds absolute
  paths to the interpreter it was built from. Rebuild it instead.

## Git

- Work happens on the branch **`bvref`**. It is already created and checked out.
  `main` holds the untouched upstream code — do not commit to it.
- Commit after each feature that works, with a short descriptive message.
  Do not batch several unrelated features into one commit.
- **Every commit raises `VERSION` by one**, in the same commit as the change
  itself. See "Versioning and releases" below.
- If a change breaks the app and cannot be fixed quickly, revert rather than
  layering fixes on top.

## Versioning and releases

The application is developed on one PC and used on another. That works only if
both machines can name which build they have, and if a board always opens in
the newest installed version.

**Version numbers.** `VERSION` in `beeref/constants.py` is the single source of
truth; `pyproject.toml` reads it from there via `[tool.setuptools.dynamic]`, so
the two can never drift. Blackboard numbers itself, starting at **3.6** —
BeeRef's `0.3.x` numbering is gone and upstream releases are not tracked. Raise
`VERSION` by one on every commit, so the number in Help → About identifies the
exact commit a build came from.

**Install location, and why it is fixed.** A `.blk` file records nothing about
which version wrote it, and Windows does not remember which program created a
file. Boards opening in an outdated version is always the same bug: two
executables, with the file association pointing at the one that never got
refreshed. So the association points at one fixed path

    %LOCALAPPDATA%\Programs\Blackboard\Blackboard.exe

and updating means replacing the file there. **Never point the association at
`dist\`** — `Blackboard.spec` puts the version in the built filename, so that
path changes with every release and would go stale immediately.

**Always show the build before publishing.** Once a change is committed, start
the application so the owner can look at it:

    .venv\Scripts\python.exe -m beeref

Running from source is instant and needs no build, so use it for this. Say which
version is running and what to look at, then wait. Publish only once the owner
has said so -- a published release is what the other computer installs, and
pulling one back is far more disruptive than checking first. Restart the
previewer after every new commit: an already-open window is running the older
code, which is a good way to have a fix judged as broken.

**Cutting a release.** Commit first (the script refuses a dirty tree, so the
version identifies exactly the released code), then:

    powershell -ExecutionPolicy Bypass -File tools\release.ps1

It checks style, runs the tests against the baseline, builds, packages
`dist\Blackboard-<version>.zip`, installs that same package locally, and tags
the commit `v<version>`. It deliberately stops there: publishing is a separate,
explicit step, so a build can never publish by accident.

    git push origin bvref --tags
    gh release create v<version> dist\Blackboard-<version>.zip --title "Blackboard <version>"

`origin` is the private repo `pedromf1999/blackboard`; `upstream` is BeeRef,
which cannot be pushed to. The release notes are the only place a change gets
described in plain language for the other computer, so say what changed and how
to install — not what the commits did.

The zip is the only file the other computer needs: it holds `Install.cmd` plus
`app\Blackboard.exe`, and `Install.cmd` does the copy and the association in
pure `cmd`/`reg` — no admin rights, no Python, no PowerShell policy to fight.
It deliberately leaves `.bee` alone so a stock BeeRef install keeps its own
files.

**Opening a board written by a newer version is safe.** `fileio/sql.py` fetches
items by absence of image data rather than by a list of known types, so an item
this version does not understand still loads — as a red error item, which the
save path then leaves untouched in the file. Every save also records the writing
version in a `blackboard_meta` table, and opening a file written by a later
version logs a warning. Do not reintroduce a type list in that query: listing
known types is what silently deleted groups and drawings twice before.

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
- `Blackboard.spec` — PyInstaller build spec (executable name and icon).

Checks available: `pytest tests` for tests, `flake8 beeref tests` for style. Run
them before committing; existing tests must keep passing.

Scope both commands explicitly. `setup.cfg` excludes only `squashfs-root`,
`build` and `dist`, so a bare `flake8 .` lints everything inside `.venv` and
buries real errors under thousands from third-party source.

Current baseline: **1377 passing, 9 failing**. The nine fail on unmodified
upstream code too — two in `tests/fileio/test_export_images_to_directory.py`
about a directory not being writeable, seven in `tests/test_view.py` about
window flags, move-window mouse handling and `\` vs `/` path separators. Treat
that as the pass mark; anything beyond those nine is a real regression.

## Planned features, in intended order

Do these one at a time. Confirm each works and is committed before starting
the next. Ask before making changes that go beyond the feature at hand.

### 1. Rename to Blackboard
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
**Done.** Resolved in favour of the rich-text version: text items store HTML
(`items.py` keeps an `html` key, `commands.ChangeText` handles undo/redo), so
highlighting applies to selected words within a note rather than the whole item.

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
