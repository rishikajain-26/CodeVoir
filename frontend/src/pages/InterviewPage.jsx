import { useEffect, useRef } from "react"

import Editor from "@monaco-editor/react"

const socketUrl =
  "ws://localhost:8000/ws/test"

export default function InterviewPage() {

  const wsRef = useRef(null)

  const lastEditTime = useRef(
    Date.now()
  )

  useEffect(() => {

    wsRef.current = new WebSocket(
      socketUrl
    )

    wsRef.current.onopen = () => {

      console.log(
        "WebSocket connected"
      )
    }

    wsRef.current.onmessage = (
      event
    ) => {

      console.log(
        "Server response:",
        JSON.parse(event.data)
      )
    }

    return () => {

      wsRef.current.close()
    }

  }, [])

  const handleEditorMount = (
    editor,
    monaco
  ) => {

    editor.onDidChangeModelContent(

      (event) => {

        const now = Date.now()

        const pauseDuration =
          now - lastEditTime.current

        lastEditTime.current = now

        event.changes.forEach(
          (change) => {

            let eventType =
              "insert"

            if (
              change.text === ""
            ) {

              eventType =
                "delete"
            }

            if (
              change.text.length > 20
            ) {

              eventType =
                "paste"
            }

            const telemetryEvent = {

              event_type:
                "telemetry",

              payload: {

                event_type:
                  eventType,

                content_delta:
                  change.text,

                range_offset:
                  change.rangeOffset,

                range_length:
                  change.rangeLength,

                pause_duration:
                  pauseDuration,

                timestamp:
                  Date.now(),
              },
            }

            console.log(
              telemetryEvent
            )

            if (

              wsRef.current &&

              wsRef.current.readyState
                === WebSocket.OPEN

            ) {

              wsRef.current.send(

                JSON.stringify(
                  telemetryEvent
                )
              )
            }
          }
        )
      }
    )
  }

  return (

    <div className="h-screen w-screen">

      <Editor

        height="100%"

        defaultLanguage="python"

        defaultValue={`n = int(input())
print(n * 2)`}

        theme="vs-dark"

        onMount={
          handleEditorMount
        }
      />
    </div>
  )
}