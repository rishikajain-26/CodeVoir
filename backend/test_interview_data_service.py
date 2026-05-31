from app.services.interview_data_service import (
    get_cs_fundamentals_config,
    get_dsa_config,
    get_project_behavioral_config,
    get_round_config,
    interview_data_service,
    list_companies,
    resolve_company,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    summary = interview_data_service.get_summary()
    companies = list_companies()

    assert_true(summary["company_count"] >= 400, "Master dataset should contain hundreds of companies.")
    assert_true(len(companies) == summary["company_count"], "Company list should match summary count.")

    assert_true(resolve_company("amazon") == "Amazon", "Lowercase company input should resolve.")
    assert_true(resolve_company("Amazon.com") == "Amazon", "Partial company input should resolve.")
    assert_true(resolve_company("walmart") in {"Walmart", "Walmart Labs"}, "Walmart alias should resolve.")
    assert_true(resolve_company("walmart labs") in {"Walmart", "Walmart Labs"}, "Walmart Labs alias should resolve.")

    dsa = get_dsa_config("Amazon")
    assert_true(dsa["round_type"] == "dsa", "DSA config should identify dsa round.")
    assert_true(dsa["question_count"] >= 1, "DSA config should have at least one question.")
    assert_true(dsa["minutes"] >= 10, "DSA config should have a useful duration.")
    assert_true("evaluation_focus" in dsa, "DSA config should include evaluation focus.")

    project_behavioral = get_project_behavioral_config("Walmart")
    assert_true(project_behavioral["round_type"] == "project_behavioral", "Project + Behavioural config should identify its round.")
    assert_true(project_behavioral["interview_style"], "Project + Behavioural config should include interview style.")
    assert_true(project_behavioral["focus_areas"], "Project + Behavioural config should include focus areas.")
    assert_true(project_behavioral["red_flags"], "Project + Behavioural config should include red flags.")

    combined_alias = get_round_config("Amazon", "combined")
    assert_true(combined_alias["round_type"] == "project_behavioral", "Old combined round name should map to project_behavioral.")

    cs = get_cs_fundamentals_config("Amazon")
    assert_true(cs["round_type"] == "cs_fundamentals", "CS config should identify cs_fundamentals round.")
    assert_true(cs["suggested_question_count"] >= 5, "CS config should suggest enough questions.")
    assert_true(cs["topics"] or cs["fallback_topics"], "CS config should include topics or fallbacks.")

    unknown = get_round_config("Unknown Future Company", "cs_fundamentals")
    assert_true(unknown["round_type"] == "cs_fundamentals", "Unknown company should still return requested round.")
    assert_true(unknown["topics"], "Unknown company should use default CS topics.")

    print("Interview data service baseline passed")


if __name__ == "__main__":
    main()
