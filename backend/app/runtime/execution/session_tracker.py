from app.runtime.schemas.coding_session import (
    CodeRevision
)

import time


class CodingSessionTracker:

    def __init__(self):

        self.revisions = []

    def add_revision(

        self,

        code: str,

        execution_result,

    ):

        revision = CodeRevision(

            revision_id=len(
                self.revisions
            ) + 1,

            code=code,

            execution_result=str(
                execution_result
            ),

            passed_testcases=(
                execution_result
                .passed_testcases
            ),

            total_testcases=(
                execution_result
                .total_testcases
            ),

            execution_time_ms=(
                execution_result
                .testcase_results[0]
                .execution_time_ms
                if execution_result
                .testcase_results
                else 0
            ),

            timestamp=time.time(),
        )

        self.revisions.append(
            revision
        )

    def get_revision_history(
        self
    ):

        return self.revisions