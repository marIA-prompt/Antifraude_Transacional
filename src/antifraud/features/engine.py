from __future__ import annotations

from antifraud.domain.models import TransactionPayload
from antifraud.features.profile import CustomerProfile


class FeatureEngine:
    """Cálculo de features transacionais e comportamentais (AS-IS: passo 3).

    Implementação de referência determinística. O pipeline real de
    featurização (com feature store, joins históricos etc.) fica fora do
    escopo deste repositório; o contrato (nomes e tipos de features) é o
    que deve permanecer estável entre treino e serviço online.
    """

    def compute(
        self, payload: TransactionPayload, profile: CustomerProfile
    ) -> dict[str, float]:
        amount_ratio = 0.0
        if profile.average_amount > 0:
            amount_ratio = payload.amount / profile.average_amount

        return {
            "amount": float(payload.amount),
            "installments": float(payload.installments),
            "merchant_is_new": 1.0 if payload.merchant_is_new else 0.0,
            "customer_transaction_count": float(profile.transaction_count),
            "customer_history_days": float(profile.history_days),
            "amount_to_avg_ratio": float(amount_ratio),
            "hour_of_day": float(payload.timestamp.hour),
        }
