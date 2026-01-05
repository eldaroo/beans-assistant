# Checklist de Deployment - Multi-Tenant

## Problema Detectado

❌ El servidor está usando código viejo:
- No reconoce clientes existentes (perdió persistencia)
- Confunde productos (pulseras negras → clásicas)
- No tiene el fix del resolver

## Solución: Actualizar Servidor

### Opción A: Deployment Automático (Recomendado)

```bash
# 1. Conéctate al servidor
ssh tu_usuario@tu_servidor

# 2. Ve al directorio del proyecto
cd /ruta/a/supabase-sql-agent

# 3. Sube los archivos nuevos (desde tu máquina local)
# En tu máquina local:
scp tenant_manager.py tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/
scp onboarding_agent.py tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/
scp whatsapp_server_multitenant.py tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/
scp setup_client1.py tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/
scp agents/resolver.py tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/agents/
scp deploy_multitenant.sh tu_usuario@tu_servidor:/ruta/a/supabase-sql-agent/

# 4. En el servidor, ejecuta:
chmod +x deploy_multitenant.sh
./deploy_multitenant.sh
```

### Opción B: Deployment Manual

Si prefieres hacerlo paso a paso:

#### 1. Subir Archivos Nuevos

Desde tu máquina local:

```bash
# Archivos críticos a subir:
scp tenant_manager.py tu_servidor:/ruta/proyecto/
scp onboarding_agent.py tu_servidor:/ruta/proyecto/
scp whatsapp_server_multitenant.py tu_servidor:/ruta/proyecto/
scp setup_client1.py tu_servidor:/ruta/proyecto/
scp agents/resolver.py tu_servidor:/ruta/proyecto/agents/
```

#### 2. En el Servidor

```bash
# Conectar al servidor
ssh tu_usuario@tu_servidor
cd /ruta/a/supabase-sql-agent

# Detener servidor actual
./stop_server.sh

# Backup de seguridad
cp beansco.db beansco_backup_$(date +%Y%m%d).db

# Crear directorios necesarios
mkdir -p data/clients data/templates configs

# Setup cliente 1
python3 setup_client1.py --force

# Verificar que se creó
ls -la data/clients/+5491153695627/

# Debería mostrar:
# - business.db
# - config.json
```

#### 3. Actualizar Script de Inicio

```bash
# Editar start_server.sh
nano start_server.sh

# Cambiar:
# python whatsapp_server.py
# Por:
# python whatsapp_server_multitenant.py

# Guardar: Ctrl+X, Y, Enter
```

#### 4. Iniciar Servidor

```bash
# Iniciar servidor multi-tenant
./start_server.sh

# Ver logs
tail -f whatsapp.log
# O si usas systemd:
sudo journalctl -u whatsapp-bot -f
```

## Verificación

### ✅ Checklist Post-Deployment

Envía estos mensajes desde WhatsApp (+5491153695627):

1. **Test 1: Reconocimiento de cliente**
   ```
   Mensaje: "hola"

   ❌ Si dice: "Bienvenido! Primera vez..."
      → El servidor NO está usando multi-tenant

   ✅ Si dice: "¡Hola! Soy el asistente de Beans&Co..."
      → Funciona correctamente
   ```

2. **Test 2: Consulta de stock**
   ```
   Mensaje: "cuánto stock tengo de pulseras negras?"

   ✅ Debería responder con el stock correcto
   ```

3. **Test 3: Registro de venta (FIX DEL RESOLVER)**
   ```
   Mensaje: "vendí 1 pulsera negra"

   ❌ Si dice: "No hay stock de pulsera CLÁSICA"
      → El fix del resolver NO está aplicado

   ✅ Si dice: "Venta registrada! 1 Pulsera Negra..."
      → Funciona correctamente
   ```

### Logs a Verificar

En los logs del servidor deberías ver:

**✅ CORRECTO:**
```
[TENANT] Existing client: +5491153695627
[TENANT] Using database: data/clients/+5491153695627/business.db
[AGENT] Processing...
```

**❌ INCORRECTO:**
```
[TENANT] New client detected: +5491153695627  ← NO debería decir esto
[TENANT] Starting onboarding process...
```

## Persistencia de Datos

### Verificar Base de Datos

```bash
# En el servidor
sqlite3 data/clients/+5491153695627/business.db

# Ejecutar:
SELECT COUNT(*) FROM products;
SELECT COUNT(*) FROM sales;
SELECT * FROM stock_current;

# Debería mostrar tus datos:
# - 6 productos
# - 28+ ventas
# - Stock actual
```

### Si Perdiste Datos

```bash
# Restaurar desde backup
cp beansco_backup_YYYYMMDD.db data/clients/+5491153695627/business.db

# O usar el backup automático
cp data/clients/+5491153695627/business.db.backup data/clients/+5491153695627/business.db

# Reiniciar servidor
./stop_server.sh
./start_server.sh
```

## Troubleshooting

### Problema: "New client detected" cada vez

**Causa:** El servidor no está usando `whatsapp_server_multitenant.py`

**Solución:**
```bash
# Verificar qué servidor está corriendo
ps aux | grep whatsapp

# Si muestra whatsapp_server.py (sin multitenant):
./stop_server.sh
# Edita start_server.sh para usar whatsapp_server_multitenant.py
./start_server.sh
```

### Problema: Confunde productos (negras → clásicas)

**Causa:** El fix del resolver no está aplicado

**Solución:**
```bash
# Verificar que agents/resolver.py tiene el fix
grep "best_match" agents/resolver.py

# Si no aparece, vuelve a subir:
scp agents/resolver.py servidor:/ruta/proyecto/agents/

# Reiniciar servidor
./stop_server.sh
./start_server.sh
```

### Problema: Base de datos se resetea

**Causa:** No está usando la DB correcta

**Solución:**
```bash
# Verificar tenant registry
cat configs/tenant_registry.json

# Debería mostrar:
# {
#   "+5491153695627": {
#     "business_name": "Beans&Co",
#     "created_at": "...",
#     "status": "active"
#   }
# }

# Si está vacío, recrear:
python3 setup_client1.py --force
```

## Archivos Críticos a Subir

Lista completa de archivos que necesitan estar actualizados en el servidor:

- [ ] `tenant_manager.py` (nuevo)
- [ ] `onboarding_agent.py` (nuevo)
- [ ] `whatsapp_server_multitenant.py` (nuevo)
- [ ] `setup_client1.py` (nuevo)
- [ ] `agents/resolver.py` (FIX CRÍTICO - scoring de productos)
- [ ] `start_server.sh` (modificado para usar multitenant)

## Soporte

Si algo falla:

1. **Revisar logs:** `tail -f whatsapp.log`
2. **Verificar DB:** `ls -la data/clients/+5491153695627/`
3. **Test resolver:** `python3 test_resolver_fix.py`
4. **Restaurar backup:** `cp backups/LATEST/beansco.db data/clients/+5491153695627/business.db`

## Comandos Útiles

```bash
# Ver estructura de clientes
tree data/clients/

# Ver registro de tenants
cat configs/tenant_registry.json | python3 -m json.tool

# Ver config de cliente
cat data/clients/+5491153695627/config.json | python3 -m json.tool

# Ver stats
python3 -c "from tenant_manager import get_tenant_manager; tm = get_tenant_manager(); print(tm.get_tenant_stats('+5491153695627'))"

# Reinicio completo
./stop_server.sh && sleep 2 && ./start_server.sh && tail -f whatsapp.log
```
