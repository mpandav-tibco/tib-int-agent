from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawDocument:
    content: str
    source: str
    metadata: dict = field(default_factory=dict)


class KnowledgeSource(ABC):
    name: str = ""

    @abstractmethod
    def load(self) -> list[RawDocument]:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
