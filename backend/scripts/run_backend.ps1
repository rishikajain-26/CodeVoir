<<<<<<< HEAD
Set-Location "C:\Users\Asus\Documents\Codex\2026-05-20\files-mentioned-by-the-user-ai\clio-src\clio\backend"
& "C:\Users\Asus\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level critical
=======
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $BackendDir

$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
& $Python -m uvicorn main:app --host 127.0.0.1 --port 8010 --log-level info
>>>>>>> b2a9557 (WIP: saving local work before sync)
Read-Host "Backend exited"
