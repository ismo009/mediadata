import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "dashboard.sqlite3"


def migrate(db_path: Path = DB_PATH):
    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Check existing columns in shotgrid_records
    cursor.execute("PRAGMA table_info(shotgrid_records)")
    columns = {row[1] for row in cursor.fetchall()}

    if "project_id" not in columns:
        print("Adding column project_id...")
        cursor.execute("ALTER TABLE shotgrid_records ADD COLUMN project_id INTEGER")
    if "status" not in columns:
        print("Adding column status...")
        cursor.execute("ALTER TABLE shotgrid_records ADD COLUMN status TEXT")

    # 2. Populate project_id and status from data_json
    print("Populating project_id and status from data_json...")
    cursor.execute("SELECT entity_type, entity_id, data_json FROM shotgrid_records")
    rows = cursor.fetchall()

    updates = []
    fts_rows = []

    for entity_type, entity_id, data_raw in rows:
        try:
            data = json.loads(data_raw)
        except Exception:
            continue

        name = data.get("name") or data.get("code") or data.get("cached_display_name")
        status = data.get("sg_status") or data.get("sg_status_list")

        project_id = None
        if entity_type == "Project":
            project_id = entity_id
        else:
            proj = data.get("project")
            if isinstance(proj, dict) and "id" in proj:
                project_id = proj["id"]

        updates.append((project_id, status, name, entity_type, entity_id))

        # Content for FTS5
        content_parts = []
        if data.get("subject"):
            content_parts.append(str(data["subject"]))
        if data.get("content"):
            content_parts.append(str(data["content"]))
        if data.get("sg_description"):
            content_parts.append(str(data["sg_description"]))
        if data.get("description"):
            content_parts.append(str(data["description"]))
        if data.get("code"):
            content_parts.append(str(data["code"]))

        fts_rows.append((
            entity_type,
            entity_id,
            project_id,
            name or "",
            " ".join(content_parts),
        ))

    cursor.executemany(
        """
        UPDATE shotgrid_records
        SET project_id = ?, status = ?, name = COALESCE(?, name)
        WHERE entity_type = ? AND entity_id = ?
        """,
        updates,
    )
    print(f"Updated {len(updates)} records with project_id and status.")

    # 3. Create indexes
    print("Creating indexes...")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_type_project ON shotgrid_records(entity_type, project_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_type_name ON shotgrid_records(entity_type, name COLLATE NOCASE)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_project ON shotgrid_records(project_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_status ON shotgrid_records(status)"
    )

    # 4. FTS5 Virtual Table
    print("Creating and populating FTS5 virtual table...")
    cursor.execute("DROP TABLE IF EXISTS shotgrid_fts")
    cursor.execute(
        """
        CREATE VIRTUAL TABLE shotgrid_fts USING fts5(
            entity_type,
            entity_id UNINDEXED,
            project_id UNINDEXED,
            name,
            content,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    cursor.executemany(
        """
        INSERT INTO shotgrid_fts (entity_type, entity_id, project_id, name, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        fts_rows,
    )

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()

