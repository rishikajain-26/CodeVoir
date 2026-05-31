from app.runtime.languages.python_adapter import (
    PythonAdapter
)

from app.runtime.schemas.execution import (
    ExecutionResult,
    TestCaseResult,
)


from app.runtime.sandbox.docker_executor import (
    DockerExecutor
)

executor = DockerExecutor()


async def run_testcases(

    code: str,

    testcases: list,

):

    results = []

    passed = 0

    for testcase in testcases:

        execution = await (
    executor.execute(
                code=code,

                stdin=testcase["input"],
            )
        )

        actual_output = (
            execution.get(
                "stdout",
                ""
            ).strip()
        )

        expected_output = (
            testcase[
                "expected_output"
            ].strip()
        )

        did_pass = (
            actual_output
            == expected_output
        )

        if did_pass:
            passed += 1

        result = TestCaseResult(

            input=testcase["input"],

            expected_output=expected_output,

            actual_output=actual_output,

            passed=did_pass,

            execution_time_ms=execution.get(
                "execution_time_ms",
                0,
            ),

            memory_used_mb=0,
        )

        results.append(result)

    return ExecutionResult(

        success=True,

        compilation_error=False,

        runtime_error=False,

        timeout=False,

        overall_score=(
            passed / len(testcases)
        ) * 100,

        passed_testcases=passed,

        total_testcases=len(
            testcases
        ),

        testcase_results=results,

        execution_logs="",
    )