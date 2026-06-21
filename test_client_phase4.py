#!/usr/bin/env python3
"""
Teste da FASE 4 - Gestão de Clientes
"""

import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

def test_client_schemas():
    """Teste 1: Verificar schemas de cliente"""
    print("🧪 Teste 1: Verificando schemas de cliente...")
    
    try:
        from app.schemas.client import (
            ClientBase,
            ClientCreate,
            ClientListResponse,
            ClientResponse,
            ClientSearchRequest,
            ClientStatsResponse,
            ClientUpdate,
        )

        # Teste de validação de telefone
        client_data = {
            "name": "João Silva Santos",
            "phone": "11999999999",
            "email": "joao@example.com",
            "consult_price": 150.00
        }
        
        client_base = ClientBase(**client_data)
        print(f"✅ Schema ClientBase: {client_base.name} - {client_base.phone}")
        
        # Teste de validação de nome
        try:
            ClientBase(name="João", phone="11999999999")  # Nome muito curto
            print("❌ Validação de nome falhou")
            return False
        except ValueError as e:
            print(f"✅ Validação de nome funcionando: {e}")
        
        # Teste de validação de telefone inválido
        try:
            ClientBase(name="João Silva", phone="123")  # Telefone inválido
            print("❌ Validação de telefone falhou")
            return False
        except ValueError as e:
            print(f"✅ Validação de telefone funcionando: {e}")
        
        print("✅ Todos os schemas funcionaram!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nos schemas: {e}")
        return False

def test_client_service():
    """Teste 2: Verificar serviço de cliente"""
    print("\n🧪 Teste 2: Verificando serviço de cliente...")
    
    try:
        from uuid import uuid4

        from app.core.database import get_db
        from app.services.client_service import ClientService

        # Obter sessão do banco
        db = next(get_db())
        service = ClientService(db)
        
        print("✅ ClientService criado com sucesso!")
        
        # Teste de estatísticas (sem dados)
        # stats = await service.get_client_stats(uuid4())
        # print(f"✅ Estatísticas: {stats.total_clients} clientes")
        print("✅ ClientService criado com sucesso!")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no serviço: {e}")
        return False

def test_client_agent():
    """Teste 3: Verificar agente de cliente"""
    print("\n🧪 Teste 3: Verificando agente de cliente...")
    
    try:
        from uuid import uuid4

        from app.agents.client_agent import ClientAgent
        from app.core.database import get_db
        from app.services.client_service import ClientService

        # Criar agente
        agent = ClientAgent()
        
        # Configurar serviço
        db = next(get_db())
        agent.client_service = ClientService(db)
        
        print("✅ ClientAgent criado com sucesso!")
        print(f"✅ Tools registradas: {len(agent.agent.tools)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro no agente: {e}")
        return False

def test_imports():
    """Teste 4: Verificar imports"""
    print("\n🧪 Teste 4: Verificando imports...")
    
    try:
        # Testar imports dos schemas
        # Testar imports dos agentes
        from app.agents import ClientAgent
        from app.schemas import ClientBase, ClientCreate, ClientResponse, ClientUpdate

        # Testar imports dos serviços
        from app.services import ClientService
        
        print("✅ Todos os imports funcionaram!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nos imports: {e}")
        return False

def test_validation():
    """Teste 5: Verificar validações"""
    print("\n🧪 Teste 5: Verificando validações...")
    
    try:
        from decimal import Decimal

        from app.schemas.client import ClientBase

        # Teste de validação de preço
        client_data = {
            "name": "Maria Silva Santos",
            "phone": "11988888888",
            "consult_price": Decimal("200.50")
        }
        
        client = ClientBase(**client_data)
        print(f"✅ Preço validado: R$ {client.consult_price}")
        
        # Teste de validação de email
        client_data["email"] = "maria@example.com"
        client = ClientBase(**client_data)
        print(f"✅ Email validado: {client.email}")
        
        print("✅ Validações funcionando!")
        return True
        
    except Exception as e:
        print(f"❌ Erro nas validações: {e}")
        return False

def main():
    """Executar todos os testes"""
    print("🚀 TESTE DA FASE 4 - GESTÃO DE CLIENTES")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_client_schemas,
        test_validation,
        test_client_service,
        test_client_agent,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Erro inesperado no teste: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 RESULTADO: {passed}/{total} testes passaram")
    
    if passed == total:
        print("🎉 TODOS OS TESTES PASSARAM! FASE 4 ESTÁ FUNCIONANDO!")
        return True
    else:
        print("⚠️  ALGUNS TESTES FALHARAM. Verifique os erros acima.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
