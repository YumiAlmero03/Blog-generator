from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> str:
        pass