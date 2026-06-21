#!/usr/bin/env python3
"""
Script para corrigir as funções das tools dos agentes
"""

import re


def fix_client_agent():
    """Corrigir ClientAgent"""
    file_path = "app/agents/client_agent.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Padrões para corrigir
    patterns = [
        # client_update
        (r'async def client_update\(\s*self,\s*client_id: str,', 
         'async def client_update(\n        self,\n        ctx: RunContext[None],\n        client_id: str,'),
        
        # client_list
        (r'async def client_list\(\s*self,', 
         'async def client_list(\n        self,\n        ctx: RunContext[None],'),
        
        # client_search
        (r'async def client_search\(\s*self,', 
         'async def client_search(\n        self,\n        ctx: RunContext[None],'),
        
        # client_deactivate
        (r'async def client_deactivate\(\s*self, client_id: str\)', 
         'async def client_deactivate(\n        self,\n        ctx: RunContext[None],\n        client_id: str)'),
        
        # client_activate
        (r'async def client_activate\(\s*self, client_id: str\)', 
         'async def client_activate(\n        self,\n        ctx: RunContext[None],\n        client_id: str)'),
        
        # client_stats
        (r'async def client_stats\(\s*self\)', 
         'async def client_stats(\n        self,\n        ctx: RunContext[None])'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("✅ ClientAgent corrigido!")

def fix_agent_manager():
    """Corrigir AgentManager"""
    file_path = "app/agents/agent_manager.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Corrigir função classify_intention
    pattern = r'def classify_intention\(\s*self, message: str, context: Dict\[str, Any\]\)'
    replacement = 'def classify_intention(\n        self,\n        ctx: RunContext[None],\n        message: str,\n        context: Dict[str, Any])'
    
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("✅ AgentManager corrigido!")

def fix_calendar_agent():
    """Corrigir CalendarAgent"""
    file_path = "app/agents/calendar_agent.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Corrigir função create_event
    pattern = r'def create_event\(\s*self,'
    replacement = 'def create_event(\n        self,\n        ctx: RunContext[None],'
    
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("✅ CalendarAgent corrigido!")

if __name__ == "__main__":
    print("🔧 Corrigindo funções das tools dos agentes...")
    
    try:
        fix_client_agent()
        fix_agent_manager()
        fix_calendar_agent()
        print("\n🎉 Todas as correções aplicadas com sucesso!")
    except Exception as e:
        print(f"❌ Erro: {e}")
