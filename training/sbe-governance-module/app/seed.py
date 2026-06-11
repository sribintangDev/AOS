from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import TrainingAnswer, TrainingQuestion, TrainingSession, TrainingSubmission

DEFAULT_SESSION_ID = "sbe-governance-2026"
CONTENT_VERSION = "rounds-cards-technical-v1"

ROUND_LABELS = {
    1: "Round 1: Live Core Round",
    2: "Round 2: Self-Study Practice",
    3: "Round 3: Advanced Scenarios",
}

CASE_TAGS = [
    "Academic / Principal",
    "Finance",
    "CX / School Admin",
    "HR",
    "Technical / IT",
    "Management",
    "Emergency / Urgent",
    "Not Urgent",
    "Cross-Department",
]

TAG_GUIDANCE = [
    {
        "tag": "Academic / Principal",
        "body": "Principal covers academic authority and school operations: academic validity, assessment impact, programme content, class continuity, and school-level operational decisions.",
    },
    {
        "tag": "Finance",
        "body": "Finance validates approved pricing, payment position, discount/refund policy, fee difference, and financial impact. Finance does not approve exceptions alone.",
    },
    {
        "tag": "CX / School Admin",
        "body": "CX/Admin manages parent communication, parent-experience clarity, operational records, student records, and case closure updates.",
    },
    {
        "tag": "HR",
        "body": "HR is relevant when staff conduct, employment, accountability, or internal people matters need review.",
    },
    {
        "tag": "Technical / IT",
        "body": "Technical / IT supports portals, systems access, live class links, broadcast tools, logs, platform support, data/security containment, and technical evidence.",
    },
    {
        "tag": "Management",
        "body": "Management decides exceptions, waivers, policy gaps, sensitive matters, reputational risk, and unresolved cross-department conflict.",
    },
    {
        "tag": "Emergency / Urgent",
        "body": "Urgency is based on real risk: safety, privacy, assessment access, live disruption, reputational exposure, security, or high-stake loss.",
    },
    {
        "tag": "Not Urgent",
        "body": "Not urgent applies when there is pressure or dissatisfaction but no immediate safety, privacy, academic, operational, reputational, or technical risk.",
    },
    {
        "tag": "Cross-Department",
        "body": "Cross-department cases need split authority. One person should not make all decisions across academic, financial, technical, HR, and parent communication areas.",
    },
]

GOVERNANCE_RULES = [
    "Principal covers academic decisions and school operations.",
    "Financial matters must stay close to policy.",
    "If policy deviation is needed, escalate to Management.",
    "If no policy exists, escalate to Management.",
    "Loud is not equal to urgent.",
    "Urgency is based on real risk, not pressure.",
    "CX/Admin may flag parent-experience or communication misalignment.",
    "Technical / IT supports systems, access, logs, links, and data/security containment.",
    "Management decides exceptions, waivers, sensitive matters, and cross-department conflict.",
    "No case should be closed without decision, communication, action, and closure record.",
]

TRAINING_NOTES = [
    {
        "title": "Principal Authority",
        "body": "The Principal is the authority for academic decisions and school operations. This includes subject validity, assessment impact, class continuity, programme claims, school procedures, and operational direction.",
        "visual": "Principal = academic authority + school operations",
    },
    {
        "title": "Financial Policy Discipline",
        "body": "Fee waivers, refunds, discounts, and temporary access decisions must be checked against approved policy. Staff may acknowledge pressure, gather facts, and escalate, but should not promise exceptions.",
        "visual": "Policy first, exception second",
    },
    {
        "title": "Management Escalation",
        "body": "Management handles exceptions, policy gaps, sensitive matters, reputational risk, waivers, privacy incidents, safeguarding concerns, and unresolved cross-department conflict.",
        "visual": "Exceptions belong to Management",
    },
    {
        "title": "Cross-Department Workflows",
        "body": "Cases involving multiple authorities should be split by responsibility. Principal validates academic/school-operation impact, Finance validates financial position, Technical / IT validates systems evidence, CX/Admin communicates and records, and Management decides exceptions.",
        "visual": "Split authority, then close the loop",
    },
    {
        "title": "Technical / IT Escalation",
        "body": "Technical / IT should be tagged when the case involves portal access, platform errors, live-class links, broadcast tools, logs, data/security containment, or technical evidence needed for decisions.",
        "visual": "Access, links, logs, containment",
    },
    {
        "title": "Emergency and Urgency",
        "body": "Urgency is based on real risk: safety, privacy, assessment access, live disruption, reputational exposure, security, or high-stake loss. Anger, volume, and pressure alone do not create urgency.",
        "visual": "Risk creates urgency, not volume",
    },
    {
        "title": "Grey Area Handling",
        "body": "When policy is unclear or authority overlaps, record the case, identify the authority owner, contain immediate risk, escalate if needed, communicate carefully, and close the case with evidence.",
        "visual": "Contain, decide, communicate, record",
    },
]

PRESENTATION_SLIDES = [
    {
        "type": "teaching",
        "title": "Authority Map",
        "subtitle": "Who owns which part of the decision?",
        "points": [
            "Academic / Principal: academic authority and school operations.",
            "Finance: payment position, pricing, refunds, discounts, and policy validation.",
            "CX / School Admin: parent communication, records, and operational updates.",
            "Technical / IT: systems access, live links, portal evidence, logs, and data/security containment.",
            "HR: staff conduct and internal people matters.",
            "Management: exceptions, waivers, policy gaps, sensitive escalation, and conflict.",
        ],
    },
    {
        "type": "teaching",
        "title": "Urgency Matrix",
        "subtitle": "Pressure is not the same as risk.",
        "points": [
            "Urgent: safety, privacy, assessment access, live disruption, security, public exposure, or high-stake loss.",
            "Not urgent: anger, repeated messages, pressure for discount, or dissatisfaction without immediate risk.",
            "Urgent action can contain risk before the final decision is made.",
            "Urgent does not mean automatic approval, waiver, or exception.",
        ],
    },
    {
        "type": "teaching",
        "title": "Escalation Ladder",
        "subtitle": "Move from containment to closure.",
        "points": [
            "1. Contain immediate risk.",
            "2. Identify the authority owner.",
            "3. Check policy and evidence.",
            "4. Escalate exception or policy gap to Management.",
            "5. Communicate the decision clearly.",
            "6. Record action and closure.",
        ],
    },
    {
        "type": "discussion",
        "title": "Grey Area: Angry Parent Fee Waiver",
        "scenario": "A parent is upset and demands a fee waiver immediately.",
        "question": "What can staff say now, and what must wait for authority review?",
        "likely_tags": ["Finance", "CX / School Admin", "Management"],
        "guidance": "Acknowledge the concern, record facts, check policy, avoid promising a waiver, and escalate any exception.",
        "warning": "Do not treat loud pressure as urgency or promise a financial exception.",
    },
    {
        "type": "discussion",
        "title": "Grey Area: Assessment Access Blocked",
        "scenario": "A student has an assessment today, but portal access is blocked due to unpaid fees.",
        "question": "What should be contained urgently, and who decides the final exception?",
        "likely_tags": ["Academic / Principal", "Finance", "Technical / IT", "Management", "Emergency / Urgent", "Cross-Department"],
        "guidance": "Principal confirms assessment impact, Finance validates payment status, Technical / IT supports access evidence, and Management decides exceptions.",
        "warning": "Do not confuse temporary containment with a fee waiver.",
    },
    {
        "type": "discussion",
        "title": "Grey Area: CX Flags Academic Wording",
        "scenario": "An academic announcement is ready, but CX thinks parents may misunderstand it.",
        "question": "Is this a CX veto or an Academic / Principal decision?",
        "likely_tags": ["Academic / Principal", "CX / School Admin"],
        "guidance": "CX flags clarity and parent-experience risk. Principal retains academic authority and school-operation decision ownership.",
        "warning": "Do not let communication feedback become an automatic content veto.",
    },
    {
        "type": "discussion",
        "title": "Grey Area: Unauthorised Discount Promise",
        "scenario": "A staff member promised a discount in WhatsApp without approval.",
        "question": "Who checks policy, who decides goodwill, and who reviews conduct?",
        "likely_tags": ["Finance", "CX / School Admin", "HR", "Management", "Cross-Department"],
        "guidance": "Finance validates approved pricing, Management decides honour/reject/goodwill, CX communicates, and HR reviews staff conduct if needed.",
        "warning": "Do not let the staff promise automatically override policy.",
    },
    {
        "type": "discussion",
        "title": "Grey Area: Wrong Parent Broadcast",
        "scenario": "Student-specific information is sent to the wrong parent group.",
        "question": "What happens first, and what happens after containment?",
        "likely_tags": ["Academic / Principal", "CX / School Admin", "Technical / IT", "Management", "Emergency / Urgent"],
        "guidance": "Stop further sharing, preserve evidence/logs, inform Management/Principal, identify affected information, and prepare controlled communication.",
        "warning": "Do not send rushed follow-up messages that expand the breach.",
    },
    {
        "type": "discussion",
        "title": "Grey Area: Technical Access vs Policy",
        "scenario": "A portal access issue has technical evidence but also unpaid-fee implications.",
        "question": "What can Technical / IT fix, and what must Finance or Management decide?",
        "likely_tags": ["Technical / IT", "Finance", "Management", "Cross-Department"],
        "guidance": "Technical / IT validates system facts and enables approved access changes. Finance validates payment/policy. Management decides exceptions.",
        "warning": "Do not let a technical workaround become an unauthorised policy decision.",
    },
]


def json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


def card(card_id: str, text: str) -> dict[str, str]:
    return {"id": card_id, "text": text}


WORKFLOW_CARD_BANKS = {
    "fee_waiver": {
        "cards": [
            card("acknowledge", "Acknowledge the concern calmly"),
            card("record", "Record the case and facts"),
            card("check_policy", "Check fee waiver/refund policy"),
            card("no_promise", "Do not promise a waiver"),
            card("finance", "Ask Finance to validate payment/policy position"),
            card("management_exception", "Escalate exceptions to Management"),
            card("communicate", "Communicate the approved decision"),
            card("closure", "Close with action and record"),
            card("approve_now", "Approve the waiver immediately"),
            card("parent_decides", "Ask the parent what outcome they want"),
        ],
        "required": ["acknowledge", "record", "check_policy", "no_promise", "finance", "management_exception", "communicate", "closure"],
        "optional": [],
        "distractors": ["approve_now", "parent_decides"],
        "sample_remarks": "Staff can acknowledge and gather facts immediately, but must not promise a waiver. Finance checks policy/payment position and Management decides any exception.",
    },
    "access_fees": {
        "cards": [
            card("confirm_assessment", "Principal confirms academic/assessment impact"),
            card("technical_status", "Technical / IT checks portal/access status"),
            card("finance_status", "Finance validates payment and policy position"),
            card("contain_risk", "Contain urgent assessment risk if needed"),
            card("management_exception", "Management decides any exception or temporary access outside policy"),
            card("cx_communicate", "CX/Admin communicates clearly with parent"),
            card("record_close", "Record action, decision, and closure"),
            card("waive_fee", "Waive the fee because the assessment is today"),
            card("ignore_academic", "Let Finance decide academic access alone"),
        ],
        "required": ["confirm_assessment", "technical_status", "finance_status", "contain_risk", "management_exception", "cx_communicate", "record_close"],
        "optional": [],
        "distractors": ["waive_fee", "ignore_academic"],
        "sample_remarks": "Urgency may require containment, but it does not create an automatic waiver. Principal, Technical / IT, Finance, Management, and CX/Admin each own different parts.",
    },
    "announcement_cx": {
        "cards": [
            card("academic_owner", "Principal retains academic content authority"),
            card("cx_flag", "CX/Admin flags clarity and parent-experience risk"),
            card("discuss", "Record discussion and proposed wording concern"),
            card("revise_if_agreed", "Revise wording if Principal agrees"),
            card("escalate_risk", "Escalate only if policy/reputational/management risk remains"),
            card("publish_record", "Publish approved wording and record decision"),
            card("cx_veto", "CX vetoes the academic message"),
            card("publish_without_review", "Publish without recording the concern"),
        ],
        "required": ["academic_owner", "cx_flag", "discuss", "revise_if_agreed", "escalate_risk", "publish_record"],
        "optional": [],
        "distractors": ["cx_veto", "publish_without_review"],
        "sample_remarks": "CX can flag parent-experience risk, but Principal retains academic and school-operation authority. Escalation is only needed for policy, reputational, or unresolved risk.",
    },
    "urgent_final": {
        "cards": [
            card("identify_risk", "Identify immediate real risk"),
            card("contain", "Take urgent containment action"),
            card("owner", "Identify authority owner"),
            card("policy", "Check policy and evidence"),
            card("final_decision", "Final decision follows authority and policy"),
            card("communicate", "Communicate decision once approved"),
            card("record", "Document action and closure"),
            card("instant_approval", "Treat urgency as instant approval"),
            card("skip_record", "Skip documentation because it was urgent"),
        ],
        "required": ["identify_risk", "contain", "owner", "policy", "final_decision", "communicate", "record"],
        "optional": [],
        "distractors": ["instant_approval", "skip_record"],
        "sample_remarks": "Urgent action prevents immediate harm. It is not the same as final approval, which must still follow authority, policy, communication, and records.",
    },
    "privacy_breach": {
        "cards": [
            card("stop_sharing", "Stop further sharing immediately"),
            card("technical_logs", "Technical / IT preserves broadcast evidence/logs"),
            card("inform_management", "Inform Management and Principal"),
            card("identify_info", "Identify affected information and recipients"),
            card("controlled_comms", "Prepare controlled parent communication"),
            card("record_incident", "Record incident and action timeline"),
            card("prevention", "Review prevention measures"),
            card("mass_apology", "Send a fast apology to every parent group"),
            card("delete_without_record", "Delete records before review"),
        ],
        "required": ["stop_sharing", "technical_logs", "inform_management", "identify_info", "controlled_comms", "record_incident", "prevention"],
        "optional": [],
        "distractors": ["mass_apology", "delete_without_record"],
        "sample_remarks": "First contain and preserve evidence. Afterwards, Management/Principal lead the response, CX/Admin controls communication, and prevention measures are reviewed.",
    },
}


def make_workflow_question(text: str, bank_key: str, category: str, round_number: int) -> TrainingQuestion:
    bank = WORKFLOW_CARD_BANKS[bank_key]
    expected_elements = [next(item["text"] for item in bank["cards"] if item["id"] == card_id) for card_id in bank["required"]]
    sample_order = " -> ".join(expected_elements)
    return TrainingQuestion(
        session_id=DEFAULT_SESSION_ID,
        question_type="open_ended",
        question_text=text,
        options=json_dump(bank["cards"]),
        hidden_rubric=json_dump(
            {
                "interaction": "workflow_cards",
                "required_card_order": bank["required"],
                "optional_cards": bank["optional"],
                "distractor_cards": bank["distractors"],
                "expected_elements": expected_elements,
                "sample_order": sample_order,
                "sample_remarks": bank["sample_remarks"],
                "scale": "70% card workflow score and 30% AI/remark review. Score remains reported out of 5 for open-ended workflows.",
            }
        ),
        expected_answer=f"{sample_order}. Sample remarks: {bank['sample_remarks']}",
        scoring_weight=1.0,
        category=category,
        round_number=round_number,
        round_label=ROUND_LABELS[round_number],
    )


def make_mcq(text: str, options: list[str], correct: str, category: str, round_number: int) -> TrainingQuestion:
    return TrainingQuestion(
        session_id=DEFAULT_SESSION_ID,
        question_type="mcq",
        question_text=text,
        options=json_dump(options),
        correct_answer=correct,
        scoring_weight=1.0,
        category=category,
        round_number=round_number,
        round_label=ROUND_LABELS[round_number],
    )


def make_case(
    title: str,
    scenario: str,
    required_tags: list[str],
    reasoning: str,
    category: str,
    round_number: int,
    optional_tags: list[str] | None = None,
) -> TrainingQuestion:
    return TrainingQuestion(
        session_id=DEFAULT_SESSION_ID,
        question_type="case_tagging",
        question_text=f"{title}: {scenario}",
        options=json_dump(CASE_TAGS),
        expected_tags=json_dump(required_tags),
        optional_tags=json_dump(optional_tags or []),
        expected_answer=reasoning,
        hidden_rubric=(
            "Assess whether selected tags reflect split authority and real urgency. "
            "Accepted optional tags should not be penalized. Expected reasoning: " + reasoning
        ),
        scoring_weight=1.0,
        category=category,
        round_number=round_number,
        round_label=ROUND_LABELS[round_number],
    )


def build_questions() -> list[TrainingQuestion]:
    questions: list[TrainingQuestion] = [
        make_mcq(
            "A parent is angry and demands an immediate fee waiver. What should staff do first?",
            [
                "Promise the waiver to calm the parent",
                "Acknowledge the concern, record the case, check policy, and escalate if outside policy",
                "Tell Finance to approve the waiver immediately",
                "Close the case because the parent is difficult",
            ],
            "Acknowledge the concern, record the case, check policy, and escalate if outside policy",
            "finance",
            1,
        ),
        make_mcq(
            "Which statement best describes urgency in AOS governance?",
            [
                "Urgency exists whenever a parent is loud",
                "Urgency is based on real risk, not pressure",
                "Urgency allows any staff member to make a final decision",
                "Urgency always means Finance must waive fees",
            ],
            "Urgency is based on real risk, not pressure",
            "emergency",
            1,
        ),
        make_mcq(
            "Who should decide whether a subject change is academically allowed?",
            [
                "Finance",
                "CX / School Admin",
                "Academic / Principal",
                "Any staff member who receives the parent message",
            ],
            "Academic / Principal",
            "academic",
            1,
        ),
        make_case(
            "Portal Access Blocked Before Assessment",
            "A student has an assessment today, but portal access is blocked due to unpaid fees.",
            ["Academic / Principal", "Finance", "Technical / IT", "Management", "Emergency / Urgent", "Cross-Department"],
            "This may be urgent because assessment access is affected. Urgency does not mean automatic financial waiver. Principal confirms assessment impact. Technical / IT checks access status. Finance validates payment position. Management decides any exception or temporary access if outside policy.",
            "emergency",
            1,
        ),
        make_case(
            "Parent Threatens Public Complaint Over Refund",
            "A parent demands refund outside policy and threatens to post publicly on social media within the hour.",
            ["Finance", "Management", "CX / School Admin", "Emergency / Urgent", "Cross-Department"],
            "Refund still requires policy and management review. Reputational risk may require urgent containment and careful communication.",
            "management",
            1,
        ),
        make_case(
            "Wrong Parent Broadcast",
            "A school announcement containing student-specific information is accidentally sent to the wrong parent group.",
            ["Management", "CX / School Admin", "Academic / Principal", "Technical / IT", "Emergency / Urgent"],
            "This is a privacy/data protection concern. Contain immediately, preserve technical evidence/logs, inform Management and Principal, and control parent communication.",
            "emergency",
            1,
        ),
        make_case(
            "Staff Promised Unauthorised Discount",
            "A parent produces a WhatsApp screenshot showing that a staff member promised a discount without approval.",
            ["Finance", "Management", "CX / School Admin", "HR", "Cross-Department"],
            "Finance checks approved pricing. Management decides whether to honour, reject, or offer goodwill. HR may review staff conduct separately.",
            "hr",
            1,
        ),
        make_case(
            "Safeguarding Concern Raised by Parent",
            "A parent reports that a student shared worrying messages suggesting possible harm or danger.",
            ["Academic / Principal", "Management", "Emergency / Urgent", "Cross-Department"],
            "This is a safety concern. Immediate escalation is required. It should not be treated as a normal parent complaint.",
            "emergency",
            1,
        ),
        make_workflow_question(
            "A matter involves both academic access and unpaid fees. Arrange the action cards in the correct workflow and add brief remarks.",
            "access_fees",
            "cross_department",
            1,
        ),
        make_workflow_question(
            "Explain the difference between an urgent action and a final decision by arranging the workflow cards and adding brief remarks.",
            "urgent_final",
            "emergency",
            1,
        ),
        make_mcq(
            "A case has no clear policy. What is the correct governance route?",
            [
                "Use personal judgement and close the case",
                "Escalate to Management for decision",
                "Ask the parent to choose the outcome",
                "Let CX veto all other departments",
            ],
            "Escalate to Management for decision",
            "management",
            2,
        ),
        make_mcq(
            "What should happen before a cross-department case is closed?",
            [
                "Only the loudest department signs off",
                "Decision, communication, action, and closure record are completed",
                "The parent is sent a generic apology",
                "The case is moved to Finance regardless of topic",
            ],
            "Decision, communication, action, and closure record are completed",
            "cross_department",
            2,
        ),
        make_mcq(
            "CX believes an academic announcement may confuse parents. What is the correct role of CX?",
            [
                "CX can flag clarity or parent-experience concerns for Academic / Principal to consider",
                "CX automatically owns the academic content",
                "CX should publish a different academic policy",
                "CX should bypass Academic / Principal and ask Finance",
            ],
            "CX can flag clarity or parent-experience concerns for Academic / Principal to consider",
            "cx",
            2,
        ),
        make_case(
            "Subject Change After Deadline",
            "A parent requests a subject change after timetable and teacher allocation have been finalised.",
            ["Academic / Principal", "CX / School Admin", "Cross-Department"],
            "Principal decides whether the subject change is allowed. CX / School Admin handles parent communication and record updates. This is not automatically a finance or management issue unless there is fee, exception, or dispute involved.",
            "academic",
            2,
        ),
        make_case(
            "Subject Change with Fee Difference",
            "A parent requests a subject change, and the new subject package has a different fee.",
            ["Academic / Principal", "Finance", "CX / School Admin", "Cross-Department"],
            "Principal decides whether the change is academically allowed. Finance validates the fee impact. CX / School Admin communicates and updates records.",
            "finance",
            2,
        ),
        make_case(
            "Parent Requests Refund Outside Policy",
            "A parent withdraws after the allowed refund period and requests a full refund.",
            ["Finance", "Management", "CX / School Admin"],
            "Finance checks refund policy and payment record. Management decides any exception. CX handles parent communication. Not automatically urgent unless reputational, legal, safeguarding, or privacy risk exists.",
            "finance",
            2,
        ),
        make_case(
            "Teacher Complaint with Fee Reduction Demand",
            "A parent complains that a teacher is ineffective and demands fee reduction.",
            ["Academic / Principal", "Finance", "CX / School Admin", "Management", "Cross-Department"],
            "Principal investigates teaching/school-operation issue. Finance does not reduce fees without approval. CX manages parent communication. Management decides exception if required.",
            "academic",
            2,
        ),
        make_workflow_question(
            "An academic announcement is ready to be published, but CX believes the wording may confuse parents. Arrange the governance workflow and add brief remarks.",
            "announcement_cx",
            "academic",
            2,
        ),
        make_mcq(
            "A staff member promised an unapproved discount. Which authority decides whether it is honoured?",
            [
                "The staff member who made the promise",
                "Management, after Finance validates approved pricing and impact",
                "The parent",
                "CX alone",
            ],
            "Management, after Finance validates approved pricing and impact",
            "management",
            3,
        ),
        make_mcq(
            "What is the safest immediate response to a privacy breach through a wrong parent broadcast?",
            [
                "Contain it immediately, stop further sharing, inform Management, preserve evidence, and control communication",
                "Ignore it unless a parent complains",
                "Offer a fee waiver immediately",
                "Ask teachers to delete all unrelated records",
            ],
            "Contain it immediately, stop further sharing, inform Management, preserve evidence, and control communication",
            "emergency",
            3,
        ),
        make_case(
            "Live Class Intruder",
            "An unknown person enters a live class link and disrupts the lesson.",
            ["Academic / Principal", "Technical / IT", "Management", "Emergency / Urgent", "Cross-Department"],
            "This is a security and student safety concern. Immediate containment is required. Principal handles class continuity, Technical / IT secures links/logs, and Management handles risk and policy response.",
            "emergency",
            3,
        ),
        make_case(
            "Medical Emergency During Online Class",
            "A student appears faint, distressed, or unresponsive during live online class.",
            ["Academic / Principal", "Management", "Emergency / Urgent", "CX / School Admin"],
            "Immediate safety response is required. Contact parent/guardian immediately, inform management, document the incident, and follow emergency protocol.",
            "emergency",
            3,
            optional_tags=["Technical / IT"],
        ),
        make_case(
            "High-Stake Partnership Opportunity",
            "A potential partner requests urgent confirmation of fee structure and programme details before approving a collaboration.",
            ["Management", "Finance", "Academic / Principal", "Emergency / Urgent", "Cross-Department"],
            "This may be urgent if opportunity loss is real and high-stake. Finance validates pricing. Principal validates programme claims. Management decides final position.",
            "cross_department",
            3,
        ),
        make_workflow_question(
            "A parent is very angry and demands an immediate fee waiver. Arrange how staff should respond without making an unauthorised decision.",
            "fee_waiver",
            "finance",
            3,
        ),
        make_workflow_question(
            "A privacy breach happens through a wrong parent broadcast. Arrange what should happen first and afterwards, then add brief remarks.",
            "privacy_breach",
            "management",
            3,
        ),
    ]
    return questions


def seed_default_session(db: Session) -> TrainingSession:
    existing = db.get(TrainingSession, DEFAULT_SESSION_ID)
    if existing and existing.training_type == f"sbe_governance:{CONTENT_VERSION}":
        return existing

    if existing:
        for submission in list(existing.submissions):
            db.query(TrainingAnswer).filter(TrainingAnswer.submission_id == submission.id).delete()
        db.query(TrainingSubmission).filter(TrainingSubmission.session_id == existing.id).delete()
        db.query(TrainingQuestion).filter(TrainingQuestion.session_id == existing.id).delete()
        existing.title = "SBE Governance Training: AOS Decision Discipline"
        existing.description = (
            "EXCO and staff training on Principal authority, financial policy discipline, "
            "Technical / IT tagging, management escalation, cross-department workflows, "
            "urgency classification, grey area handling, and card-based workflow assessment."
        )
        existing.status = "active"
        existing.facilitator_id = "sbe-facilitator"
        existing.training_type = f"sbe_governance:{CONTENT_VERSION}"
        session = existing
    else:
        session = TrainingSession(
            id=DEFAULT_SESSION_ID,
            title="SBE Governance Training: AOS Decision Discipline",
            description=(
                "EXCO and staff training on Principal authority, financial policy discipline, "
                "Technical / IT tagging, management escalation, cross-department workflows, "
                "urgency classification, grey area handling, and card-based workflow assessment."
            ),
            created_by="AOS",
            status="active",
            facilitator_id="sbe-facilitator",
            training_type=f"sbe_governance:{CONTENT_VERSION}",
        )
        db.add(session)
        db.flush()

    questions = build_questions()
    db.add_all(questions)
    db.commit()
    db.refresh(session)
    return session
