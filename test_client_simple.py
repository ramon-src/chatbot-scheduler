#!/usr/bin/env python3
"""
Teste simples do ClientAgent sem rate limit
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Adicionar o diretório raiz do projeto ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agents.client_agent import ClientAgent
from app.agents.context import AgentContext, MessageContext, SessionContext, UserContext
from app.core.config import settings
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.services.client_service import ClientService

logger = get_logger(__name__)

async def test_client_agent_simple():
    """Teste simples do ClientAgent."""
    print("🚀 TESTE SIMPLES DO CLIENTAGENT")
    print("=" * 50)
    
    # Verificar se a chave da OpenAI está configurada
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key_here":
        print("❌ OPENAI_API_KEY não encontrada!")
        return False

    try:
        # 1. Configurar contexto
        user_id = "18b047b1-4872-4f79-804e-2ce5253cc8ed"  # Usuário de teste real
        session_id = uuid4()
        
        user_context = UserContext(
            user_id=user_id,
            name="Dr. Ramon",
            email="ramon@simplificapsi.com",
            phone_number="+5511987654321"
        )
        
        session_context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            whatsapp_id="whatsapp_chat_id_123",
            client_phone_number="+5511999998888"
        )
        
        message_context = MessageContext(
            message_id=uuid4(),
            session_id=session_id,
            role="user",
            content="Cadastrar cliente João Silva, telefone 11999999999"
        )
        
        agent_context = AgentContext(
            user=user_context,
            session=session_context,
            current_message=message_context,
            message_history=[]
        )
        
        # 2. Instanciar ClientAgent
        client_agent = ClientAgent()
        
        # 3. Injetar ClientService
        with get_db_context() as db:
            client_service = ClientService(db)
            client_agent.client_service = client_service
            
            # 4. Testar processamento
            print(f"💬 Mensagem: {message_context.content}")
            response = await client_agent.process(message_context.content, agent_context)
            
            print("\n--- RESPOSTA DO AGENTE ---")
            print(f"Agente: {response.get('agent')}")
            print(f"Resposta: {response.get('response')}")
            print(f"Uso de tokens: {response.get('usage')}")
            print(f"Metadados: {response.get('metadata')}")
            
            if "sucesso" in response.get("response", "").lower() or "criado" in response.get("response", "").lower():
                print("✅ Teste do ClientAgent bem-sucedido!")
                return True
            else:
                print("❌ Teste do ClientAgent falhou: Resposta inesperada.")
                return False
                
    except Exception as e:
        print(f"❌ Erro ao executar o teste: {e}")
        return False

async def main():
    """Função principal."""
    success = await test_client_agent_simple()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
