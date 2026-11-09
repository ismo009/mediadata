"""Bring an existing dashboard.sqlite3 up to the current schema and rebuild derived indexes.

The server does this automatically on first connection; this script is for doing it by
hand (e.g. after copying a database from another machine):

    python -m backend.migrate_db            # migrate if needed
    python -m backend.migrate_db --rebuild  # also recompute full-text index and links
"""
import sys

from backend.db import database, rebuild_derived


def main() -> None:
    connection = database()  # runs ensure_schema()
    try:
        if "--rebuild" in sys.argv:
            with connection:
                rebuild_derived(connection)
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        records = connection.execute("SELECT COUNT(*) FROM shotgrid_records").fetchone()[0]
        fts = connection.execute("SELECT COUNT(*) FROM shotgrid_fts").fetchone()[0]
        links = connection.execute("SELECT COUNT(*) FROM shotgrid_links").fetchone()[0]
        print(f"schema v{version}: {records} records, {fts} FTS rows, {links} links")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
