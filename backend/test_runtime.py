import asyncio

from app.runtime.testcases.runner import (
    run_testcases
)


CODE = """
n = int(input())

print(n * 2)
"""


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


async def main():

    result = await run_testcases(

        code=CODE,

        testcases=TESTCASES,
    )

    print(result)


asyncio.run(main())