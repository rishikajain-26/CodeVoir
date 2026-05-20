import tempfile
import subprocess
import time

from app.runtime.languages.base import (
    BaseLanguageAdapter
)


class PythonAdapter(
    BaseLanguageAdapter
):

    async def compile_code(
        self,
        code: str,
    ):

        return True

    async def execute_code(

        self,
        code: str,
        stdin: str,

    ):

        with tempfile.NamedTemporaryFile(

            suffix=".py",

            delete=False,

            mode="w",

        ) as f:

            f.write(code)

            file_path = f.name

        start = time.time()

        try:

            result = subprocess.run(

                ["python", file_path],

                input=stdin,

                text=True,

                capture_output=True,

                timeout=2,

            )

            end = time.time()

            return {

                "stdout":
                    result.stdout.strip(),

                "stderr":
                    result.stderr.strip(),

                "execution_time_ms":
                    (end - start) * 1000,
            }

        except subprocess.TimeoutExpired:

            return {

                "timeout": True
            }