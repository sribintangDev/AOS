from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from statistics import mean
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import TrainingAnswer, TrainingQuestion, TrainingSubmission


TAG_EXPLANATIONS = {
    "Academic / Principal": "Principal authority should decide academic validity, school operations, programme content, assessment impact, or class continuity.",
    "Finance": "Finance should validate approved pricing, payment status, discounts, refunds, and fee impact.",
    "CX / School Admin": "CX / School Admin should manage parent communication, records, and operational updates.",
    "HR": "HR is relevant when staff conduct, employment, or internal people matters need review.",
    "Technical / IT": "Technical / IT supports portals, systems access, live class links, broadcast tools, logs, platform support, and data/security containment.",
    "Management": "Management decides exceptions, waivers, sensitive cases, policy gaps, and cross-department conflict.",
    "Emergency / Urgent": "Urgency applies when real risk exists, such as safety, privacy, assessment access, live disruption, reputational exposure, or high-stake loss.",
    "Not Urgent": "Not urgent applies when there is pressure but no immediate operational, safety, privacy, assessment, or reputational risk.",
    "Cross-Department": "Cross-department applies when more than one authority must coordinate a split decision.",
}


@dataclass
class OpenEndedGrade:
    score: float
    feedback: str
    missing_elements: list[str]
    discussion_flag: bool
    follow_up_question: str


def decode_json(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def score_tag_answer(
    selected: list[str],
    expected: list[str],
    optional: list[str] | None = None,
) -> tuple[float, bool, list[str], str]:
    selected_set = set(selected)
    expected_set = set(expected)
    optional_set = set(optional or [])
    selected_for_precision = selected_set - optional_set
    missed = sorted(expected_set - selected_set)
    extra = sorted(selected_set - expected_set - optional_set)
    accepted_optional = sorted(selected_set & optional_set)

    if not selected_set and expected_set:
        f1 = 0.0
    else:
        true_positive = len(selected_set & expected_set)
        precision = true_positive / len(selected_for_precision) if selected_for_precision else (1 if true_positive else 0)
        recall = true_positive / len(expected_set) if expected_set else 0
        f1 = 0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall)

    gaps = [f"Missed tag: {tag}" for tag in missed] + [f"Extra tag selected: {tag}" for tag in extra]
    feedback_parts = []
    if missed:
        feedback_parts.append("Missed: " + ", ".join(missed))
    if extra:
        feedback_parts.append("Review whether these tags truly apply: " + ", ".join(extra))
    if accepted_optional:
        feedback_parts.append("Accepted optional tag(s): " + ", ".join(accepted_optional))
    if not feedback_parts:
        feedback_parts.append("Tags match the expected authority split.")

    exact_or_accepted = not missed and not extra
    return round(f1 * 100, 2), exact_or_accepted, gaps, " ".join(feedback_parts)


def keyword_match(answer: str, expected_element: str) -> bool:
    answer_norm = normalize_text(answer)
    element_norm = normalize_text(expected_element)
    tokens = [token for token in re.findall(r"[a-z0-9]+", element_norm) if len(token) > 2]
    if not tokens:
        return False
    important = {
        "academic",
        "finance",
        "management",
        "policy",
        "record",
        "urgent",
        "urgency",
        "waiver",
        "escalate",
        "cx",
        "admin",
        "communicates",
        "communication",
        "contain",
        "privacy",
        "promise",
        "authority",
        "assessment",
        "payment",
        "exception",
        "documentation",
        "parent",
        "principal",
        "risk",
        "sharing",
        "affected",
        "prevention",
        "technical",
        "principal",
        "systems",
        "logs",
    }
    selected = [token for token in tokens if token in important] or tokens[:3]
    hits = sum(1 for token in selected if token in answer_norm)
    return hits >= max(1, min(2, len(selected)))


def local_open_ended_grade(question: TrainingQuestion, answer_text: str) -> OpenEndedGrade:
    rubric = decode_json(question.hidden_rubric, {})
    expected_elements = rubric.get("expected_elements", [])
    answer = answer_text.strip()

    if not answer:
        return OpenEndedGrade(
            score=0,
            feedback="No answer was provided.",
            missing_elements=expected_elements,
            discussion_flag=True,
            follow_up_question="What decision owner and escalation path should apply here?",
        )

    matched = [element for element in expected_elements if keyword_match(answer, element)]
    missing = [element for element in expected_elements if element not in matched]
    coverage = len(matched) / len(expected_elements) if expected_elements else 0

    risky_patterns = [
        "promise the waiver",
        "promise waiver",
        "approve immediately",
        "waive immediately",
        "ignore policy",
        "cx decides academic",
        "finance decides academic",
    ]
    risky = any(pattern in normalize_text(answer) for pattern in risky_patterns)
    if risky:
        coverage = max(0, coverage - 0.25)

    if coverage >= 0.9:
        score = 5
        label = "Excellent"
    elif coverage >= 0.7:
        score = 4
        label = "Good"
    elif coverage >= 0.45:
        score = 3
        label = "Partial / developing"
    elif coverage >= 0.2:
        score = 2
        label = "Weak / unclear"
    else:
        score = 1
        label = "Incorrect or risky"

    if risky and score > 2:
        score = 2
        label = "Risky"

    feedback = f"{label}. Covered {len(matched)} of {len(expected_elements)} expected governance elements."
    if missing:
        feedback += " Needs clearer handling of: " + ", ".join(missing[:3]) + "."

    return OpenEndedGrade(
        score=float(score),
        feedback=feedback,
        missing_elements=missing,
        discussion_flag=score <= 3 or bool(missing[:2]),
        follow_up_question=build_follow_up_question(question, missing),
    )


def build_follow_up_question(question: TrainingQuestion, missing: list[str]) -> str:
    if missing:
        return f"How would you include '{missing[0]}' in the workflow before closing this case?"
    if question.category == "finance":
        return "What would make this a Management exception rather than a Finance-only matter?"
    if question.category == "academic":
        return "Where does Academic authority end and parent communication support begin?"
    if question.category == "emergency":
        return "What immediate containment action is needed before the final decision?"
    return "What record should be kept so the decision can be reviewed later?"


async def openai_open_ended_grade(question: TrainingQuestion, answer_text: str) -> OpenEndedGrade:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("AOS_AI_MODEL", "gpt-4o-mini")
    rubric = decode_json(question.hidden_rubric, {})
    system_prompt = (
        "You grade AOS governance training answers. Keep rubrics confidential. "
        "Return strict JSON only with keys: score, short_feedback, missing_elements, "
        "discussion_flag, suggested_facilitator_follow_up_question. Score must be 0-5."
    )
    user_prompt = {
        "question": question.question_text,
        "participant_answer": answer_text,
        "hidden_rubric": rubric,
        "expected_answer": question.expected_answer,
        "grading_instructions": (
            "Assess department authority, escalation path, urgency vs pressure, finance discipline, "
            "academic authority, Management exceptions, workflow completeness, parent communication, "
            "avoidance of unauthorised promises, closure and record-keeping."
        ),
    }
    response = await client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt)},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    score = max(0, min(5, float(data.get("score", 0))))
    missing = data.get("missing_elements") or []
    return OpenEndedGrade(
        score=score,
        feedback=str(data.get("short_feedback", "AI grading completed.")),
        missing_elements=[str(item) for item in missing],
        discussion_flag=bool(data.get("discussion_flag", score <= 3)),
        follow_up_question=str(
            data.get("suggested_facilitator_follow_up_question")
            or build_follow_up_question(question, [str(item) for item in missing])
        ),
    )


async def grade_open_ended(question: TrainingQuestion, answer_text: str) -> OpenEndedGrade:
    provider = os.getenv("AOS_AI_PROVIDER", "local").lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            return await openai_open_ended_grade(question, answer_text)
        except Exception as exc:
            fallback = local_open_ended_grade(question, answer_text)
            fallback.feedback += f" Server-side local fallback used because AI provider failed: {exc.__class__.__name__}."
            return fallback
    return local_open_ended_grade(question, answer_text)


def score_workflow_cards(question: TrainingQuestion, selected_cards: list[str], remarks: str) -> OpenEndedGrade:
    rubric = decode_json(question.hidden_rubric, {})
    required = rubric.get("required_card_order", [])
    optional = set(rubric.get("optional_cards", []))
    distractors = set(rubric.get("distractor_cards", []))
    selected = [card_id for card_id in selected_cards if card_id]
    selected_set = set(selected)

    required_set = set(required)
    required_selected = selected_set & required_set
    missed = [card_id for card_id in required if card_id not in selected_set]
    risky = [card_id for card_id in selected if card_id in distractors]
    unnecessary = [
        card_id
        for card_id in selected
        if card_id not in required_set and card_id not in optional and card_id not in distractors
    ]

    selection_score = len(required_selected) / len(required) if required else 0
    order_pairs = max(1, len(required) - 1)
    ordered_hits = 0
    for left, right in zip(required, required[1:]):
        if left in selected and right in selected and selected.index(left) < selected.index(right):
            ordered_hits += 1
    order_score = ordered_hits / order_pairs
    distractor_penalty = min(0.35, 0.18 * len(risky) + 0.08 * len(unnecessary))
    card_score = max(0.0, ((selection_score * 0.6) + (order_score * 0.4)) - distractor_penalty)

    remark_grade = local_open_ended_grade(question, remarks)
    remark_score = remark_grade.score / 5
    final_score = round(((card_score * 0.7) + (remark_score * 0.3)) * 5, 2)

    card_labels = {item["id"]: item["text"] for item in decode_json(question.options, [])}
    missing_labels = [card_labels.get(card_id, card_id) for card_id in missed]
    risky_labels = [card_labels.get(card_id, card_id) for card_id in risky]
    unnecessary_labels = [card_labels.get(card_id, card_id) for card_id in unnecessary]

    feedback_parts = [
        f"Workflow cards: {round(card_score * 100, 1)}%. Remark review: {round(remark_score * 100, 1)}%."
    ]
    if missing_labels:
        feedback_parts.append("Missed cards: " + ", ".join(missing_labels[:3]) + ".")
    if risky_labels:
        feedback_parts.append("Risky cards used: " + ", ".join(risky_labels[:3]) + ".")
    if unnecessary_labels:
        feedback_parts.append("Review unnecessary cards: " + ", ".join(unnecessary_labels[:3]) + ".")
    if order_score < 1:
        feedback_parts.append("Some selected cards should appear in a clearer governance order.")
    feedback_parts.append(remark_grade.feedback)

    missing_elements = [f"Missed card: {label}" for label in missing_labels]
    missing_elements.extend([f"Risky card used: {label}" for label in risky_labels])
    missing_elements.extend(remark_grade.missing_elements[:3])

    return OpenEndedGrade(
        score=final_score,
        feedback=" ".join(feedback_parts),
        missing_elements=missing_elements,
        discussion_flag=final_score < 4 or bool(missed) or bool(risky),
        follow_up_question=build_follow_up_question(question, remark_grade.missing_elements or missing_labels),
    )


async def grade_submission(db: Session, submission: TrainingSubmission) -> TrainingSubmission:
    questions = {question.id: question for question in submission.session.questions}

    mcq_scores: list[float] = []
    case_scores: list[float] = []
    open_scores: list[float] = []
    feedback_snippets: list[str] = []
    open_missing: list[str] = []

    for answer in submission.answers:
        question = questions[answer.question_id]
        if question.question_type == "mcq":
            correct = normalize_text(answer.selected_option) == normalize_text(question.correct_answer)
            answer.is_correct = correct
            answer.ai_score = 100.0 if correct else 0.0
            answer.ai_feedback = "Correct." if correct else "Review the governance rule behind this question."
            answer.detected_gaps = json.dumps([] if correct else [f"MCQ missed: {question.category}"])
            answer.discussion_flag = not correct
            mcq_scores.append(answer.ai_score)
        elif question.question_type == "case_tagging":
            selected = decode_json(answer.selected_tags, [])
            expected = decode_json(question.expected_tags, [])
            optional = decode_json(question.optional_tags, [])
            score, exact, gaps, feedback = score_tag_answer(selected, expected, optional)
            answer.is_correct = exact
            answer.ai_score = score
            answer.ai_feedback = feedback
            answer.detected_gaps = json.dumps(gaps)
            answer.discussion_flag = score < 80
            case_scores.append(score)
        elif question.question_type == "open_ended":
            selected_cards = decode_json(answer.selected_cards, [])
            if selected_cards:
                grade = score_workflow_cards(question, selected_cards, answer.answer_text or "")
            else:
                grade = await grade_open_ended(question, answer.answer_text or "")
            answer.is_correct = grade.score >= 4
            answer.ai_score = grade.score
            answer.ai_feedback = grade.feedback
            answer.detected_gaps = json.dumps(grade.missing_elements)
            answer.discussion_flag = grade.discussion_flag
            open_scores.append(grade.score * 20)
            feedback_snippets.append(grade.feedback)
            open_missing.extend(grade.missing_elements)

    submission.mcq_score = round(mean(mcq_scores), 2) if mcq_scores else 0
    submission.case_tagging_score = round(mean(case_scores), 2) if case_scores else 0
    submission.ai_open_ended_score = round(mean(open_scores), 2) if open_scores else 0
    components = [submission.mcq_score, submission.case_tagging_score, submission.ai_open_ended_score]
    submission.total_score = round(mean(components), 2)
    submission.ai_feedback_summary = build_feedback_summary(submission, feedback_snippets, open_missing)
    submission.status = "graded"
    db.commit()
    db.refresh(submission)
    return submission


def build_feedback_summary(
    submission: TrainingSubmission,
    feedback_snippets: list[str],
    open_missing: list[str],
) -> str:
    areas = []
    if submission.mcq_score < 80:
        areas.append("review core governance rules")
    if submission.case_tagging_score < 80:
        areas.append("strengthen department/authority tagging")
    if submission.ai_open_ended_score < 80:
        areas.append("make open-ended workflows more complete")
    if open_missing:
        most_common = []
        for item in open_missing:
            if item not in most_common:
                most_common.append(item)
        areas.append("clarify: " + ", ".join(most_common[:4]))

    base = "Open-ended responses were reviewed server-side. "
    if feedback_snippets:
        base += " ".join(feedback_snippets[:2]) + " "
    if areas:
        return base + "Key improvement areas: " + "; ".join(areas) + "."
    return base + "Strong governance coverage. Keep decisions tied to authority, policy, communication, and records."


def answer_to_public_result(answer: TrainingAnswer) -> dict[str, Any]:
    question = answer.question
    options = decode_json(question.options, [])
    card_labels = {item.get("id"): item.get("text") for item in options if isinstance(item, dict)}
    selected_cards = decode_json(answer.selected_cards, [])
    selected_card_labels = [card_labels.get(card_id, card_id) for card_id in selected_cards]
    unused_card_labels = [
        item.get("text")
        for item in options
        if isinstance(item, dict) and item.get("id") not in selected_cards
    ]
    return {
        "question_id": answer.question_id,
        "question_type": question.question_type,
        "question_text": question.question_text,
        "options": options,
        "round_number": question.round_number,
        "round_label": question.round_label,
        "selected_option": answer.selected_option,
        "selected_tags": decode_json(answer.selected_tags, []),
        "selected_cards": selected_cards,
        "selected_card_labels": selected_card_labels,
        "unused_card_labels": unused_card_labels,
        "answer_text": answer.answer_text,
        "is_correct": answer.is_correct,
        "score": answer.ai_score,
        "feedback": answer.ai_feedback,
        "detected_gaps": decode_json(answer.detected_gaps, []),
        "discussion_flag": answer.discussion_flag,
    }
