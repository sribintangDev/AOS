from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


QuestionType = Literal["mcq", "case_tagging", "open_ended"]


class TrainingSessionCreate(BaseModel):
    title: str
    description: str
    created_by: str = "AOS"
    facilitator_id: Optional[str] = None
    training_type: str = "sbe_governance"


class PublicQuestion(BaseModel):
    id: int
    question_type: QuestionType
    question_text: str
    options: Optional[list[str]] = None
    scoring_weight: float
    category: str
    round_number: int = 1
    round_label: str = "Round 1: Live Core Round"


class PublicSession(BaseModel):
    id: str
    title: str
    description: str
    status: str
    training_type: str
    questions: list[PublicQuestion]


class AnswerInput(BaseModel):
    question_id: int
    answer_text: Optional[str] = None
    selected_option: Optional[str] = None
    selected_tags: list[str] = Field(default_factory=list)
    selected_cards: list[str] = Field(default_factory=list)


class SubmissionCreate(BaseModel):
    participant_name: str
    participant_role: str
    participant_email: Optional[str] = None
    round_number: int = 1
    answers: list[AnswerInput]


class AnswerResult(BaseModel):
    question_id: int
    question_type: str
    is_correct: Optional[bool]
    score: Optional[float]
    feedback: Optional[str]
    detected_gaps: list[str]
    discussion_flag: bool


class SubmissionResult(BaseModel):
    id: str
    mcq_score: float
    case_tagging_score: float
    ai_open_ended_score: float
    total_score: float
    ai_feedback_summary: Optional[str]
    status: str
    answers: list[AnswerResult]


class DashboardSubmission(BaseModel):
    id: str
    participant_name: str
    participant_role: str
    participant_email: Optional[str]
    submitted_at: str
    round_number: int
    round_label: str
    mcq_score: float
    case_tagging_score: float
    ai_open_ended_score: float
    total_score: float
    status: str
    discussion_flags: int


class DashboardData(BaseModel):
    session_id: str
    total_participants: int
    completion_rate: float
    average_mcq_score: float
    average_case_tagging_score: float
    average_ai_open_ended_score: float
    lowest_scoring_questions: list[dict[str, Any]]
    most_commonly_missed_tags: list[dict[str, Any]]
    common_misconceptions: list[str]
    submissions: list[DashboardSubmission]
    ai_discussion_summary: Optional[dict[str, Any]] = None
