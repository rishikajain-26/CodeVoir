"""
Static code analysis using tree-sitter.

Provides structural complexity estimation, syntax validation, and code quality
metrics without any LLM calls. Runs in <10ms for typical DSA solutions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.utils.logger import logger

try:
    from tree_sitter import Language, Parser, Node
    import tree_sitter_python as ts_python
    import tree_sitter_java as ts_java
    import tree_sitter_cpp as ts_cpp
    import tree_sitter_c as ts_c

    _LANGUAGES: dict[str, Language] = {
        "python": Language(ts_python.language()),
        "java": Language(ts_java.language()),
        "cpp": Language(ts_cpp.language()),
        "c": Language(ts_c.language()),
    }
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False
    _LANGUAGES = {}


@dataclass
class FunctionInfo:
    name: str
    params: list[str]
    has_return: bool
    body_lines: int
    is_recursive: bool = False


@dataclass
class CodeAnalysis:
    # Syntax
    parses_ok: bool = False
    syntax_error: str | None = None
    language: str = ""

    # Structure
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    total_lines: int = 0
    non_blank_lines: int = 0

    # Complexity signals
    max_loop_depth: int = 0
    has_recursion: bool = False
    has_memoization: bool = False
    has_sort_call: bool = False
    has_heap_op: bool = False
    has_binary_search: bool = False
    loop_count: int = 0

    # Data structures detected
    structures_used: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    # Quality
    avg_name_length: float = 0.0
    single_char_vars: list[str] = field(default_factory=list)
    has_boundary_check: bool = False
    has_empty_input_guard: bool = False
    dead_code_lines: int = 0

    # Completeness
    code_complete: bool = False
    pass_statements: int = 0
    has_main_function: bool = False

    # Inferred complexity
    estimated_time: str = ""
    estimated_space: str = ""
    time_reason: str = ""
    space_reason: str = ""


# ─── Language-specific node type mappings ────────────────────────────────────

_LOOP_TYPES = {
    "python": {"for_statement", "while_statement"},
    "java": {"for_statement", "enhanced_for_statement", "while_statement", "do_statement"},
    "cpp": {"for_statement", "for_range_loop", "while_statement", "do_statement"},
    "c": {"for_statement", "while_statement", "do_statement"},
}

_FUNCTION_TYPES = {
    "python": {"function_definition"},
    "java": {"method_declaration", "constructor_declaration"},
    "cpp": {"function_definition"},
    "c": {"function_definition"},
}

_CLASS_TYPES = {
    "python": {"class_definition"},
    "java": {"class_declaration"},
    "cpp": {"class_specifier", "struct_specifier"},
    "c": {"struct_specifier"},
}

_CALL_TYPES = {
    "python": {"call"},
    "java": {"method_invocation", "object_creation_expression"},
    "cpp": {"call_expression"},
    "c": {"call_expression"},
}

_RETURN_TYPES = {
    "python": {"return_statement"},
    "java": {"return_statement"},
    "cpp": {"return_statement"},
    "c": {"return_statement"},
}

_IDENTIFIER_TYPES = {
    "python": {"identifier"},
    "java": {"identifier"},
    "cpp": {"identifier"},
    "c": {"identifier"},
}


# ─── Sort/heap/bisect patterns per language ──────────────────────────────────

_SORT_PATTERNS = {
    "python": {"sort", "sorted"},
    "java": {"Arrays.sort", "Collections.sort", "sort"},
    "cpp": {"sort", "std::sort", "stable_sort"},
    "c": {"qsort"},
}

_HEAP_PATTERNS = {
    "python": {"heapq", "heappush", "heappop", "heapify", "nlargest", "nsmallest"},
    "java": {"PriorityQueue", "offer", "poll"},
    "cpp": {"priority_queue", "push_heap", "pop_heap", "make_heap"},
    "c": set(),
}

_BINARY_SEARCH_PATTERNS = {
    "python": {"bisect", "bisect_left", "bisect_right"},
    "java": {"Arrays.binarySearch", "Collections.binarySearch"},
    "cpp": {"lower_bound", "upper_bound", "binary_search"},
    "c": {"bsearch"},
}

_DATA_STRUCTURE_PATTERNS = {
    "python": {
        "dict": ["dict(", "{}", "defaultdict", "Counter", "OrderedDict"],
        "set": ["set(", "frozenset("],
        "deque": ["deque(", "collections.deque"],
        "heap": ["heapq", "heappush"],
        "stack": ["append(", "pop()"],  # heuristic
        "list": ["list(", "[]"],
        "trie": ["Trie", "TrieNode", "children = {}"],
    },
    "java": {
        "HashMap": ["HashMap", "HashSet", "LinkedHashMap"],
        "TreeMap": ["TreeMap", "TreeSet"],
        "Queue": ["Queue", "LinkedList", "ArrayDeque", "PriorityQueue"],
        "Stack": ["Stack", "Deque"],
        "List": ["ArrayList", "LinkedList"],
    },
    "cpp": {
        "unordered_map": ["unordered_map", "unordered_set"],
        "map": [" map<", "\tmap<", "set<"],
        "queue": ["queue<", "deque<", "priority_queue<"],
        "stack": ["stack<"],
        "vector": ["vector<"],
    },
    "c": {
        "array": ["malloc", "calloc"],
    },
}

_MEMOIZATION_PATTERNS = {
    "python": {"@cache", "@lru_cache", "functools.cache", "memo[", "memo =", "dp[", "dp ="},
    "java": {"memo[", "memo.", "dp[", "int[] dp", "int[][] dp", "Integer[] memo"},
    "cpp": {"memo[", "memo.", "dp[", "vector<int> dp", "vector<vector"},
    "c": {"memo[", "dp["},
}

_BOUNDARY_PATTERNS = {
    "python": [
        r"if\s+(not\s+\w+|len\(\w+\)\s*==\s*0|\w+\s*==\s*\[\]|\w+\s*is\s+None)",
        r"if\s+\w+\s*<=?\s*0",
        r"if\s+n\s*[<=>]",
    ],
    "java": [
        r"if\s*\(\s*\w+\s*==\s*null",
        r"if\s*\(\s*\w+\.length\s*==\s*0",
        r"if\s*\(\s*\w+\.isEmpty\(\)",
        r"if\s*\(\s*n\s*[<=>]",
    ],
    "cpp": [
        r"if\s*\(\s*\w+\.empty\(\)",
        r"if\s*\(\s*\w+\.size\(\)\s*==\s*0",
        r"if\s*\(\s*\w+\s*==\s*(nullptr|NULL|0)",
        r"if\s*\(\s*n\s*[<=>]",
    ],
    "c": [
        r"if\s*\(\s*\w+\s*==\s*NULL",
        r"if\s*\(\s*n\s*[<=>]",
        r"if\s*\(\s*\w+\s*==\s*0",
    ],
}


# ─── Main analysis function ──────────────────────────────────────────────────


def analyze_code(code: str, language: str) -> CodeAnalysis:
    """
    Analyze code structure and estimate complexity using tree-sitter.
    Falls back to regex-based heuristics if tree-sitter is unavailable.
    """
    language = _normalize_language(language)
    analysis = CodeAnalysis(language=language)

    if not code or not code.strip():
        return analysis

    lines = code.splitlines()
    analysis.total_lines = len(lines)
    analysis.non_blank_lines = sum(1 for ln in lines if ln.strip())

    if _TS_AVAILABLE and language in _LANGUAGES:
        _analyze_with_tree_sitter(code, language, analysis)
    else:
        _analyze_with_regex(code, language, analysis)

    _detect_data_structures(code, language, analysis)
    _detect_memoization(code, language, analysis)
    _detect_boundary_checks(code, language, analysis)
    _estimate_complexity(analysis)
    _assess_completeness(analysis)
    _analyze_naming(code, language, analysis)

    return analysis


def _normalize_language(language: str) -> str:
    lang = language.lower().strip()
    if lang in ("c++", "cpp", "c plus plus"):
        return "cpp"
    if lang in ("python", "python3", "py"):
        return "python"
    if lang in ("java",):
        return "java"
    if lang in ("c",):
        return "c"
    return lang


# ─── Tree-sitter analysis ────────────────────────────────────────────────────


def _analyze_with_tree_sitter(code: str, language: str, analysis: CodeAnalysis) -> None:
    parser = Parser(_LANGUAGES[language])
    tree = parser.parse(code.encode("utf-8"))
    root = tree.root_node

    # Check for parse errors
    if root.has_error:
        error_node = _find_first_error(root)
        if error_node:
            analysis.syntax_error = f"line {error_node.start_point[0] + 1}: unexpected syntax"
        else:
            analysis.syntax_error = "parse error detected"
        analysis.parses_ok = False
    else:
        analysis.parses_ok = True

    loop_types = _LOOP_TYPES.get(language, set())
    func_types = _FUNCTION_TYPES.get(language, set())
    class_types = _CLASS_TYPES.get(language, set())
    call_types = _CALL_TYPES.get(language, set())
    return_types = _RETURN_TYPES.get(language, set())

    # Extract functions
    func_nodes = _find_nodes_of_type(root, func_types)
    for fn_node in func_nodes:
        fi = _extract_function_info(fn_node, language, call_types, return_types, loop_types)
        analysis.functions.append(fi)
        if fi.is_recursive:
            analysis.has_recursion = True

    # Extract classes
    class_nodes = _find_nodes_of_type(root, class_types)
    for cls_node in class_nodes:
        name_node = cls_node.child_by_field_name("name")
        if name_node:
            analysis.classes.append(name_node.text.decode("utf-8"))

    # Max loop depth (global)
    analysis.max_loop_depth = _compute_max_loop_depth(root, loop_types)
    analysis.loop_count = len(_find_nodes_of_type(root, loop_types))

    # Sort/heap/binary search detection via call nodes
    all_calls = _find_nodes_of_type(root, call_types)
    _detect_algorithmic_calls(all_calls, language, analysis)

    # Dead code: statements after return in function bodies
    analysis.dead_code_lines = _count_dead_code(func_nodes, language, return_types)

    # Pass statements (Python)
    if language == "python":
        pass_nodes = _find_nodes_of_type(root, {"pass_statement"})
        analysis.pass_statements = len(pass_nodes)


def _find_first_error(node: "Node") -> "Node | None":
    if node.type == "ERROR" or node.is_missing:
        return node
    for child in node.children:
        result = _find_first_error(child)
        if result:
            return result
    return None


def _find_nodes_of_type(root: "Node", types: set[str]) -> list["Node"]:
    results = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in types:
            results.append(node)
        stack.extend(node.children)
    return results


def _extract_function_info(
    fn_node: "Node",
    language: str,
    call_types: set[str],
    return_types: set[str],
    loop_types: set[str],
) -> FunctionInfo:
    name_node = fn_node.child_by_field_name("name")
    if not name_node:
        name_node = fn_node.child_by_field_name("declarator")
        if name_node and name_node.child_by_field_name("declarator"):
            name_node = name_node.child_by_field_name("declarator")
    name = name_node.text.decode("utf-8") if name_node else "<anonymous>"

    # Extract parameters
    params: list[str] = []
    params_node = fn_node.child_by_field_name("parameters")
    if params_node:
        for child in params_node.children:
            if child.type in ("identifier", "typed_parameter", "formal_parameter",
                              "parameter_declaration", "typed_default_parameter"):
                param_name = child.child_by_field_name("name")
                if param_name:
                    params.append(param_name.text.decode("utf-8"))
                elif child.type == "identifier":
                    params.append(child.text.decode("utf-8"))

    # Check for return statement
    returns = _find_nodes_of_type(fn_node, return_types)
    has_return = len(returns) > 0

    # Body lines
    body_node = fn_node.child_by_field_name("body")
    body_lines = 0
    if body_node:
        body_lines = body_node.end_point[0] - body_node.start_point[0] + 1

    # Recursion: function calls itself
    is_recursive = False
    calls_in_fn = _find_nodes_of_type(fn_node, call_types)
    for call in calls_in_fn:
        call_name = _extract_call_name(call, language)
        if call_name == name:
            is_recursive = True
            break

    return FunctionInfo(
        name=name,
        params=params,
        has_return=has_return,
        body_lines=body_lines,
        is_recursive=is_recursive,
    )


def _extract_call_name(call_node: "Node", language: str) -> str:
    if language == "python":
        func_node = call_node.child_by_field_name("function")
        if func_node:
            return func_node.text.decode("utf-8").split(".")[-1]
    elif language == "java":
        name_node = call_node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode("utf-8")
    else:
        func_node = call_node.child_by_field_name("function")
        if func_node:
            text = func_node.text.decode("utf-8")
            return text.split("::")[-1].split(".")[-1]
    return ""


def _compute_max_loop_depth(root: "Node", loop_types: set[str]) -> int:
    max_depth = 0

    def walk(node: "Node", current_depth: int) -> None:
        nonlocal max_depth
        if node.type in loop_types:
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        for child in node.children:
            walk(child, current_depth)

    walk(root, 0)
    return max_depth


def _detect_algorithmic_calls(
    call_nodes: list["Node"], language: str, analysis: CodeAnalysis
) -> None:
    sort_patterns = _SORT_PATTERNS.get(language, set())
    heap_patterns = _HEAP_PATTERNS.get(language, set())
    bs_patterns = _BINARY_SEARCH_PATTERNS.get(language, set())

    for call in call_nodes:
        call_text = call.text.decode("utf-8").lower()
        name = _extract_call_name(call, language).lower()

        if any(p.lower() in call_text or p.lower() == name for p in sort_patterns):
            analysis.has_sort_call = True
        if any(p.lower() in call_text or p.lower() == name for p in heap_patterns):
            analysis.has_heap_op = True
        if any(p.lower() in call_text or p.lower() == name for p in bs_patterns):
            analysis.has_binary_search = True


def _count_dead_code(
    func_nodes: list["Node"], language: str, return_types: set[str]
) -> int:
    dead_lines = 0
    for fn_node in func_nodes:
        body = fn_node.child_by_field_name("body")
        if not body:
            continue
        found_return = False
        for child in body.children:
            if found_return and child.type not in ("comment", "pass_statement", "}"):
                dead_lines += child.end_point[0] - child.start_point[0] + 1
            if child.type in return_types:
                found_return = True
    return dead_lines


# ─── Regex fallback (when tree-sitter is unavailable) ────────────────────────


def _analyze_with_regex(code: str, language: str, analysis: CodeAnalysis) -> None:
    """Basic structural analysis using regex when tree-sitter isn't installed."""
    code_lower = code.lower()

    # Syntax: try Python's ast for Python, otherwise assume valid
    if language == "python":
        import ast as python_ast
        try:
            python_ast.parse(code)
            analysis.parses_ok = True
        except SyntaxError as e:
            analysis.parses_ok = False
            analysis.syntax_error = f"line {e.lineno}: {e.msg}" if e.lineno else str(e.msg)
    else:
        # Can't validate syntax without tree-sitter for non-Python
        analysis.parses_ok = True  # optimistic

    # Functions
    if language == "python":
        for match in re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)", code):
            name = match.group(1)
            params = [p.strip().split(":")[0].strip() for p in match.group(2).split(",") if p.strip()]
            has_return = bool(re.search(rf"def\s+{name}.*?(\n\s+return\s)", code, re.DOTALL))
            is_recursive = bool(re.search(rf"{name}\s*\(", code[match.end():]))
            analysis.functions.append(FunctionInfo(
                name=name, params=params, has_return=has_return,
                body_lines=0, is_recursive=is_recursive,
            ))
    elif language in ("java", "cpp", "c"):
        for match in re.finditer(r"(?:public|private|static|void|int|long|bool|string|auto)\s+(\w+)\s*\(", code):
            name = match.group(1)
            analysis.functions.append(FunctionInfo(
                name=name, params=[], has_return="return" in code,
                body_lines=0, is_recursive=bool(re.search(rf"{name}\s*\(", code[match.end():])),
            ))

    if any(f.is_recursive for f in analysis.functions):
        analysis.has_recursion = True

    # Loop depth via indentation/brace nesting
    analysis.max_loop_depth = _regex_loop_depth(code, language)
    analysis.loop_count = len(re.findall(
        r"\b(for|while)\b", code_lower
    ))

    # Sort/heap/bisect
    sort_pats = _SORT_PATTERNS.get(language, set())
    analysis.has_sort_call = any(p.lower() in code_lower for p in sort_pats)
    heap_pats = _HEAP_PATTERNS.get(language, set())
    analysis.has_heap_op = any(p.lower() in code_lower for p in heap_pats)
    bs_pats = _BINARY_SEARCH_PATTERNS.get(language, set())
    analysis.has_binary_search = any(p.lower() in code_lower for p in bs_pats)

    # Pass statements
    if language == "python":
        analysis.pass_statements = len(re.findall(r"^\s*pass\s*$", code, re.MULTILINE))


def _regex_loop_depth(code: str, language: str) -> int:
    """Estimate max loop nesting from indentation (Python) or braces (C-like)."""
    if language == "python":
        max_depth = 0
        current_depth = 0
        loop_indents: list[int] = []
        for line in code.splitlines():
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)
            # Pop loop indents that are at same or greater level
            while loop_indents and indent <= loop_indents[-1]:
                loop_indents.pop()
            if re.match(r"(for|while)\b", stripped):
                loop_indents.append(indent)
                current_depth = len(loop_indents)
                max_depth = max(max_depth, current_depth)
        return max_depth
    else:
        # Brace-based: count nested for/while within braces
        max_depth = 0
        depth = 0
        for match in re.finditer(r"\b(for|while)\b|\{|\}", code):
            token = match.group()
            if token in ("for", "while"):
                depth += 1
                max_depth = max(max_depth, depth)
            elif token == "}":
                depth = max(0, depth - 1)
        return max_depth


# ─── Shared detection helpers ────────────────────────────────────────────────


def _detect_data_structures(code: str, language: str, analysis: CodeAnalysis) -> None:
    code_text = code
    patterns = _DATA_STRUCTURE_PATTERNS.get(language, {})
    for ds_name, indicators in patterns.items():
        if any(ind in code_text for ind in indicators):
            analysis.structures_used.append(ds_name)

    # Imports (Python-specific)
    if language == "python":
        for match in re.finditer(r"(?:from|import)\s+([\w.]+)", code):
            analysis.imports.append(match.group(1))


def _detect_memoization(code: str, language: str, analysis: CodeAnalysis) -> None:
    patterns = _MEMOIZATION_PATTERNS.get(language, set())
    if any(p in code for p in patterns):
        analysis.has_memoization = True


def _detect_boundary_checks(code: str, language: str, analysis: CodeAnalysis) -> None:
    patterns = _BOUNDARY_PATTERNS.get(language, [])
    for pattern in patterns:
        if re.search(pattern, code):
            analysis.has_boundary_check = True
            break
    # Empty input guard: checking len == 0 or not arr near the top
    first_lines = "\n".join(code.splitlines()[:15])
    empty_patterns = [
        r"if\s+(not\s+\w+|len\(\w+\)\s*==\s*0|\w+\s*==\s*\[\])",
        r"if\s*\(\s*\w+\s*==\s*null",
        r"if\s*\(\s*\w+\.empty\(\)",
        r"if\s*\(\s*\w+\.length\s*==\s*0",
        r"if\s*\(\s*\w+\.isEmpty\(\)",
    ]
    for pattern in empty_patterns:
        if re.search(pattern, first_lines):
            analysis.has_empty_input_guard = True
            break


def _estimate_complexity(analysis: CodeAnalysis) -> None:
    """Estimate time and space complexity from structural signals."""
    # ── Time complexity ──
    depth = analysis.max_loop_depth
    has_recursion = analysis.has_recursion
    has_memo = analysis.has_memoization

    if has_recursion and has_memo:
        # DP with memoization — hard to pin exactly, usually O(n*k) or O(n²)
        analysis.estimated_time = "O(n*k) or O(n²)"
        analysis.time_reason = "recursion with memoization (dynamic programming)"
    elif has_recursion and not has_memo:
        if depth >= 1:
            analysis.estimated_time = "O(2^n) or O(n!)"
            analysis.time_reason = "unbounded recursion with loops (backtracking)"
        else:
            analysis.estimated_time = "O(2^n)"
            analysis.time_reason = "recursion without memoization"
    elif analysis.has_sort_call and depth <= 1:
        analysis.estimated_time = "O(n log n)"
        analysis.time_reason = "sort dominates"
    elif analysis.has_heap_op and depth <= 1:
        analysis.estimated_time = "O(n log n)"
        analysis.time_reason = "heap operations in loop"
    elif analysis.has_binary_search and depth <= 1:
        analysis.estimated_time = "O(n log n)"
        analysis.time_reason = "binary search in loop"
    elif analysis.has_binary_search and depth == 0:
        analysis.estimated_time = "O(log n)"
        analysis.time_reason = "binary search without outer loop"
    elif depth == 0:
        analysis.estimated_time = "O(1) or O(n)"
        analysis.time_reason = "no loops detected"
    elif depth == 1:
        analysis.estimated_time = "O(n)"
        analysis.time_reason = "single loop"
    elif depth == 2:
        analysis.estimated_time = "O(n²)"
        analysis.time_reason = "nested loops (depth 2)"
    elif depth == 3:
        analysis.estimated_time = "O(n³)"
        analysis.time_reason = "nested loops (depth 3)"
    else:
        analysis.estimated_time = f"O(n^{depth})"
        analysis.time_reason = f"nested loops (depth {depth})"

    # ── Space complexity ──
    structures = analysis.structures_used
    has_aux_structure = bool(structures)

    if has_memo:
        analysis.estimated_space = "O(n) or O(n²)"
        analysis.space_reason = "memoization table"
    elif has_aux_structure:
        if any(s in structures for s in ("dict", "set", "HashMap", "unordered_map", "TreeMap")):
            analysis.estimated_space = "O(n)"
            analysis.space_reason = f"auxiliary {', '.join(structures)}"
        elif any(s in structures for s in ("list", "vector", "ArrayList", "deque")):
            analysis.estimated_space = "O(n)"
            analysis.space_reason = f"auxiliary {', '.join(structures)}"
        else:
            analysis.estimated_space = "O(n)"
            analysis.space_reason = f"allocates {', '.join(structures)}"
    elif has_recursion:
        analysis.estimated_space = "O(n)"
        analysis.space_reason = "recursion stack"
    else:
        analysis.estimated_space = "O(1)"
        analysis.space_reason = "no auxiliary allocation detected"


def _assess_completeness(analysis: CodeAnalysis) -> None:
    """Determine if the code looks complete."""
    if not analysis.functions:
        analysis.code_complete = analysis.non_blank_lines > 3
        analysis.has_main_function = False
        return

    main_fn = analysis.functions[0]  # first function is usually the solution
    analysis.has_main_function = True
    analysis.code_complete = (
        main_fn.has_return
        and main_fn.body_lines > 1
        and analysis.pass_statements == 0
    )


def _analyze_naming(code: str, language: str, analysis: CodeAnalysis) -> None:
    """Assess variable naming quality."""
    # Collect identifiers (simple regex approach — good enough)
    if language == "python":
        # Exclude keywords and built-ins
        identifiers = set(re.findall(r"\b([a-z_]\w*)\b", code))
        exclude = {
            "def", "return", "if", "else", "elif", "for", "while", "in", "not",
            "and", "or", "is", "none", "true", "false", "import", "from", "class",
            "self", "range", "len", "int", "str", "list", "dict", "set", "print",
            "append", "pop", "sort", "sorted", "min", "max", "sum", "abs", "map",
            "filter", "enumerate", "zip", "break", "continue", "pass", "with", "as",
            "try", "except", "raise", "finally", "lambda", "yield", "global",
        }
    elif language == "java":
        identifiers = set(re.findall(r"\b([a-z]\w*)\b", code))
        exclude = {
            "public", "private", "static", "void", "int", "long", "double", "float",
            "boolean", "char", "string", "class", "return", "if", "else", "for",
            "while", "new", "this", "null", "true", "false", "import", "package",
            "extends", "implements", "try", "catch", "throw", "throws", "finally",
            "break", "continue", "switch", "case", "default",
        }
    else:
        identifiers = set(re.findall(r"\b([a-z_]\w*)\b", code))
        exclude = {
            "int", "long", "double", "float", "char", "void", "bool", "auto",
            "return", "if", "else", "for", "while", "do", "switch", "case",
            "break", "continue", "struct", "class", "public", "private",
            "include", "using", "namespace", "std", "cout", "cin", "endl",
            "nullptr", "null", "true", "false", "const", "static", "vector",
            "string", "map", "set", "pair", "queue", "stack", "sizeof",
        }

    identifiers -= exclude
    if not identifiers:
        analysis.avg_name_length = 0
        return

    lengths = [len(name) for name in identifiers]
    analysis.avg_name_length = round(sum(lengths) / len(lengths), 1)
    analysis.single_char_vars = sorted([name for name in identifiers if len(name) == 1])


# ─── Public helpers for integration ─────────────────────────────────────────


def analysis_to_complexity_fields(analysis: CodeAnalysis) -> dict:
    """Convert analysis to fields compatible with ComplexityProfile."""
    return {
        "actual_time": analysis.estimated_time,
        "actual_space": analysis.estimated_space,
    }


def analysis_to_implementation_fields(analysis: CodeAnalysis) -> dict:
    """Convert analysis to fields compatible with ImplementationQuality."""
    name_score = min(1.0, analysis.avg_name_length / 7.0) if analysis.avg_name_length > 0 else 0.3
    readability = round(
        (name_score * 0.4)
        + (0.3 if analysis.parses_ok else 0.0)
        + (0.2 if not analysis.dead_code_lines else 0.0)
        + (0.1 if analysis.code_complete else 0.0),
        3,
    )
    return {
        "compilation_success": analysis.parses_ok,
        "syntax_error_count": 0 if analysis.parses_ok else 1,
        "code_complete": analysis.code_complete,
        "naming_quality": round(name_score, 3),
        "readability_score": readability,
        "dead_code_present": analysis.dead_code_lines > 0,
        "boundary_checks_handled": analysis.has_boundary_check,
    }


def analysis_to_context_dict(analysis: CodeAnalysis) -> dict:
    """Produce a compact dict for inclusion in LLM context or fallback responses."""
    return {
        "parses": analysis.parses_ok,
        "syntax_error": analysis.syntax_error,
        "functions": [f.name for f in analysis.functions],
        "has_return": any(f.has_return for f in analysis.functions),
        "loop_depth": analysis.max_loop_depth,
        "loop_count": analysis.loop_count,
        "has_recursion": analysis.has_recursion,
        "has_memoization": analysis.has_memoization,
        "structures_used": analysis.structures_used,
        "estimated_time": analysis.estimated_time,
        "time_reason": analysis.time_reason,
        "estimated_space": analysis.estimated_space,
        "space_reason": analysis.space_reason,
        "code_complete": analysis.code_complete,
        "has_boundary_check": analysis.has_boundary_check,
        "has_empty_input_guard": analysis.has_empty_input_guard,
        "dead_code_lines": analysis.dead_code_lines,
    }
