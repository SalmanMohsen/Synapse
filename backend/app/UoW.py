from abc import ABC, abstractmethod


class AbstractUnitOfWork(ABC):
    """
    Base Unit of Work.

    Handles the context manager lifecycle and enforces commit/rollback on
    every concrete implementation. Module UoWs inherit from this and add
    their typed repository attributes — no boilerplate repeated.
    """

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass