#!/usr/bin/env python3
"""
Script para criar um usuário de teste no banco de dados
"""

import sys
from pathlib import Path
from uuid import uuid4

# Adicionar o diretório raiz do projeto ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

def create_test_user():
    """Cria um usuário de teste no banco de dados."""
    print("🔧 CRIANDO USUÁRIO DE TESTE...")
    
    try:
        with get_db_context() as db:
            # Verificar se já existe um usuário de teste
            existing_user = db.query(User).filter(User.email == "teste@simplificapsi.com").first()
            
            if existing_user:
                print(f"✅ Usuário de teste já existe: {existing_user.id}")
                return existing_user.id
            
            # Criar novo usuário de teste
            test_user = User(
                id=uuid4(),
                name="Dr. Teste",
                email="teste@simplificapsi.com",
                phone="11999999999",
                is_active=True
            )
            
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
            
            print(f"✅ Usuário de teste criado com sucesso!")
            print(f"   ID: {test_user.id}")
            print(f"   Nome: {test_user.name}")
            print(f"   Email: {test_user.email}")
            
            return test_user.id
            
    except Exception as e:
        print(f"❌ Erro ao criar usuário de teste: {e}")
        return None

if __name__ == "__main__":
    user_id = create_test_user()
    if user_id:
        print(f"\n🎯 Use este user_id nos testes: {user_id}")
        sys.exit(0)
    else:
        sys.exit(1)
