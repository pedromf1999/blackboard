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

"""BeeRef's native file format is using SQLite. Embedded files are
stored in an sqlar table so that they can be extracted using sqlite's
archive command line option.

For more info, see:

https://www.sqlite.org/appfileformat.html
https://www.sqlite.org/sqlar.html
"""

import json
import logging
import os
import pathlib
import shutil
import sqlite3
import tempfile

from PyQt6 import QtGui

from beeref import constants
from beeref.items import BeePixmapItem, BeeErrorItem
from .errors import BeeFileIOError, IMG_LOADING_ERROR_MSG
from .schema import (SCHEMA, USER_VERSION, MIGRATIONS, APPLICATION_ID,
                     META_TABLE, META_VERSION_KEY)


logger = logging.getLogger(__name__)


def is_bee_file(path):
    """Check whether the file at the given path is one of ours.

    Files saved by BeeRef count too, so older boards still open.
    """

    return os.path.splitext(path)[1].lower() in constants.FILE_EXTS


def version_as_numbers(version):
    """Turn a version like '3.10' into (3, 10) so it can be compared.

    Returns None for anything not purely numeric, so an unexpected
    version string is simply not compared rather than guessed at.
    """

    try:
        return tuple(int(part) for part in version.split('.'))
    except (AttributeError, ValueError):
        return None


def handle_sqlite_errors(func):
    def wrapper(self, *args, **kwargs):
        try:
            func(self, *args, **kwargs)
        except Exception as e:
            logger.exception(f'Error while reading/writing {self.filename}')
            try:
                # Try to roll back transaction if there is any
                if (hasattr(self, '_connection')
                        and self._connection.in_transaction):
                    self.ex('ROLLBACK')
                    logger.debug('Transaction rolled back')
            except sqlite3.Error:
                pass
            self._close_connection()
            if self.worker:
                self.worker.finished.emit(self.filename, [str(e)])
            else:
                raise BeeFileIOError(msg=str(e), filename=self.filename) from e

    return wrapper


class SQLiteIO:

    def __init__(self, filename, scene, create_new=False, readonly=False,
                 worker=None):
        self.scene = scene
        self.create_new = create_new
        self.filename = filename
        self.readonly = readonly
        self.worker = worker
        self.retry = False

    def __del__(self):
        self._close_connection()

    def _close_connection(self):
        if hasattr(self, '_connection'):
            self._connection.close()
            delattr(self, '_connection')
        if hasattr(self, '_cursor'):
            delattr(self, '_cursor')
        if hasattr(self, '_tmpdir'):
            self._tmpdir.cleanup()
            delattr(self, '_tmpdir')

    def _establish_connection(self):
        if (self.create_new
                and not self.readonly
                and os.path.exists(self.filename)):
            os.remove(self.filename)

        if self.create_new:
            self.scene.clear_save_ids()

        uri = pathlib.Path(self.filename).resolve().as_uri()
        if self.readonly:
            uri = f'{uri}?mode=rw'
        self._connection = sqlite3.connect(uri, uri=True)
        self._cursor = self.connection.cursor()
        if not self.create_new:
            try:
                self._migrate()
            except Exception:
                # Updating a file failed; try creating it from scratch instead
                logger.exception('Error migrating bee file')
                self.create_new = True
                self._establish_connection()

    def _migrate(self):
        """Migrate database if necessary."""

        version = self.fetchone('PRAGMA user_version')[0]
        logger.debug(f'Found bee file version: {version}')
        if version >= USER_VERSION:
            logger.debug('Version ok; no migrations necessary')
            return

        if self.readonly:
            try:
                # See whether file is writable so we can migrate it directly
                self.ex('PRAGMA application_id=%s' % APPLICATION_ID)
            except sqlite3.Error:
                logger.debug('File not writable; use temporary copy instead')
                self._connection.close()
                self._tmpdir = tempfile.TemporaryDirectory(
                    prefix=constants.APPNAME)
                tmpname = os.path.join(
                    self._tmpdir.name, f'mig{constants.FILE_EXT}')
                shutil.copyfile(self.filename, tmpname)
                self._connection = sqlite3.connect(tmpname)
                self._cursor = self.connection.cursor()

        self.ex('BEGIN TRANSACTION')
        for i in range(version, USER_VERSION):
            logger.debug(f'Migrating from version {i} to {i + 1}...')
            for migration in MIGRATIONS[i + 1]:
                self.ex(migration)
        self.write_meta()
        self.connection.commit()
        logger.debug('Migration finished')

    @property
    def connection(self):
        if not hasattr(self, '_connection'):
            self._establish_connection()
        return self._connection

    @property
    def cursor(self):
        if not hasattr(self, '_cursor'):
            self._establish_connection()
        return self._cursor

    def ex(self, *args, **kwargs):
        return self.cursor.execute(*args, **kwargs)

    def exmany(self, *args, **kwargs):
        return self.cursor.executemany(*args, **kwargs)

    def fetchone(self, *args, **kwargs):
        self.ex(*args, **kwargs)
        return self.cursor.fetchone()

    def fetchall(self, *args, **kwargs):
        self.ex(*args, **kwargs)
        return self.cursor.fetchall()

    def write_meta(self):
        self.ex('PRAGMA application_id=%s' % APPLICATION_ID)
        self.ex('PRAGMA user_version=%s' % USER_VERSION)
        self.ex('PRAGMA foreign_keys=ON')

    def write_blackboard_meta(self):
        """Record which version of Blackboard is writing this file."""

        self.ex(META_TABLE)
        self.ex('INSERT OR REPLACE INTO blackboard_meta (key, value) '
                'VALUES (?, ?)', (META_VERSION_KEY, constants.VERSION))

    def saved_by_version(self):
        """The version that last wrote this file, or None.

        Files written by BeeRef, or by Blackboard before this was
        recorded, simply have no such entry.
        """

        table = self.fetchone(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='blackboard_meta'")
        if not table:
            return None
        row = self.fetchone(
            'SELECT value FROM blackboard_meta WHERE key=?',
            (META_VERSION_KEY,))
        return row[0] if row else None

    def warn_if_written_by_newer(self):
        """Log a warning if a later version of Blackboard wrote this file.

        Opening is still safe: item types this version does not know are
        shown as error items and left untouched when saving. The board
        will not look the way it did when it was saved, though, and that
        is worth saying out loud.
        """

        written_by = self.saved_by_version()
        if not written_by:
            return
        theirs = version_as_numbers(written_by)
        ours = version_as_numbers(constants.VERSION)
        if theirs and ours and theirs > ours:
            logger.warning(
                f'{self.filename} was saved by {constants.APPNAME} '
                f'{written_by}, which is newer than this version '
                f'({constants.VERSION}). Items this version does not know '
                'are shown as errors, and kept as they are when saving.')

    def create_schema_on_new(self):
        if self.create_new:
            self.write_meta()
            for schema in SCHEMA:
                self.ex(schema)

    IMAGE_ROWS = ('SELECT items.id, type, x, y, z, scale, rotation, flip, '
                  'items.data, sqlar.data '
                  'FROM sqlar JOIN items on sqlar.item_id = items.id')

    # Avoid OUTER JOIN for performance reasons; fetch the items
    # without image data separately instead.
    #
    # Everything without image data is fetched, whatever its type. This
    # used to list the known types instead, which lost items twice over
    # when a file written by a newer version was opened: the unknown
    # rows were never read, and the next save then deleted them as
    # items that no longer existed. Reading them means the scene turns
    # them into visible error items, and error items are preserved on
    # save. Adding a new item type no longer needs a change here.
    OTHER_ROWS = ('SELECT items.id, type, x, y, z, scale, rotation, flip, '
                  ' items.data, null as data '
                  'FROM items '
                  'WHERE items.id NOT IN (SELECT item_id FROM sqlar)')

    # How many items to hand over before pausing for the main thread.
    # The pause used to come after every single item, and a pause is far
    # more expensive than it looks: Windows rounds any sleep up to the
    # system timer granularity, so asking for ten milliseconds actually
    # costs about fifteen. On a five hundred image board that was the
    # best part of eight seconds spent doing nothing. Sleeping less
    # often is the only lever that works -- sleeping for less time does
    # nothing at all, since the granularity is the same either way.
    ITEMS_PER_PAUSE = 10

    def count_rows(self):
        """How many items the file holds, without reading any of them."""

        return self.fetchone(
            f'SELECT (SELECT COUNT(*) FROM ({self.IMAGE_ROWS})) '
            f'+ (SELECT COUNT(*) FROM ({self.OTHER_ROWS}))')[0]

    def iter_rows(self):
        """Yield the item rows one at a time.

        Reading them all up front meant every image in the file sat in
        memory at once, which on a multi-gigabyte board is enough to
        push the machine into swapping. Streaming costs no more time --
        the database reads the same bytes either way -- and never holds
        more than one image.

        Each query gets its own cursor, since the shared one would be
        rebound by the second query while the first is still being read.
        """

        for query in (self.IMAGE_ROWS, self.OTHER_ROWS):
            cursor = self.connection.cursor()
            cursor.execute(query)
            yield from cursor

    @handle_sqlite_errors
    def read(self):
        self.warn_if_written_by_newer()
        if self.worker:
            self.worker.begin_processing.emit(self.count_rows())

        for i, row in enumerate(self.iter_rows()):
            data = {
                'save_id': row[0],
                'type': row[1],
                'x': row[2],
                'y': row[3],
                'z': row[4],
                'scale': row[5],
                'rotation': row[6],
                'flip': row[7],
                'data': json.loads(row[8]),
            }

            if data['type'] == 'pixmap':
                if row[9] is None:
                    # An image item with no matching row in the archive.
                    # Only reachable now that items are fetched by absence
                    # of image data rather than by type; show it as an
                    # error instead of handing None to the image loader.
                    data['data']['text'] = (
                        'Image data is missing from this file.\n'
                        + IMG_LOADING_ERROR_MSG)
                    data['type'] = BeeErrorItem.TYPE
                else:
                    item = BeePixmapItem(QtGui.QImage())
                    item.pixmap_from_bytes(row[9])
                    if item.pixmap().isNull():
                        item = data['data']['text'] = (
                            f'Image could not be loaded: {item.filename}\n'
                            + IMG_LOADING_ERROR_MSG)
                        data['type'] = BeeErrorItem.TYPE
                    data['item'] = item

            self.scene.add_item_later(data)

            if self.worker:
                logger.trace(f'Emit progress: {i}')
                self.worker.progress.emit(i)
                if self.worker.canceled:
                    self.worker.finished.emit('', [])
                    return
                # Give main thread time to process items:
                if (i + 1) % self.ITEMS_PER_PAUSE == 0:
                    self.worker.msleep(10)
        if self.worker:
            self.worker.finished.emit(self.filename, [])

    @handle_sqlite_errors
    def write(self):
        if self.readonly:
            raise sqlite3.OperationalError(
                'Attempt to write to a readonly database')
        try:
            self.create_schema_on_new()
            self.write_data()
        except Exception:
            if self.retry:
                # Trying to recover failed
                raise
            else:
                self.retry = True
                # Try creating file from scratch and save again
                logger.exception(
                    f'Updating to existing file {self.filename} failed')
                self.create_new = True
                self._close_connection()
                self.write()

    def write_data(self):
        self.write_blackboard_meta()
        to_delete = {row[0] for row in self.fetchall('SELECT id from ITEMS')}
        # We don't want to touch existing items that are displayed as errors:
        keep = {item.original_save_id
                for item in self.scene.items_by_type(BeeErrorItem.TYPE)}
        logger.debug(f'Not saving error items: {keep}')
        to_delete = to_delete - keep

        to_save = list(self.scene.items_for_save())
        if self.worker:
            self.worker.begin_processing.emit(len(to_save))
        for i, item in enumerate(to_save):
            logger.debug(f'Saving {item} with id {item.save_id}')
            if item.save_id:
                self.update_item(item)
                to_delete.remove(item.save_id)
            else:
                self.insert_item(item)
            if self.worker:
                # One-based: emitting the index left the bar one item short
                # of full, so it sat at 99% for everything that happens
                # after this loop -- deleting, committing, vacuuming -- and
                # looked like a hang at the very end of every save.
                self.worker.progress.emit(i + 1)
                if self.worker.canceled:
                    break
        self.delete_items(to_delete)
        # Everything above is one transaction, committed here. Committing
        # per item makes saving a large file needlessly slow.
        self.connection.commit()

        # Deleted rows leave free space in the file, which SQLite hands
        # back out to whatever is written next. Returning it to the disk
        # means rewriting the file from scratch, and that was done here
        # on every save that removed anything: deleting one image from a
        # big board turned a save that took a moment into one that took
        # the better part of a minute. Compacting is its own command now.

        if self.worker:
            self.worker.finished.emit(self.filename, [])

    @handle_sqlite_errors
    def vacuum(self):
        """Rewrite the file without the space deleted items left behind.

        Slow -- the whole file is written again -- so this is asked for
        rather than done as part of saving.
        """

        if self.readonly:
            raise sqlite3.OperationalError(
                'Attempt to write to a readonly database')
        if self.worker:
            self.worker.begin_processing.emit(0)
        logger.debug(f'Compacting {self.filename}')
        self.ex('VACUUM')
        self.connection.commit()
        if self.worker:
            self.worker.finished.emit(self.filename, [])

    def delete_items(self, to_delete):
        to_delete = [(pk,) for pk in to_delete]
        self.exmany('DELETE FROM items WHERE id=?', to_delete)
        self.exmany('DELETE FROM sqlar WHERE item_id=?', to_delete)

    def insert_item(self, item):
        self.ex(
            'INSERT INTO items (type, x, y, z, scale, rotation, flip, '
            'data) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (item.TYPE, item.pos().x(), item.pos().y(), item.zValue(),
             item.scale(), item.rotation(), item.flip(),
             json.dumps(item.get_save_data())))
        item.save_id = self.cursor.lastrowid

        if hasattr(item, 'pixmap_to_bytes'):
            pixmap, imgformat = item.pixmap_to_bytes()
            name = item.get_filename_for_export(imgformat)
            self.ex(
                'INSERT INTO sqlar (item_id, name, mode, sz, data) '
                'VALUES (?, ?, ?, ?, ?)',
                (item.save_id, name, 0o644, len(pixmap), pixmap))

    def update_item(self, item):
        """Update item data.

        We only update the item data, not the pixmap data, as pixmap
        data never changes and is also time-consuming to save.
        """
        self.ex(
            'UPDATE items SET x=?, y=?, z=?, scale=?, rotation=?, flip=?, '
            'data=? '
            'WHERE id=?',
            (item.pos().x(), item.pos().y(), item.zValue(), item.scale(),
             item.rotation(), item.flip(),
             json.dumps(item.get_save_data()),
             item.save_id))
