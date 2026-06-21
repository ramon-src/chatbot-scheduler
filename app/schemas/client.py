"""
Schemas Pydantic para Client
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from phonenumbers import NumberParseException, is_valid_number, parse
from pydantic import BaseModel, EmailStr, Field, validator

from app.models.client import Client as ClientModel


class ClientBase(BaseModel):
    """Schema base para Client com validações comuns"""
    
    name: str = Field(
        ..., 
        min_length=2, 
        max_length=255,
        description="Nome completo do cliente"
    )
    phone: str = Field(
        ..., 
        min_length=10,
        max_length=20,
        description="Telefone do cliente (formato brasileiro)"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Email do cliente (opcional)"
    )
    birth_date: Optional[date] = Field(
        None,
        description="Data de nascimento do cliente"
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Observações sobre o cliente"
    )
    is_active: bool = Field(
        True,
        description="Status ativo/inativo do cliente"
    )

    @validator('phone')
    def validate_phone(cls, v):
        """Validação de telefone brasileiro"""
        if not v:
            raise ValueError('Telefone é obrigatório')
        
        try:
            # Remove caracteres não numéricos
            phone_clean = ''.join(filter(str.isdigit, v))
            
            # Adiciona código do país se necessário
            if len(phone_clean) == 11 and phone_clean.startswith('11'):
                phone_clean = '55' + phone_clean
            elif len(phone_clean) == 10:
                phone_clean = '55' + phone_clean
            
            # Parse e validação
            parsed_phone = parse(phone_clean, 'BR')
            if not is_valid_number(parsed_phone):
                raise ValueError('Número de telefone inválido')
            
            # Retorna no formato brasileiro
            return f"+{parsed_phone.country_code}{parsed_phone.national_number}"
            
        except NumberParseException:
            raise ValueError('Formato de telefone inválido')
    
    @validator('birth_date')
    def validate_birth_date(cls, v):
        """Validação de data de nascimento"""
        if v and v > date.today():
            raise ValueError('Data de nascimento não pode ser futura')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validação de nome"""
        if not v or not v.strip():
            raise ValueError('Nome não pode ser vazio')
        
        # Remove espaços extras
        name_clean = ' '.join(v.strip().split())
        
        # Verifica se tem pelo menos 2 palavras
        if len(name_clean.split()) < 2:
            raise ValueError('Nome deve conter pelo menos nome e sobrenome')
        
        return name_clean.title()
    
    @validator('notes')
    def validate_notes(cls, v):
        """Validação de observações"""
        if v and len(v.strip()) == 0:
            return None
        return v


class ClientCreate(ClientBase):
    """Schema para criação de cliente"""
    
    user_id: UUID = Field(
        ...,
        description="ID do psicólogo proprietário"
    )


class ClientUpdate(BaseModel):
    """Schema para atualização de cliente (todos os campos opcionais)"""
    
    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=255,
        description="Nome completo do cliente"
    )
    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=20,
        description="Telefone do cliente"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Email do cliente"
    )
    birth_date: Optional[date] = Field(
        None,
        description="Data de nascimento do cliente"
    )
    invoice_day: Optional[int] = Field(
        None,
        ge=1,
        le=31,
        description="Dia do mês para faturamento"
    )
    consult_price: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Preço da consulta em reais"
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Observações sobre o cliente"
    )
    is_active: Optional[bool] = Field(
        None,
        description="Status ativo/inativo do cliente"
    )

    @validator('phone')
    def validate_phone(cls, v):
        """Validação de telefone brasileiro"""
        if v is None:
            return v
        
        try:
            # Remove caracteres não numéricos
            phone_clean = ''.join(filter(str.isdigit, v))
            
            # Adiciona código do país se necessário
            if len(phone_clean) == 11 and phone_clean.startswith('11'):
                phone_clean = '55' + phone_clean
            elif len(phone_clean) == 10:
                phone_clean = '55' + phone_clean
            
            # Parse e validação
            parsed_phone = parse(phone_clean, 'BR')
            if not is_valid_number(parsed_phone):
                raise ValueError('Número de telefone inválido')
            
            # Retorna no formato brasileiro
            return f"+{parsed_phone.country_code}{parsed_phone.national_number}"
            
        except NumberParseException:
            raise ValueError('Formato de telefone inválido')
    
    @validator('birth_date')
    def validate_birth_date(cls, v):
        """Validação de data de nascimento"""
        if v and v > date.today():
            raise ValueError('Data de nascimento não pode ser futura')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validação de nome"""
        if v is None:
            return v
        
        if not v or not v.strip():
            raise ValueError('Nome não pode ser vazio')
        
        # Remove espaços extras
        name_clean = ' '.join(v.strip().split())
        
        # Verifica se tem pelo menos 2 palavras
        if len(name_clean.split()) < 2:
            raise ValueError('Nome deve conter pelo menos nome e sobrenome')
        
        return name_clean.title()
    
    @validator('notes')
    def validate_notes(cls, v):
        """Validação de observações"""
        if v and len(v.strip()) == 0:
            return None
        return v


class ClientResponse(ClientBase):
    """Schema para resposta de cliente"""
    
    id: UUID = Field(
        ...,
        description="ID único do cliente"
    )
    user_id: UUID = Field(
        ...,
        description="ID do psicólogo proprietário"
    )
    created_at: date = Field(
        ...,
        description="Data de criação do cliente"
    )
    updated_at: date = Field(
        ...,
        description="Data da última atualização"
    )

    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str,
            date: lambda v: v.isoformat(),
        }

    @classmethod
    def from_orm(cls, client: ClientModel) -> "ClientResponse":
        """Cria ClientResponse a partir do modelo SQLAlchemy"""
        return cls(
            id=client.id,
            user_id=client.user_id,
            name=client.name,
            phone=client.phone,
            email=client.email,
            birth_date=client.birth_date,
            invoice_day=client.invoice_day,
            consult_price=client.consult_price,
            notes=client.notes,
            is_active=client.is_active,
            created_at=client.created_at,
            updated_at=client.updated_at,
        )


class ClientListResponse(BaseModel):
    """Schema para lista de clientes com paginação"""
    
    clients: list[ClientResponse] = Field(
        ...,
        description="Lista de clientes"
    )
    total: int = Field(
        ...,
        description="Total de clientes"
    )
    page: int = Field(
        ...,
        ge=1,
        description="Página atual"
    )
    per_page: int = Field(
        ...,
        ge=1,
        le=100,
        description="Itens por página"
    )
    total_pages: int = Field(
        ...,
        ge=1,
        description="Total de páginas"
    )


class ClientSearchRequest(BaseModel):
    """Schema para busca de clientes"""
    
    query: Optional[str] = Field(
        None,
        min_length=2,
        max_length=255,
        description="Termo de busca (nome ou telefone)"
    )
    is_active: Optional[bool] = Field(
        None,
        description="Filtrar por status ativo/inativo"
    )
    user_id: Optional[UUID] = Field(
        None,
        description="Filtrar por psicólogo proprietário"
    )
    page: int = Field(
        1,
        ge=1,
        description="Página da busca"
    )
    per_page: int = Field(
        20,
        ge=1,
        le=100,
        description="Itens por página"
    )


class ClientStatsResponse(BaseModel):
    """Schema para estatísticas de clientes"""
    
    total_clients: int = Field(
        ...,
        description="Total de clientes"
    )
    active_clients: int = Field(
        ...,
        description="Clientes ativos"
    )
    inactive_clients: int = Field(
        ...,
        description="Clientes inativos"
    )
    clients_this_month: int = Field(
        ...,
        description="Clientes criados este mês"
    )
    average_consult_price: Optional[Decimal] = Field(
        None,
        description="Preço médio das consultas"
    )
