import asyncio
import os

from main import MessageRequest, SESSIONS, StartSessionRequest, interview_message, start_session


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
            round_type="cs_fundamentals",
            timer_minutes=30,
        )
    )

    session_id = created["session_id"]
    session = SESSIONS[session_id]

    assert_true(session["round_type"] == "cs_fundamentals", "CS session should use cs_fundamentals round type.")
    assert_true(session["llm_enabled"] is False, "No-key CS baseline should not enable LLM calls.")
    assert_true(session["round_config"].get("topics") or session["round_config"].get("fallback_topics"), "CS session should have topic config.")
    assert_true("scratchpad" in created["ai_text"].lower(), "Opening prompt should mention optional scratchpad.")

    reply = await interview_message(
        MessageRequest(
            session_id=session_id,
            user_text="A database transaction is a set of operations that should be committed together. ACID helps with correctness and consistency in a backend system.",
            scratchpad={
                "mode": "sql",
                "content": "BEGIN; UPDATE accounts SET balance = balance - 100 WHERE id = 1; UPDATE accounts SET balance = balance + 100 WHERE id = 2; COMMIT;",
            },
        )
    )

    memory = session.get("cs_fundamentals", {})

    assert_true(reply["ai_text"], "CS graph should return an interviewer question.")
    assert_true(reply["phase"] == "cs_fundamentals", "CS graph should keep cs_fundamentals phase.")
    assert_true(memory.get("current_topic"), "CS graph should store current topic.")
    assert_true(memory.get("questions_asked"), "CS graph should store question history.")
    assert_true(memory.get("scratchpad_history"), "CS graph should store scratchpad history when provided.")
    assert_true(session.get("scratchpad_history"), "Session should retain raw scratchpad history.")

    print("CS Fundamentals baseline passed")


if __name__ == "__main__":
    asyncio.run(main())
