import json
from collections import Counter
from pathlib import Path

from export_leetcode_dataset import split_signature


DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "leetcode_dataset_balanced.json"


def main() -> None:
    problems = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    counter = Counter()
    for problem in problems:
        method, params, return_type = split_signature(problem.get("starter_code", {}).get("python", ""))
        if not method:
            continue
        counter[return_type] += 1
        for _name, annotation in params:
            counter[annotation] += 1
    print(counter.most_common(100))


if __name__ == "__main__":
    main()
