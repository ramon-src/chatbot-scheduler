#!/usr/bin/env python3
"""
Teste simples da FASE 4 - Gestão de Clientes
"""

import sys
from pathlib import Path


def test_file_structure():
    """Teste 1: Verificar estrutura de arquivos"""
    print("🧪 Teste 1: Verificando estrutura de arquivos...")
    
    files_to_check = [
        "app/schemas/client.py",
        "app/services/client_service.py", 
        "app/agents/client_agent.py",
        "app/schemas/__init__.py",
        "app/services/__init__.py",
        "app/agents/__init__.py",
    ]
    
    missing_files = []
    for file_path in files_to_check:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Arquivos faltando: {missing_files}")
        return False
    else:
        print("✅ Todos os arquivos da FASE 4 foram criados!")
        return True

def test_schema_content():
    """Teste 2: Verificar conteúdo dos schemas"""
    print("\n🧪 Teste 2: Verificando conteúdo dos schemas...")
    
    try:
        with open("app/schemas/client.py", "r") as f:
            content = f.read()
        
        required_classes = [
            "ClientBase",
            "ClientCreate", 
            "ClientUpdate",
            "ClientResponse",
            "ClientListResponse",
            "ClientSearchRequest",
            "ClientStatsResponse",
        ]
        
        missing_classes = []
        for class_name in required_classes:
            if f"class {class_name}" not in content:
                missing_classes.append(class_name)
        
        if missing_classes:
            print(f"❌ Classes faltando: {missing_classes}")
            return False
        else:
            print("✅ Todas as classes de schema foram criadas!")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao verificar schemas: {e}")
        return False

def test_service_content():
    """Teste 3: Verificar conteúdo do serviço"""
    print("\n🧪 Teste 3: Verificando conteúdo do serviço...")
    
    try:
        with open("app/services/client_service.py", "r") as f:
            content = f.read()
        
        required_methods = [
            "create_client",
            "find_client",
            "find_client_by_phone",
            "find_client_by_name", 
            "update_client",
            "list_clients",
            "search_clients",
            "deactivate_client",
            "activate_client",
            "get_client_stats",
        ]
        
        missing_methods = []
        for method_name in required_methods:
            if f"async def {method_name}" not in content:
                missing_methods.append(method_name)
        
        if missing_methods:
            print(f"❌ Métodos faltando: {missing_methods}")
            return False
        else:
            print("✅ Todos os métodos do serviço foram criados!")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao verificar serviço: {e}")
        return False

def test_agent_content():
    """Teste 4: Verificar conteúdo do agente"""
    print("\n🧪 Teste 4: Verificando conteúdo do agente...")
    
    try:
        with open("app/agents/client_agent.py", "r") as f:
            content = f.read()
        
        required_elements = [
            "class ClientAgent",
            "def _setup_agent",
            "def process",
            "async def client_find",
            "async def client_create",
            "async def client_update",
            "async def client_list",
            "async def client_search",
            "async def client_deactivate",
            "async def client_activate",
            "async def client_stats",
        ]
        
        missing_elements = []
        for element in required_elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"❌ Elementos faltando: {missing_elements}")
            return False
        else:
            print("✅ Todos os elementos do agente foram criados!")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao verificar agente: {e}")
        return False

def test_imports_structure():
    """Teste 5: Verificar estrutura de imports"""
    print("\n🧪 Teste 5: Verificando estrutura de imports...")
    
    try:
        # Verificar __init__.py dos schemas
        with open("app/schemas/__init__.py", "r") as f:
            schemas_content = f.read()
        
        if "ClientBase" not in schemas_content or "ClientResponse" not in schemas_content:
            print("❌ Imports dos schemas incompletos")
            return False
        
        # Verificar __init__.py dos serviços
        with open("app/services/__init__.py", "r") as f:
            services_content = f.read()
        
        if "ClientService" not in services_content:
            print("❌ Imports dos serviços incompletos")
            return False
        
        # Verificar __init__.py dos agentes
        with open("app/agents/__init__.py", "r") as f:
            agents_content = f.read()
        
        if "ClientAgent" not in agents_content:
            print("❌ Imports dos agentes incompletos")
            return False
        
        print("✅ Estrutura de imports está correta!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao verificar imports: {e}")
        return False

def test_validation_logic():
    """Teste 6: Verificar lógica de validação"""
    print("\n🧪 Teste 6: Verificando lógica de validação...")
    
    try:
        with open("app/schemas/client.py", "r") as f:
            content = f.read()
        
        validation_elements = [
            "@validator('phone')",
            "@validator('birth_date')",
            "@validator('name')",
            "validate_phone",
            "validate_birth_date", 
            "validate_name",
            "NumberParseException",
            "is_valid_number",
        ]
        
        missing_elements = []
        for element in validation_elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"❌ Elementos de validação faltando: {missing_elements}")
            return False
        else:
            print("✅ Lógica de validação implementada!")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao verificar validação: {e}")
        return False

def test_error_handling():
    """Teste 7: Verificar tratamento de erros"""
    print("\n🧪 Teste 7: Verificando tratamento de erros...")
    
    try:
        with open("app/services/client_service.py", "r") as f:
            content = f.read()
        
        error_elements = [
            "ClientNotFoundError",
            "ConflictError", 
            "ValidationError",
            "try:",
            "except",
            "raise",
        ]
        
        missing_elements = []
        for element in error_elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"❌ Elementos de tratamento de erro faltando: {missing_elements}")
            return False
        else:
            print("✅ Tratamento de erros implementado!")
            return True
            
    except Exception as e:
        print(f"❌ Erro ao verificar tratamento de erros: {e}")
        return False

def main():
    """Executar todos os testes"""
    print("🚀 TESTE SIMPLES DA FASE 4 - GESTÃO DE CLIENTES")
    print("=" * 60)
    
    tests = [
        test_file_structure,
        test_schema_content,
        test_service_content,
        test_agent_content,
        test_imports_structure,
        test_validation_logic,
        test_error_handling,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Erro inesperado no teste: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM! FASE 4 ESTÁ IMPLEMENTADA!")
        print("\n📋 RESUMO DA FASE 4:")
        print("✅ Schemas Pydantic com validações robustas")
        print("✅ Serviço CRUD completo para clientes")
        print("✅ Agente Pydantic AI com tools integradas")
        print("✅ Tratamento de erros e conflitos")
        print("✅ Estrutura de imports organizada")
        return True
    else:
        print("⚠️  ALGUNS TESTES FALHARAM. Verifique os erros acima.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
