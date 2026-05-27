from main import _dashboard_interview_summary, _session_belongs_to_user


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    session = {
        "session_id": "dashboard-test",
        "user_id": "candidate-1",
        "created_at": "2026-05-27T10:00:00Z",
        "completed_at": "2026-05-27T10:35:00Z",
        "round_type": "dsa",
        "target_company": "Amazon",
        "job_role": "Software Engineer",
        "phase": "complete",
        "exchange_count": 3,
        "problem": {"title": "Two Sum"},
        "report": {
            "overall_score": 82,
            "hiring_signal": "Strong hire",
            "summary": "Solved the coding round with clear tradeoffs.",
            "strengths": ["Passed all tests."],
            "weak_areas": ["Explain complexity earlier."],
            "study_plan": ["Practice complexity narration."],
            "parameter_scores": [{"name": "Coding", "score": 85}],
            "topic_mastery": [{"topic": "Hash Table", "mastery": 80}],
            "round_breakdown": {
                "round_score": 84,
                "problem": {"title": "Two Sum"},
                "evidence": [{"role": "candidate", "content": "Used a map."}],
            },
            "integrity": {"score": 100},
        },
    }

    assert_true(_session_belongs_to_user(session, "candidate-1"), "Dashboard should include owned sessions.")
    assert_true(not _session_belongs_to_user(session, "candidate-2"), "Dashboard should exclude other users.")

    summary = _dashboard_interview_summary(session)
    assert_true(summary["session_id"] == "dashboard-test", "Summary should preserve session id.")
    assert_true(summary["has_report"], "Cached reports should be detected.")
    assert_true(summary["overall_score"] == 82, "Summary should expose overall score.")
    assert_true(summary["target_company"] == "Amazon", "Summary should expose company.")
    assert_true(summary["problem_title"] == "Two Sum", "Summary should expose problem title.")

    legacy_session = {**session, "session_id": "legacy", "user_id": ""}
    assert_true(_session_belongs_to_user(legacy_session, "local-user"), "Legacy sessions without user ids should appear for the local user.")

    print("Dashboard summary baseline passed")


if __name__ == "__main__":
    main()
