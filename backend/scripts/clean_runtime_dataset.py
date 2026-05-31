import json
import re
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"

SUPPORTED_TYPES = {
    "int",
    "bool",
    "str",
    "List[int]",
    "List[str]",
    "List[List[int]]",
    "ListNode",
    "Optional[ListNode]",
    "TreeNode",
    "Optional[TreeNode]",
}

SUPPORTED_RETURN_TYPES = {
    "int",
    "bool",
    "str",
    "List[int]",
    "ListNode",
    "Optional[ListNode]",
    "TreeNode",
    "Optional[TreeNode]",
}

BAD_OUTPUT_PATTERNS = (
    "error:",
    "traceback",
    "exception",
    "list index out of range",
    "missing ",
    "unexpected keyword",
)


def split_top_level(text: str) -> list[str]:
    parts = []
    start = 0
    depth = 0
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in "[<(":
            depth += 1
        elif char in "]>)":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def split_signature(starter_code: str) -> tuple[str, list[tuple[str, str]], str]:
    solution_match = re.search(r"class\s+Solution\s*:\s*([\s\S]*)", starter_code or "")
    search_area = solution_match.group(1) if solution_match else (starter_code or "")
    match = re.search(r"def\s+(\w+)\s*\(\s*self\s*(?:,\s*(.*?))?\)\s*->\s*([^:]+):", search_area, re.S)
    if not match:
        return "", [], "Any"
    params = []
    for part in split_top_level(match.group(2) or ""):
        if ":" not in part:
            params.append((part.strip(), "Any"))
            continue
        name, annotation = part.split(":", 1)
        params.append((name.strip(), clean_type(annotation)))
    return match.group(1), params, clean_type(match.group(3))


def clean_type(value: str) -> str:
    value = value.strip().strip("\"'")
    value = value.replace("typing.", "")
    return re.sub(r"\s+", "", value)


def parse_assignments(raw_input: str) -> dict[str, str]:
    text = raw_input.strip()
    text = re.sub(r"^Input:\s*", "", text, flags=re.I).strip()
    assignments = {}
    for part in split_top_level(text):
        if "=" in part:
            name, value = part.split("=", 1)
            assignments[name.strip()] = value.strip()
    return assignments


def normalize_literal_text(text: str) -> str:
    text = re.sub(r"\bNone\b", "null", str(text))
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    return text


def bad_expected_output(value: str) -> bool:
    lowered = str(value).lower()
    if lowered.strip() == "none":
        return True
    return any(pattern in lowered for pattern in BAD_OUTPUT_PATTERNS)


def case_matches_signature(case: dict[str, Any], params: list[tuple[str, str]]) -> bool:
    assignments = parse_assignments(case.get("input", ""))
    if not assignments:
        return len(params) <= 1
    param_names = {name for name, _type in params}
    return set(assignments).issubset(param_names) and all(name in assignments for name, _type in params)


def supported_problem(problem: dict[str, Any]) -> tuple[bool, list[tuple[str, str]], str]:
    _method, params, return_type = split_signature(problem.get("starter_code", {}).get("python", ""))
    param_types = [annotation for _name, annotation in params]
    return all(t in SUPPORTED_TYPES for t in param_types) and return_type in SUPPORTED_RETURN_TYPES, params, return_type


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    cleaned = []
    removed_unsupported = 0
    removed_no_cases = 0
    removed_cases = 0
    for problem in problems:
        ok, params, _return_type = supported_problem(problem)
        if not ok:
            removed_unsupported += 1
            continue
        good_cases = []
        for case in problem.get("testcases", []):
            if bad_expected_output(case.get("expected_output", "")):
                removed_cases += 1
                continue
            if not case_matches_signature(case, params):
                removed_cases += 1
                continue
            case = dict(case)
            case["input"] = normalize_literal_text(case.get("input", ""))
            case["expected_output"] = normalize_literal_text(case.get("expected_output", ""))
            case["visible"] = True
            good_cases.append(case)
        if not good_cases:
            removed_no_cases += 1
            continue
        problem["testcases"] = good_cases[:3]
        problem["examples"] = [
            {"input": case["input"].strip(), "output": case["expected_output"], "explanation": ""}
            for case in problem["testcases"]
        ]
        problem["topics"] = []
        problem["python_check"] = ""
        cleaned.append(problem)

    DATA_PATH.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"kept={len(cleaned)} removed_unsupported={removed_unsupported} removed_no_cases={removed_no_cases} removed_cases={removed_cases}")


if __name__ == "__main__":
    main()
