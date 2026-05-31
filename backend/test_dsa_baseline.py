import asyncio
import os

from main import (
    CodeSubmitRequest,
    MessageRequest,
    SESSIONS,
    StartSessionRequest,
    interview_message,
    start_session,
    submit_code,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


async def main():
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""

    created = await start_session(
        StartSessionRequest(
            job_role="Software Engineer",
            experience_level="fresher",
            target_company="Amazon",
            round_type="dsa",
            difficulty="medium",
            timer_minutes=35,
        )
    )

    session_id = created["session_id"]
    session = SESSIONS[session_id]

    assert_true(created["status"] == "created", "DSA session should be created.")
    assert_true(created["problem"]["title"], "DSA session should include a selected problem.")
    assert_true(created["languages"]["python"] == "Python", "DSA languages should include Python.")
    assert_true(session["round_type"] == "dsa", "Session round_type should remain dsa.")
    assert_true(session["phase"] == "dsa", "DSA session should start in dsa phase.")
    assert_true(session["llm_enabled"] is False, "No-key baseline should not enable LLM calls.")

    message = await interview_message(
        MessageRequest(
            session_id=session_id,
            user_text=(
                "I would first clarify the input and constraints, then use a hash map or "
                "dynamic programming approach depending on the repeated subproblem structure. "
                "I will state time and space complexity before coding."
            ),
        )
    )

    assert_true(message["ai_text"], "DSA interview message should return interviewer text.")
    assert_true(message["phase"] == "dsa", "DSA message should keep dsa phase active.")
    assert_true(message["round_complete"] is False, "DSA round should not complete after one message.")
    assert_true(message["question_count"] == 1, "DSA question count should increment.")

    submitted = await submit_code(
        CodeSubmitRequest(
            session_id=session_id,
            language="python",
            code="print('baseline')\n",
        )
    )

    assert_true("ai_text" in submitted, "Code submission should return review text.")
    assert_true("result" in submitted, "Code submission should include execution result.")
    assert_true(submitted["phase"] == "dsa", "Code submission should keep dsa phase active.")
    assert_true(isinstance(session["code_runs"], list), "Session should track code runs.")

    print("DSA baseline passed")


if __name__ == "__main__":
    asyncio.run(main())
