#!/usr/bin/env python3
"""
Teste simples do Pydantic AI
"""

import asyncio
import os
import sys
from pathlib import Path

# Adicionar o diretório raiz do projeto ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel


async def test_simple_agent():
    """Teste simples do Pydantic AI"""
    print("🤖 TESTE SIMPLES DO PYDANTIC AI")
    print("=" * 50)
    
    # Verificar chave da OpenAI
    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_openai_api_key_here":
        print("❌ OPENAI_API_KEY não encontrada!")
        return False
    
    print("✅ OPENAI_API_KEY encontrada!")
    
    try:
        # Criar modelo
        model = OpenAIChatModel(
            model_name="gpt-4o",
        )
        print("✅ Modelo criado com sucesso!")
        
        # Criar agente simples
        agent = Agent(
            model=model,
            output_type=str,
            system_prompt="Você é um assistente útil. Responda de forma concisa.",
        )
        print("✅ Agente criado com sucesso!")
        
        # Testar o agente
        result = await agent.run("Olá! Como você está?")
        print(f"✅ Resposta do agente: {result.output}")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simple_agent())
    sys.exit(0 if success else 1)
