import asyncio
import os

from main import interview_companies, interview_company_config, interview_round_options, llm_status


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


async def main():
    os.environ["GROQ_API_KEY"] = ""
    os.environ["GEMINI_API_KEY"] = ""

    options = await interview_round_options()
    round_ids = {round_info["id"] for round_info in options["rounds"]}

    assert_true("dsa" in round_ids, "Round options should include DSA.")
    assert_true("project_behavioral" in round_ids, "Round options should include Project + Behavioural.")
    assert_true("cs_fundamentals" in round_ids, "Round options should include CS Fundamentals metadata.")
    assert_true(options["dataset"]["company_count"] >= 400, "Round options should expose master dataset summary.")

    dsa_companies = await interview_companies("dsa")
    project_companies = await interview_companies("combined")
    cs_companies = await interview_companies("cs_fundamentals")

    assert_true(dsa_companies["company_count"] >= 400, "DSA should expose broad company coverage.")
    assert_true(project_companies["round_type"] == "project_behavioral", "combined should map to project_behavioral.")
    assert_true(project_companies["company_count"] >= dsa_companies["company_count"], "Project + Behavioural should have broad fallback coverage.")
    assert_true(cs_companies["company_count"] >= 50, "CS Fundamentals should expose evidence-backed companies.")

    walmart_config = await interview_company_config("Walmart", "project_behavioral")
    assert_true(walmart_config["round_type"] == "project_behavioral", "Company config should normalize round type.")
    assert_true("scale" in " ".join(walmart_config["config"].get("focus_areas", [])).lower(), "Walmart profile should include scale/practical focus.")

    status = await llm_status()
    assert_true(status["provider"] == "local", "No-key LLM status should be local.")
    assert_true(status["configured"] is False, "No-key LLM status should be unconfigured.")

    print("Round metadata API baseline passed")


if __name__ == "__main__":
    asyncio.run(main())
