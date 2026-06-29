"""
Serviço para gestão de clientes
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ClientNotFoundError, ConflictError, ValidationError
from app.models.client import Client
from app.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientSearchRequest,
    ClientStatsResponse,
    ClientUpdate,
)


class ClientService:
    """Serviço para operações CRUD de clientes"""

    def __init__(self, db: Session):
        self.db = db

    async def create_client(self, client_data: ClientCreate) -> ClientResponse:
        """
        Criar novo cliente
        
        Args:
            client_data: Dados do cliente para criação
            
        Returns:
            ClientResponse: Cliente criado
            
        Raises:
            ConflictError: Se já existe cliente com mesmo telefone/email
            ValidationError: Se dados são inválidos
        """
        try:
            # Verificar se já existe cliente com mesmo telefone
            existing_phone = self.db.query(Client).filter(
                and_(
                    Client.phone == client_data.phone,
                    Client.user_id == client_data.user_id,
                    Client.is_active == True
                )
            ).first()
            
            if existing_phone:
                raise ConflictError(
                    f"Já existe um cliente ativo com o telefone {client_data.phone}"
                )
            
            # Verificar se já existe cliente com mesmo email (se fornecido)
            if client_data.email:
                existing_email = self.db.query(Client).filter(
                    and_(
                        Client.email == client_data.email,
                        Client.user_id == client_data.user_id,
                        Client.is_active == True
                    )
                ).first()
                
                if existing_email:
                    raise ConflictError(
                        f"Já existe um cliente ativo com o email {client_data.email}"
                    )
            
            # Criar cliente
            client = Client(
                user_id=client_data.user_id,
                name=client_data.name,
                phone=client_data.phone,
                email=client_data.email,
                birth_date=client_data.birth_date,
                notes=client_data.notes,
                is_active=client_data.is_active,
                invoice_day=client_data.invoice_day,
                consult_price=client_data.consult_price,
                billing_mode=client_data.billing_mode,
            )
            
            self.db.add(client)
            self.db.commit()
            self.db.refresh(client)
            
            return ClientResponse.from_orm(client)
            
        except Exception as e:
            self.db.rollback()
            if isinstance(e, (ConflictError, ValidationError)):
                raise
            raise ValidationError(f"Erro ao criar cliente: {str(e)}")

    async def find_client(self, client_id: UUID, user_id: UUID) -> ClientResponse:
        """
        Buscar cliente por ID
        
        Args:
            client_id: ID do cliente
            user_id: ID do psicólogo proprietário
            
        Returns:
            ClientResponse: Cliente encontrado
            
        Raises:
            ClientNotFoundError: Se cliente não encontrado
        """
        client = self.db.query(Client).filter(
            and_(
                Client.id == client_id,
                Client.user_id == user_id
            )
        ).first()
        
        if not client:
            raise ClientNotFoundError(str(client_id))
        
        return ClientResponse.from_orm(client)

    async def find_client_by_phone(
        self, 
        phone: str, 
        user_id: UUID
    ) -> Optional[ClientResponse]:
        """
        Buscar cliente por telefone
        
        Args:
            phone: Telefone do cliente
            user_id: ID do psicólogo proprietário
            
        Returns:
            ClientResponse ou None: Cliente encontrado ou None
        """
        client = self.db.query(Client).filter(
            and_(
                Client.phone == phone,
                Client.user_id == user_id
            )
        ).first()
        
        if not client:
            return None
        
        return ClientResponse.from_orm(client)

    async def find_client_by_name(
        self, 
        name: str, 
        user_id: UUID
    ) -> List[ClientResponse]:
        """
        Buscar clientes por nome (busca parcial)
        
        Args:
            name: Nome do cliente (busca parcial)
            user_id: ID do psicólogo proprietário
            
        Returns:
            List[ClientResponse]: Lista de clientes encontrados
        """
        clients = self.db.query(Client).filter(
            and_(
                Client.name.ilike(f"%{name}%"),
                Client.user_id == user_id
            )
        ).order_by(Client.name).all()
        
        return [ClientResponse.from_orm(client) for client in clients]

    async def update_client(
        self, 
        client_id: UUID, 
        user_id: UUID, 
        client_data: ClientUpdate
    ) -> ClientResponse:
        """
        Atualizar cliente
        
        Args:
            client_id: ID do cliente
            user_id: ID do psicólogo proprietário
            client_data: Dados para atualização
            
        Returns:
            ClientResponse: Cliente atualizado
            
        Raises:
            ClientNotFoundError: Se cliente não encontrado
            ConflictError: Se há conflito com telefone/email existente
        """
        try:
            # Buscar cliente
            client = self.db.query(Client).filter(
                and_(
                    Client.id == client_id,
                    Client.user_id == user_id
                )
            ).first()
            
            if not client:
                raise ClientNotFoundError(str(client_id))
            
            # Verificar conflitos de telefone (se está sendo alterado)
            if client_data.phone and client_data.phone != client.phone:
                existing_phone = self.db.query(Client).filter(
                    and_(
                        Client.phone == client_data.phone,
                        Client.user_id == user_id,
                        Client.id != client_id,
                        Client.is_active == True
                    )
                ).first()
                
                if existing_phone:
                    raise ConflictError(
                        f"Já existe um cliente ativo com o telefone {client_data.phone}"
                    )
            
            # Verificar conflitos de email (se está sendo alterado)
            if client_data.email and client_data.email != client.email:
                existing_email = self.db.query(Client).filter(
                    and_(
                        Client.email == client_data.email,
                        Client.user_id == user_id,
                        Client.id != client_id,
                        Client.is_active == True
                    )
                ).first()
                
                if existing_email:
                    raise ConflictError(
                        f"Já existe um cliente ativo com o email {client_data.email}"
                    )
            
            # Atualizar campos fornecidos
            update_data = client_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(client, field, value)
            
            client.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(client)
            
            return ClientResponse.from_orm(client)
            
        except Exception as e:
            self.db.rollback()
            if isinstance(e, (ClientNotFoundError, ConflictError)):
                raise
            raise ValidationError(f"Erro ao atualizar cliente: {str(e)}")

    async def list_clients(
        self, 
        user_id: UUID, 
        is_active: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20
    ) -> ClientListResponse:
        """
        Listar clientes com paginação
        
        Args:
            user_id: ID do psicólogo proprietário
            is_active: Filtrar por status ativo/inativo
            page: Página atual
            per_page: Itens por página
            
        Returns:
            ClientListResponse: Lista paginada de clientes
        """
        query = self.db.query(Client).filter(Client.user_id == user_id)
        
        if is_active is not None:
            query = query.filter(Client.is_active == is_active)
        
        # Contar total
        total = query.count()
        
        # Aplicar paginação
        offset = (page - 1) * per_page
        clients = query.order_by(Client.name).offset(offset).limit(per_page).all()
        
        # Calcular total de páginas (mínimo 1 — uma lista vazia ainda é "página 1 de 1")
        total_pages = max(1, (total + per_page - 1) // per_page)
        
        return ClientListResponse(
            clients=[ClientResponse.from_orm(client) for client in clients],
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    async def search_clients(
        self, 
        search_request: ClientSearchRequest
    ) -> ClientListResponse:
        """
        Buscar clientes com filtros
        
        Args:
            search_request: Parâmetros de busca
            
        Returns:
            ClientListResponse: Lista paginada de clientes encontrados
        """
        query = self.db.query(Client)
        
        # Filtro por usuário
        if search_request.user_id:
            query = query.filter(Client.user_id == search_request.user_id)
        
        # Filtro por status
        if search_request.is_active is not None:
            query = query.filter(Client.is_active == search_request.is_active)
        
        # Busca por nome ou telefone
        if search_request.query:
            search_term = f"%{search_request.query}%"
            query = query.filter(
                or_(
                    Client.name.ilike(search_term),
                    Client.phone.ilike(search_term)
                )
            )
        
        # Contar total
        total = query.count()
        
        # Aplicar paginação
        offset = (search_request.page - 1) * search_request.per_page
        clients = query.order_by(Client.name).offset(offset).limit(search_request.per_page).all()
        
        # Calcular total de páginas
        total_pages = (total + search_request.per_page - 1) // search_request.per_page
        
        return ClientListResponse(
            clients=[ClientResponse.from_orm(client) for client in clients],
            total=total,
            page=search_request.page,
            per_page=search_request.per_page,
            total_pages=total_pages,
        )

    async def deactivate_client(self, client_id: UUID, user_id: UUID) -> ClientResponse:
        """
        Desativar cliente (soft delete)
        
        Args:
            client_id: ID do cliente
            user_id: ID do psicólogo proprietário
            
        Returns:
            ClientResponse: Cliente desativado
            
        Raises:
            ClientNotFoundError: Se cliente não encontrado
        """
        try:
            client = self.db.query(Client).filter(
                and_(
                    Client.id == client_id,
                    Client.user_id == user_id
                )
            ).first()
            
            if not client:
                raise ClientNotFoundError(str(client_id))
            
            client.is_active = False
            client.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(client)
            
            return ClientResponse.from_orm(client)
            
        except Exception as e:
            self.db.rollback()
            if isinstance(e, ClientNotFoundError):
                raise
            raise ValidationError(f"Erro ao desativar cliente: {str(e)}")

    async def activate_client(self, client_id: UUID, user_id: UUID) -> ClientResponse:
        """
        Reativar cliente
        
        Args:
            client_id: ID do cliente
            user_id: ID do psicólogo proprietário
            
        Returns:
            ClientResponse: Cliente reativado
            
        Raises:
            ClientNotFoundError: Se cliente não encontrado
            ConflictError: Se há conflito com telefone/email ativo
        """
        try:
            client = self.db.query(Client).filter(
                and_(
                    Client.id == client_id,
                    Client.user_id == user_id
                )
            ).first()
            
            if not client:
                raise ClientNotFoundError(str(client_id))
            
            # Verificar conflitos antes de reativar
            if client.phone:
                existing_phone = self.db.query(Client).filter(
                    and_(
                        Client.phone == client.phone,
                        Client.user_id == user_id,
                        Client.id != client_id,
                        Client.is_active == True
                    )
                ).first()
                
                if existing_phone:
                    raise ConflictError(
                        f"Já existe um cliente ativo com o telefone {client.phone}"
                    )
            
            if client.email:
                existing_email = self.db.query(Client).filter(
                    and_(
                        Client.email == client.email,
                        Client.user_id == user_id,
                        Client.id != client_id,
                        Client.is_active == True
                    )
                ).first()
                
                if existing_email:
                    raise ConflictError(
                        f"Já existe um cliente ativo com o email {client.email}"
                    )
            
            client.is_active = True
            client.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(client)
            
            return ClientResponse.from_orm(client)
            
        except Exception as e:
            self.db.rollback()
            if isinstance(e, (ClientNotFoundError, ConflictError)):
                raise
            raise ValidationError(f"Erro ao reativar cliente: {str(e)}")

    async def get_client_stats(self, user_id: UUID) -> ClientStatsResponse:
        """
        Obter estatísticas de clientes
        
        Args:
            user_id: ID do psicólogo proprietário
            
        Returns:
            ClientStatsResponse: Estatísticas dos clientes
        """
        # Total de clientes
        total_clients = self.db.query(Client).filter(Client.user_id == user_id).count()
        
        # Clientes ativos
        active_clients = self.db.query(Client).filter(
            and_(
                Client.user_id == user_id,
                Client.is_active == True
            )
        ).count()
        
        # Clientes inativos
        inactive_clients = total_clients - active_clients
        
        # Clientes criados este mês
        current_month = date.today().replace(day=1)
        clients_this_month = self.db.query(Client).filter(
            and_(
                Client.user_id == user_id,
                Client.created_at >= current_month
            )
        ).count()
        
        # Preço médio das consultas
        avg_price_result = self.db.query(
            func.avg(Client.consult_price)
        ).filter(
            and_(
                Client.user_id == user_id,
                Client.is_active == True,
                Client.consult_price.isnot(None)
            )
        ).scalar()
        
        average_consult_price = Decimal(str(avg_price_result)) if avg_price_result else None
        
        return ClientStatsResponse(
            total_clients=total_clients,
            active_clients=active_clients,
            inactive_clients=inactive_clients,
            clients_this_month=clients_this_month,
            average_consult_price=average_consult_price,
        )
