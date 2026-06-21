"""
Agente de Cliente usando Pydantic AI
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import settings
from app.core.exceptions import ClientNotFoundError, ConflictError, ValidationError
from app.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientSearchRequest,
    ClientStatsResponse,
    ClientUpdate,
)
from app.services.client_service import ClientService


class ClientAgent:
    """Agente para gestão de clientes usando Pydantic AI"""

    def __init__(self):
        self.client_service: Optional[ClientService] = None
        self.agent = self._setup_agent()

    def _setup_agent(self) -> Agent:
        """Configurar o agente Pydantic AI"""
        
        model = OpenAIChatModel(
            model_name=settings.OPENAI_MODEL,
        )
        
        agent = Agent(
            model=model,
            output_type=Dict[str, Any],
            system_prompt=self._get_system_prompt(),
        )
        
        # Registrar tools
        agent.tool(self.client_find)
        agent.tool(self.client_create)
        agent.tool(self.client_update)
        agent.tool(self.client_list)
        agent.tool(self.client_search)
        agent.tool(self.client_deactivate)
        agent.tool(self.client_activate)
        agent.tool(self.client_stats)
        
        return agent

    def _get_system_prompt(self) -> str:
        """Prompt do sistema para o agente de cliente"""
        return """
Você é um assistente especializado em gestão de clientes para psicólogos.

Sua função é ajudar psicólogos a:
- Cadastrar novos clientes
- Buscar informações de clientes existentes
- Atualizar dados de clientes
- Listar clientes com filtros
- Gerenciar status ativo/inativo de clientes
- Obter estatísticas de clientes

REGRAS IMPORTANTES:
1. Sempre valide dados antes de processar
2. Use as tools apropriadas para cada operação
3. Forneça respostas claras e estruturadas
4. Trate erros de forma amigável
5. Mantenha confidencialidade dos dados dos clientes

FORMATO DE RESPOSTA:
- Sempre retorne um JSON com: response, success, data (quando aplicável)
- Inclua mensagens de erro claras quando algo der errado
- Forneça sugestões quando apropriado

EXEMPLOS DE OPERAÇÕES:
- "Cadastrar cliente João Silva, telefone 11999999999"
- "Buscar cliente por telefone 11999999999"
- "Listar todos os clientes ativos"
- "Atualizar preço da consulta do cliente João Silva para R$ 150,00"
- "Desativar cliente João Silva"
- "Mostrar estatísticas dos clientes"
"""

    async def process(self, message: str, user_id: UUID) -> Dict[str, Any]:
        """
        Processar mensagem do usuário
        
        Args:
            message: Mensagem do usuário
            user_id: ID do psicólogo proprietário
            
        Returns:
            Dict com resposta estruturada
        """
        if not self.client_service:
            return {
                "response": "Serviço de cliente não configurado",
                "success": False,
                "error": "ClientService not initialized"
            }
        
        try:
            # Adicionar contexto do usuário à mensagem
            context_message = f"""
Usuário (ID: {user_id}) disse: {message}

Use as tools disponíveis para processar a solicitação do usuário.
"""
            
            result = await self.agent.run(context_message)
            
            return {
                "response": result.data.get("response", "Operação realizada com sucesso"),
                "success": result.data.get("success", True),
                "data": result.data.get("data"),
                "agent": "client_agent",
                "usage": result.usage.model_dump() if result.usage else {}
            }
            
        except Exception as e:
            return {
                "response": f"Erro ao processar solicitação: {str(e)}",
                "success": False,
                "error": str(e),
                "agent": "client_agent"
            }

    async def client_find(
        self, 
        ctx: RunContext[None],
        client_id: str = None, 
        phone: str = None, 
        name: str = None
    ) -> Dict[str, Any]:
        """
        Buscar cliente por ID, telefone ou nome
        
        Args:
            client_id: ID do cliente
            phone: Telefone do cliente
            name: Nome do cliente (busca parcial)
            
        Returns:
            Dict com resultado da busca
        """
        try:
            if client_id:
                client = await self.client_service.find_client(
                    UUID(client_id), 
                    self._get_current_user_id()
                )
                return {
                    "response": f"Cliente encontrado: {client.name}",
                    "success": True,
                    "data": client.dict()
                }
            
            elif phone:
                client = await self.client_service.find_client_by_phone(
                    phone, 
                    self._get_current_user_id()
                )
                if client:
                    return {
                        "response": f"Cliente encontrado: {client.name}",
                        "success": True,
                        "data": client.dict()
                    }
                else:
                    return {
                        "response": f"Nenhum cliente encontrado com o telefone {phone}",
                        "success": False
                    }
            
            elif name:
                clients = await self.client_service.find_client_by_name(
                    name, 
                    self._get_current_user_id()
                )
                if clients:
                    return {
                        "response": f"Encontrados {len(clients)} cliente(s) com nome '{name}'",
                        "success": True,
                        "data": [client.dict() for client in clients]
                    }
                else:
                    return {
                        "response": f"Nenhum cliente encontrado com o nome '{name}'",
                        "success": False
                    }
            
            else:
                return {
                    "response": "É necessário fornecer client_id, phone ou name para buscar",
                    "success": False
                }
                
        except ClientNotFoundError as e:
            return {
                "response": f"Cliente não encontrado: {str(e)}",
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Erro ao buscar cliente: {str(e)}",
                "success": False
            }

    async def client_create(
        self,
        ctx: RunContext[None],
        name: str,
        phone: str,
        email: str = None,
        birth_date: str = None,
        invoice_day: int = None,
        consult_price: float = None,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        Criar novo cliente
        
        Args:
            name: Nome completo do cliente
            phone: Telefone do cliente
            email: Email do cliente (opcional)
            birth_date: Data de nascimento (YYYY-MM-DD)
            invoice_day: Dia do mês para faturamento (1-31)
            consult_price: Preço da consulta em reais
            notes: Observações sobre o cliente
            
        Returns:
            Dict com resultado da criação
        """
        try:
            from datetime import datetime
            from decimal import Decimal

            # Preparar dados
            client_data = ClientCreate(
                user_id=self._get_current_user_id(),
                name=name,
                phone=phone,
                email=email,
                birth_date=datetime.strptime(birth_date, "%Y-%m-%d").date() if birth_date else None,
                invoice_day=invoice_day,
                consult_price=Decimal(str(consult_price)) if consult_price else None,
                notes=notes,
            )
            
            client = await self.client_service.create_client(client_data)
            
            return {
                "response": f"Cliente '{client.name}' criado com sucesso!",
                "success": True,
                "data": client.dict()
            }
            
        except ConflictError as e:
            return {
                "response": f"Erro: {str(e)}",
                "success": False
            }
        except ValidationError as e:
            return {
                "response": f"Dados inválidos: {str(e)}",
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Erro ao criar cliente: {str(e)}",
                "success": False
            }

    async def client_update(
        self,
        ctx: RunContext[None],
        client_id: str,
        name: str = None,
        phone: str = None,
        email: str = None,
        birth_date: str = None,
        invoice_day: int = None,
        consult_price: float = None,
        notes: str = None,
        is_active: bool = None
    ) -> Dict[str, Any]:
        """
        Atualizar cliente existente
        
        Args:
            client_id: ID do cliente
            name: Nome completo do cliente
            phone: Telefone do cliente
            email: Email do cliente
            birth_date: Data de nascimento (YYYY-MM-DD)
            invoice_day: Dia do mês para faturamento (1-31)
            consult_price: Preço da consulta em reais
            notes: Observações sobre o cliente
            is_active: Status ativo/inativo
            
        Returns:
            Dict com resultado da atualização
        """
        try:
            from datetime import datetime
            from decimal import Decimal

            # Preparar dados de atualização
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if phone is not None:
                update_data["phone"] = phone
            if email is not None:
                update_data["email"] = email
            if birth_date is not None:
                update_data["birth_date"] = datetime.strptime(birth_date, "%Y-%m-%d").date()
            if invoice_day is not None:
                update_data["invoice_day"] = invoice_day
            if consult_price is not None:
                update_data["consult_price"] = Decimal(str(consult_price))
            if notes is not None:
                update_data["notes"] = notes
            if is_active is not None:
                update_data["is_active"] = is_active
            
            client_update = ClientUpdate(**update_data)
            client = await self.client_service.update_client(
                UUID(client_id),
                self._get_current_user_id(),
                client_update
            )
            
            return {
                "response": f"Cliente '{client.name}' atualizado com sucesso!",
                "success": True,
                "data": client.dict()
            }
            
        except ClientNotFoundError as e:
            return {
                "response": f"Cliente não encontrado: {str(e)}",
                "success": False
            }
        except ConflictError as e:
            return {
                "response": f"Erro: {str(e)}",
                "success": False
            }
        except ValidationError as e:
            return {
                "response": f"Dados inválidos: {str(e)}",
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Erro ao atualizar cliente: {str(e)}",
                "success": False
            }

    async def client_list(
        self,
        ctx: RunContext[None],
        is_active: bool = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict[str, Any]:
        """
        Listar clientes com paginação
        
        Args:
            is_active: Filtrar por status ativo/inativo
            page: Página atual
            per_page: Itens por página
            
        Returns:
            Dict com lista de clientes
        """
        try:
            result = await self.client_service.list_clients(
                self._get_current_user_id(),
                is_active=is_active,
                page=page,
                per_page=per_page
            )
            
            return {
                "response": f"Lista de clientes (página {page} de {result.total_pages})",
                "success": True,
                "data": result.dict()
            }
            
        except Exception as e:
            return {
                "response": f"Erro ao listar clientes: {str(e)}",
                "success": False
            }

    async def client_search(
        self,
        ctx: RunContext[None],
        query: str = None,
        is_active: bool = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict[str, Any]:
        """
        Buscar clientes com filtros
        
        Args:
            query: Termo de busca (nome ou telefone)
            is_active: Filtrar por status ativo/inativo
            page: Página atual
            per_page: Itens por página
            
        Returns:
            Dict com resultado da busca
        """
        try:
            search_request = ClientSearchRequest(
                query=query,
                is_active=is_active,
                page=page,
                per_page=per_page,
                user_id=self._get_current_user_id()
            )
            
            result = await self.client_service.search_clients(search_request)
            
            return {
                "response": f"Busca realizada: {result.total} cliente(s) encontrado(s)",
                "success": True,
                "data": result.dict()
            }
            
        except Exception as e:
            return {
                "response": f"Erro ao buscar clientes: {str(e)}",
                "success": False
            }

    async def client_deactivate(
        self,
        ctx: RunContext[None],
        client_id: str) -> Dict[str, Any]:
        """
        Desativar cliente
        
        Args:
            client_id: ID do cliente
            
        Returns:
            Dict com resultado da desativação
        """
        try:
            client = await self.client_service.deactivate_client(
                UUID(client_id),
                self._get_current_user_id()
            )
            
            return {
                "response": f"Cliente '{client.name}' desativado com sucesso!",
                "success": True,
                "data": client.dict()
            }
            
        except ClientNotFoundError as e:
            return {
                "response": f"Cliente não encontrado: {str(e)}",
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Erro ao desativar cliente: {str(e)}",
                "success": False
            }

    async def client_activate(
        self,
        ctx: RunContext[None],
        client_id: str) -> Dict[str, Any]:
        """
        Reativar cliente
        
        Args:
            client_id: ID do cliente
            
        Returns:
            Dict com resultado da reativação
        """
        try:
            client = await self.client_service.activate_client(
                UUID(client_id),
                self._get_current_user_id()
            )
            
            return {
                "response": f"Cliente '{client.name}' reativado com sucesso!",
                "success": True,
                "data": client.dict()
            }
            
        except ClientNotFoundError as e:
            return {
                "response": f"Cliente não encontrado: {str(e)}",
                "success": False
            }
        except ConflictError as e:
            return {
                "response": f"Erro: {str(e)}",
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Erro ao reativar cliente: {str(e)}",
                "success": False
            }

    async def client_stats(
        self,
        ctx: RunContext[None]) -> Dict[str, Any]:
        """
        Obter estatísticas de clientes
        
        Returns:
            Dict com estatísticas
        """
        try:
            stats = await self.client_service.get_client_stats(
                self._get_current_user_id()
            )
            
            return {
                "response": "Estatísticas dos clientes obtidas com sucesso!",
                "success": True,
                "data": stats.dict()
            }
            
        except Exception as e:
            return {
                "response": f"Erro ao obter estatísticas: {str(e)}",
                "success": False
            }

    def _get_current_user_id(self, context: AgentContext) -> UUID:
        """
        Obter ID do usuário atual do contexto
        """
        return context.user.user_id
