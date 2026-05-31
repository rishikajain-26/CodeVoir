import asyncio

from app.agents.contradiction.agent import (
    analyze_contradiction
)


async def main():

    result = await analyze_contradiction(

        previous_claims="""
Candidate claimed:
- designed scalable Redis architecture
- built distributed caching systems
- optimized replication reliability
""",

        latest_answer="""
Redis replication is asynchronous.
"""
    )

    print(result)


asyncio.run(main())