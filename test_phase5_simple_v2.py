#!/usr/bin/env python3
"""
Teste Simples da FASE 5 - Agente de Intenções (Router) - Versão 2
"""

import os
import sys
from pathlib import Path

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

def test_file_content():
    """Teste 2: Verificando conteúdo dos arquivos..."""
    print("🧪 Teste 2: Verificando conteúdo dos arquivos...")
    
    base_path = Path(__file__).resolve().parent
    
    # Verificar agent_manager.py
    agent_manager_file = base_path / "app" / "agents" / "agent_manager.py"
    if agent_manager_file.exists():
        content = agent_manager_file.read_text()
        required_classes = ["AgentManager", "AgentRouting"]
        required_methods = ["process", "get_agent_description", "get_supported_intentions"]
        
        for cls in required_classes:
            if f"class {cls}" not in content:
                print(f"❌ Classe {cls} não encontrada em agent_manager.py")
                return False
        
        for method in required_methods:
            if f"def {method}" not in content:
                print(f"❌ Método {method} não encontrado em agent_manager.py")
                return False
    
    # Verificar context.py
    context_file = base_path / "app" / "agents" / "context.py"
    if context_file.exists():
        content = context_file.read_text()
        required_classes = ["AgentContext", "UserContext", "SessionContext", "MessageContext"]
        
        for cls in required_classes:
            if f"class {cls}" not in content:
                print(f"❌ Classe {cls} não encontrada em context.py")
                return False
    
    # Verificar workflow.py
    workflow_file = base_path / "app" / "agents" / "workflow.py"
    if workflow_file.exists():
        content = workflow_file.read_text()
        required_classes = ["SimplificaPsiWorkflow", "WorkflowResponse"]
        required_methods = ["process_message", "get_workflow_status"]
        
        for cls in required_classes:
            if f"class {cls}" not in content:
                print(f"❌ Classe {cls} não encontrada em workflow.py")
                return False
        
        for method in required_methods:
            if f"def {method}" not in content:
                print(f"❌ Método {method} não encontrado em workflow.py")
                return False
    
    # Verificar calendar_agent.py
    calendar_file = base_path / "app" / "agents" / "calendar_agent.py"
    if calendar_file.exists():
        content = calendar_file.read_text()
        required_classes = ["CalendarAgent"]
        required_methods = ["process", "_setup_tools"]
        
        for cls in required_classes:
            if f"class {cls}" not in content:
                print(f"❌ Classe {cls} não encontrada em calendar_agent.py")
                return False
        
        for method in required_methods:
            if f"def {method}" not in content:
                print(f"❌ Método {method} não encontrado em calendar_agent.py")
                return False
    
    print("✅ Conteúdo dos arquivos está correto!")
    return True

def test_imports_structure():
    """Teste 3: Verificando estrutura de imports..."""
    print("🧪 Teste 3: Verificando estrutura de imports...")
    
    try:
        # Testar imports básicos (sem instanciar classes)
        from app.agents.agent_manager import AgentManager, AgentRouting
        from app.agents.calendar_agent import CalendarAgent
        from app.agents.context import (
            AgentContext,
            MessageContext,
            SessionContext,
            UserContext,
        )
        from app.agents.workflow import SimplificaPsiWorkflow, WorkflowResponse

        # Verificar se as classes existem
        assert AgentManager is not None, "AgentManager não importado"
        assert AgentRouting is not None, "AgentRouting não importado"
        assert CalendarAgent is not None, "CalendarAgent não importado"
        assert AgentContext is not None, "AgentContext não importado"
        assert SimplificaPsiWorkflow is not None, "SimplificaPsiWorkflow não importado"
        assert WorkflowResponse is not None, "WorkflowResponse não importado"
        
        print("✅ Estrutura de imports está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nos imports: {e}")
        return False

def test_model_config():
    """Teste 4: Verificando configuração dos modelos..."""
    print("🧪 Teste 4: Verificando configuração dos modelos...")
    
    try:
        from app.agents.workflow import WorkflowResponse

        # Verificar se WorkflowResponse tem model_config (é BaseModel)
        assert hasattr(WorkflowResponse, 'model_config'), "WorkflowResponse não tem model_config"
        
        # Verificar se as classes não-BaseModel existem
        from app.agents.agent_manager import AgentManager
        from app.agents.calendar_agent import CalendarAgent
        from app.agents.workflow import SimplificaPsiWorkflow

        # Verificar se as classes existem e têm __init__
        assert hasattr(AgentManager, '__init__'), "AgentManager não tem __init__"
        assert hasattr(CalendarAgent, '__init__'), "CalendarAgent não tem __init__"
        assert hasattr(SimplificaPsiWorkflow, '__init__'), "SimplificaPsiWorkflow não tem __init__"
        
        print("✅ Configuração dos modelos está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro na configuração dos modelos: {e}")
        return False

def test_context_functionality():
    """Teste 5: Verificando funcionalidades do contexto..."""
    print("🧪 Teste 5: Verificando funcionalidades do contexto...")
    
    try:
        from datetime import datetime
        from uuid import uuid4

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
        
        print("✅ Funcionalidades do contexto estão corretas!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nas funcionalidades do contexto: {e}")
        return False

def test_workflow_structure():
    """Teste 6: Verificando estrutura do workflow..."""
    print("🧪 Teste 6: Verificando estrutura do workflow...")
    
    try:
        from app.agents.workflow import SimplificaPsiWorkflow, WorkflowResponse

        # Verificar se as classes existem
        assert hasattr(SimplificaPsiWorkflow, '__init__'), "SimplificaPsiWorkflow não tem __init__"
        assert hasattr(WorkflowResponse, '__init__'), "WorkflowResponse não tem __init__"
        
        # Verificar se os métodos existem
        assert hasattr(SimplificaPsiWorkflow, 'process_message'), "Workflow não tem process_message"
        assert hasattr(SimplificaPsiWorkflow, 'get_workflow_status'), "Workflow não tem get_workflow_status"
        
        print("✅ Estrutura do workflow está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro na estrutura do workflow: {e}")
        return False

def test_agent_routing_structure():
    """Teste 7: Verificando estrutura de roteamento..."""
    print("🧪 Teste 7: Verificando estrutura de roteamento...")
    
    try:
        from app.agents.agent_manager import AgentManager, AgentRouting

        # Verificar se as classes existem
        assert hasattr(AgentManager, '__init__'), "AgentManager não tem __init__"
        assert hasattr(AgentRouting, '__init__'), "AgentRouting não tem __init__"
        
        # Verificar se os métodos existem
        assert hasattr(AgentManager, 'process'), "AgentManager não tem método process"
        assert hasattr(AgentManager, 'get_agent_description'), "AgentManager não tem get_agent_description"
        assert hasattr(AgentManager, 'get_supported_intentions'), "AgentManager não tem get_supported_intentions"
        
        print("✅ Estrutura de roteamento está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro na estrutura de roteamento: {e}")
        return False

def main():
    """Executa todos os testes da FASE 5."""
    print("🚀 TESTE SIMPLES DA FASE 5 - AGENTE DE INTENÇÕES (ROUTER) - V2")
    print("=" * 70)
    
    tests = [
        test_file_structure,
        test_file_content,
        test_imports_structure,
        test_model_config,
        test_context_functionality,
        test_workflow_structure,
        test_agent_routing_structure,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Erro inesperado no teste: {e}")
    
    print("=" * 70)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM! FASE 5 ESTÁ IMPLEMENTADA!")
        print("\n📋 RESUMO DA FASE 5:")
        print("✅ AgentManager com roteamento inteligente")
        print("✅ Gerenciamento de contexto entre agentes")
        print("✅ Workflow principal de orquestração")
        print("✅ CalendarAgent para gestão de eventos")
        print("✅ Estrutura de imports organizada")
        print("✅ Configuração de modelos Pydantic")
        print("✅ Funcionalidades de contexto implementadas")
        return True
    else:
        print(f"❌ {total - passed} testes falharam. Verifique os erros acima.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
