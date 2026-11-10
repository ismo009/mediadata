"""Shared fixtures: a fake in-memory ShotGrid and a temporary SQLite database."""
import dataclasses
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("APP_SECRET", "test-secret")
os.environ["SYNC_INTERVAL_MINUTES"] = "0"

from backend import api, config, shotgrid  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeShotGrid:
    """Minimal stand-in for shotgun_api3.Shotgun covering the calls the app makes."""

    def __init__(self, data):
        self.data = data  # {entity_type: [records]}
        self.fail_on = None
        self.find_calls = []

    def schema_field_read(self, entity_type):
        fields = {"id"}
        for record in self.data.get(entity_type, []):
            fields |= set(record)
        return {f: {} for f in fields}

    def schema_entity_read(self):
        return {et: {"name": {"value": f"{et} label"}, "visible": {"value": True}} for et in self.data}

    def summarize(self, entity_type, filters, summary_fields):
        return {"summaries": {"id": len(self.data.get(entity_type, []))}}

    @staticmethod
    def _match(record, flt):
        field, op, value = flt
        current = record.get(field)
        if op == "greater_than":
            return current is not None and current > value
        if op == "in":
            return current in value
        if op == "is":
            return current == value
        if op == "ends_with":
            return isinstance(current, str) and current.endswith(value)
        raise NotImplementedError(op)

    def find(self, entity_type, filters, fields, order=None, limit=0, page=1):
        self.find_calls.append((entity_type, filters))
        if entity_type == self.fail_on:
            raise RuntimeError("boom")
        records = [r for r in self.data.get(entity_type, []) if all(self._match(r, f) for f in filters)]
        records.sort(key=lambda r: r["id"])
        if limit:
            records = records[(page - 1) * limit: page * limit]
        return [{k: v for k, v in r.items() if k in fields or k in ("id", "type")} for r in records]


def link(entity_type, entity_id, name=None):
    return {"type": entity_type, "id": entity_id, "name": name or f"{entity_type} {entity_id}"}


def project(pid, **extra):
    return {"id": pid, "type": "Project", "name": f"Projet {pid}", "sg_status": None,
            "archived": False, "is_template": False, "updated_at": T0, **extra}


def task(tid, content, *, step=None, shot=None, assignee=None, status="wtg", due=None, upstream=(), pid=1):
    return {
        "id": tid, "type": "Task", "content": content, "sg_status_list": status, "due_date": due,
        "project": link("Project", pid, f"Projet {pid}"),
        "step": step, "entity": shot, "task_assignees": [assignee] if assignee else [],
        "upstream_tasks": [link("Task", u) for u in upstream], "updated_at": T0,
    }


def human(uid, name, email, role, status="act", login=None):
    first, last = name.split(" ", 1)
    return {"id": uid, "type": "HumanUser", "name": name, "firstname": first, "lastname": last,
            "email": email, "login": login or email.split("@")[0], "sg_status_list": status,
            "permission_rule_set": {"type": "PermissionRuleSet", "id": 1, "name": role}, "updated_at": T0}


def sample_data():
    comp, anim = link("Step", 30, "Compositing"), link("Step", 31, "Animation")
    marie = link("HumanUser", 40, "Marie Curie")
    sh20, sh21 = link("Shot", 20, "SH020"), link("Shot", 21, "SH021")
    return {
        "Project": [project(1, name="Les Cocottes en Papier", users=[marie]),
                    project(2, name="Vieux Projet", archived=True, users=[link("HumanUser", 41, "Paul Martin")])],
        "Sequence": [{"id": 10, "type": "Sequence", "code": "SQ010", "project": link("Project", 1),
                      "updated_at": T0}],
        "Shot": [
            {"id": 20, "type": "Shot", "code": "SH020", "sg_status_list": "ip", "project": link("Project", 1),
             "sg_sequence": link("Sequence", 10, "SQ010"), "updated_at": T0},
            {"id": 21, "type": "Shot", "code": "SH021", "sg_status_list": "fin", "project": link("Project", 1),
             "sg_sequence": link("Sequence", 10, "SQ010"), "updated_at": T0},
        ],
        "Step": [
            {"id": 30, "type": "Step", "code": "Compositing", "short_name": "Comp", "updated_at": T0},
            {"id": 31, "type": "Step", "code": "Animation", "short_name": "Anim", "updated_at": T0},
        ],
        "HumanUser": [
            human(40, "Marie Curie", "marie@studio.test", "Admin"),
            human(41, "Paul Martin", "paul@studio.test", "Artist"),
            human(42, "Ancien Compte", "ancien@studio.test", "Artist", status="dis"),
            human(43, "Double Un", "double@studio.test", "Artist", login="double1"),
            human(44, "Double Deux", "double@studio.test", "Artist", login="double@studio.test"),
            human(45, "Triple Un", "triple@studio.test", "Artist", login="triple1"),
            human(46, "Triple Deux", "triple@studio.test", "Artist", login="triple2"),
        ],
        "Task": [
            task(100, "comp sh020", step=comp, shot=sh20, assignee=marie, status="ip", due="2020-01-01",
                 upstream=[101]),
            task(101, "anim sh020", step=anim, shot=sh20, status="wtg", due="2999-01-01"),
            task(102, "comp sh021", step=comp, shot=sh21, assignee=marie, status="fin", due="2020-01-01"),
            task(103, "anim sh021", step=anim, shot=sh21, status="rev"),
            task(104, "lighting", status="ip", pid=2),
        ],
        "Note": [{"id": 50, "type": "Note", "subject": "Retour SH020", "project": link("Project", 1),
                  "content": "Le flou de mouvement est trop fort", "note_links": [sh20], "updated_at": T0}],
        # Must never be synced:
        "AssetShotConnection": [{"id": 1, "type": "AssetShotConnection", "updated_at": T0}],
        "EventLogEntry": [],
        "Playlist": [],  # empty types are skipped
    }


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config, "settings",
        dataclasses.replace(
            config.settings,
            database_path=str(tmp_path / "test.sqlite3"),
            shotgrid_url="https://example.shotgrid.test",
            sync_entities="auto",
            sync_interval_minutes=0,
            app_base_url="http://localhost:8000",
            dev_login_as="",
            aps_client_id="",
            aps_client_secret="",
        ),
    )
    from backend import sync
    monkeypatch.setattr(sync, "SYNC_PAGE_SIZE", 2)  # force multi-page fetches
    client = FakeShotGrid(sample_data())
    monkeypatch.setattr(shotgrid, "shotgrid_client", lambda: client)
    monkeypatch.setattr(api, "_thumb_client", None)
    api._thumb_cache.clear()
    return client


def later(minutes=60):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def sign_in(http, monkeypatch, who: str) -> None:
    """Sign the TestClient in as a ShotGrid user (through the localhost dev login)."""
    http.post("/auth/logout")
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, dev_login_as=who))
    response = http.get("/auth/dev-login", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/", response.text


@pytest.fixture
def http(fake, monkeypatch):
    """TestClient on synced data, signed in as Marie (Admin: sees everything)."""
    from fastapi.testclient import TestClient

    from backend import main, sync
    sync.sync_shotgrid(mode="full")
    with TestClient(main.app) as client:
        sign_in(client, monkeypatch, "marie@studio.test")
        yield client
