from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    @abstractmethod
    def apply(self, base_prompt: str) -> str:
        pass

    @abstractmethod
    def metadata(self) -> dict:
        pass

    def __repr__(self) -> str:
        meta = self.metadata()
        return f"<Strategy: {meta.get('name', self.__class__.__name__)}>"
