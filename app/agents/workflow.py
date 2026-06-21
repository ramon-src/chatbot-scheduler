"""
SimplificaPsi Workflow - Orquestração principal dos agentes
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.agents.agent_manager import AgentManager, AgentRouting
from app.agents.calendar_agent import CalendarAgent
from app.agents.client_agent import ClientAgent
from app.agents.context import AgentContext, MessageContext, SessionContext, UserContext
from app.core.exceptions import SimplificaPsiException
from app.core.logging import get_logger

logger = get_logger(__name__)


class WorkflowResponse(BaseModel):
    """Resposta do workflow."""
    
    response: str = Field(..., description="Resposta gerada pelo agente")
    agent: str = Field(..., description="Agente que processou a mensagem")
    confidence: float = Field(..., description="Confiança na resposta")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Entidades extraídas")
    usage: Dict[str, Any] = Field(default_factory=dict, description="Uso de tokens e custos")
    response_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class SimplificaPsiWorkflow:
    """Workflow principal do SimplificaPsi."""
    
    def __init__(self):
        """Inicializa o workflow."""
        # Agentes
        self.manager = AgentManager()
        self.client_agent = ClientAgent()
        self.calendar_agent = CalendarAgent()
        
        # Configurações
        self.max_retries = 3
        self.timeout_seconds = 30

    def _create_context(
        self, 
        message: str, 
        user_id: UUID, 
        session_id: Optional[UUID] = None,
        whatsapp_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None
    ) -> AgentContext:
        """
        Cria o contexto do agente a partir dos dados fornecidos.
        
        Args:
            message: Mensagem do usuário
            user_id: ID do usuário
            session_id: ID da sessão (opcional)
            whatsapp_id: ID do WhatsApp (opcional)
            user_name: Nome do usuário (opcional)
            user_email: Email do usuário (opcional)
            user_phone: Telefone do usuário (opcional)
            
        Returns:
            AgentContext: Contexto criado
        """
        # Usar session_id fornecido ou gerar novo
        if session_id is None:
            session_id = uuid4()
        
        # Criar contexto do usuário
        user_context = UserContext(
            user_id=user_id,
            name=user_name,
            email=user_email,
            phone=user_phone
        )
        
        # Criar contexto da sessão
        session_context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            whatsapp_id=whatsapp_id
        )
        
        # Criar contexto da mensagem
        message_context = MessageContext(
            message_id=uuid4(),
            session_id=session_id,
            role="user",
            content=message
        )
        
        # Criar contexto principal
        context = AgentContext(
            user=user_context,
            session=session_context,
            current_message=message_context
        )
        
        return context

    async def process_message(
        self,
        message: str,
        user_id: UUID,
        session_id: Optional[UUID] = None,
        whatsapp_id: Optional[str] = None,
        user_name: Optional[str] = None,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None,
        client_service: Optional[Any] = None,
        calendar_service: Optional[Any] = None
    ) -> WorkflowResponse:
        """
        Processa uma mensagem através do workflow completo.
        
        Args:
            message: Mensagem do usuário
            user_id: ID do usuário
            session_id: ID da sessão (opcional)
            whatsapp_id: ID do WhatsApp (opcional)
            user_name: Nome do usuário (opcional)
            user_email: Email do usuário (opcional)
            user_phone: Telefone do usuário (opcional)
            client_service: Serviço de cliente (opcional)
            calendar_service: Serviço de calendário (opcional)
            
        Returns:
            WorkflowResponse: Resposta processada
        """
        try:
            logger.info(f"Processando mensagem: {message[:100]}...")
            
            # Criar contexto
            context = self._create_context(
                message=message,
                user_id=user_id,
                session_id=session_id,
                whatsapp_id=whatsapp_id,
                user_name=user_name,
                user_email=user_email,
                user_phone=user_phone
            )
            
            # Adicionar mensagem ao histórico
            context.add_message(context.current_message)
            
            # Roteamento através do AgentManager
            routing = await self.manager.process(message, context.to_dict())
            
            # Atualizar metadados de roteamento
            context.update_routing_metadata({
                "routed_agent": routing.agent,
                "confidence": routing.confidence,
                "reasoning": routing.reasoning,
                "entities": routing.entities
            })
            
            # Processar com o agente apropriado
            if routing.agent == "client_agent":
                return await self._process_with_client_agent(
                    message, context, routing, client_service
                )
            elif routing.agent == "calendar_agent":
                return await self._process_with_calendar_agent(
                    message, context, routing, calendar_service
                )
            else:
                return await self._process_with_manager(
                    message, context, routing
                )
                
        except Exception as e:
            logger.error(f"Erro no workflow: {e}")
            return WorkflowResponse(
                response=f"Desculpe, ocorreu um erro ao processar sua mensagem: {str(e)}",
                agent="agent_manager",
                confidence=0.0,
                entities={},
                usage={},
                response_metadata={"error": str(e)}
            )

    async def _process_with_client_agent(
        self,
        message: str,
        context: AgentContext,
        routing: AgentRouting,
        client_service: Optional[Any]
    ) -> WorkflowResponse:
        """Processa mensagem com o ClientAgent."""
        try:
            # Injetar dependências
            if client_service:
                self.client_agent.client_service = client_service
            
            # Processar mensagem
            result = await self.client_agent.process(message, context.to_dict())
            
            return WorkflowResponse(
                response=result.get("response", "Processado pelo ClientAgent"),
                agent="client_agent",
                confidence=routing.confidence,
                entities=routing.entities,
                usage=result.get("usage", {}),
                response_metadata={
                    "routing_reasoning": routing.reasoning,
                    "client_agent_metadata": result.get("metadata", {})
                }
            )
            
        except Exception as e:
            logger.error(f"Erro no ClientAgent: {e}")
            return WorkflowResponse(
                response=f"Erro ao processar com ClientAgent: {str(e)}",
                agent="client_agent",
                confidence=0.0,
                entities=routing.entities,
                usage={},
                response_metadata={"error": str(e)}
            )

    async def _process_with_calendar_agent(
        self,
        message: str,
        context: AgentContext,
        routing: AgentRouting,
        calendar_service: Optional[Any]
    ) -> WorkflowResponse:
        """Processa mensagem com o CalendarAgent."""
        try:
            # Injetar dependências
            if calendar_service:
                self.calendar_agent.calendar_service = calendar_service
            
            # Processar mensagem
            result = await self.calendar_agent.process(message, context.to_dict())
            
            return WorkflowResponse(
                response=result.get("response", "Processado pelo CalendarAgent"),
                agent="calendar_agent",
                confidence=routing.confidence,
                entities=routing.entities,
                usage=result.get("usage", {}),
                response_metadata={
                    "routing_reasoning": routing.reasoning,
                    "calendar_agent_metadata": result.get("metadata", {})
                }
            )
            
        except Exception as e:
            logger.error(f"Erro no CalendarAgent: {e}")
            return WorkflowResponse(
                response=f"Erro ao processar com CalendarAgent: {str(e)}",
                agent="calendar_agent",
                confidence=0.0,
                entities=routing.entities,
                usage={},
                response_metadata={"error": str(e)}
            )

    async def _process_with_manager(
        self,
        message: str,
        context: AgentContext,
        routing: AgentRouting
    ) -> WorkflowResponse:
        """Processa mensagem com o AgentManager."""
        try:
            # Resposta padrão do manager
            response = self._generate_manager_response(message, routing)
            
            return WorkflowResponse(
                response=response,
                agent="agent_manager",
                confidence=routing.confidence,
                entities=routing.entities,
                usage={},
                response_metadata={
                    "routing_reasoning": routing.reasoning,
                    "manager_response": True
                }
            )
            
        except Exception as e:
            logger.error(f"Erro no AgentManager: {e}")
            return WorkflowResponse(
                response=f"Erro ao processar com AgentManager: {str(e)}",
                agent="agent_manager",
                confidence=0.0,
                entities=routing.entities,
                usage={},
                response_metadata={"error": str(e)}
            )

    def _generate_manager_response(self, message: str, routing: AgentRouting) -> str:
        """
        Gera resposta padrão do AgentManager.
        
        Args:
            message: Mensagem original
            routing: Informações de roteamento
            
        Returns:
            str: Resposta gerada
        """
        # Respostas baseadas na confiança
        if routing.confidence < 0.3:
            return "Desculpe, não consegui entender sua mensagem. Pode reformular de outra forma? Estou aqui para ajudar com gestão de clientes e agendamentos."
        
        # Respostas baseadas em palavras-chave
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["oi", "olá", "bom dia", "boa tarde", "boa noite"]):
            return "Olá! Sou o SimplificaPsi, seu assistente para gestão de consultório. Posso ajudar com cadastro de clientes e agendamentos. Como posso te ajudar hoje?"
        
        if any(word in message_lower for word in ["ajuda", "help", "como funciona"]):
            return """Posso te ajudar com:

👥 **Gestão de Clientes:**
- Cadastrar novos clientes
- Buscar clientes existentes
- Atualizar dados de clientes
- Listar todos os clientes

📅 **Agendamentos:**
- Agendar consultas
- Ver horários disponíveis
- Cancelar consultas
- Listar eventos

Como posso te ajudar hoje?"""
        
        if any(word in message_lower for word in ["obrigado", "valeu", "tchau", "até logo"]):
            return "De nada! Estou sempre aqui para ajudar. Até a próxima! 😊"
        
        # Resposta padrão
        return f"Entendi sua mensagem. {routing.reasoning} Como posso te ajudar melhor?"

    def get_workflow_status(self) -> Dict[str, Any]:
        """
        Retorna o status do workflow.
        
        Returns:
            Dict[str, Any]: Status do workflow
        """
        return {
            "workflow_version": "0.1.0",
            "agents_available": [
                "agent_manager",
                "client_agent", 
                "calendar_agent"
            ],
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "status": "active"
        }
