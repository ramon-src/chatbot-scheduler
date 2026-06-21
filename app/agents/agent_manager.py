"""
Agent Manager - Roteamento inteligente de intenções
"""

from typing import Any, Dict, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AgentRouting(BaseModel):
    """Modelo para roteamento de agentes."""
    
    agent: Literal["client_agent", "calendar_agent", "agent_manager"] = Field(
        ..., description="Agente que deve processar a mensagem"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confiança na classificação (0.0 a 1.0)"
    )
    reasoning: str = Field(
        ..., description="Explicação do roteamento escolhido"
    )
    entities: Dict[str, Any] = Field(
        default_factory=dict, description="Entidades extraídas da mensagem"
    )


class AgentManager:
    """Agente responsável por rotear mensagens para o agente correto."""
    
    def __init__(self):
        """Inicializa o AgentManager."""
        model = OpenAIChatModel(
            model_name=settings.OPENAI_MODEL,
        )
        
        self.agent = Agent(
            model=model,
            output_type=AgentRouting,
            system_prompt="""Você é um agente especializado em classificar intenções e rotear mensagens para agentes especializados.

Sua função é analisar mensagens de usuários e determinar qual agente deve processá-las:

1. **client_agent**: Para operações relacionadas a clientes:
   - Cadastro de novos clientes
   - Busca de clientes existentes
   - Atualização de dados de clientes
   - Listagem de clientes
   - Desativação de clientes
   - Palavras-chave: cliente, cadastrar, buscar, atualizar, listar, desativar, nome, telefone, email

2. **calendar_agent**: Para operações relacionadas a agendamentos:
   - Criação de consultas/eventos
   - Busca de horários disponíveis
   - Atualização de agendamentos
   - Cancelamento de consultas
   - Listagem de eventos
   - Palavras-chave: agendar, consulta, horário, data, cancelar, evento, calendário

3. **agent_manager**: Para mensagens que não se encaixam nas categorias acima:
   - Saudações gerais
   - Dúvidas sobre o sistema
   - Mensagens ambíguas
   - Palavras-chave: oi, olá, ajuda, como funciona, dúvida

**Instruções importantes:**
- Analise cuidadosamente a mensagem do usuário
- Identifique palavras-chave e contexto
- Extraia entidades relevantes (nomes, datas, horários, etc.)
- Atribua uma confiança de 0.0 a 1.0 baseada na clareza da intenção
- Se a mensagem for ambígua, use agent_manager com baixa confiança
- Sempre explique seu raciocínio no campo reasoning

**Exemplos de classificação:**
- "Quero cadastrar um novo cliente" → client_agent (confiança: 0.9)
- "Agendar consulta para amanhã às 14h" → calendar_agent (confiança: 0.9)
- "Oi, como você funciona?" → agent_manager (confiança: 0.8)
- "Buscar cliente João Silva" → client_agent (confiança: 0.8)
- "Cancelar consulta de hoje" → calendar_agent (confiança: 0.8)
""",
        )
        self._setup_tools()

    def _setup_tools(self) -> None:
        """Configura as ferramentas do agente."""
        # O AgentManager não precisa de tools, apenas usa o system prompt
        # para classificar intenções e retornar AgentRouting
        pass

    async def process(self, message: str, user_context: Dict[str, Any]) -> AgentRouting:
        """
        Processa uma mensagem e retorna o roteamento para o agente apropriado.
        
        Args:
            message: Mensagem do usuário
            user_context: Contexto do usuário
            
        Returns:
            AgentRouting: Informações sobre o roteamento
        """
        try:
            logger.info(f"AgentManager processando mensagem: {message[:100]}...")
            
            # Configurar ferramentas
            self._setup_tools()
            
            # Processar mensagem com o agente
            result = await self.agent.run(
                message,
                user_context=user_context,
                result_type=AgentRouting
            )
            
            logger.info(f"Roteamento escolhido: {result.agent} (confiança: {result.confidence})")
            return result
            
        except Exception as e:
            logger.error(f"Erro no AgentManager: {e}")
            # Em caso de erro, rotear para agent_manager
            return AgentRouting(
                agent="agent_manager",
                confidence=0.0,
                reasoning=f"Erro no processamento: {str(e)}",
                entities={}
            )

    def get_agent_description(self, agent_name: str) -> str:
        """
        Retorna a descrição de um agente específico.
        
        Args:
            agent_name: Nome do agente
            
        Returns:
            str: Descrição do agente
        """
        descriptions = {
            "client_agent": "Agente especializado em gestão de clientes (cadastro, busca, atualização, listagem)",
            "calendar_agent": "Agente especializado em gestão de calendário (agendamentos, consultas, eventos)",
            "agent_manager": "Agente geral para saudações, dúvidas e mensagens ambíguas"
        }
        return descriptions.get(agent_name, "Agente desconhecido")

    def get_supported_intentions(self) -> Dict[str, list]:
        """
        Retorna as intenções suportadas por cada agente.
        
        Returns:
            Dict[str, list]: Mapeamento de agente para lista de intenções
        """
        return {
            "client_agent": [
                "cadastrar_cliente",
                "buscar_cliente", 
                "atualizar_cliente",
                "listar_clientes",
                "desativar_cliente"
            ],
            "calendar_agent": [
                "agendar_consulta",
                "buscar_horarios",
                "atualizar_agendamento",
                "cancelar_consulta",
                "listar_eventos"
            ],
            "agent_manager": [
                "saudacao",
                "duvida_sistema",
                "mensagem_ambigua",
                "ajuda_geral"
            ]
        }
