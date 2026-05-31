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
            job_role="Backend Engineer",
            experience_level="fresher",
            target_company="Walmart",
            job_description=(
                "Build reliable FastAPI and React services using PostgreSQL, Docker, "
                "testing, customer impact, and scalable API design."
            ),
            round_type="project_behavioral",
            timer_minutes=35,
        )
    )

    session_id = created["session_id"]
    session = SESSIONS[session_id]
    session["resume_data"] = {
        "skills": ["FastAPI", "React", "PostgreSQL", "Docker", "Testing"],
        "projects": [
            {
                "name": "AI Interview Platform",
                "description": "Built a React and FastAPI platform with resume parsing, coding rounds, and interview reports.",
                "technologies": ["React", "FastAPI", "PostgreSQL", "Docker"],
            }
        ],
    }

    assert_true(session["round_type"] == "project_behavioral", "Project + Behavioural session should use normalized round type.")
    assert_true(session["llm_enabled"] is False, "No-key Project + Behavioural baseline should not enable LLM calls.")
    assert_true(session["round_config"]["interview_style"], "Project + Behavioural session should store round config.")

    reply = await interview_message(
        MessageRequest(
            session_id=session_id,
            user_text=(
                "I owned the FastAPI backend for the AI Interview Platform. I designed the session APIs, "
                "connected the React frontend, added Docker-based setup, and improved reliability by testing "
                "resume upload and interview message flows for repeated user sessions."
            ),
        )
    )

    memory = session.get("project_behavioral", {})

    assert_true(reply["ai_text"], "Project + Behavioural graph should return an interviewer question.")
    assert_true(reply["phase"] == "resume_walkthrough", "First Project + Behavioural turn should be resume walkthrough.")
    assert_true(memory.get("company_profile") == "Walmart", "Graph should use master data company profile.")
    assert_true(memory.get("jd_signals", {}).get("skills"), "Graph should extract JD skill signals.")
    assert_true(memory.get("resume_focus", {}).get("selected_project") == "AI Interview Platform", "Graph should use resume project focus.")
    assert_true(memory.get("round_config", {}).get("focus_areas"), "Graph memory should include round config focus areas.")

    print("Project + Behavioural baseline passed")


if __name__ == "__main__":
    asyncio.run(main())
