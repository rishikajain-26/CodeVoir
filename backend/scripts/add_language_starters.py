import json
from pathlib import Path

from export_leetcode_dataset import c_starter, cpp_starter, java_starter


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for problem in problems:
        starters = problem.setdefault("starter_code", {})
        python_starter = starters.get("python", "")
        starters["cpp"] = cpp_starter(python_starter)
        starters["java"] = java_starter(python_starter)
        starters["c"] = c_starter(python_starter)
    DATA_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated starters for {len(problems)} problems")


if __name__ == "__main__":
    main()
