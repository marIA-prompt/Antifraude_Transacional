from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class CustomerProfile:
    """Perfil histórico mínimo de um CPF, usado para features e cold start.

    Em produção isto seria alimentado por um data store transacional /
    feature store; aqui expomos apenas a interface e uma implementação em
    memória para uso em testes e desenvolvimento local.
    """

    cpf: str
    first_seen_at: datetime
    transaction_count: int
    history_days: int
    average_amount: float = 0.0

    def is_cold_start(self, min_transactions: int = 3, min_history_days: int = 7) -> bool:
        return self.transaction_count < min_transactions or self.history_days < min_history_days


class CustomerProfileRepository(ABC):
    @abstractmethod
    def get_profile(self, cpf: str) -> CustomerProfile | None:
        raise NotImplementedError


class InMemoryCustomerProfileRepository(CustomerProfileRepository):
    def __init__(self) -> None:
        self._profiles: dict[str, CustomerProfile] = {}

    def upsert(self, profile: CustomerProfile) -> None:
        self._profiles[profile.cpf] = profile

    def get_profile(self, cpf: str) -> CustomerProfile | None:
        return self._profiles.get(cpf)


def new_customer_profile(cpf: str) -> CustomerProfile:
    """Perfil padrão para CPF nunca visto (cold start absoluto)."""

    return CustomerProfile(
        cpf=cpf,
        first_seen_at=datetime.now(timezone.utc),
        transaction_count=0,
        history_days=0,
        average_amount=0.0,
    )
