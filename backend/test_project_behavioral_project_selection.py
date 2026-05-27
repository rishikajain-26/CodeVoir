from app.orchestration.project_behavioral_graph import (
    _detect_candidate_project_choice,
    _evaluate_answer,
    _extract_resume_signals,
    _greeting_evaluation,
    _project_switch_evaluation,
    _select_followup_intent,
    _memory_node,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_candidate_named_project_is_respected():
    resume_data = {
        "skills": ["Python", "NLP"],
        "projects": [
            {
                "name": "Traffic Agent Simulation",
                "description": "Developed 3 agent-based models to evaluate the economic impact of a traffic lane change.",
                "technologies": ["Python", "Mesa"],
            }
        ],
    }
    choice = _detect_candidate_project_choice(
        "OK, I will be explaining my NLP project which is an AI debate judge.",
        resume_data,
        {},
    )
    signals = _extract_resume_signals(resume_data, {"skills": ["Python"]}, choice)

    assert_true(choice["name"] == "AI debate judge", "Candidate-selected project should be extracted from the answer.")
    assert_true(signals["selected_project"] == "AI debate judge", "Resume focus should follow the candidate-selected project.")
    assert_true(signals["selected_project_source"] == "candidate", "Free-text candidate project should be marked as candidate-selected.")
    assert_true("Traffic Agent Simulation" not in signals["selected_project"], "First resume project should not override the candidate choice.")


def test_selected_project_persists_after_generic_followup_answer():
    previous = {
        "candidate_selected_project": {
            "name": "AI debate judge",
            "source": "candidate",
            "summary": "Candidate chose an NLP project called AI debate judge.",
        }
    }
    resume_data = {
        "skills": ["Python", "NLP"],
        "projects": [
            {
                "name": "Traffic Agent Simulation",
                "description": "Developed 3 agent-based models to evaluate the economic impact of a traffic lane change.",
            }
        ],
    }
    choice = _detect_candidate_project_choice(
        "I built the scoring pipeline and changed the evaluation prompts based on edge cases.",
        resume_data,
        previous,
    )
    signals = _extract_resume_signals(resume_data, {"skills": ["Python"]}, choice)

    assert_true(signals["selected_project"] == "AI debate judge", "Generic follow-up answers should keep the chosen project.")


def test_memory_stores_candidate_selected_project():
    state = {
        "session": {
            "project_behavioral": {},
            "target_company": "AQR Capital Management",
        },
        "user_text": "I will explain my NLP project which is an AI debate judge.",
        "answer_evaluation": {},
        "strategy": {},
        "company_profile": {"company": "AQR Capital Management"},
        "resume_signals": {
            "selected_project": "AI debate judge",
            "selected_project_source": "candidate",
            "candidate_selected_project": "AI debate judge",
            "project_summary": "Candidate chose an NLP project called AI debate judge.",
        },
        "jd_signals": {},
    }
    memory = _memory_node(state)["project_behavioral"]

    assert_true(
        memory["candidate_selected_project"]["name"] == "AI debate judge",
        "Project + Behavioural memory should persist the candidate-selected project.",
    )


def test_project_switch_request_asks_for_new_project():
    resume_signals = {
        "selected_project": "AI debate judge",
        "project_count": 1,
    }
    evaluation = _project_switch_evaluation(resume_signals)

    assert_true(evaluation["followup_intent"] == "switch_project", "Switch request should be treated as a control intent.")
    assert_true("Which project" in evaluation["next_question"], "Switch request should ask the candidate to name the new project.")
    assert_true("AI debate judge" in evaluation["next_question"], "Switch question should mention the current project context.")


def test_greeting_only_gets_interview_nudge():
    evaluation = _greeting_evaluation({"selected_project": "AI debate judge"})

    assert_true(evaluation["followup_intent"] == "phase_default", "Greeting should not be treated as project switch.")
    assert_true("Let us continue" in evaluation["next_question"], "Greeting should nudge the candidate back to the active project.")


def test_pending_switch_accepts_plain_project_name():
    previous = {
        "pending_project_switch": True,
        "candidate_selected_project": {
            "name": "AI debate judge",
            "source": "candidate",
            "summary": "Candidate chose an NLP project called AI debate judge.",
        },
    }
    resume_data = {
        "skills": ["Python"],
        "projects": [
            {
                "name": "Traffic Agent Simulation",
                "description": "Developed 3 agent-based models to evaluate the economic impact of a traffic lane change.",
            }
        ],
    }
    choice = _detect_candidate_project_choice("Traffic Agent Simulation", resume_data, previous)
    signals = _extract_resume_signals(resume_data, {"skills": ["Python"]}, choice)

    assert_true(signals["selected_project"] == "Traffic Agent Simulation", "Pending switch should accept a plain project name.")


def test_pending_switch_cleans_discuss_on_project_name():
    previous = {
        "pending_project_switch": True,
        "candidate_selected_project": {"name": "AI debate judge", "source": "candidate"},
    }
    choice = _detect_candidate_project_choice(
        "I want to discuss on the Grid Hero app which is AC and Java based game.",
        {"skills": [], "projects": []},
        previous,
    )

    assert_true(choice["name"] == "Grid Hero app", "Project switch should not store names like 'on the Grid Hero app'.")


def test_observable_outcome_does_not_repeat_quantify_followup():
    evaluation = _evaluate_answer(
        "The main outcome was unbiased debate judging, free from human personal biases and hyped up speakers.",
        {},
        {"selected_project": "AI debate judge", "project_count": 1, "project_summary": "AI debate judge"},
        {},
        {},
        {},
    )
    previous = {
        "turns": [
            {
                "followup_intent": "quantify_impact",
                "next_question": "What measurable or observable result came from your work on AI debate judge?",
            }
        ]
    }
    next_intent = _select_followup_intent(evaluation, previous)

    assert_true(evaluation["has_observable_result"], "Qualitative project outcomes should count as observable results.")
    assert_true(next_intent != "quantify_impact", "Interviewer should not repeat the same quantify-impact follow-up.")


if __name__ == "__main__":
    test_candidate_named_project_is_respected()
    test_selected_project_persists_after_generic_followup_answer()
    test_memory_stores_candidate_selected_project()
    test_project_switch_request_asks_for_new_project()
    test_greeting_only_gets_interview_nudge()
    test_pending_switch_accepts_plain_project_name()
    test_pending_switch_cleans_discuss_on_project_name()
    test_observable_outcome_does_not_repeat_quantify_followup()
    print("Project + Behavioural project selection passed")
