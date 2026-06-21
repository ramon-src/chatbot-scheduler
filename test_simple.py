#!/usr/bin/env python3
"""
Teste simples da FASE 2
"""

import sys


def test_database_tables():
    """Teste 1: Verificar se as tabelas existem no banco"""
    print("🧪 Teste 1: Verificando tabelas no banco...")
    
    import subprocess
    import sys
    
    try:
        # Executar comando SQL para listar tabelas
        result = subprocess.run([
            "docker-compose", "exec", "-T", "postgres", 
            "psql", "-U", "simplificapsi", "-d", "simplificapsi_dev", 
            "-c", "SELECT table_name FROM information_schema.tables WHERE table_schema = 'simplificapsi' ORDER BY table_name;"
        ], capture_output=True, text=True, check=True)
        
        print("✅ Conexão com banco funcionando!")
        print("📋 Tabelas encontradas:")
        for line in result.stdout.split('\n'):
            if 'table_name' in line or '|' in line and 'table_name' not in line:
                print(f"   {line}")
        
        # Verificar se temos as 6 tabelas esperadas
        expected_tables = ['calendars', 'chat_messages', 'chat_sessions', 'clients', 'events', 'users']
        found_tables = []
        for line in result.stdout.split('\n'):
            for table in expected_tables:
                if table in line:
                    found_tables.append(table)
        
        if len(found_tables) == 6:
            print(f"✅ Todas as {len(found_tables)} tabelas esperadas foram encontradas!")
            return True
        else:
            print(f"❌ Esperado 6 tabelas, encontrado {len(found_tables)}: {found_tables}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao conectar com banco: {e}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def test_redis_connection():
    """Teste 2: Verificar conexão com Redis"""
    print("\n🧪 Teste 2: Verificando conexão com Redis...")
    
    import subprocess
    import sys
    
    try:
        # Testar conexão com Redis
        result = subprocess.run([
            "docker-compose", "exec", "-T", "redis", 
            "redis-cli", "ping"
        ], capture_output=True, text=True, check=True)
        
        if "PONG" in result.stdout:
            print("✅ Conexão com Redis funcionando!")
            return True
        else:
            print(f"❌ Resposta inesperada do Redis: {result.stdout}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao conectar com Redis: {e}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def test_docker_containers():
    """Teste 3: Verificar se os containers estão rodando"""
    print("\n🧪 Teste 3: Verificando containers Docker...")
    
    import subprocess
    import sys
    
    try:
        # Listar containers
        result = subprocess.run([
            "docker-compose", "ps"
        ], capture_output=True, text=True, check=True)
        
        print("📋 Status dos containers:")
        print(result.stdout)
        
        # Verificar se postgres e redis estão rodando
        if "simplificapsi_postgres" in result.stdout and "Up" in result.stdout:
            print("✅ Container PostgreSQL está rodando!")
        else:
            print("❌ Container PostgreSQL não está rodando!")
            return False
            
        if "simplificapsi_redis" in result.stdout and "Up" in result.stdout:
            print("✅ Container Redis está rodando!")
        else:
            print("❌ Container Redis não está rodando!")
            return False
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao verificar containers: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def test_database_data():
    """Teste 4: Verificar dados de exemplo no banco"""
    print("\n🧪 Teste 4: Verificando dados de exemplo...")
    
    import subprocess
    import sys
    
    try:
        # Verificar se há dados de exemplo
        result = subprocess.run([
            "docker-compose", "exec", "-T", "postgres", 
            "psql", "-U", "simplificapsi", "-d", "simplificapsi_dev", 
            "-c", "SELECT COUNT(*) as user_count FROM simplificapsi.users;"
        ], capture_output=True, text=True, check=True)
        
        print("📊 Dados no banco:")
        print(result.stdout)
        
        # Verificar estrutura de uma tabela
        result = subprocess.run([
            "docker-compose", "exec", "-T", "postgres", 
            "psql", "-U", "simplificapsi", "-d", "simplificapsi_dev", 
            "-c", "\\d simplificapsi.users"
        ], capture_output=True, text=True, check=True)
        
        print("📋 Estrutura da tabela users:")
        print(result.stdout)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao verificar dados: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def main():
    """Executar todos os testes"""
    print("🚀 TESTE SIMPLES DA FASE 2")
    print("=" * 50)
    
    tests = [
        test_docker_containers,
        test_database_tables,
        test_redis_connection,
        test_database_data,
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
