"""
Calendar Agent - Gestão de agendamentos e eventos
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CalendarAgent:
    """Agente especializado em gestão de calendário e agendamentos."""
    
    def __init__(self):
        """Inicializa o CalendarAgent."""
        self.calendar_service: Optional[Any] = None
        model = OpenAIChatModel(
            model_name=settings.OPENAI_MODEL,
        )
        
        self.agent = Agent(
            model=model,
            output_type=Dict[str, Any],
            system_prompt="""Você é um assistente especializado em gestão de calendário e agendamentos para psicólogos.

Sua função é ajudar com:
- Agendamento de consultas
- Busca de horários disponíveis
- Atualização de agendamentos
- Cancelamento de consultas
- Listagem de eventos

**Instruções importantes:**
- Sempre valide se o cliente existe antes de agendar
- Verifique conflitos de horário
- Use formato de data/hora brasileiro
- Seja claro e objetivo nas respostas
- Confirme sempre os dados antes de criar/atualizar

**Exemplos de uso:**
- "Agendar consulta para João Silva amanhã às 14h"
- "Ver horários disponíveis na próxima semana"
- "Cancelar consulta de hoje às 16h"
- "Listar consultas da próxima semana"

Seja sempre educado, prestativo e preciso nas informações.""",
        )
        self._setup_tools()

    def _setup_tools(self) -> None:
        """Configura as ferramentas do agente."""
        
        @self.agent.tool
        def event_create(
            ctx: RunContext[None],
            title: str,
            start_time: str,
            duration_minutes: int,
            client_id: str,
            user_id: str,
            description: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Cria um novo evento/consulta.
            
            Args:
                ctx: Contexto de execução do Pydantic AI
                title: Título do evento
                start_time: Data/hora de início (formato ISO)
                duration_minutes: Duração em minutos
                client_id: ID do cliente
                user_id: ID do usuário (psicólogo)
                description: Descrição opcional
                
            Returns:
                Dict[str, Any]: Resultado da criação
            """
            try:
                if not self.calendar_service:
                    return {
                        "success": False,
                        "error": "Serviço de calendário não disponível",
                        "event_id": None
                    }
                
                # Aqui seria implementada a lógica real de criação
                # Por enquanto, retornamos um mock
                return {
                    "success": True,
                    "event_id": "mock_event_id",
                    "message": f"Evento '{title}' criado com sucesso para {start_time}",
                    "event_data": {
                        "title": title,
                        "start_time": start_time,
                        "duration_minutes": duration_minutes,
                        "client_id": client_id,
                        "user_id": user_id,
                        "description": description
                    }
                }
            except Exception as e:
                logger.error(f"Erro ao criar evento: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "event_id": None
                }

        @self.agent.tool
        def event_find(
            event_id: Optional[str] = None,
            client_id: Optional[str] = None,
            user_id: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None
        ) -> List[Dict[str, Any]]:
            """
            Busca eventos baseado nos critérios fornecidos.
            
            Args:
                event_id: ID específico do evento
                client_id: ID do cliente
                user_id: ID do usuário
                start_date: Data de início (formato ISO)
                end_date: Data de fim (formato ISO)
                
            Returns:
                List[Dict[str, Any]]: Lista de eventos encontrados
            """
            try:
                if not self.calendar_service:
                    return []
                
                # Aqui seria implementada a lógica real de busca
                # Por enquanto, retornamos um mock
                return [
                    {
                        "event_id": "mock_event_1",
                        "title": "Consulta com João Silva",
                        "start_time": "2024-01-15T14:00:00",
                        "duration_minutes": 50,
                        "client_id": "client_123",
                        "user_id": "user_456",
                        "status": "scheduled"
                    }
                ]
            except Exception as e:
                logger.error(f"Erro ao buscar eventos: {e}")
                return []

        @self.agent.tool
        def event_update(
            event_id: str,
            title: Optional[str] = None,
            start_time: Optional[str] = None,
            duration_minutes: Optional[int] = None,
            description: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Atualiza um evento existente.
            
            Args:
                event_id: ID do evento
                title: Novo título (opcional)
                start_time: Nova data/hora (opcional)
                duration_minutes: Nova duração (opcional)
                description: Nova descrição (opcional)
                
            Returns:
                Dict[str, Any]: Resultado da atualização
            """
            try:
                if not self.calendar_service:
                    return {
                        "success": False,
                        "error": "Serviço de calendário não disponível"
                    }
                
                # Aqui seria implementada a lógica real de atualização
                # Por enquanto, retornamos um mock
                return {
                    "success": True,
                    "message": f"Evento {event_id} atualizado com sucesso",
                    "updated_fields": {
                        "title": title,
                        "start_time": start_time,
                        "duration_minutes": duration_minutes,
                        "description": description
                    }
                }
            except Exception as e:
                logger.error(f"Erro ao atualizar evento: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }

        @self.agent.tool
        def event_list(
            user_id: str,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            status: Optional[str] = None
        ) -> List[Dict[str, Any]]:
            """
            Lista eventos do usuário.
            
            Args:
                user_id: ID do usuário
                start_date: Data de início (opcional)
                end_date: Data de fim (opcional)
                status: Status dos eventos (opcional)
                
            Returns:
                List[Dict[str, Any]]: Lista de eventos
            """
            try:
                if not self.calendar_service:
                    return []
                
                # Aqui seria implementada a lógica real de listagem
                # Por enquanto, retornamos um mock
                return [
                    {
                        "event_id": "mock_event_1",
                        "title": "Consulta com João Silva",
                        "start_time": "2024-01-15T14:00:00",
                        "duration_minutes": 50,
                        "client_id": "client_123",
                        "status": "scheduled"
                    },
                    {
                        "event_id": "mock_event_2", 
                        "title": "Consulta com Maria Santos",
                        "start_time": "2024-01-15T16:00:00",
                        "duration_minutes": 50,
                        "client_id": "client_456",
                        "status": "scheduled"
                    }
                ]
            except Exception as e:
                logger.error(f"Erro ao listar eventos: {e}")
                return []

        @self.agent.tool
        def event_cancel(event_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
            """
            Cancela um evento.
            
            Args:
                event_id: ID do evento
                reason: Motivo do cancelamento (opcional)
                
            Returns:
                Dict[str, Any]: Resultado do cancelamento
            """
            try:
                if not self.calendar_service:
                    return {
                        "success": False,
                        "error": "Serviço de calendário não disponível"
                    }
                
                # Aqui seria implementada a lógica real de cancelamento
                # Por enquanto, retornamos um mock
                return {
                    "success": True,
                    "message": f"Evento {event_id} cancelado com sucesso",
                    "reason": reason
                }
            except Exception as e:
                logger.error(f"Erro ao cancelar evento: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }

    async def process(self, message: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa uma mensagem relacionada a calendário.
        
        Args:
            message: Mensagem do usuário
            user_context: Contexto do usuário
            
        Returns:
            Dict[str, Any]: Resposta processada
        """
        try:
            logger.info(f"CalendarAgent processando mensagem: {message[:100]}...")
            
            # Configurar ferramentas
            self._setup_tools()
            
            # Processar mensagem com o agente
            result = await self.agent.run(message, user_context=user_context)
            
            logger.info("CalendarAgent processou mensagem com sucesso")
            return {
                "response": result.data if hasattr(result, 'data') else str(result),
                "agent": "calendar_agent",
                "usage": getattr(result, 'usage', {}),
                "metadata": {
                    "processed_at": "2024-01-15T12:00:00Z",
                    "agent_version": "0.1.0"
                }
            }
            
        except Exception as e:
            logger.error(f"Erro no CalendarAgent: {e}")
            return {
                "response": f"Desculpe, ocorreu um erro ao processar sua solicitação de calendário: {str(e)}",
                "agent": "calendar_agent",
                "usage": {},
                "metadata": {"error": str(e)}
            }
