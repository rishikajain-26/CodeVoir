import json
import re
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sections(text: str) -> tuple[str, list[str]]:
    text = clean_text(text)
    constraints = []
    constraints_match = re.search(r"\bConstraints:\s*(.*)$", text, re.I)
    if constraints_match:
        raw = constraints_match.group(1).strip()
        constraints = [part.strip() for part in re.split(r"\s{2,}|;\s*", raw) if part.strip()]
        text = text[: constraints_match.start()].strip()
    example_match = re.search(r"\bExample\s+\d+\s*:", text, re.I)
    if example_match:
        text = text[: example_match.start()].strip()
    return text, constraints


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cleaned = 0
    for problem in problems:
        prompt, constraints = split_sections(problem.get("prompt", ""))
        if prompt != problem.get("prompt", ""):
            cleaned += 1
        problem["prompt"] = prompt
        if constraints and not problem.get("constraints"):
            problem["constraints"] = constraints
    DATA_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cleaned prompts for {cleaned} problems")


if __name__ == "__main__":
    main()
