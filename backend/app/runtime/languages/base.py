from abc import ABC
from abc import abstractmethod


class BaseLanguageAdapter(ABC):

    @abstractmethod
    async def compile_code(
        self,
        code: str,
    ):
        pass

    @abstractmethod
    async def execute_code(
        self,
        code: str,
        stdin: str,
    ):
        pass