from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid4())


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="AOS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    facilitator_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    training_type: Mapped[str] = mapped_column(String(100), nullable=False, default="sbe_governance")

    questions: Mapped[list["TrainingQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TrainingQuestion.id",
    )
    submissions: Mapped[list["TrainingSubmission"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TrainingSubmission.submitted_at.desc()",
    )


class TrainingQuestion(Base):
    __tablename__ = "training_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correct_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    optional_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hidden_rubric: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scoring_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round_label: Mapped[str] = mapped_column(String(120), nullable=False, default="Round 1: Live Core Round")

    session: Mapped[TrainingSession] = relationship(back_populates="questions")
    answers: Mapped[list["TrainingAnswer"]] = relationship(back_populates="question")


class TrainingSubmission(Base):
    __tablename__ = "training_submissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("training_sessions.id"), index=True)
    participant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_role: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round_label: Mapped[str] = mapped_column(String(120), nullable=False, default="Round 1: Live Core Round")
    mcq_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    case_tagging_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    ai_open_ended_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    ai_feedback_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="submitted")

    session: Mapped[TrainingSession] = relationship(back_populates="submissions")
    answers: Mapped[list["TrainingAnswer"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="TrainingAnswer.id",
    )


class TrainingAnswer(Base):
    __tablename__ = "training_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey("training_submissions.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("training_questions.id"), index=True)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_option: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_cards: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_gaps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discussion_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    submission: Mapped[TrainingSubmission] = relationship(back_populates="answers")
    question: Mapped[TrainingQuestion] = relationship(back_populates="answers")
