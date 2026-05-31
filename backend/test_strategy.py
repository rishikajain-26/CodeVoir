import asyncio

from app.agents.strategy.agent import (
    generate_strategy
)


async def main():

    result = await generate_strategy(

        technical_evaluation="""
Candidate demonstrates shallow Redis knowledge.
Weak understanding of replication internals.
Possible superficial distributed systems exposure.
""",

        contradiction_analysis="""
Candidate claimed strong distributed caching experience,
but failed to explain replication reliability deeply.
Potential exaggeration detected.
"""
    )

    print(result)


asyncio.run(main())