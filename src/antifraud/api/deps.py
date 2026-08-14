from __future__ import annotations

from fastapi import Header, HTTPException, status

from antifraud.domain.enums import ApiConsumerRole

# Mapeamento de API keys para perfis, apenas para fins de demonstração.
# Em produção isto deve vir de um provedor de identidade / gateway de API
# (OAuth2/mTLS + autorização por perfil), nunca de uma constante em código.
_DEMO_API_KEYS: dict[str, ApiConsumerRole] = {
    "demo-basic-key": ApiConsumerRole.BASIC,
    "demo-analyst-key": ApiConsumerRole.ANALYST,
    "demo-admin-key": ApiConsumerRole.ADMIN,
}


def require_v2_role(x_api_key: str = Header(default="")) -> ApiConsumerRole:
    """Autenticação/autorização por perfil para a API v2 (explicabilidade).

    A API v2 expõe score, sinais, features e pesos -- dados sensíveis do
    ponto de vista de exposição indevida da lógica antifraude -- por isso
    exige um consumidor autorizado e autenticado.
    """

    role = _DEMO_API_KEYS.get(x_api_key)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Consumidor não autenticado/autorizado para a API v2.",
        )
    return role
