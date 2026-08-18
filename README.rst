Blackboard
==========

A reference image board: drop in images, arrange them freely, annotate them,
and keep them in view while you work.

Blackboard is a personal fork of `BeeRef <https://github.com/rbreu/beeref>`_ by
Rebecca Breu, forked at version 0.3.4.dev0 and developed for its author's own
use. It is published because the licence invites it, not because it is a
supported product: there is no roadmap, no release schedule, and issues or pull
requests may go unanswered. If you want a maintained reference viewer, use
`BeeRef <https://beeref.org>`_ — it is excellent, and everything good here
started there.

What it adds to BeeRef
----------------------

- **Groups** — collect items into a box that moves, scales and rotates as one,
  with the box colour and rounding under your control
- **A layers panel** (``Ctrl+J``) listing everything in stacking order, with
  drag-and-drop reordering
- **Drawing tools** — freehand sketches, straight lines, curves and arrows
- **Rich text** — per-word colour, highlighting, clickable links, and text
  scaling by percentage rather than by point size
- **A background grid** that adapts its spacing to the zoom level
- **Text search** across the board with ``F3``
- **A configurable canvas colour**, and a dark interface throughout
- Boards are saved as ``.blk``; boards written by BeeRef still open

Installing on Windows
---------------------

Download the zip from the `latest release
<https://github.com/pedromf1999/blackboard/releases/latest>`_, extract all of
it, and run ``Install.cmd``. It copies the application to
``%LOCALAPPDATA%\Programs\Blackboard`` and associates ``.blk`` files with it.
No administrator rights are needed, and ``.bee`` files are left alone so an
existing BeeRef installation keeps its own.

Running from source
-------------------

Python 3.11 or 3.12 (``pyproject.toml`` requires ``>=3.9,<3.13``)::

    py -3.11 -m venv .venv
    .venv\Scripts\activate
    pip install -e . -r requirements\dev.txt
    python -m beeref

Checks are ``pytest tests`` and ``flake8 beeref tests``. Building a release is
``powershell -ExecutionPolicy Bypass -File tools\release.ps1``, which runs both,
builds the executable with PyInstaller and packages it for installation.

Licence and attribution
-----------------------

GPL-3, inherited from BeeRef. See ``LICENSE``.

BeeRef is copyright © 2021-2024 Rebecca Breu. The files in this repository that
came from BeeRef have been modified from their originals, starting in August
2026: the application was renamed, and the features listed above were added or
changed throughout ``beeref/``. The full record of what was changed and when is
the commit history of the ``bvref`` branch; the ``main`` branch holds the
unmodified upstream code it started from, so the two can be compared directly.

The name and logo are this fork's own. "BeeRef" is Rebecca Breu's project, and
this fork is not endorsed by or affiliated with it.
