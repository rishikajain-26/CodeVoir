import asyncio

from app.agents.technical.evaluator import (
    evaluate_technical_response
)


async def main():

    result = await evaluate_technical_response(

        question=(
            "Explain Redis replication"
        ),

        answer=(
            "Redis uses asynchronous "
            "replication between primary "
            "and replica nodes."
        )
    )

    print(result)


asyncio.run(main())