import tempfile
import subprocess
import uuid
import os
import time
import shutil


class DockerExecutor:

    async def execute(

        self,

        code: str,

        stdin: str,

    ):

        filename = (
            f"{uuid.uuid4()}.py"
        )

        temp_dir = tempfile.mkdtemp()

        file_path = os.path.join(
            temp_dir,
            filename,
        )

        with open(
            file_path,
            "w",
            encoding="utf-8",
        ) as f:

            f.write(code)

        start = time.time()

        try:

            docker_command = [

                "docker",
                "run",

                "--rm",

                "--network",
                "none",

                "--memory",
                "128m",

                "--cpus",
                "0.5",

                "-i",

                "-v",
                f"{temp_dir}:/app",

                "verity-python-runner",

                "python",
                f"/app/{filename}",
            ]

            result = subprocess.run(

                docker_command,

                input=stdin,

                text=True,

                capture_output=True,

                timeout=3,
            )

            end = time.time()

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )

            return {

                "stdout":
                    result.stdout.strip(),

                "stderr":
                    result.stderr.strip(),

                "execution_time_ms":
                    (end - start) * 1000,

                "timeout":
                    False,
            }

        except subprocess.TimeoutExpired:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )

            return {

                "stdout": "",

                "stderr":
                    "Execution timed out",

                "execution_time_ms":
                    3000,

                "timeout":
                    True,
            }

        except Exception as e:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )

            return {

                "stdout": "",

                "stderr": str(e),

                "execution_time_ms": 0,

                "timeout": False,
            }