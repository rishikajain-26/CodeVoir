import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for problem in problems:
        visible = [case for case in problem.get("testcases", []) if case.get("visible", True)]
        if not visible:
            visible = problem.get("testcases", [])[:3]
        visible = visible[:3]
        for case in visible:
            case["visible"] = True
        problem["testcases"] = visible
        problem["examples"] = [
            {
                "input": case.get("input", "").strip(),
                "output": case.get("expected_output", ""),
                "explanation": "",
            }
            for case in visible
        ]
    DATA_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kept only visible testcases for {len(problems)} problems")


if __name__ == "__main__":
    main()
