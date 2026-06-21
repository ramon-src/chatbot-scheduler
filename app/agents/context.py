"""
Context Management - Compartilhamento de dados entre agentes
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)


class UserContext(BaseModel):
    """Contexto do usuário (psicólogo)."""
    
    user_id: UUID = Field(..., description="ID único do usuário")
    name: Optional[str] = Field(None, description="Nome do usuário")
    email: Optional[str] = Field(None, description="Email do usuário")
    phone: Optional[str] = Field(None, description="Telefone do usuário")
    is_active: bool = Field(True, description="Se o usuário está ativo")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionContext(BaseModel):
    """Contexto da sessão de chat."""
    
    session_id: UUID = Field(..., description="ID único da sessão")
    user_id: UUID = Field(..., description="ID do usuário da sessão")
    whatsapp_id: Optional[str] = Field(None, description="ID do WhatsApp")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(True, description="Se a sessão está ativa")
    message_count: int = Field(0, description="Número de mensagens na sessão")


class MessageContext(BaseModel):
    """Contexto de uma mensagem específica."""
    
    message_id: UUID = Field(..., description="ID único da mensagem")
    session_id: UUID = Field(..., description="ID da sessão")
    role: str = Field(..., description="Papel da mensagem (user, assistant, system)")
    content: str = Field(..., description="Conteúdo da mensagem")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados da mensagem")


class AgentContext(BaseModel):
    """Contexto principal compartilhado entre agentes."""
    
    # Contexto do usuário
    user: UserContext = Field(..., description="Contexto do usuário")
    
    # Contexto da sessão
    session: SessionContext = Field(..., description="Contexto da sessão")
    
    # Mensagem atual
    current_message: MessageContext = Field(..., description="Mensagem atual")
    
    # Histórico de mensagens (últimas 10)
    message_history: List[MessageContext] = Field(
        default_factory=list, 
        description="Histórico de mensagens da sessão"
    )
    
    # Dados compartilhados entre agentes
    shared_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dados compartilhados entre agentes"
    )
    
    # Configurações da sessão
    session_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Configurações específicas da sessão"
    )
    
    # Metadados de roteamento
    routing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados do último roteamento"
    )

    def add_message(self, message: MessageContext) -> None:
        """
        Adiciona uma mensagem ao histórico.
        
        Args:
            message: Mensagem a ser adicionada
        """
        self.message_history.append(message)
        # Manter apenas as últimas 10 mensagens
        if len(self.message_history) > 10:
            self.message_history = self.message_history[-10:]
        
        # Atualizar contador da sessão
        self.session.message_count += 1
        self.session.updated_at = datetime.utcnow()

    def get_recent_messages(self, count: int = 5) -> List[MessageContext]:
        """
        Retorna as mensagens mais recentes.
        
        Args:
            count: Número de mensagens a retornar
            
        Returns:
            List[MessageContext]: Lista de mensagens recentes
        """
        return self.message_history[-count:] if self.message_history else []

    def set_shared_data(self, key: str, value: Any) -> None:
        """
        Define um valor nos dados compartilhados.
        
        Args:
            key: Chave do dado
            value: Valor a ser armazenado
        """
        self.shared_data[key] = value

    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """
        Recupera um valor dos dados compartilhados.
        
        Args:
            key: Chave do dado
            default: Valor padrão se a chave não existir
            
        Returns:
            Any: Valor armazenado ou valor padrão
        """
        return self.shared_data.get(key, default)

    def update_routing_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Atualiza os metadados de roteamento.
        
        Args:
            metadata: Novos metadados
        """
        self.routing_metadata.update(metadata)

    def get_routing_metadata(self, key: str, default: Any = None) -> Any:
        """
        Recupera um valor dos metadados de roteamento.
        
        Args:
            key: Chave do metadado
            default: Valor padrão se a chave não existir
            
        Returns:
            Any: Valor armazenado ou valor padrão
        """
        return self.routing_metadata.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """
        Converte o contexto para dicionário.
        
        Returns:
            Dict[str, Any]: Contexto em formato de dicionário
        """
        return {
            "user": self.user.model_dump(),
            "session": self.session.model_dump(),
            "current_message": self.current_message.model_dump(),
            "message_history": [msg.model_dump() for msg in self.message_history],
            "shared_data": self.shared_data,
            "session_config": self.session_config,
            "routing_metadata": self.routing_metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentContext":
        """
        Cria um contexto a partir de um dicionário.
        
        Args:
            data: Dados do contexto
            
        Returns:
            AgentContext: Contexto criado
        """
        # Converter mensagens do histórico
        message_history = []
        for msg_data in data.get("message_history", []):
            message_history.append(MessageContext(**msg_data))
        
        return cls(
            user=UserContext(**data["user"]),
            session=SessionContext(**data["session"]),
            current_message=MessageContext(**data["current_message"]),
            message_history=message_history,
            shared_data=data.get("shared_data", {}),
            session_config=data.get("session_config", {}),
            routing_metadata=data.get("routing_metadata", {}),
        )

    def __str__(self) -> str:
        """Representação string do contexto."""
        return f"AgentContext(user_id={self.user.user_id}, session_id={self.session.session_id})"
