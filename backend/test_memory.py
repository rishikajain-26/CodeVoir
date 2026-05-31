import asyncio

from app.agents.memory.agent import (
    generate_memory_summary
)


async def main():

    result = await generate_memory_summary(

        conversation_history="""
Candidate claims strong distributed systems experience.

Explained Redis replication only superficially.

Contradiction engine flagged possible exaggeration.

Strategy engine increased skepticism and pressure.

Candidate appears confident but avoids deep internals.
"""
    )

    print(result)


asyncio.run(main())