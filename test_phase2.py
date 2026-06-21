#!/usr/bin/env python3
"""
Teste da FASE 2 - Banco de Dados e Configurações Centrais
"""

import asyncio
import os
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).parent))

def test_imports():
    """Teste 1: Verificar se todos os imports funcionam"""
    print("🧪 Teste 1: Verificando imports...")
    
    try:
        from app.core.config import settings
        from app.core.database import check_connection, get_db
        from app.core.exceptions import SimplificaPsiException
        from app.core.logging import get_logger, setup_logging
        from app.core.redis import cache_manager, check_redis_health, session_manager
        from app.models import Calendar, ChatMessage, ChatSession, Client, Event, User
        print("✅ Todos os imports funcionaram!")
        return True
    except Exception as e:
        print(f"❌ Erro nos imports: {e}")
        return False

def test_config():
    """Teste 2: Verificar configurações"""
    print("\n🧪 Teste 2: Verificando configurações...")
    
    try:
        from app.core.config import settings

        # Verificar se as configurações foram carregadas
        assert settings.ENVIRONMENT is not None
        assert settings.DATABASE_URL is not None
        assert settings.REDIS_URL is not None
        
        print(f"✅ Environment: {settings.ENVIRONMENT}")
        print(f"✅ Database URL: {settings.DATABASE_URL[:50]}...")
        print(f"✅ Redis URL: {settings.REDIS_URL}")
        return True
    except Exception as e:
        print(f"❌ Erro nas configurações: {e}")
        return False

def test_database_connection():
    """Teste 3: Verificar conexão com banco"""
    print("\n🧪 Teste 3: Verificando conexão com banco...")
    
    try:
        from app.core.database import check_connection
        
        if check_connection():
            print("✅ Conexão com banco funcionando!")
            return True
        else:
            print("❌ Falha na conexão com banco")
            return False
    except Exception as e:
        print(f"❌ Erro na conexão com banco: {e}")
        return False

def test_redis_connection():
    """Teste 4: Verificar conexão com Redis"""
    print("\n🧪 Teste 4: Verificando conexão com Redis...")
    
    try:
        from app.core.redis import check_redis_health
        
        if check_redis_health():
            print("✅ Conexão com Redis funcionando!")
            return True
        else:
            print("❌ Falha na conexão com Redis")
            return False
    except Exception as e:
        print(f"❌ Erro na conexão com Redis: {e}")
        return False

def test_models():
    """Teste 5: Verificar modelos SQLAlchemy"""
    print("\n🧪 Teste 5: Verificando modelos...")
    
    try:
        import uuid
        from datetime import date, datetime

        from app.models import Calendar, ChatMessage, ChatSession, Client, Event, User

        # Teste de criação de instâncias
        user = User(
            email="test@example.com",
            name="Test User",
            phone="+5511999999999"
        )
        
        client = Client(
            user_id=user.id,
            name="Test Client",
            phone="+5511888888888",
            birth_date=date(1990, 1, 1)
        )
        
        calendar = Calendar(
            user_id=user.id,
            name="Test Calendar",
            is_primary=True
        )
        
        event = Event(
            user_id=user.id,
            calendar_id=calendar.id,
            client_id=client.id,
            title="Test Event",
            start_time=datetime.now(),
            end_time=datetime.now()
        )
        
        session = ChatSession(
            user_id=user.id,
            session_id="test-session-123",
            phone_number="+5511777777777"
        )
        
        message = ChatMessage(
            session_id=session.id,
            message_type="user",
            content="Hello, this is a test message"
        )
        
        print("✅ Todos os modelos foram criados com sucesso!")
        print(f"   - User: {user}")
        print(f"   - Client: {client}")
        print(f"   - Calendar: {calendar}")
        print(f"   - Event: {event}")
        print(f"   - Session: {session}")
        print(f"   - Message: {message}")
        return True
    except Exception as e:
        print(f"❌ Erro nos modelos: {e}")
        return False

def test_database_operations():
    """Teste 6: Verificar operações no banco"""
    print("\n🧪 Teste 6: Verificando operações no banco...")
    
    try:
        import uuid
        from datetime import datetime

        from app.core.database import create_tables, get_db
        from app.models import User

        # Criar tabelas se não existirem
        create_tables()
        
        # Teste de inserção
        with next(get_db()) as db:
            # Verificar se a tabela users existe
            result = db.execute("SELECT COUNT(*) FROM simplificapsi.users").scalar()
            print(f"✅ Tabela users existe com {result} registros")
            
            # Verificar estrutura da tabela
            result = db.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'simplificapsi' 
                AND table_name = 'users'
                ORDER BY ordinal_position
            """).fetchall()
            
            print("✅ Estrutura da tabela users:")
            for row in result:
                print(f"   - {row[0]}: {row[1]}")
        
        return True
    except Exception as e:
        print(f"❌ Erro nas operações do banco: {e}")
        return False

def test_redis_operations():
    """Teste 7: Verificar operações no Redis"""
    print("\n🧪 Teste 7: Verificando operações no Redis...")
    
    try:
        from app.core.redis import cache_manager, session_manager

        # Teste de sessão
        session_id = "test-session-123"
        user_id = "test-user-456"
        
        # Criar sessão
        success = session_manager.create_session(session_id, user_id, {"test": "data"})
        if success:
            print("✅ Sessão criada com sucesso")
            
            # Recuperar sessão
            session_data = session_manager.get_session(session_id)
            if session_data:
                print(f"✅ Sessão recuperada: {session_data}")
            else:
                print("❌ Falha ao recuperar sessão")
                return False
        else:
            print("❌ Falha ao criar sessão")
            return False
        
        # Teste de cache
        cache_key = "test:cache:key"
        cache_value = {"message": "Hello Redis!", "timestamp": datetime.now().isoformat()}
        
        success = cache_manager.cache_set("test", cache_value, 60, "key")
        if success:
            print("✅ Cache definido com sucesso")
            
            # Recuperar cache
            cached_value = cache_manager.cache_get("test", "key")
            if cached_value:
                print(f"✅ Cache recuperado: {cached_value}")
            else:
                print("❌ Falha ao recuperar cache")
                return False
        else:
            print("❌ Falha ao definir cache")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Erro nas operações do Redis: {e}")
        return False

def test_logging():
    """Teste 8: Verificar sistema de logging"""
    print("\n🧪 Teste 8: Verificando sistema de logging...")
    
    try:
        from app.core.logging import get_logger, setup_logging

        # Setup logging
        setup_logging()
        
        # Testar logger
        logger = get_logger("test_logger")
        logger.info("Teste de logging funcionando!", extra={"test": True})
        
        print("✅ Sistema de logging funcionando!")
        return True
    except Exception as e:
        print(f"❌ Erro no sistema de logging: {e}")
        return False

def test_exceptions():
    """Teste 9: Verificar exceções customizadas"""
    print("\n🧪 Teste 9: Verificando exceções customizadas...")
    
    try:
        from fastapi import HTTPException

        from app.core.exceptions import (
            ClientNotFoundError,
            EventNotFoundError,
            SimplificaPsiException,
            ValidationError,
            to_http_exception,
        )

        # Teste de exceção básica
        try:
            raise SimplificaPsiException("Teste de exceção")
        except SimplificaPsiException as e:
            print(f"✅ Exceção básica: {e.message}")
        
        # Teste de exceção específica
        try:
            raise ClientNotFoundError("client-123")
        except ClientNotFoundError as e:
            print(f"✅ Exceção específica: {e.message}")
        
        # Teste de conversão para HTTP
        try:
            raise EventNotFoundError("event-456")
        except EventNotFoundError as e:
            http_exc = to_http_exception(e)
            print(f"✅ Conversão para HTTP: {http_exc.status_code}")
        
        print("✅ Sistema de exceções funcionando!")
        return True
    except Exception as e:
        print(f"❌ Erro no sistema de exceções: {e}")
        return False

def main():
    """Executar todos os testes"""
    print("🚀 INICIANDO TESTES DA FASE 2")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_config,
        test_database_connection,
        test_redis_connection,
        test_models,
        test_database_operations,
        test_redis_operations,
        test_logging,
        test_exceptions,
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
        print("🎉 TODOS OS TESTES PASSARAM! FASE 2 ESTÁ FUNCIONANDO!")
        return True
    else:
        print("⚠️  ALGUNS TESTES FALHARAM. Verifique os erros acima.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
