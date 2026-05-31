import asyncio

from app.runtime.execution.session_tracker import (
    CodingSessionTracker
)

from app.runtime.testcases.runner import (
    run_testcases
)

from app.agents.coding_analytics.agent import (
    analyze_coding_behavior
)


TESTCASES = [

    {
        "input": "2",

        "expected_output": "4",
    },

    {
        "input": "5",

        "expected_output": "10",
    },
]


REVISION_1 = """
n = int(input())

print(n)
"""


REVISION_2 = """
n = int(input())

print(n * 2)
"""


async def main():

    tracker = (
        CodingSessionTracker()
    )

    result1 = await run_testcases(

        code=REVISION_1,

        testcases=TESTCASES,
    )

    tracker.add_revision(
        REVISION_1,
        result1,
    )

    result2 = await run_testcases(

        code=REVISION_2,

        testcases=TESTCASES,
    )

    tracker.add_revision(
        REVISION_2,
        result2,
    )

    history = str(
        tracker.get_revision_history()
    )

    analysis = await (
        analyze_coding_behavior(
            history
        )
    )

    print(analysis)


asyncio.run(main())