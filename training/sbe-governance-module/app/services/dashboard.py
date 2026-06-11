from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.models import TrainingAnswer, TrainingSession, TrainingSubmission
from app.services.grading import decode_json


def session_dashboard(db: Session, session: TrainingSession, round_number: int | None = None) -> dict[str, Any]:
    submissions = [
        submission
        for submission in session.submissions
        if round_number is None or submission.round_number == round_number
    ]
    graded = [submission for submission in submissions if submission.status == "graded"]

    question_scores: dict[int, list[float]] = defaultdict(list)
    missed_tags: Counter[str] = Counter()
    misconceptions: Counter[str] = Counter()
    question_misses: dict[int, Counter[str]] = defaultdict(Counter)
    question_flags: dict[int, int] = defaultdict(int)

    for submission in graded:
        for answer in submission.answers:
            question = answer.question
            if answer.ai_score is not None:
                score = answer.ai_score * 20 if question.question_type == "open_ended" else answer.ai_score
                question_scores[question.id].append(score)
            gaps = decode_json(answer.detected_gaps, [])
            for gap in gaps:
                if str(gap).startswith("Missed tag: "):
                    missed_tags[str(gap).replace("Missed tag: ", "")] += 1
                else:
                    misconceptions[str(gap)] += 1
                question_misses[question.id][str(gap)] += 1
            if answer.discussion_flag:
                question_flags[question.id] += 1

    lowest_scoring_questions = []
    included_questions = [
        question for question in session.questions if round_number is None or question.round_number == round_number
    ]
    questions_by_id = {question.id: question for question in included_questions}
    for question_id, scores in question_scores.items():
        avg = round(mean(scores), 2) if scores else 0
        if avg < 80:
            lowest_scoring_questions.append(
                {
                    "question_id": question_id,
                    "question_text": questions_by_id[question_id].question_text,
                    "question_type": questions_by_id[question_id].question_type,
                    "average_score": avg,
                }
            )
    lowest_scoring_questions.sort(key=lambda item: item["average_score"])

    participant_rows = [
        {
            "id": submission.id,
            "participant_name": submission.participant_name,
            "participant_role": submission.participant_role,
            "participant_email": submission.participant_email,
            "submitted_at": submission.submitted_at.isoformat(),
            "round_number": submission.round_number,
            "round_label": submission.round_label,
            "mcq_score": submission.mcq_score,
            "case_tagging_score": submission.case_tagging_score,
            "ai_open_ended_score": submission.ai_open_ended_score,
            "total_score": submission.total_score,
            "status": submission.status,
            "discussion_flags": sum(1 for answer in submission.answers if answer.discussion_flag),
        }
        for submission in submissions
    ]

    question_review = []
    for question in included_questions:
        scores = question_scores.get(question.id, [])
        options = decode_json(question.options, [])
        rubric = decode_json(question.hidden_rubric, {}) if question.question_type == "open_ended" else {}
        sample_cards = []
        if rubric.get("required_card_order"):
            card_labels = {item["id"]: item["text"] for item in options}
            sample_cards = [
                {"id": card_id, "text": card_labels.get(card_id, card_id)}
                for card_id in rubric.get("required_card_order", [])
            ]
        question_review.append(
            {
                "question_id": question.id,
                "round_number": question.round_number,
                "round_label": question.round_label,
                "question_type": question.question_type,
                "question_text": question.question_text,
                "category": question.category,
                "options": options,
                "correct_answer": question.correct_answer if question.question_type == "mcq" else None,
                "expected_tags": decode_json(question.expected_tags, []),
                "optional_tags": decode_json(question.optional_tags, []),
                "average_score": round(mean(scores), 2) if scores else None,
                "discussion_flags": question_flags.get(question.id, 0),
                "common_misses": [
                    {"gap": gap, "count": count}
                    for gap, count in question_misses.get(question.id, Counter()).most_common(5)
                ],
                "sample_cards": sample_cards,
                "sample_remarks": rubric.get("sample_remarks"),
            }
        )

    return {
        "session_id": session.id,
        "round_number": round_number,
        "total_participants": len(submissions),
        "completion_rate": 100.0 if submissions else 0.0,
        "average_mcq_score": round(mean([s.mcq_score for s in graded]), 2) if graded else 0.0,
        "average_case_tagging_score": round(mean([s.case_tagging_score for s in graded]), 2) if graded else 0.0,
        "average_ai_open_ended_score": round(mean([s.ai_open_ended_score for s in graded]), 2) if graded else 0.0,
        "lowest_scoring_questions": lowest_scoring_questions[:8],
        "most_commonly_missed_tags": [
            {"tag": tag, "count": count} for tag, count in missed_tags.most_common(10)
        ],
        "common_misconceptions": [item for item, _ in misconceptions.most_common(10)],
        "submissions": participant_rows,
        "question_review": question_review,
        "ai_discussion_summary": None,
    }


def build_local_discussion_summary(session: TrainingSession, dashboard: dict[str, Any]) -> dict[str, Any]:
    lowest = dashboard["lowest_scoring_questions"][:5]
    missed_tags = dashboard["most_commonly_missed_tags"][:5]
    flagged_answers: list[TrainingAnswer] = [
        answer
        for submission in session.submissions
        for answer in submission.answers
        if answer.discussion_flag
    ]
    participants_follow_up = sorted(
        {
            answer.submission.participant_name
            for answer in flagged_answers
            if answer.submission.total_score < 75 or answer.ai_score in (None, 0) or answer.discussion_flag
        }
    )

    gaps = []
    if dashboard["average_case_tagging_score"] < 80:
        gaps.append("Split authority across departments is not yet consistently identified.")
    if dashboard["average_ai_open_ended_score"] < 80:
        gaps.append("Open-ended workflows need clearer closure, record-keeping, and escalation logic.")
    if missed_tags:
        gaps.append("Frequently missed tags: " + ", ".join(item["tag"] for item in missed_tags) + ".")
    if dashboard["average_mcq_score"] < 80:
        gaps.append("Core governance rules need reinforcement before policy exceptions are discussed.")
    if not gaps:
        gaps.append("Scores indicate solid baseline understanding; discussion can focus on grey areas and policy consistency.")

    return {
        "overall_average_score": round(
            mean(
                [
                    dashboard["average_mcq_score"],
                    dashboard["average_case_tagging_score"],
                    dashboard["average_ai_open_ended_score"],
                ]
            ),
            2,
        ),
        "top_5_governance_gaps": gaps[:5],
        "common_misunderstanding": dashboard["common_misconceptions"][:5],
        "questions_most_participants_got_wrong": [
            {
                "question": item["question_text"],
                "average_score": item["average_score"],
            }
            for item in lowest
        ],
        "case_tags_most_frequently_missed": missed_tags,
        "open_ended_responses_requiring_discussion": [
            {
                "participant": answer.submission.participant_name,
                "question": answer.question.question_text,
                "feedback": answer.ai_feedback,
                "gaps": decode_json(answer.detected_gaps, []),
            }
            for answer in flagged_answers
            if answer.question.question_type == "open_ended"
        ][:10],
        "recommended_clarification_points_for_exco": [
            "Reconfirm that Finance validates policy and payment position but Management owns exceptions.",
            "Reconfirm that Academic / Principal authority owns academic validity and assessment impact.",
            "Separate immediate containment from final approval in urgent cases.",
            "Use CX/Admin for parent communication and records, not as an automatic decision veto.",
            "Close every case with decision, communication, action, and record.",
        ],
        "participants_who_need_follow_up": participants_follow_up[:12],
        "suggested_next_training_focus": "Grey-area escalation drills with split authority, urgency classification, and closure records.",
        "suggested_management_policy_follow_up": "Document policy gaps for refunds, temporary access, privacy incident response, and unauthorised discount promises.",
        "suggested_aos_workflow_improvement": "Create a single escalation intake record that captures owner, policy basis, urgency reason, decision, communication, action, and closure evidence.",
    }


async def generate_discussion_summary(db: Session, session: TrainingSession) -> dict[str, Any]:
    dashboard = session_dashboard(db, session)
    provider = os.getenv("AOS_AI_PROVIDER", "local").lower()
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        try:
            return await openai_discussion_summary(session, dashboard)
        except Exception:
            return build_local_discussion_summary(session, dashboard)
    return build_local_discussion_summary(session, dashboard)


async def openai_discussion_summary(session: TrainingSession, dashboard: dict[str, Any]) -> dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("AOS_AI_MODEL", "gpt-4o-mini")
    submissions_payload = []
    for submission in session.submissions:
        submissions_payload.append(
            {
                "participant_name": submission.participant_name,
                "role": submission.participant_role,
                "scores": {
                    "mcq": submission.mcq_score,
                    "case_tagging": submission.case_tagging_score,
                    "open_ended": submission.ai_open_ended_score,
                    "total": submission.total_score,
                },
                "flagged_answers": [
                    {
                        "question": answer.question.question_text,
                        "type": answer.question.question_type,
                        "score": answer.ai_score,
                        "feedback": answer.ai_feedback,
                        "gaps": decode_json(answer.detected_gaps, []),
                    }
                    for answer in submission.answers
                    if answer.discussion_flag
                ],
            }
        )

    prompt = {
        "dashboard_metrics": dashboard,
        "participant_submissions": submissions_payload,
        "required_output": [
            "overall_average_score",
            "top_5_governance_gaps",
            "common_misunderstanding",
            "questions_most_participants_got_wrong",
            "case_tags_most_frequently_missed",
            "open_ended_responses_requiring_discussion",
            "recommended_clarification_points_for_exco",
            "participants_who_need_follow_up",
            "suggested_next_training_focus",
            "suggested_management_policy_follow_up",
            "suggested_aos_workflow_improvement",
        ],
    }
    response = await client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "Create a concise facilitator discussion summary for AOS governance training. Return strict JSON only.",
            },
            {"role": "user", "content": json.dumps(prompt)},
        ],
    )
    return json.loads(response.choices[0].message.content or "{}")
