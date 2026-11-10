"""Evaluate Lia end to end against the running server and the real local data.

Expected facts are computed from the local database at run time, so the checks stay
valid after every sync. Requires the API (default http://localhost:8000) and Ollama.

    python scripts/eval_assistant.py [--base http://localhost:8000] [--model llama3.1:latest] [--only 3,5]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.records import DONE_STATUSES, IN_PROGRESS_STATUSES, REVIEW_STATUSES  # noqa: E402

DONE_SQL = ",".join(f"'{s}'" for s in DONE_STATUSES)
REVIEW_SQL = ",".join(f"'{s}'" for s in REVIEW_STATUSES)
PROGRESS_SQL = ",".join(f"'{s}'" for s in IN_PROGRESS_STATUSES)
LATE = f"json_extract(data_json,'$.due_date') < date('now') AND LOWER(COALESCE(status,'')) NOT IN ({DONE_SQL})"
NOT_FOUND = r"(ne trouve pas|pas d'information|aucune information|pas disponible|n'est pas (présent|disponible|indiqu)|ne contiennent pas|ne figure pas|pas dans les données)"


def num_re(n: int) -> str:
    """Match a number written with or without a thousands separator (1096, 1 096, 1 096)."""
    s = str(n)
    if len(s) <= 3:
        return rf"(?<![\d]){s}(?![\d])"
    return rf"(?<![\d]){s[:-3]}[\s  .,]?{s[-3:]}(?![\d])"


def facts(db: sqlite3.Connection) -> dict:
    one = lambda sql, *p: db.execute(sql, p).fetchone()[0]  # noqa: E731
    projects = db.execute("SELECT entity_id, name, data_json FROM shotgrid_records WHERE entity_type='Project'").fetchall()
    active = [p for p in projects
              if not json.loads(p[2]).get("archived") and not json.loads(p[2]).get("is_template")
              and (json.loads(p[2]).get("sg_status") or "").lower() not in ("done", "lost", "bidding")]
    cocottes = next(p[0] for p in projects if p[1] == "Les Cocottes en Papier")
    late_by_project = db.execute(
        f"SELECT project_id, COUNT(*) n FROM shotgrid_records WHERE entity_type='Task' AND {LATE} "
        "GROUP BY project_id ORDER BY n DESC LIMIT 1"
    ).fetchone()
    worst_project = one("SELECT name FROM shotgrid_records WHERE entity_type='Project' AND entity_id=?", late_by_project[0])
    top_person = db.execute(
        f"""SELECT u.name, COUNT(*) n FROM shotgrid_records t
        JOIN shotgrid_links l ON l.src_type='Task' AND l.src_id=t.entity_id AND l.field='task_assignees'
        JOIN shotgrid_records u ON u.entity_type='HumanUser' AND u.entity_id=l.dst_id
        WHERE t.entity_type='Task' AND LOWER(COALESCE(t.status,'')) NOT IN ({DONE_SQL})
        GROUP BY u.entity_id ORDER BY n DESC LIMIT 1"""
    ).fetchone()
    first_late = db.execute(
        f"SELECT name FROM shotgrid_records WHERE entity_type='Task' AND project_id=? AND {LATE} "
        "ORDER BY json_extract(data_json,'$.due_date') LIMIT 1", (cocottes,)
    ).fetchone()[0]
    comp_in_progress = one(
        f"""SELECT COUNT(*) FROM shotgrid_records t
        JOIN shotgrid_links l ON l.src_type='Task' AND l.src_id=t.entity_id AND l.field='step'
        JOIN shotgrid_records s ON s.entity_type='Step' AND s.entity_id=l.dst_id AND s.name='Compositing'
        WHERE t.entity_type='Task' AND LOWER(t.status) IN ({PROGRESS_SQL})"""
    )
    maxime_open = one(
        f"""SELECT COUNT(*) FROM shotgrid_records t
        JOIN shotgrid_links l ON l.src_type='Task' AND l.src_id=t.entity_id AND l.field='task_assignees'
        JOIN shotgrid_records u ON u.entity_type='HumanUser' AND u.entity_id=l.dst_id AND u.name='Maxime Pierre'
        WHERE t.entity_type='Task' AND LOWER(COALESCE(t.status,'')) NOT IN ({DONE_SQL})"""
    )
    return {
        "comp_in_progress": comp_in_progress,
        "maxime_open": maxime_open,
        "active": len(active),
        "cocottes_tasks": one("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND project_id=?", cocottes),
        "cocottes_open": one(f"SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND project_id=? "
                             f"AND LOWER(COALESCE(status,'')) NOT IN ({DONE_SQL})", cocottes),
        "cocottes_late": one(f"SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND project_id=? AND {LATE}", cocottes),
        "cocottes_shots": one("SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Shot' AND project_id=?", cocottes),
        "first_late": first_late,
        "review_total": one(f"SELECT COUNT(*) FROM shotgrid_records WHERE entity_type='Task' AND LOWER(status) IN ({REVIEW_SQL})"),
        "worst_project": worst_project,
        "worst_project_late": late_by_project[1],
        "top_person": top_person[0],
        "top_person_open": top_person[1],
    }


def cases(f: dict) -> list[dict]:
    """(question, checks): every regex in `must` has to match, none in `must_not`."""
    return [
        {"q": "Quels sont les projets actifs ?", "must": [num_re(f["active"])], "must_not": [r"Jacques a dit\b(?!\.\.\.)"]},
        {"q": "Combien de tâches sont en retard sur Les Cocottes en Papier ?", "must": [num_re(f["cocottes_late"])]},
        {"q": "Quelles tâches sont en retard sur Les Cocottes en Papier ?", "must": [re.escape(f["first_late"])]},
        {"q": "Où en est Les Cocottes en Papier ?", "must": [num_re(f["cocottes_tasks"]), num_re(f["cocottes_late"])]},
        {"q": "Combien de plans compte Les Cocottes en Papier ?", "must": [num_re(f["cocottes_shots"])]},
        {"q": "Combien de tâches sont en review ?", "must": [num_re(f["review_total"])]},
        {"q": "Qui a le plus de tâches ouvertes ?", "must": [re.escape(f["top_person"]), num_re(f["top_person_open"])]},
        {"q": "Quelle production a le plus de tâches en retard ?", "must": [re.escape(f["worst_project"]), num_re(f["worst_project_late"])]},
        {"q": "Quel est le budget de Les Cocottes en Papier ?", "must": [NOT_FOUND], "must_not": [r"\d+\s?(€|euros|k€)"]},
        {"q": "Qui est le réalisateur de Les Cocottes en Papier ?", "must": [NOT_FOUND]},
        {"q": "Combien de tâches de compositing sont en cours ?", "must": [num_re(f["comp_in_progress"])]},
        {"q": "Combien de tâches non terminées a Maxime Pierre ?", "must": [num_re(f["maxime_open"])]},
        {"q": "quelles sont la taches a faire deans le projet des cocottes en pappier",
         "must": [num_re(f["cocottes_open"])], "must_not": [NOT_FOUND]},
        {"q": "et combien sont en retard ?",
         "history": [{"role": "user", "content": "Où en est Les Cocottes en Papier ?"},
                     {"role": "assistant", "content": f"Les Cocottes en Papier compte {f['cocottes_tasks']} tâches."}],
         "must": [num_re(f["cocottes_late"])]},
    ]


CLIENT: httpx.Client | None = None


def sign_in(base: str) -> httpx.Client:
    """The API requires a session: sign in through the localhost dev login (DEV_LOGIN_AS)."""
    client = httpx.Client(base_url=base, timeout=600)
    response = client.get("/auth/dev-login")
    if response.status_code == 404 or not client.get("/api/me").json().get("authenticated"):
        sys.exit("Connexion impossible : lancez le serveur avec DEV_LOGIN_AS=<login ShotGrid d'un Admin> "
                 "et APP_BASE_URL sur localhost.")
    return client


def ask(base: str, question: str, model: str | None, history: list | None = None) -> tuple[str, float]:
    started = time.time()
    answer = []
    with CLIENT.stream("POST", "/api/query/stream", json={"question": question, "history": history or [], "model": model}) as response:
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "token":
                answer.append(event["token"])
            elif event["type"] == "error":
                answer.append(f"[ERREUR] {event['error']}")
    return "".join(answer), time.time() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--model", default=None)
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    global CLIENT
    CLIENT = sign_in(args.base)
    db = sqlite3.connect(f"file:{ROOT / 'dashboard.sqlite3'}?mode=ro", uri=True)
    all_cases = cases(facts(db))
    selected = {int(i) for i in args.only.split(",") if i} or set(range(1, len(all_cases) + 1))
    passed, results = 0, []
    for i, case in enumerate(all_cases, 1):
        if i not in selected:
            continue
        answer, seconds = ask(args.base, case["q"], args.model, case.get("history"))
        failures = [f"manque {p}" for p in case["must"] if not re.search(p, answer, re.I)]
        failures += [f"interdit {p}" for p in case.get("must_not", []) if re.search(p, answer, re.I)]
        ok = not failures
        passed += ok
        results.append({"q": case["q"], "ok": ok, "failures": failures, "seconds": round(seconds, 1), "answer": answer})
        print(f"{'OK ' if ok else 'KO '} {i:2}. {case['q']}  ({seconds:.0f} s)")
        for failure in failures:
            print(f"        {failure}")
    print(f"\n{passed}/{len(results)} réussis")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
