async def handle_code_event(

    session_id: str,

    payload: dict,

):

    code = payload.get(
        "code",
        ""
    )

    print("\n=== LIVE CODE UPDATE ===")

    print(code)

    print("========================\n")

    return {

        "type":
            "code_ack",

        "payload": {

            "received": True,

            "code_length":
                len(code),
        },
    }