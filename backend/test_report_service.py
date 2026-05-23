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
            "turns": [{"phase": "project_deep_dive", "answer_excerpt": "I owned the backend APIs.", "scores": {"ownership": 7}, "flags": []}],
        },
    ))
    assert_true(project_report["round_breakdown"]["type"] == "project_behavioral", "Project report should include project breakdown.")
    assert_true("AI Interview Platform" in " ".join(project_report["strengths"]), "Project report should use resume project evidence.")

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
            "questions_asked": [{"topic": "DBMS", "question_type": "concept", "answer_excerpt": "Transactions group operations.", "scores": {"clarity": 8}}],
        },
    ))
    assert_true(cs_report["round_breakdown"]["type"] == "cs_fundamentals", "CS report should include CS breakdown.")
    assert_true(cs_report["round_breakdown"]["scratchpad_observations"], "CS report should include scratchpad evidence.")

    print("Report service baseline passed")


if __name__ == "__main__":
    main()
