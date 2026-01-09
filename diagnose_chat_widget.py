"""
Script para diagnosticar problemas con el chat widget.
Verifica la conexion a la base de datos y el agente de IA.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

print("=" * 60)
print("DIAGNOSTICO DEL CHAT WIDGET")
print("=" * 60)

# Test 1: Verificar imports
print("\n[1/6] Verificando imports...")
try:
    from backend.api import chat_tenant
    print("  [OK] chat_tenant importado")
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

try:
    from tenant_manager import get_tenant_manager
    print("  [OK] tenant_manager importado")
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

try:
    from graph import create_business_agent_graph
    print("  [OK] graph importado")
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

try:
    import database
    print(f"  [OK] database importado (usando: {database.__name__})")
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

# Test 2: Verificar variables de entorno
print("\n[2/6] Verificando configuracion...")
import os
from dotenv import load_dotenv
load_dotenv()

use_postgres = os.getenv("USE_POSTGRES", "false").lower() == "true"
print(f"  USE_POSTGRES: {use_postgres}")

if use_postgres:
    print(f"  POSTGRES_HOST: {os.getenv('POSTGRES_HOST', 'not set')}")
    print(f"  POSTGRES_PORT: {os.getenv('POSTGRES_PORT', 'not set')}")
    print(f"  POSTGRES_DB: {os.getenv('POSTGRES_DB', 'not set')}")
else:
    print("  Usando SQLite")

google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    print(f"  [OK] GOOGLE_API_KEY configurada")
else:
    print(f"  [WARNING] GOOGLE_API_KEY no configurada")

# Test 3: Verificar tenants
print("\n[3/6] Verificando tenants...")
try:
    tenant_manager = get_tenant_manager()
    tenants = tenant_manager.list_tenants()
    if tenants:
        print(f"  [OK] {len(tenants)} tenant(s) encontrado(s):")
        for tenant in tenants[:3]:  # Mostrar solo los primeros 3
            phone = tenant.get('phone_number', 'Unknown')
            name = tenant.get('business_name', 'Unknown')
            print(f"    - {phone}: {name}")
        
        # Usar el primer tenant para pruebas
        test_tenant = tenants[0]['phone_number']
    else:
        print("  [ERROR] No hay tenants")
        sys.exit(1)
except Exception as e:
    print(f"  [ERROR] {e}")
    sys.exit(1)

# Test 4: Verificar conexion a base de datos
print(f"\n[4/6] Verificando conexion a base de datos del tenant {test_tenant}...")
try:
    # Obtener DB path del tenant
    db_path = tenant_manager.get_tenant_db_path(test_tenant)
    print(f"  DB Path: {db_path}")
    
    # Configurar database path
    database.DB_PATH = db_path
    
    # Intentar una query simple
    result = database.fetch_one("SELECT COUNT(*) as count FROM products")
    if result:
        print(f"  [OK] Conexion exitosa - {result['count']} productos encontrados")
    else:
        print(f"  [WARNING] Query exitosa pero sin resultados")
except Exception as e:
    print(f"  [ERROR] No se pudo conectar a la base de datos")
    print(f"  Error: {e}")
    import traceback
    print(traceback.format_exc())

# Test 5: Verificar agente de IA
print(f"\n[5/6] Verificando agente de IA...")
try:
    graph = create_business_agent_graph()
    print(f"  [OK] Agente creado exitosamente")
except Exception as e:
    print(f"  [ERROR] No se pudo crear el agente")
    print(f"  Error: {e}")
    import traceback
    print(traceback.format_exc())

# Test 6: Simular mensaje de chat
print(f"\n[6/6] Simulando mensaje de chat...")
try:
    # Configurar estado inicial
    initial_state = {
        "messages": [],
        "user_input": "hola",
        "phone": test_tenant,
        "sender": test_tenant,
        "normalized_entities": {},
        "metadata": {}
    }
    
    print(f"  Enviando mensaje de prueba: 'hola'")
    result = graph.invoke(initial_state)
    
    # Extraer respuesta
    if "messages" in result and len(result["messages"]) > 0:
        last_message = result["messages"][-1]
        if hasattr(last_message, 'content'):
            response = last_message.content
        elif isinstance(last_message, dict):
            response = last_message.get('content', str(last_message))
        else:
            response = str(last_message)
        
        print(f"  [OK] Respuesta del agente:")
        print(f"  '{response[:100]}...'")
    else:
        print(f"  [WARNING] No hay respuesta del agente")
        print(f"  Estado final: {result}")
        
except Exception as e:
    print(f"  [ERROR] Error al procesar mensaje")
    print(f"  Error: {e}")
    import traceback
    print(traceback.format_exc())

print("\n" + "=" * 60)
print("DIAGNOSTICO COMPLETO")
print("=" * 60)
print("\nSi todos los tests pasaron, el chat deberia funcionar.")
print("Si hay errores, revisa los mensajes arriba para mas detalles.")
