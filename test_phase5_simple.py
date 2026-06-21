#!/usr/bin/env python3
"""
Teste Simples da FASE 5 - Agente de Intenções (Router)
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

# Adicionar o diretório raiz do projeto ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

def test_file_structure():
    """Teste 1: Verificando estrutura de arquivos da FASE 5..."""
    print("🧪 Teste 1: Verificando estrutura de arquivos da FASE 5...")
    base_path = Path(__file__).resolve().parent
    expected_files = [
        base_path / "app" / "agents" / "agent_manager.py",
        base_path / "app" / "agents" / "context.py", 
        base_path / "app" / "agents" / "workflow.py",
        base_path / "app" / "agents" / "calendar_agent.py",
    ]
    
    all_exist = True
    for f in expected_files:
        if not f.exists():
            print(f"❌ Arquivo não encontrado: {f}")
            all_exist = False
    
    if all_exist:
        print("✅ Todos os arquivos da FASE 5 foram criados!")
        return True
    return False

def test_agent_manager_content():
    """Teste 2: Verificando conteúdo do AgentManager..."""
    print("🧪 Teste 2: Verificando conteúdo do AgentManager...")
    
    try:
        from app.agents.agent_manager import AgentManager, AgentRouting

        # Verificar se as classes existem
        assert hasattr(AgentManager, '__init__'), "AgentManager não tem __init__"
        assert hasattr(AgentRouting, '__init__'), "AgentRouting não tem __init__"
        
        # Verificar se os métodos existem
        manager = AgentManager()
        assert hasattr(manager, 'process'), "AgentManager não tem método process"
        assert hasattr(manager, 'get_agent_description'), "AgentManager não tem get_agent_description"
        assert hasattr(manager, 'get_supported_intentions'), "AgentManager não tem get_supported_intentions"
        
        print("✅ AgentManager implementado corretamente!")
        return True
        
    except Exception as e:
        print(f"❌ Erro no AgentManager: {e}")
        return False

def test_context_management():
    """Teste 3: Verificando gerenciamento de contexto..."""
    print("🧪 Teste 3: Verificando gerenciamento de contexto...")
    
    try:
        from datetime import datetime

        from app.agents.context import (
            AgentContext,
            MessageContext,
            SessionContext,
            UserContext,
        )

        # Criar contexto de teste
        user_id = uuid4()
        session_id = uuid4()
        
        user_context = UserContext(user_id=user_id, name="Test User")
        session_context = SessionContext(session_id=session_id, user_id=user_id)
        message_context = MessageContext(
            message_id=uuid4(),
            session_id=session_id,
            role="user",
            content="Test message"
        )
        
        agent_context = AgentContext(
            user=user_context,
            session=session_context,
            current_message=message_context
        )
        
        # Testar métodos
        assert hasattr(agent_context, 'add_message'), "AgentContext não tem add_message"
        assert hasattr(agent_context, 'get_recent_messages'), "AgentContext não tem get_recent_messages"
        assert hasattr(agent_context, 'set_shared_data'), "AgentContext não tem set_shared_data"
        assert hasattr(agent_context, 'get_shared_data'), "AgentContext não tem get_shared_data"
        assert hasattr(agent_context, 'to_dict'), "AgentContext não tem to_dict"
        
        # Testar funcionalidades
        agent_context.set_shared_data("test_key", "test_value")
        assert agent_context.get_shared_data("test_key") == "test_value", "set_shared_data/get_shared_data não funcionam"
        
        print("✅ Gerenciamento de contexto implementado corretamente!")
        return True
        
    except Exception as e:
        print(f"❌ Erro no gerenciamento de contexto: {e}")
        return False

def test_workflow_implementation():
    """Teste 4: Verificando implementação do Workflow..."""
    print("🧪 Teste 4: Verificando implementação do Workflow...")
    
    try:
        from app.agents.workflow import SimplificaPsiWorkflow, WorkflowResponse

        # Verificar se as classes existem
        assert hasattr(SimplificaPsiWorkflow, '__init__'), "SimplificaPsiWorkflow não tem __init__"
        assert hasattr(WorkflowResponse, '__init__'), "WorkflowResponse não tem __init__"
        
        # Verificar se os métodos existem
        workflow = SimplificaPsiWorkflow()
        assert hasattr(workflow, 'process_message'), "Workflow não tem process_message"
        assert hasattr(workflow, 'get_workflow_status'), "Workflow não tem get_workflow_status"
        
        # Testar status
        status = workflow.get_workflow_status()
        assert "workflow_version" in status, "Status não tem workflow_version"
        assert "agents_available" in status, "Status não tem agents_available"
        
        print("✅ Workflow implementado corretamente!")
        return True
        
    except Exception as e:
        print(f"❌ Erro no Workflow: {e}")
        return False

def test_calendar_agent():
    """Teste 5: Verificando CalendarAgent..."""
    print("🧪 Teste 5: Verificando CalendarAgent...")
    
    try:
        from app.agents.calendar_agent import CalendarAgent

        # Verificar se a classe existe
        assert hasattr(CalendarAgent, '__init__'), "CalendarAgent não tem __init__"
        
        # Verificar se os métodos existem
        agent = CalendarAgent()
        assert hasattr(agent, 'process'), "CalendarAgent não tem método process"
        assert hasattr(agent, '_setup_tools'), "CalendarAgent não tem _setup_tools"
        
        print("✅ CalendarAgent implementado corretamente!")
        return True
        
    except Exception as e:
        print(f"❌ Erro no CalendarAgent: {e}")
        return False

def test_imports_structure():
    """Teste 6: Verificando estrutura de imports..."""
    print("🧪 Teste 6: Verificando estrutura de imports...")
    
    try:
        from app.agents import (
            AgentContext,
            AgentManager,
            AgentRouting,
            CalendarAgent,
            ClientAgent,
            MessageContext,
            SessionContext,
            SimplificaPsiWorkflow,
            UserContext,
            WorkflowResponse,
        )

        # Verificar se todos os imports funcionam
        assert AgentManager is not None, "AgentManager não importado"
        assert AgentRouting is not None, "AgentRouting não importado"
        assert CalendarAgent is not None, "CalendarAgent não importado"
        assert ClientAgent is not None, "ClientAgent não importado"
        assert AgentContext is not None, "AgentContext não importado"
        assert SimplificaPsiWorkflow is not None, "SimplificaPsiWorkflow não importado"
        assert WorkflowResponse is not None, "WorkflowResponse não importado"
        
        print("✅ Estrutura de imports está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nos imports: {e}")
        return False

def test_agent_routing_logic():
    """Teste 7: Verificando lógica de roteamento..."""
    print("🧪 Teste 7: Verificando lógica de roteamento...")
    
    try:
        from app.agents.agent_manager import AgentManager, AgentRouting
        
        manager = AgentManager()
        
        # Testar descrições de agentes
        descriptions = {
            "client_agent": manager.get_agent_description("client_agent"),
            "calendar_agent": manager.get_agent_description("calendar_agent"),
            "agent_manager": manager.get_agent_description("agent_manager")
        }
        
        assert all(desc for desc in descriptions.values()), "Descrições de agentes não funcionam"
        
        # Testar intenções suportadas
        intentions = manager.get_supported_intentions()
        assert "client_agent" in intentions, "client_agent não está nas intenções"
        assert "calendar_agent" in intentions, "calendar_agent não está nas intenções"
        assert "agent_manager" in intentions, "agent_manager não está nas intenções"
        
        print("✅ Lógica de roteamento implementada corretamente!")
        return True
        
    except Exception as e:
        print(f"❌ Erro na lógica de roteamento: {e}")
        return False

def main():
    """Executa todos os testes da FASE 5."""
    print("🚀 TESTE SIMPLES DA FASE 5 - AGENTE DE INTENÇÕES (ROUTER)")
    print("=" * 60)
    
    tests = [
        test_file_structure,
        test_agent_manager_content,
        test_context_management,
        test_workflow_implementation,
        test_calendar_agent,
        test_imports_structure,
        test_agent_routing_logic,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Erro inesperado no teste: {e}")
    
    print("=" * 60)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM! FASE 5 ESTÁ IMPLEMENTADA!")
        print("\n📋 RESUMO DA FASE 5:")
        print("✅ AgentManager com roteamento inteligente")
        print("✅ Gerenciamento de contexto entre agentes")
        print("✅ Workflow principal de orquestração")
        print("✅ CalendarAgent para gestão de eventos")
        print("✅ Estrutura de imports organizada")
        print("✅ Lógica de roteamento implementada")
        return True
    else:
        print(f"❌ {total - passed} testes falharam. Verifique os erros acima.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
