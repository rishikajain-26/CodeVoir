from app.services.report_service import build_feedback_report


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


BASE_SESSION = {
    "session_id": "report-test",
    "target_company": "Amazon",
    "job_role": "Software Engineer",
    "scores": {"clarity": [4], "depth": [3], "relevance": [4], "structure": [3], "confidence": [4]},
    "violations": [],
    "behavioral_signals": {"focus_loss": 0, "paste_events": 0, "large_pastes": 0, "idle_gaps": 0, "voice_turns": 1},
    "behavior_log": [],
    "weak_areas": [],
    "messages": [{"role": "candidate", "content": "I explained my approach with tradeoffs."}],
    "hint_count": 0,
    "code_runs": [],
}


def session_with(**updates):
    session = {**BASE_SESSION}
    session.update(updates)
    return session


def main():
    dsa_report = build_feedback_report(session_with(
        round_type="dsa",
        problem={"title": "Two Sum", "difficulty": "Easy", "topics": ["Hash Table"], "companies": ["Amazon"]},
        code_runs=[{"language": "python", "passed_testcases": 2, "total_testcases": 3, "overall_score": 66.7}],
    ))
    assert_true(dsa_report["round_breakdown"]["type"] == "dsa", "DSA report should include DSA breakdown.")
    assert_true("Tests:" in " ".join(dsa_report["round_breakdown"]["strengths"] + dsa_report["round_breakdown"]["weak_areas"]) or dsa_report["round_breakdown"]["submission"]["total_testcases"] == 3, "DSA report should use test evidence.")

    project_report = build_feedback_report(session_with(
        round_type="project_behavioral",
        project_behavioral={
            "company_profile": "Amazon",
            "company_style": "ownership-heavy",
            "resume_focus": {"selected_project": "AI Interview Platform"},
            "jd_signals": {"skills": ["FastAPI", "Docker"]},
            "latest_scores": {"specificity": 8, "ownership": 7, "technical_depth": 7, "impact": 5, "reflection": 6},
            "latest_flags": ["Impact is not quantified."],
            "turns": [{"phase": "project_deep_dive", "answer_text": "In the AI Interview Platform, I owned the backend APIs for sessions and reports, connected the React flow, and tested repeated interview message paths.", "answer_excerpt": "In the AI Interview Platform, I owned the backend APIs for sessions and reports, connected the React flow, and tested repeated interview message paths.", "scores": {"ownership": 7}, "flags": []}],
        },
    ))
    assert_true(project_report["round_breakdown"]["type"] == "project_behavioral", "Project report should include project breakdown.")
    assert_true("AI Interview Platform" in " ".join(project_report["strengths"]), "Project report should use candidate project evidence, not resume-only evidence.")
    assert_true(project_report["parameter_scores"], "Project report should expose realistic parameter scores.")

    resume_only_project_report = build_feedback_report(session_with(
        round_type="project_behavioral",
        project_behavioral={
            "resume_focus": {"selected_project": "Resume Only Project"},
            "latest_scores": {"specificity": 3, "ownership": 3, "technical_depth": 3, "impact": 3, "reflection": 3},
            "turns": [],
        },
    ))
    assert_true(
        "Resume Only Project" not in " ".join(resume_only_project_report["strengths"]),
        "Resume project selection alone should not be reported as a strength.",
    )

    cs_report = build_feedback_report(session_with(
        round_type="cs_fundamentals",
        cs_fundamentals={
            "current_topic": "DBMS",
            "topic_plan": ["DBMS", "Operating Systems"],
            "topics_covered": ["DBMS"],
            "strong_topics": ["DBMS"],
            "weak_topics": ["Operating Systems"],
            "latest_scores": {"clarity": 8, "correctness": 7, "application": 6, "depth": 6, "communication": 8},
            "latest_flags": ["Answer needs a practical example."],
            "scratchpad_history": [{"topic": "DBMS", "mode": "sql", "content": "SELECT * FROM users;"}],
            "questions_asked": [{"topic": "DBMS", "question_type": "concept", "answer_excerpt": "Transactions group operations.", "scores": {"clarity": 8, "correctness": 7, "application": 6, "depth": 6, "communication": 8}}],
        },
    ))
    assert_true(cs_report["round_breakdown"]["type"] == "cs_fundamentals", "CS report should include CS breakdown.")
    assert_true(cs_report["round_breakdown"]["scratchpad_observations"], "CS report should include scratchpad evidence.")
    assert_true(cs_report["parameter_scores"], "CS report should expose parameter scores.")

    wrong_cs_report = build_feedback_report(session_with(
        round_type="cs_fundamentals",
        cs_fundamentals={
            "current_topic": "Computer Networks",
            "topic_plan": ["Computer Networks"],
            "topics_covered": ["Computer Networks"],
            "questions_asked": [{
                "topic": "Computer Networks",
                "question_type": "concept",
                "answer_excerpt": "UDP guarantees delivery and TCP does not guarantee order.",
                "scores": {"clarity": 8, "correctness": 3, "application": 4, "depth": 4, "communication": 8},
                "flags": ["Incorrect concept: UDP does not guarantee delivery or ordering."],
                "misconceptions": ["UDP does not guarantee delivery or ordering."],
            }],
        },
    ))
    correctness = next(item for item in wrong_cs_report["parameter_scores"] if item["name"] == "Correctness")
    depth = next(item for item in wrong_cs_report["parameter_scores"] if item["name"] == "Depth of Understanding")
    assert_true(correctness["score"] <= 45, "Wrong CS answers should not receive correctness credit.")
    assert_true(depth["score"] <= 55, "Wrong CS answers should cap depth credit.")

    print("Report service baseline passed")


if __name__ == "__main__":
    main()
