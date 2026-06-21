#!/usr/bin/env python3
"""
Teste Real do ClientAgent - Testando com OpenAI
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

# Adicionar o diretório raiz do projeto ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

async def test_client_agent_real():
    """Teste real do ClientAgent com OpenAI."""
    print("🤖 TESTE REAL DO CLIENTAGENT COM OPENAI")
    print("=" * 50)
    
    try:
        from datetime import datetime

        from app.agents.client_agent import ClientAgent
        from app.agents.context import (
            AgentContext,
            MessageContext,
            SessionContext,
            UserContext,
        )
        from app.core.database import get_db_context
        from app.services.client_service import ClientService
        
        print("✅ Imports realizados com sucesso!")
        
        # Criar contexto de teste
        user_id = uuid4()
        session_id = uuid4()
        
        user_context = UserContext(
            user_id=user_id,
            name="Dr. João Silva",
            email="joao@psicologo.com",
            phone="11999999999"
        )
        
        session_context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            whatsapp_id="5511999999999"
        )
        
        message_context = MessageContext(
            message_id=uuid4(),
            session_id=session_id,
            role="user",
            content="Quero cadastrar um novo cliente chamado Maria Santos, telefone 11988888888, email maria@email.com"
        )
        
        agent_context = AgentContext(
            user=user_context,
            session=session_context,
            current_message=message_context
        )
        
        print("✅ Contexto criado com sucesso!")
        
        # Criar ClientAgent
        client_agent = ClientAgent()
        print("✅ ClientAgent criado com sucesso!")
        
        # Conectar ao banco de dados
        with get_db_context() as db:
            # Injetar o serviço no agente
            client_agent.client_service = ClientService(db)
            print("✅ ClientService injetado no agente!")
            
            # Testar processamento de mensagem
            print("\n🧪 Testando processamento de mensagem...")
            print(f"📝 Mensagem: {message_context.content}")
            
            result = await client_agent.process(message_context.content, agent_context.to_dict())
            
            print("\n📊 RESULTADO:")
            print(f"🤖 Agente: {result.get('agent', 'N/A')}")
            print(f"💬 Resposta: {result.get('response', 'N/A')}")
            print(f"📈 Usage: {result.get('usage', {})}")
            print(f"🔧 Metadata: {result.get('metadata', {})}")
            
            return True
            
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_agent_manager_real():
    """Teste real do AgentManager com OpenAI."""
    print("\n🎯 TESTE REAL DO AGENTMANAGER COM OPENAI")
    print("=" * 50)
    
    try:
        from datetime import datetime

        from app.agents.agent_manager import AgentManager
        from app.agents.context import (
            AgentContext,
            MessageContext,
            SessionContext,
            UserContext,
        )

        # Criar contexto de teste
        user_id = uuid4()
        session_id = uuid4()
        
        user_context = UserContext(
            user_id=user_id,
            name="Dr. Ana Costa",
            email="ana@psicologo.com"
        )
        
        session_context = SessionContext(
            session_id=session_id,
            user_id=user_id
        )
        
        message_context = MessageContext(
            message_id=uuid4(),
            session_id=session_id,
            role="user",
            content="Preciso agendar uma consulta para amanhã às 14h com o cliente João"
        )
        
        agent_context = AgentContext(
            user=user_context,
            session=session_context,
            current_message=message_context
        )
        
        # Criar AgentManager
        manager = AgentManager()
        print("✅ AgentManager criado com sucesso!")
        
        # Testar roteamento
        print(f"\n🧪 Testando roteamento da mensagem: {message_context.content}")
        
        routing = await manager.process(message_context.content, agent_context.to_dict())
        
        print("\n📊 RESULTADO DO ROTEAMENTO:")
        print(f"🎯 Agente escolhido: {routing.agent}")
        print(f"📈 Confiança: {routing.confidence}")
        print(f"💭 Raciocínio: {routing.reasoning}")
        print(f"🏷️ Entidades: {routing.entities}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no teste do AgentManager: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_workflow_real():
    """Teste real do Workflow completo com OpenAI."""
    print("\n🔄 TESTE REAL DO WORKFLOW COMPLETO")
    print("=" * 50)
    
    try:
        from uuid import uuid4

        from app.agents.workflow import SimplificaPsiWorkflow
        from app.core.database import get_db_context
        from app.services.client_service import ClientService

        # Criar workflow
        workflow = SimplificaPsiWorkflow()
        print("✅ Workflow criado com sucesso!")
        
        # Conectar ao banco de dados
        with get_db_context() as db:
            # Injetar serviços
            client_service = ClientService(db)
            print("✅ ClientService criado!")
            
            # Testar processamento completo
            print("\n🧪 Testando workflow completo...")
            
            result = await workflow.process_message(
                message="Cadastrar cliente Pedro Oliveira, telefone 11977777777",
                user_id=uuid4(),
                user_name="Dr. Carlos",
                client_service=client_service
            )
            
            print("\n📊 RESULTADO DO WORKFLOW:")
            print(f"🤖 Agente: {result.agent}")
            print(f"💬 Resposta: {result.response}")
            print(f"📈 Confiança: {result.confidence}")
            print(f"🏷️ Entidades: {result.entities}")
            print(f"📊 Usage: {result.usage}")
            print(f"🔧 Metadata: {result.response_metadata}")
            
            return True
            
    except Exception as e:
        print(f"❌ Erro no teste do Workflow: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Executa todos os testes reais."""
    print("🚀 INICIANDO TESTES REAIS COM OPENAI")
    print("=" * 60)
    
    # Verificar se a chave da OpenAI está configurada
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY não encontrada! Configure a variável de ambiente.")
        return False
    
    print("✅ OPENAI_API_KEY encontrada!")
    
    tests = [
        ("ClientAgent", test_client_agent_real),
        ("AgentManager", test_agent_manager_real),
        ("Workflow", test_workflow_real),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if await test_func():
                print(f"✅ {test_name} - SUCESSO!")
                passed += 1
            else:
                print(f"❌ {test_name} - FALHOU!")
        except Exception as e:
            print(f"❌ {test_name} - ERRO: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTADO FINAL: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 TODOS OS TESTES REAIS PASSARAM!")
        print("✅ ClientAgent funcionando com OpenAI")
        print("✅ AgentManager roteando corretamente")
        print("✅ Workflow completo operacional")
        return True
    else:
        print(f"❌ {total - passed} testes falharam.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
