"""Behavioral & HR question bank with rubrics for campus placement and engineering hiring."""
import random
from typing import Any, Dict, List, Optional

HR_TRACKS = [
    {
        "id": "leadership_ownership",
        "title": "Leadership & Personal Ownership",
        "icon": "military_tech",
        "desc": "Demonstrating individual initiative, end-to-end accountability, and bias for action.",
        "rubric_focus": "Evaluates 'I' vs 'we' ownership, personal conviction, and proactive problem solving without waiting for instructions.",
    },
    {
        "id": "conflict_resilience",
        "title": "Conflict Resolution & Collaboration",
        "icon": "handshake",
        "desc": "Navigating difficult disagreements with peers, seniors, or cross-functional stakeholders.",
        "rubric_focus": "Evaluates emotional intelligence, active listening, de-escalation, and finding win-win technical consensus.",
    },
    {
        "id": "failure_adaptability",
        "title": "Failure, Mistakes & Resilience",
        "icon": "restart_alt",
        "desc": "Admitting past miscalculations, taking accountability, and bouncing back with maturity.",
        "rubric_focus": "Evaluates humility, root-cause self-awareness, and concrete corrective systems put in place.",
    },
    {
        "id": "culture_motivation",
        "title": "Company Motivation & Culture Fit",
        "icon": "domain",
        "desc": "Explaining genuine organizational fit, long-term engineering vision, and ethics.",
        "rubric_focus": "Evaluates depth of research into the company, value alignment, and intrinsic motivation.",
    },
    {
        "id": "ambiguity_prioritization",
        "title": "Ambiguity & Prioritization",
        "icon": "alt_route",
        "desc": "Thriving under shifting requirements, tight deadlines, and competing stakeholder demands.",
        "rubric_focus": "Evaluates triage frameworks, trade-off communication, and pragmatic delivery.",
    },
]

# Curated core behavioral interview question bank
HR_QUESTIONS = [
    # 1. Leadership & Personal Ownership
    {
        "id": "hr_lead_01",
        "track": "leadership_ownership",
        "text": "Tell me about a time you identified a major flaw or bottleneck in a project and took complete ownership to fix it without being asked.",
        "rubric": {
            "green_flags": ["Explicit personal agency ('I investigated', 'I drafted')", "Quantified result", "Proactive communication with team"],
            "red_flags": ["Passive language ('We kind of decided')", "Taking credit for team's work without clear personal action", "Lack of measurable outcome"],
        },
    },
    {
        "id": "hr_lead_02",
        "track": "leadership_ownership",
        "text": "Describe a situation where a teammate was underperforming or missing deadlines on a critical deliverable. How did you handle it?",
        "rubric": {
            "green_flags": ["Direct, empathetic 1-on-1 communication", "Focus on unblocking rather than finger-pointing", "Delivering the project on time"],
            "red_flags": ["Complaining to management immediately", "Ignoring the issue and letting project suffer", "Aggressive confrontation"],
        },
    },
    {
        "id": "hr_lead_03",
        "track": "leadership_ownership",
        "text": "Can you share an experience where you had to persuade peers or stakeholders to adopt your technical proposal over an alternative?",
        "rubric": {
            "green_flags": ["Data-driven evidence and trade-off comparison", "Respect for opposing viewpoints", "Clear post-decision alignment"],
            "red_flags": ["Pushing authority without evidence", "Dismissing other opinions as stupid", "Grudging compromise"],
        },
    },

    # 2. Conflict & Collaboration
    {
        "id": "hr_conf_01",
        "track": "conflict_resilience",
        "text": "Tell me about a time you strongly disagreed with a decision made by a project lead or manager. How did you communicate your dissent, and what was the outcome?",
        "rubric": {
            "green_flags": ["Disagree and commit mentality", "Professional framing with data/trade-offs", "Support for final team direction"],
            "red_flags": ["Passive-aggressive resistance", "Undermining the decision behind closed doors", "Blind obedience without sharing concerns"],
        },
    },
    {
        "id": "hr_conf_02",
        "track": "conflict_resilience",
        "text": "Describe a scenario where you received harsh or unexpected constructive feedback on your code, design, or behavior. How did you react?",
        "rubric": {
            "green_flags": ["Emotional maturity and listening", "Asking clarifying questions", "Concrete behavioral or technical adjustment"],
            "red_flags": ["Defensiveness and excuse-making", "Blaming the reviewer", "Ignoring feedback"],
        },
    },

    # 3. Failure & Resilience
    {
        "id": "hr_fail_01",
        "track": "failure_adaptability",
        "text": "Tell me about your biggest technical or project failure. What went wrong, what was your role in the breakdown, and what did you learn?",
        "rubric": {
            "green_flags": ["Genuine vulnerability and accountability ('My assumption was wrong')", "Concrete post-mortem analysis", "Preventative systems created"],
            "red_flags": ["Fake failure ('I cared too much about quality')", "Blaming teammates or third parties entirely", "No lasting takeaway"],
        },
    },
    {
        "id": "hr_fail_02",
        "track": "failure_adaptability",
        "text": "Describe a project where you realized halfway through that you were going to miss the deadline. How did you handle stakeholder expectations?",
        "rubric": {
            "green_flags": ["Early proactive communication (bad news early)", "Offering scoped-down MVP options", "Clear mitigation roadmap"],
            "red_flags": ["Waiting until deadline day to disclose delay", "Hoping nobody notices", "Blaming external circumstances"],
        },
    },

    # 4. Motivation & Culture Fit
    {
        "id": "hr_cult_01",
        "track": "culture_motivation",
        "text": "Why are you interested in joining our engineering team specifically, and how do our company values align with how you work best?",
        "rubric": {
            "green_flags": ["Specific knowledge of company's technical architecture or mission", "Genuine cultural resonance", "Clear career trajectory"],
            "red_flags": ["Generic platitudes ('You are a market leader')", "Focus solely on compensation or brand status", "Zero specific knowledge"],
        },
    },
    {
        "id": "hr_cult_02",
        "track": "culture_motivation",
        "text": "Where do you see your engineering craftsmanship evolving over the next 2 to 3 years, and what environment brings out your best performance?",
        "rubric": {
            "green_flags": ["Self-awareness regarding growth areas", "Desire for mentorship and high-bar collaboration", "Clear goals"],
            "red_flags": ["Unrealistic grandiosity", "Apathetic / aimless response", "Wanting to coast"],
        },
    },

    # 5. Ambiguity & Prioritization
    {
        "id": "hr_ambi_01",
        "track": "ambiguity_prioritization",
        "text": "Tell me about a time you were tasked with building something with ambiguous, incomplete, or rapidly shifting specifications. How did you proceed?",
        "rubric": {
            "green_flags": ["Proactive stakeholder clarification", "Developing a phased prototype/MVP to de-risk assumptions", "Iterative validation"],
            "red_flags": ["Paralysis by analysis", "Building in isolation without checking assumptions", "Frustrated complaining about management"],
        },
    },
]


def get_hr_tracks() -> List[Dict[str, Any]]:
    """Return available behavioral interview tracks."""
    return HR_TRACKS


def get_curated_hr_questions(track: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve questions filtered by track or all."""
    if not track or track == "all" or track == "standard_hr":
        return HR_QUESTIONS
    return [q for q in HR_QUESTIONS if q["track"] == track]


def get_initial_hr_question(track: str = "standard_hr", company: Optional[str] = None) -> Dict[str, Any]:
    """Pick an appropriate opening question tailored to track and company."""
    if track == "culture_motivation":
        company_label = company or "our company"
        return {
            "id": "hr_q1_cult",
            "track": "culture_motivation",
            "text": f"To begin, why are you interested in joining {company_label} specifically, and how do our engineering values align with how you work best?",
            "rubric": HR_QUESTIONS[7]["rubric"],
        }
    elif track == "leadership_ownership":
        return HR_QUESTIONS[0]
    elif track == "conflict_resilience":
        return HR_QUESTIONS[3]
    elif track == "failure_adaptability":
        return HR_QUESTIONS[5]
    elif track == "ambiguity_prioritization":
        return HR_QUESTIONS[9]

    # Standard HR defaults to an ice-breaking ownership question
    return {
        "id": "hr_q1_intro",
        "track": "leadership_ownership",
        "text": "Can you walk me through a significant project or challenge you took personal ownership of, highlighting the situation, your specific role, and the final impact?",
        "rubric": HR_QUESTIONS[0]["rubric"],
    }
