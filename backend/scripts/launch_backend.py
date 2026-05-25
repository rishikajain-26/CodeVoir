import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Users\Asus\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
LOG = ROOT / "backend-server.log"


with LOG.open("a", encoding="utf-8") as log:
    subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8010",
            "--log-level",
            "info",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
