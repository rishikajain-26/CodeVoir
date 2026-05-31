import json
import re
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    leaked_prompts = [
        problem["title"]
        for problem in problems
        if re.search(r"\bExample\s+\d+\s*:|\bConstraints\s*:", problem.get("prompt", ""), re.I)
    ]
    bad_cpp = []
    duplicate_cpp_support = []
    for problem in problems:
        cpp = problem.get("starter_code", {}).get("cpp", "")
        if re.search(r"\b__init__\b|\bNone\b|List\[|Optional\[", cpp):
            bad_cpp.append(problem["title"])
        if "struct TreeNode" in cpp or "struct ListNode" in cpp:
            duplicate_cpp_support.append(problem["title"])
        if "javascript" in problem.get("starter_code", {}):
            duplicate_cpp_support.append(problem["title"])

    hidden_cases = [
        problem["title"]
        for problem in problems
        if any(case.get("visible") is False for case in problem.get("testcases", []))
    ]
    too_many_cases = [
        problem["title"]
        for problem in problems
        if len(problem.get("testcases", [])) > 3
    ]
    bad_expected_cases = [
        problem["title"]
        for problem in problems
        for case in problem.get("testcases", [])
        if any(pattern in str(case.get("expected_output", "")).lower() for pattern in ("error:", "traceback", "exception", "list index out of range", "unexpected keyword"))
        or str(case.get("expected_output", "")).strip().lower() == "none"
    ]
    bad_topics = [
        problem["title"]
        for problem in problems
        if problem.get("topics")
    ]

    print(f"problems={len(problems)}")
    print(f"leaked_prompts={len(leaked_prompts)}")
    print(f"bad_cpp={len(bad_cpp)}")
    print(f"duplicate_cpp_support_or_js={len(duplicate_cpp_support)}")
    print(f"hidden_cases={len(hidden_cases)}")
    print(f"too_many_cases={len(too_many_cases)}")
    print(f"bad_expected_cases={len(bad_expected_cases)}")
    print(f"bad_topics={len(bad_topics)}")
    if leaked_prompts or bad_cpp or duplicate_cpp_support or hidden_cases or too_many_cases or bad_expected_cases or bad_topics:
        print("sample_leaked_prompts=", leaked_prompts[:10])
        print("sample_bad_cpp=", bad_cpp[:10])
        print("sample_duplicate_cpp_support_or_js=", duplicate_cpp_support[:10])
        print("sample_hidden_cases=", hidden_cases[:10])
        print("sample_too_many_cases=", too_many_cases[:10])
        print("sample_bad_expected_cases=", bad_expected_cases[:10])
        print("sample_bad_topics=", bad_topics[:10])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
