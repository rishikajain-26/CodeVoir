# AI Interview Platform

Agentic AI-powered realtime interview simulation platform.

## Tech Stack

- React + Vite
- FastAPI
- LangGraph
- Redis
- PostgreSQL
- Socket.IO
- LiveKit
- Monaco Editor

## Status

Phase 1 - Infrastructure Setup

## Optional C/C++ Toolchain

The backend can run C and C++ submissions if `gcc`/`g++` are available. It first checks your system `PATH`, then falls back to:

```text
tools/w64devkit/bin
```

That toolchain is intentionally not committed to Git because it is a large local binary bundle. After cloning on Windows, restore it with:

```powershell
.\scripts\setup-w64devkit.ps1
```

Python, JavaScript, and Java support do not depend on this folder.
