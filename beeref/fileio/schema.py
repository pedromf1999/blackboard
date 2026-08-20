USER_VERSION = 2
APPLICATION_ID = 2060242126


SCHEMA = [
    """
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        x REAL DEFAULT 0,
        y REAL DEFAULT 0,
        z REAL DEFAULT 0,
        scale REAL DEFAULT 1,
        rotation REAL DEFAULT 0,
        flip INTEGER DEFAULT 1,
        data JSON
    )
    """,
    """
    CREATE TABLE sqlar (
        name TEXT PRIMARY KEY,
        item_id INTEGER NOT NULL UNIQUE,
        mode INT,
        mtime INT default current_timestamp,
        sz INT,
        data BLOB,
        FOREIGN KEY (item_id)
          REFERENCES items (id)
             ON DELETE CASCADE
             ON UPDATE NO ACTION
    )
    """,
]


# Records which version of Blackboard last wrote a file. Created on demand
# by every save rather than through a migration, and deliberately not part
# of SCHEMA: SQLite ignores tables it is not asked about, so a version that
# knows nothing about this table still opens the file normally.
META_TABLE = """
    CREATE TABLE IF NOT EXISTS blackboard_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
"""

# Keys used in the table above
META_VERSION_KEY = 'saved_by_version'
# A picture of the board as it was last looked at, base64 encoded so
# that it fits a text column and the table needs no change
META_THUMBNAIL_KEY = 'thumbnail'


MIGRATIONS = {
    2: [
        "ALTER TABLE items ADD COLUMN data JSON",
        "UPDATE items SET data = json_object('filename', filename)",
    ],
}
