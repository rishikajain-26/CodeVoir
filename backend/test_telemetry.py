import asyncio

from app.runtime.execution.telemetry_tracker import (
    TelemetryTracker
)

from app.agents.telemetry.agent import (
    analyze_telemetry
)


async def main():

    tracker = TelemetryTracker()

    tracker.add_event(
        "type",
        "n = int(input())",
        16,
    )

    tracker.add_event(
        "pause",
        "",
        16,
    )

    tracker.add_event(
        "delete",
        "print(n)",
        20,
    )

    tracker.add_event(
        "paste",
        "print(n * 2)",
        22,
    )

    history = str(
        tracker.get_events()
    )

    result = await (
        analyze_telemetry(
            history
        )
    )

    print(result)


asyncio.run(main())