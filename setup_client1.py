"""
Setup Cliente 1 - Migrar datos existentes a arquitectura multi-tenant.

Este script:
1. Crea el tenant para +541153695627
2. Migra la base de datos actual (beansco.db) a su carpeta
3. Crea su configuración personalizada
"""
import shutil
from pathlib import Path
from tenant_manager import get_tenant_manager


def setup_client1():
    """Setup del cliente 1 con número específico."""

    PHONE_NUMBER = "+5491153695627"
    BUSINESS_NAME = "Beans&Co"

    print("="*60)
    print(f"Configurando Cliente 1: {PHONE_NUMBER}")
    print("="*60)

    tm = get_tenant_manager()

    # Check if tenant already exists
    if tm.tenant_exists(PHONE_NUMBER):
        print(f"\n[!] Cliente ya existe: {PHONE_NUMBER}")
        print("Quieres recrearlo? (Se perderan datos existentes)")
        response = input("Escribe 'SI' para continuar: ")

        if response.upper() != "SI":
            print("Operacion cancelada.")
            return

        # Remove existing tenant
        tenant_path = tm.get_tenant_path(PHONE_NUMBER)
        if tenant_path.exists():
            shutil.rmtree(tenant_path)
            print(f"[OK] Carpeta eliminada: {tenant_path}")

        if PHONE_NUMBER in tm.registry:
            del tm.registry[PHONE_NUMBER]
            tm._save_registry()
            print(f"[OK] Registro eliminado")

    # Create tenant with custom config
    config = {
        "business_name": BUSINESS_NAME,
        "business_type": "Pulseras y accesorios artesanales con granos de café",
        "currency": "USD",
        "language": "es",
        "timezone": "America/Argentina/Buenos_Aires",
        "prompts": {
            "system_prompt": (
                f"Eres un asistente de negocios inteligente para {BUSINESS_NAME}. "
                "Ayudas con ventas, inventario, gastos y análisis de ganancias. "
                "Eres amigable, eficiente y siempre das respuestas claras y concisas."
            ),
            "welcome_message": (
                f"¡Hola! Soy el asistente de {BUSINESS_NAME}. "
                "¿En qué puedo ayudarte hoy?"
            )
        },
        "features": {
            "audio_enabled": True,
            "sales_enabled": True,
            "expenses_enabled": True,
            "inventory_enabled": True
        }
    }

    print(f"\n[*] Creando tenant...")
    success = tm.create_tenant(PHONE_NUMBER, BUSINESS_NAME, config)

    if not success:
        print("[X] Error al crear tenant")
        return

    print(f"[OK] Tenant creado exitosamente")

    # Migrate existing database if it exists
    existing_db = Path("beansco.db")
    if existing_db.exists():
        print(f"\n[*] Migrando base de datos existente...")

        tenant_db_path = Path(tm.get_tenant_db_path(PHONE_NUMBER))

        # Backup the auto-generated DB
        backup_path = tenant_db_path.with_suffix(".db.backup")
        shutil.copy(tenant_db_path, backup_path)
        print(f"  [OK] Backup creado: {backup_path}")

        # Copy existing DB
        shutil.copy(existing_db, tenant_db_path)
        print(f"  [OK] Base de datos migrada: {existing_db} -> {tenant_db_path}")

        print(f"\n[!] IMPORTANTE: Se creo un backup de la DB auto-generada")
        print(f"   Si algo sale mal, puedes restaurarla desde: {backup_path}")
    else:
        print(f"\n[!] No se encontro beansco.db para migrar")
        print(f"   Se usara la base de datos nueva creada automaticamente")

    # Show summary
    print(f"\n" + "="*60)
    print(f"[OK] CLIENTE 1 CONFIGURADO")
    print(f"="*60)
    print(f"Teléfono: {PHONE_NUMBER}")
    print(f"Negocio: {BUSINESS_NAME}")
    print(f"Base de datos: {tm.get_tenant_db_path(PHONE_NUMBER)}")
    print(f"Configuración: {tm.get_tenant_path(PHONE_NUMBER) / 'config.json'}")

    # Show stats
    stats = tm.get_tenant_stats(PHONE_NUMBER)
    if stats:
        print(f"\n[STATS] Estadisticas:")
        print(f"  Productos: {stats['products']}")
        print(f"  Ventas: {stats['sales']}")
        print(f"  Ingresos: ${stats['revenue_usd']:.2f}")
        print(f"  Ganancia: ${stats['profit_usd']:.2f}")

    print(f"\n[OK] Ahora puedes usar whatsapp_server_multitenant.py")
    print(f"   El número {PHONE_NUMBER} será reconocido automáticamente")


if __name__ == "__main__":
    import sys

    # Check for --force flag
    force = "--force" in sys.argv

    if force:
        # Auto-remove existing tenant
        PHONE_NUMBER = "+5491153695627"
        tm = get_tenant_manager()

        if tm.tenant_exists(PHONE_NUMBER):
            print(f"\n[!] Removing existing tenant (--force mode)...")
            tenant_path = tm.get_tenant_path(PHONE_NUMBER)
            if tenant_path.exists():
                import shutil
                shutil.rmtree(tenant_path)
                print(f"[OK] Carpeta eliminada")

            if PHONE_NUMBER in tm.registry:
                del tm.registry[PHONE_NUMBER]
                tm._save_registry()
                print(f"[OK] Registro eliminado")

    setup_client1()
