"""Assistant retrieval: the question is turned into the right scope, records and exact stats."""
import pytest

from backend import sync
from backend.assistant import compact_record_for_llm
from backend.retrieval import retrieve


@pytest.fixture
def synced(fake):
    sync.sync_shotgrid(mode="full")
    return fake


def ids(result, entity_type="Task"):
    return {r["id"] for r in result["records"] if r["entity_type"] == entity_type}


def test_late_tasks_of_a_project(synced):
    result = retrieve("Quelles tâches sont en retard sur Les Cocottes en Papier ?")
    assert ids(result) == {100}  # 102 is past due but finished
    assert result["stats"]["total"] == 1
    assert "Les Cocottes en Papier" in result["scope"]


def test_step_by_short_name_and_accents(synced):
    result = retrieve("taches comp du projet les cocottes en papier")
    assert ids(result) == {100, 102}
    assert result["stats"]["par_etape"] == {"Compositing": 2}


def test_person_by_first_name(synced):
    result = retrieve("Sur quoi travaille Marie ?")
    assert ids(result) == {100, 102}
    assert result["stats"]["par_personne"] == {"Marie Curie": 2}


def test_status_bucket(synced):
    result = retrieve("tâches en review")
    assert ids(result) == {103}


def test_blocked_tasks_name_their_blocker(synced):
    result = retrieve("quelles tâches sont bloquées ?")
    assert ids(result) == {100}
    blocked = next(r for r in result["records"] if r["id"] == 100)
    assert blocked["blocked_by"] == ["anim sh020 (wtg)"]


def test_sequence_scopes_shots(synced):
    result = retrieve("shots de la séquence SQ010")
    assert ids(result, "Shot") == {20, 21}
    assert result["stats"]["par_groupe"] == {"in_progress": 1, "done": 1}


def test_stats_are_exact_even_when_records_are_truncated(synced):
    result = retrieve("combien de tâches ?", limit=2)
    assert len([r for r in result["records"] if r["entity_type"] == "Task"]) == 2
    assert result["stats"]["total"] == 5


def test_project_snapshot(synced):
    result = retrieve("Où en est Les Cocottes en Papier ?")
    assert result["records"][0]["entity_type"] == "Project"
    assert result["stats"]["taches"]["total"] == 4
    assert result["stats"]["taches"]["en_retard"] == 1


def test_active_projects_question_lists_only_active_ones(synced):
    result = retrieve("Quels sont les projets actifs ?")
    assert ids(result, "Project") == {1}
    assert result["stats"]["actifs"] == 1 and result["stats"]["non_actifs"] == 1
    project = result["records"][0]
    assert (project["tasks_total"], project["tasks_late"]) == (4, 1)


def test_general_project_question_lists_all(synced):
    assert ids(retrieve("Liste des productions"), "Project") == {1, 2}


def test_open_tasks_and_per_production_stats(synced):
    result = retrieve("Qui a le plus de tâches ouvertes ?")
    assert result["stats"]["total"] == 4  # 100, 101, 103, 104 are not finished
    assert result["stats"]["par_personne"] == {"Marie Curie": 1}
    assert ids(result) == set()  # ranking questions are answered from stats only
    assert ids(retrieve("Quelles tâches sont ouvertes ?")) == {100, 101, 103, 104}
    late = retrieve("Quelle production a le plus de tâches en retard ?")
    assert late["stats"]["par_production"] == {"Les Cocottes en Papier": 1}


def test_free_text_uses_full_text_index(synced):
    result = retrieve("flou de mouvement")
    assert ids(result, "Note") == {50}


def test_note_lookup_by_id(synced):
    assert ids(retrieve("note #50"), "Note") == {50}


def test_compact_record_keeps_business_fields(synced):
    record = next(r for r in retrieve("tâches bloquées")["records"] if r["id"] == 100)
    compact = compact_record_for_llm(record, "Task")
    assert compact["name"] == "comp sh020"
    assert compact["step"] == "Compositing"
    assert compact["entity"] == "SH020"
    assert compact["assigned_to"] == ["Marie Curie"]
    assert compact["late"] is True
    assert compact["blocked_by"] == ["anim sh020 (wtg)"]


def test_step_name_shared_by_several_steps_matches_all(fake):
    from tests.conftest import link, task
    fake.data["Step"].append({"id": 32, "type": "Step", "code": "Compositing", "short_name": "Comp"})
    fake.data["Task"].append(task(106, "comp asset", step=link("Step", 32, "Compositing"), pid=2))
    sync.sync_shotgrid(mode="full")
    assert ids(retrieve("tâches de compositing")) == {100, 102, 106}


def test_type_with_keywords_searches_within_type(synced):
    result = retrieve("notes sur le flou")
    assert ids(result, "Note") == {50}
    assert "flou" in result["scope"]


def test_site_specific_statuses_are_bucketed(fake):
    fake.data["Task"][0]["sg_status_list"] = "intapp"  # task 100: internally approved -> done, not late
    sync.sync_shotgrid(mode="full")
    assert ids(retrieve("tâches en retard")) == set()


def test_follow_up_inherits_only_the_subject(synced):
    from backend.assistant import QueryRequest, retrieval_question
    history = [{"role": "user", "content": "Quelles tâches sont en review sur Les Cocottes en Papier ?"},
               {"role": "assistant", "content": "1 tâche."}]
    q = retrieval_question(QueryRequest(question="et combien sont en retard ?", history=history))
    assert q == "et combien sont en retard ? Les Cocottes en Papier"
    result = retrieve(q)
    assert result["stats"]["total"] == 1 and "review" not in result["scope"]
    # A question that names its own subject is left untouched.
    own = retrieval_question(QueryRequest(question="Sur quoi travaille Marie ?", history=history))
    assert own == "Sur quoi travaille Marie ?"


def test_context_is_readable_french_text(synced):
    from backend.context import render_context
    from datetime import date
    text = render_context(retrieve("Quelles tâches sont en retard ?"), {"ip": {"name": "In Progress"}}, [],
                          today=date(2026, 11, 9))
    assert "CHIFFRES EXACTS" in text
    assert "Tâche « comp sh020 » — élément : SH020 — étape : Compositing — assignée à : Marie Curie" in text
    assert "statut : En cours (In Progress)" in text
    assert "EN RETARD de" in text
    ranking = render_context(retrieve("Quelle production a le plus de tâches en retard ?"), {}, [])
    assert "1) Les Cocottes en Papier : 1" in ranking
    assert "non listés" in ranking


@pytest.mark.parametrize("question", [
    "quelles sont la taches a faire deans le projet des cocottes en pappier",
    "taches de la production cocottes en papier",
    "où en est les cocottes en papiers ?",
])
def test_production_names_tolerate_typos_and_articles(synced, question):
    assert "Les Cocottes en Papier" in retrieve(question)["scope"]


def test_fuzzy_matching_does_not_invent_a_subject(synced):
    for question in ("Quels sont les projets actifs ?", "tâches en retard", "combien de notes ?"):
        assert "production «" not in retrieve(question)["scope"]
