from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import normalize_database_url
from app.main import app, facilitator_token
from app.seed import DEFAULT_SESSION_ID


client = TestClient(app)


def test_postgres_database_url_uses_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@example.supabase.co:5432/postgres")
        == "postgresql+psycopg://user:pass@example.supabase.co:5432/postgres?sslmode=require"
    )
    assert (
        normalize_database_url("postgres://user:pass@example.supabase.co:5432/postgres")
        == "postgresql+psycopg://user:pass@example.supabase.co:5432/postgres?sslmode=require"
    )
    assert (
        normalize_database_url("postgresql://user:pass@example.supabase.co:5432/postgres?sslmode=verify-full")
        == "postgresql+psycopg://user:pass@example.supabase.co:5432/postgres?sslmode=verify-full"
    )


def test_public_session_hides_rubrics() -> None:
    with TestClient(app) as scoped:
        response = scoped.get(f"/api/training/sessions/{DEFAULT_SESSION_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["questions"]
    raw = response.text
    assert "hidden_rubric" not in raw
    assert "expected_answer" not in raw
    assert "correct_answer" not in raw
    assert "sample_remarks" not in raw


def test_submit_and_grade_central_response() -> None:
    with TestClient(app) as scoped:
        session = scoped.get(f"/api/training/sessions/{DEFAULT_SESSION_ID}").json()
        answers = []
        for question in session["questions"]:
            if question["question_type"] == "mcq":
                answers.append({"question_id": question["id"], "selected_option": question["options"][0]})
            elif question["question_type"] == "case_tagging":
                answers.append({"question_id": question["id"], "selected_tags": ["Academic", "Management"]})
            else:
                answers.append(
                    {
                        "question_id": question["id"],
                        "answer_text": (
                            "Acknowledge the concern, record the case, check policy, split authority between "
                            "Academic, Finance, CX/Admin and Management, avoid promises, contain urgent risk, "
                            "communicate clearly, and close with documentation."
                        ),
                    }
                )
        response = scoped.post(
            f"/api/training/sessions/{DEFAULT_SESSION_ID}/submissions",
            json={
                "participant_name": "Test Participant",
                "participant_role": "QA",
                "participant_email": "qa@example.com",
                "answers": answers,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "graded"
    assert 0 <= payload["total_score"] <= 100
    assert payload["ai_feedback_summary"]


def test_rounds_technical_tag_and_workflow_submission() -> None:
    with TestClient(app) as scoped:
        session = scoped.get(f"/api/training/sessions/{DEFAULT_SESSION_ID}").json()
        round_one = [question for question in session["questions"] if question["round_number"] == 1]
        round_two = [question for question in session["questions"] if question["round_number"] == 2]
        assert len(round_one) == 10
        assert round_two
        case_questions = [question for question in round_one if question["question_type"] == "case_tagging"]
        assert any("Technical / IT" in question["options"] for question in case_questions)

        answers = []
        for question in round_one:
            if question["question_type"] == "mcq":
                answers.append({"question_id": question["id"], "selected_option": question["options"][0]})
            elif question["question_type"] == "case_tagging":
                answers.append(
                    {
                        "question_id": question["id"],
                        "selected_tags": ["Academic / Principal", "Technical / IT", "Management"],
                    }
                )
            else:
                answers.append(
                    {
                        "question_id": question["id"],
                        "selected_cards": [card["id"] for card in question["options"][:5]],
                        "answer_text": "Urgent containment should happen first, but final decisions still follow authority, policy, Management approval where needed, parent communication, and records.",
                    }
                )
        response = scoped.post(
            f"/api/training/sessions/{DEFAULT_SESSION_ID}/submissions",
            json={
                "participant_name": "Round One Participant",
                "participant_role": "EXCO",
                "participant_email": "round@example.com",
                "round_number": 1,
                "answers": answers,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "graded"
    assert all(answer["round_number"] == 1 for answer in payload["answers"])
    assert any(answer["selected_cards"] for answer in payload["answers"] if answer["question_type"] == "open_ended")


def test_feedback_hides_samples_but_dashboard_has_facilitator_review() -> None:
    with TestClient(app) as scoped:
        feedback = scoped.get(f"/training/{DEFAULT_SESSION_ID}?round=1")
        assert feedback.status_code == 200
        assert "sample_remarks" not in feedback.text
        assert "Technical / IT" in feedback.text

        scoped.cookies.set("aos_facilitator", facilitator_token())
        dashboard = scoped.get(
            f"/api/training/sessions/{DEFAULT_SESSION_ID}/dashboard",
        )
        assert dashboard.status_code == 200
        payload = dashboard.json()
        assert payload["question_review"]
        assert any(item.get("sample_remarks") for item in payload["question_review"] if item["question_type"] == "open_ended")
