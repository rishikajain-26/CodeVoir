from pydantic import BaseModel

from typing import List


class TestCaseResult(BaseModel):

    input: str

    expected_output: str

    actual_output: str

    passed: bool

    execution_time_ms: float

    memory_used_mb: float


class ExecutionResult(BaseModel):

    success: bool

    compilation_error: bool

    runtime_error: bool

    timeout: bool

    overall_score: float

    passed_testcases: int

    total_testcases: int

    testcase_results: List[TestCaseResult]

    execution_logs: str