import json
import re
from pathlib import Path
from typing import Any

from datasets import load_dataset


OUT_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"
DATASET = "newfacade/LeetCodeDataset"
TARGET_TOTAL = 2800
MAX_TESTS_PER_PROBLEM = 3


def clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_problem_sections(text: str) -> tuple[str, list[str]]:
    text = clean_text(text)
    constraints = []
    constraints_match = re.search(r"\bConstraints:\s*(.*)$", text, re.I)
    if constraints_match:
        constraints_text = constraints_match.group(1).strip()
        constraints = [part.strip() for part in re.split(r"\s{2,}|;\s*", constraints_text) if part.strip()]
        text = text[: constraints_match.start()].strip()
    example_match = re.search(r"\bExample\s+\d+\s*:", text, re.I)
    if example_match:
        text = text[: example_match.start()].strip()
    return text, constraints


def normalize_difficulty(value: str) -> str:
    difficulty = (value or "Medium").strip().title()
    return difficulty if difficulty in {"Easy", "Medium", "Hard"} else "Medium"


def safe_input_output(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    cases = []
    for item in value[:MAX_TESTS_PER_PROBLEM]:
        if not isinstance(item, dict):
            continue
        raw_input = str(item.get("input") or "").strip()
        raw_output = str(item.get("output") or "").strip()
        if raw_input and raw_output:
            cases.append({
                "input": raw_input + "\n",
                "expected_output": raw_output,
                "visible": True,
            })
    return cases


def split_signature(starter_code: str) -> tuple[str, list[tuple[str, str]], str]:
    solution_match = re.search(r"class\s+Solution\s*:\s*([\s\S]*)", starter_code or "")
    search_area = solution_match.group(1) if solution_match else (starter_code or "")
    match = re.search(r"def\s+(\w+)\s*\(\s*self\s*(?:,\s*(.*?))?\)\s*->\s*([^:]+):", search_area, re.S)
    if not match:
        return "", [], "Any"
    method = match.group(1)
    raw_params = match.group(2) or ""
    return_type = match.group(3).strip()
    params = []
    if raw_params.strip():
        for part in split_top_level(raw_params):
            part = part.strip()
            if ":" in part:
                name, annotation = part.split(":", 1)
                params.append((name.strip(), annotation.strip()))
            else:
                params.append((part.strip(), "Any"))
    return method, params, return_type


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
            continue
        if char in "[<(":
            depth += 1
        elif char in "]>)":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def cpp_type(annotation: str, is_return: bool = False) -> str:
    ann = annotation.replace("typing.", "").replace("Optional[", "").replace("]", "")
    compact = re.sub(r"\s+", "", annotation)
    mappings = {
        "int": "int",
        "bool": "bool",
        "float": "double",
        "str": "string",
        "List[int]": "vector<int>",
        "List[str]": "vector<string>",
        "List[float]": "vector<double>",
        "List[bool]": "vector<bool>",
        "List[List[int]]": "vector<vector<int>>",
        "List[List[str]]": "vector<vector<string>>",
        "ListNode": "ListNode*",
        "Optional[ListNode]": "ListNode*",
        "TreeNode": "TreeNode*",
        "Optional[TreeNode]": "TreeNode*",
    }
    result = mappings.get(compact) or mappings.get(ann) or "auto"
    if result.startswith("vector") and not is_return:
        return f"{result}&"
    return result


def cpp_starter(starter_code: str) -> str:
    method, params, return_type = split_signature(starter_code)
    if not method:
        return "#include <bits/stdc++.h>\nusing namespace std;\n\nclass Solution {\npublic:\n    // TODO\n};\n"
    cpp_params = ", ".join(f"{cpp_type(annotation)} {name}" for name, annotation in params)
    ret = cpp_type(return_type, is_return=True)
    default_return = "return {};" if ret.startswith("vector") else "return false;" if ret == "bool" else "return \"\";" if ret == "string" else "return nullptr;" if ret.endswith("*") else "return 0;"
    return f"#include <bits/stdc++.h>\nusing namespace std;\n\nclass Solution {{\npublic:\n    {ret} {method}({cpp_params}) {{\n        {default_return}\n    }}\n}};\n"


def java_type(annotation: str, is_return: bool = False) -> str:
    compact = re.sub(r"\s+", "", annotation)
    mappings = {
        "int": "int",
        "bool": "boolean",
        "float": "double",
        "str": "String",
        "List[int]": "int[]",
        "List[str]": "String[]",
        "List[float]": "double[]",
        "List[bool]": "boolean[]",
        "List[List[int]]": "int[][]",
        "List[List[str]]": "String[][]",
        "ListNode": "ListNode",
        "Optional[ListNode]": "ListNode",
        "TreeNode": "TreeNode",
        "Optional[TreeNode]": "TreeNode",
    }
    return mappings.get(compact, "Object")


def java_starter(starter_code: str) -> str:
    method, params, return_type = split_signature(starter_code)
    if not method:
        return "class Solution {\n    // TODO\n}\n"
    java_params = ", ".join(f"{java_type(annotation)} {name}" for name, annotation in params)
    ret = java_type(return_type, is_return=True)
    default_return = "return null;" if ret.endswith("[]") or ret in {"String", "Object", "ListNode", "TreeNode"} else "return false;" if ret == "boolean" else "return 0;"
    return f"class Solution {{\n    public {ret} {method}({java_params}) {{\n        {default_return}\n    }}\n}}\n"


def c_starter(starter_code: str) -> str:
    method, params, return_type = split_signature(starter_code)
    if not method:
        return "#include <stdio.h>\n#include <stdbool.h>\n\n/* TODO */\n"
    c_params = []
    for name, annotation in params:
        compact = re.sub(r"\s+", "", annotation)
        if compact == "int":
            c_params.append(f"int {name}")
        elif compact == "bool":
            c_params.append(f"bool {name}")
        elif compact == "str":
            c_params.append(f"char* {name}")
        elif compact == "List[int]":
            c_params.extend([f"int* {name}", f"int {name}Size"])
        elif compact == "List[List[int]]":
            c_params.extend([f"int** {name}", f"int {name}Size", f"int* {name}ColSize"])
        elif compact == "List[str]":
            c_params.extend([f"char** {name}", f"int {name}Size"])
        elif compact in {"TreeNode", "Optional[TreeNode]"}:
            c_params.append(f"struct TreeNode* {name}")
        elif compact in {"ListNode", "Optional[ListNode]"}:
            c_params.append(f"struct ListNode* {name}")
        else:
            c_params.append(f"/* unsupported {annotation} */ void* {name}")
    compact_ret = re.sub(r"\s+", "", return_type)
    ret = "int"
    extra = ""
    if compact_ret == "bool":
        ret = "bool"
    elif compact_ret == "str":
        ret = "char*"
    elif compact_ret == "List[int]":
        ret = "int*"
        c_params.append("int* returnSize")
        extra = "    *returnSize = 0;\n"
    elif compact_ret in {"TreeNode", "Optional[TreeNode]"}:
        ret = "struct TreeNode*"
    elif compact_ret in {"ListNode", "Optional[ListNode]"}:
        ret = "struct ListNode*"
    default_return = "return false;" if ret == "bool" else "return NULL;" if ret.endswith("*") else "return 0;"
    return f"#include <stdbool.h>\n#include <stdlib.h>\n\n{ret} {method}({', '.join(c_params)}) {{\n{extra}    {default_return}\n}}\n"


def python_starter(starter_code: str) -> str:
    imports = "from typing import *\nfrom collections import *\nfrom functools import *\nfrom itertools import *\nfrom heapq import *\nfrom bisect import *\nimport math\n\n"
    code = (starter_code or "").strip()
    return imports + code + "\n"


def normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    testcases = safe_input_output(item.get("input_output"))
    prompt, constraints = split_problem_sections(item.get("problem_description") or "")
    title = str(item.get("task_id") or "").strip().replace("-", " ").title()
    if not title or len(prompt) < 40 or not testcases:
        return None
    starter = str(item.get("starter_code") or "").strip()
    question_id = item.get("question_id")
    difficulty = normalize_difficulty(item.get("difficulty") or "")
    return {
        "id": str(item.get("task_id") or question_id),
        "title": title,
        "frontend_id": str(question_id or item.get("task_id") or ""),
        "difficulty": difficulty,
        "source": "newfacade/LeetCodeDataset",
        "topics": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "prompt": prompt,
        "constraints": constraints,
        "examples": [
            {"input": case["input"].strip(), "output": case["expected_output"], "explanation": ""}
            for case in testcases[:3]
        ],
        "starter_code": {
            "python": python_starter(starter),
            "cpp": cpp_starter(starter),
            "java": java_starter(starter),
            "c": c_starter(starter),
        },
        "testcases": testcases,
        "hints": [],
        "execution_mode": "leetcode",
        "entry_point": item.get("entry_point") or "",
        "python_check": item.get("test") or "",
    }


def main() -> None:
    selected: dict[str, list[dict[str, Any]]] = {"Easy": [], "Medium": [], "Hard": []}
    target_per_bucket = TARGET_TOTAL // 3
    for split in ("train", "test"):
        dataset = load_dataset(DATASET, split=split, streaming=True)
        for item in dataset:
            problem = normalize_item(item)
            if not problem:
                continue
            bucket = problem["difficulty"]
            if len(selected[bucket]) < target_per_bucket:
                selected[bucket].append(problem)

    problems = []
    for bucket in ("Easy", "Medium", "Hard"):
        problems.extend(selected[bucket])
    OUT_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(problems)} LeetCodeDataset problems to {OUT_PATH}")
    print({bucket: len(items) for bucket, items in selected.items()})


if __name__ == "__main__":
    main()
