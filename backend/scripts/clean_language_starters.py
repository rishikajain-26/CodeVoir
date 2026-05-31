import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def strip_cpp_support_structs(cpp: str) -> str:
    for name in ("ListNode", "TreeNode"):
        marker = f"struct {name}"
        while marker in cpp:
            start = cpp.find(marker)
            brace = cpp.find("{", start)
            if brace == -1:
                break
            depth = 0
            end = brace
            for index in range(brace, len(cpp)):
                if cpp[index] == "{":
                    depth += 1
                elif cpp[index] == "}":
                    depth -= 1
                    if depth == 0:
                        end = index + 1
                        if end < len(cpp) and cpp[end] == ";":
                            end += 1
                        break
            cpp = (cpp[:start] + cpp[end:]).replace("\n\n\n", "\n\n")
    return cpp.strip() + "\n"


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    for problem in problems:
        starters = problem.get("starter_code", {})
        starters.pop("javascript", None)
        if "cpp" in starters:
            starters["cpp"] = strip_cpp_support_structs(starters["cpp"])
    DATA_PATH.write_text(json.dumps(problems, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cleaned language starters for {len(problems)} problems")


if __name__ == "__main__":
    main()
