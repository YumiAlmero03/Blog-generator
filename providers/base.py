from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    """Raised when an AI provider cannot complete a generation request."""


class BaseProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> str:
        pass
