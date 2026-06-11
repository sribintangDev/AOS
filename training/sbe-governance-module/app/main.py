from __future__ import annotations

import csv
import hmac
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import TrainingAnswer, TrainingQuestion, TrainingSession, TrainingSubmission
from .schemas import SubmissionCreate, TrainingSessionCreate
from .seed import (
    CASE_TAGS,
    DEFAULT_SESSION_ID,
    GOVERNANCE_RULES,
    PRESENTATION_SLIDES,
    ROUND_LABELS,
    TAG_GUIDANCE,
    TRAINING_NOTES,
    seed_default_session,
)
from .services.dashboard import generate_discussion_summary, session_dashboard
from .services.grading import answer_to_public_result, decode_json, grade_submission


BASE_DIR = Path(__file__).resolve().parent
FACILITATOR_PASSCODE = os.getenv("FACILITATOR_PASSCODE", "aos-demo-facilitator")
SECRET_KEY = os.getenv("AOS_TRAINING_SECRET", "change-this-secret-for-production")

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        seed_default_session(db)
    finally:
        db.close()
    yield


app = FastAPI(title="AOS SBE Governance Training", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["from_json"] = lambda value: json.loads(value or "[]")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def ensure_schema() -> None:
    migrations = {
        "training_questions": {
            "optional_tags": "TEXT",
            "round_number": "INTEGER NOT NULL DEFAULT 1",
            "round_label": "VARCHAR(120) NOT NULL DEFAULT 'Round 1: Live Core Round'",
        },
        "training_submissions": {
            "round_number": "INTEGER NOT NULL DEFAULT 1",
            "round_label": "VARCHAR(120) NOT NULL DEFAULT 'Round 1: Live Core Round'",
        },
        "training_answers": {
            "selected_cards": "TEXT",
        },
    }
    with engine.begin() as conn:
        for table_name, columns in migrations.items():
            existing = {
                row._mapping["name"]
                for row in conn.execute(text(f"PRAGMA table_info({table_name})"))
            }
            for column_name, ddl in columns.items():
                if column_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def facilitator_token() -> str:
    return hmac.new(SECRET_KEY.encode(), FACILITATOR_PASSCODE.encode(), "sha256").hexdigest()


def is_facilitator(request: Request) -> bool:
    token = request.cookies.get("aos_facilitator")
    return bool(token and hmac.compare_digest(token, facilitator_token()))


def require_facilitator(request: Request) -> None:
    if not is_facilitator(request):
        raise HTTPException(status_code=401, detail="Facilitator login required.")


def get_session_or_404(db: Session, session_id: str) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Training session not found.")
    return session


def public_question(question: TrainingQuestion) -> dict:
    return {
        "id": question.id,
        "question_type": question.question_type,
        "question_text": question.question_text,
        "options": decode_json(question.options, None),
        "scoring_weight": question.scoring_weight,
        "category": question.category,
        "round_number": question.round_number,
        "round_label": question.round_label,
    }


def public_session(session: TrainingSession) -> dict:
    return {
        "id": session.id,
        "title": session.title,
        "description": session.description,
        "status": session.status,
        "training_type": session.training_type,
        "questions": [public_question(question) for question in session.questions],
    }


async def create_and_grade_submission(
    db: Session,
    session: TrainingSession,
    payload: SubmissionCreate,
) -> TrainingSubmission:
    if not payload.participant_name.strip() or not payload.participant_role.strip():
        raise HTTPException(status_code=422, detail="Participant name and role / department are required.")

    round_number = normalized_round(payload.round_number)
    round_questions = [question for question in session.questions if question.round_number == round_number]
    if not round_questions:
        raise HTTPException(status_code=404, detail="Training round not found.")

    questions = {question.id: question for question in round_questions}
    provided = {answer.question_id: answer for answer in payload.answers}

    missing = [question.id for question in round_questions if question.id not in provided]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing answers for question ids: {missing}")

    submission = TrainingSubmission(
        session_id=session.id,
        participant_name=payload.participant_name.strip(),
        participant_role=payload.participant_role.strip(),
        participant_email=(payload.participant_email or None),
        round_number=round_number,
        round_label=ROUND_LABELS[round_number],
        status="submitted",
    )
    db.add(submission)
    db.flush()

    for question in round_questions:
        answer_input = provided[question.id]
        answer = TrainingAnswer(
            submission_id=submission.id,
            question_id=question.id,
            answer_text=(answer_input.answer_text or "").strip() if question.question_type == "open_ended" else None,
            selected_option=answer_input.selected_option if question.question_type == "mcq" else None,
            selected_tags=json.dumps(answer_input.selected_tags) if question.question_type == "case_tagging" else None,
            selected_cards=json.dumps(answer_input.selected_cards) if question.question_type == "open_ended" else None,
        )
        db.add(answer)

    db.commit()
    db.refresh(submission)
    return await grade_submission(db, submission)


def normalized_round(round_number: int | str | None) -> int:
    try:
        value = int(round_number or 1)
    except (TypeError, ValueError):
        value = 1
    return value if value in ROUND_LABELS else 1


def build_submission_payload_from_form(questions: list[TrainingQuestion], form) -> SubmissionCreate:
    answers = []
    for question in questions:
        key = f"q_{question.id}"
        if question.question_type == "mcq":
            answers.append(
                {
                    "question_id": question.id,
                    "selected_option": str(form.get(key, "")),
                }
            )
        elif question.question_type == "case_tagging":
            tags = list(form.getlist(key)) if hasattr(form, "getlist") else []
            answers.append(
                {
                    "question_id": question.id,
                    "selected_tags": tags,
                }
            )
        else:
            answers.append(
                {
                    "question_id": question.id,
                    "answer_text": str(form.get(f"{key}_remarks", "")),
                    "selected_cards": [
                        card_id
                        for card_id in str(form.get(f"{key}_cards", "")).split(",")
                        if card_id
                    ],
                }
            )

    return SubmissionCreate(
        participant_name=str(form.get("participant_name", "")).strip(),
        participant_role=str(form.get("participant_role", "")).strip(),
        participant_email=str(form.get("participant_email", "")).strip() or None,
        round_number=normalized_round(form.get("round_number", 1)),
        answers=answers,
    )


@app.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url=f"/training/{DEFAULT_SESSION_ID}", status_code=302)


@app.get("/training/{session_id}", response_class=HTMLResponse)
def participant_module(
    request: Request,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    round: int = 1,
) -> HTMLResponse:
    session = get_session_or_404(db, session_id)
    round_number = normalized_round(round)
    round_questions = [question for question in session.questions if question.round_number == round_number]
    grouped = {
        "mcq": [question for question in round_questions if question.question_type == "mcq"],
        "case_tagging": [question for question in round_questions if question.question_type == "case_tagging"],
        "open_ended": [question for question in round_questions if question.question_type == "open_ended"],
    }
    return templates.TemplateResponse(
        request,
        "participant.html",
        {
            "request": request,
            "session": public_session(session),
            "grouped": grouped,
            "notes": TRAINING_NOTES,
            "rules": GOVERNANCE_RULES,
            "case_tags": CASE_TAGS,
            "tag_guidance": TAG_GUIDANCE,
            "round_number": round_number,
            "round_label": ROUND_LABELS[round_number],
            "rounds": ROUND_LABELS,
        },
    )


@app.post("/training/{session_id}/submit", response_class=HTMLResponse)
async def participant_submit(
    request: Request,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    session = get_session_or_404(db, session_id)
    form = await request.form()
    round_number = normalized_round(form.get("round_number", 1))
    round_questions = [question for question in session.questions if question.round_number == round_number]
    payload = build_submission_payload_from_form(round_questions, form)
    submission = await create_and_grade_submission(db, session, payload)
    return templates.TemplateResponse(
        request,
        "feedback.html",
        {
            "request": request,
            "session": public_session(session),
            "submission": submission,
            "answers": [answer_to_public_result(answer) for answer in submission.answers],
            "case_tags": CASE_TAGS,
        },
    )


@app.get("/facilitator/login", response_class=HTMLResponse)
def facilitator_login_page(request: Request, session_id: str = DEFAULT_SESSION_ID) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "facilitator_login.html",
        {"request": request, "session_id": session_id, "error": None},
    )


@app.post("/facilitator/login", response_class=HTMLResponse)
def facilitator_login(
    request: Request,
    passcode: Annotated[str, Form()],
    session_id: Annotated[str, Form()] = DEFAULT_SESSION_ID,
) -> Response:
    if not hmac.compare_digest(passcode, FACILITATOR_PASSCODE):
        return templates.TemplateResponse(
            request,
            "facilitator_login.html",
            {"request": request, "session_id": session_id, "error": "Invalid facilitator passcode."},
            status_code=403,
        )
    response = RedirectResponse(url=f"/facilitator/{session_id}", status_code=302)
    response.set_cookie("aos_facilitator", facilitator_token(), httponly=True, samesite="lax")
    return response


@app.get("/facilitator/logout")
def facilitator_logout() -> RedirectResponse:
    response = RedirectResponse(url="/facilitator/login", status_code=302)
    response.delete_cookie("aos_facilitator")
    return response


@app.get("/facilitator/{session_id}", response_class=HTMLResponse)
def facilitator_dashboard(
    request: Request,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    round: str = "all",
) -> HTMLResponse:
    if not is_facilitator(request):
        return RedirectResponse(url=f"/facilitator/login?session_id={session_id}", status_code=302)
    session = get_session_or_404(db, session_id)
    round_number = None if round == "all" else normalized_round(round)
    dashboard = session_dashboard(db, session, round_number)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "session": session,
            "dashboard": dashboard,
            "summary": None,
            "rounds": ROUND_LABELS,
            "active_round": "all" if round_number is None else round_number,
        },
    )


@app.post("/facilitator/{session_id}/discussion-summary", response_class=HTMLResponse)
async def facilitator_discussion_summary(
    request: Request,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    round: str = "all",
) -> HTMLResponse:
    if not is_facilitator(request):
        return RedirectResponse(url=f"/facilitator/login?session_id={session_id}", status_code=302)
    session = get_session_or_404(db, session_id)
    round_number = None if round == "all" else normalized_round(round)
    dashboard = session_dashboard(db, session, round_number)
    summary = await generate_discussion_summary(db, session)
    dashboard["ai_discussion_summary"] = summary
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "session": session,
            "dashboard": dashboard,
            "summary": summary,
            "rounds": ROUND_LABELS,
            "active_round": "all" if round_number is None else round_number,
        },
    )


@app.get("/facilitator/{session_id}/slides", response_class=HTMLResponse)
def facilitator_slides(
    request: Request,
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    if not is_facilitator(request):
        return RedirectResponse(url=f"/facilitator/login?session_id={session_id}", status_code=302)
    session = get_session_or_404(db, session_id)
    return templates.TemplateResponse(
        request,
        "slides.html",
        {
            "request": request,
            "session": session,
            "slides": PRESENTATION_SLIDES,
            "tag_guidance": TAG_GUIDANCE,
        },
    )


@app.post("/api/training/sessions")
def api_create_session(
    payload: TrainingSessionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    require_facilitator(request)
    session = TrainingSession(**payload.model_dump(), status="active")
    db.add(session)
    db.commit()
    db.refresh(session)
    return public_session(session)


@app.get("/api/training/sessions/{session_id}")
def api_get_session(session_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    session = get_session_or_404(db, session_id)
    return public_session(session)


@app.post("/api/training/sessions/{session_id}/submissions")
async def api_submit(
    session_id: str,
    payload: SubmissionCreate,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    session = get_session_or_404(db, session_id)
    submission = await create_and_grade_submission(db, session, payload)
    return {
        "id": submission.id,
        "mcq_score": submission.mcq_score,
        "case_tagging_score": submission.case_tagging_score,
        "ai_open_ended_score": submission.ai_open_ended_score,
        "total_score": submission.total_score,
        "ai_feedback_summary": submission.ai_feedback_summary,
        "status": submission.status,
        "answers": [answer_to_public_result(answer) for answer in submission.answers],
    }


@app.post("/api/training/submissions/{submission_id}/grade")
async def api_grade_submission(
    submission_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    require_facilitator(request)
    submission = db.get(TrainingSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found.")
    submission = await grade_submission(db, submission)
    return {"id": submission.id, "status": submission.status, "total_score": submission.total_score}


@app.get("/api/training/sessions/{session_id}/dashboard")
def api_dashboard(
    session_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    round: str = "all",
) -> dict:
    require_facilitator(request)
    session = get_session_or_404(db, session_id)
    round_number = None if round == "all" else normalized_round(round)
    return session_dashboard(db, session, round_number)


@app.get("/api/training/sessions/{session_id}/export.json")
def api_export_json(
    session_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    require_facilitator(request)
    session = get_session_or_404(db, session_id)
    payload = {
        "session": {
            "id": session.id,
            "title": session.title,
            "description": session.description,
            "status": session.status,
        },
        "dashboard": session_dashboard(db, session),
        "submissions": [export_submission(submission) for submission in session.submissions],
    }
    return JSONResponse(payload)


@app.get("/api/training/sessions/{session_id}/export.csv")
def api_export_csv(
    session_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    require_facilitator(request)
    session = get_session_or_404(db, session_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "submission_id",
            "participant_name",
            "participant_role",
            "participant_email",
            "submitted_at",
            "round_number",
            "round_label",
            "status",
            "mcq_score",
            "case_tagging_score",
            "ai_open_ended_score",
            "total_score",
            "question_id",
            "question_type",
            "question_text",
            "options_or_cards",
            "selected_option",
            "selected_tags",
            "selected_cards",
            "remarks",
            "answer_score",
            "answer_feedback",
            "detected_gaps",
            "discussion_flag",
        ]
    )
    for submission in session.submissions:
        for answer in submission.answers:
            writer.writerow(
                [
                    submission.id,
                    submission.participant_name,
                    submission.participant_role,
                    submission.participant_email or "",
                    submission.submitted_at.isoformat(),
                    submission.round_number,
                    submission.round_label,
                    submission.status,
                    submission.mcq_score,
                    submission.case_tagging_score,
                    submission.ai_open_ended_score,
                    submission.total_score,
                    answer.question_id,
                    answer.question.question_type,
                    answer.question.question_text,
                    json.dumps(decode_json(answer.question.options, [])),
                    answer.selected_option or "",
                    json.dumps(decode_json(answer.selected_tags, [])),
                    json.dumps(decode_json(answer.selected_cards, [])),
                    answer.answer_text or "",
                    answer.ai_score if answer.ai_score is not None else "",
                    answer.ai_feedback or "",
                    json.dumps(decode_json(answer.detected_gaps, [])),
                    answer.discussion_flag,
                ]
            )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{session_id}-responses.csv"'},
    )


@app.get("/api/training/sessions/{session_id}/export.pdf")
def api_export_pdf(
    session_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    require_facilitator(request)
    session = get_session_or_404(db, session_id)
    dashboard = session_dashboard(db, session)
    pdf = build_pdf_summary(session, dashboard)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{session_id}-summary.pdf"'},
    )


@app.post("/api/training/sessions/{session_id}/discussion-summary")
async def api_discussion_summary(
    session_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    require_facilitator(request)
    session = get_session_or_404(db, session_id)
    return await generate_discussion_summary(db, session)


def export_submission(submission: TrainingSubmission) -> dict:
    return {
        "id": submission.id,
        "participant_name": submission.participant_name,
        "participant_role": submission.participant_role,
        "participant_email": submission.participant_email,
        "submitted_at": submission.submitted_at.isoformat(),
        "round_number": submission.round_number,
        "round_label": submission.round_label,
        "scores": {
            "mcq": submission.mcq_score,
            "case_tagging": submission.case_tagging_score,
            "ai_open_ended": submission.ai_open_ended_score,
            "total": submission.total_score,
        },
        "ai_feedback_summary": submission.ai_feedback_summary,
        "answers": [
            {
                "question_id": answer.question_id,
                "question_type": answer.question.question_type,
                "question_text": answer.question.question_text,
                "round_number": answer.question.round_number,
                "round_label": answer.question.round_label,
                "options_or_cards": decode_json(answer.question.options, []),
                "answer_text": answer.answer_text,
                "selected_option": answer.selected_option,
                "selected_tags": decode_json(answer.selected_tags, []),
                "selected_cards": decode_json(answer.selected_cards, []),
                "is_correct": answer.is_correct,
                "score": answer.ai_score,
                "feedback": answer.ai_feedback,
                "detected_gaps": decode_json(answer.detected_gaps, []),
                "discussion_flag": answer.discussion_flag,
            }
            for answer in submission.answers
        ],
    }


def build_pdf_summary(session: TrainingSession, dashboard: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"{session.title} Summary")
    styles = getSampleStyleSheet()
    story = [
        Paragraph(session.title, styles["Title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Dashboard Summary", styles["Heading2"]),
    ]
    metrics = [
        ["Total participants", dashboard["total_participants"]],
        ["Completion rate", f"{dashboard['completion_rate']}%"],
        ["Average MCQ score", f"{dashboard['average_mcq_score']}%"],
        ["Average case-tagging score", f"{dashboard['average_case_tagging_score']}%"],
        ["Average AI open-ended score", f"{dashboard['average_ai_open_ended_score']}%"],
    ]
    table = Table(metrics, colWidths=[220, 160])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([table, Spacer(1, 12)])

    if dashboard["most_commonly_missed_tags"]:
        story.append(Paragraph("Most Commonly Missed Tags", styles["Heading2"]))
        for item in dashboard["most_commonly_missed_tags"]:
            story.append(Paragraph(f"{item['tag']}: {item['count']}", styles["Normal"]))
        story.append(Spacer(1, 12))

    if dashboard["lowest_scoring_questions"]:
        story.append(Paragraph("Lowest Scoring Questions", styles["Heading2"]))
        for item in dashboard["lowest_scoring_questions"][:5]:
            story.append(
                Paragraph(
                    f"{item['average_score']}% - {item['question_text']}",
                    styles["Normal"],
                )
            )

    doc.build(story)
    return buffer.getvalue()
