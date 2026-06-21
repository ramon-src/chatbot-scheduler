"""
Schemas Pydantic para validação de dados
"""

from .client import (
    ClientBase,
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientSearchRequest,
    ClientStatsResponse,
    ClientUpdate,
)

__all__ = [
    "ClientBase",
    "ClientCreate", 
    "ClientUpdate",
    "ClientResponse",
    "ClientListResponse",
    "ClientSearchRequest",
    "ClientStatsResponse",
]
