Set-Location "C:\Users\Asus\Documents\Codex\2026-05-20\files-mentioned-by-the-user-ai\clio-src\clio\backend"
& "C:\Users\Asus\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level critical
Read-Host "Backend exited"
