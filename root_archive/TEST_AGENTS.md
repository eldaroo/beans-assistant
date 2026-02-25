# Test Agents Localmente

Guía para probar la lógica de los agentes sin deployar al VPS.

## 🎯 ¿Cuándo usar esto?

- ✅ Modificaste `graph.py` o archivos en `agents/`
- ✅ Querés probar una nueva feature antes de deployar
- ✅ Debugging de lógica de agentes
- ✅ Testing rápido sin reiniciar el bot

## 🚀 Uso básico

### Modo 1: Mensaje único

```powershell
# Probar un mensaje
python test_agent.py "cuántos productos tengo?"

# Con tenant específico
python test_agent.py --phone +5491112345678 "cuántos productos tengo?"

# Usar el .bat (más corto)
test_agent "mi mensaje aquí"
```

### Modo 2: Interactivo (REPL)

```powershell
# Modo interactivo
python test_agent.py --interactive

# O simplemente:
python test_agent.py

# O con el .bat:
test_agent -i
```

En modo interactivo:
```
[+5491112345678] >>> cuántos productos tengo?
✅ Response:
------------------------------------------------------------
Tenés 6 productos registrados.
------------------------------------------------------------

[+5491112345678] >>> cambiar teléfono
New phone number: +61476777212

[+5491112345678] >>> exit
Bye!
```

## 📝 Ejemplos de mensajes para probar

### Consultas básicas:
```powershell
test_agent "cuántos productos tengo?"
test_agent "mostrame el stock"
test_agent "cuál es mi ganancia?"
```

### Registro de productos:
```powershell
test_agent "registrar producto: Pulsera Roja, precio 500, costo 200"
test_agent "agregar stock: 10 pulseras rojas"
```

### Ventas:
```powershell
test_agent "registrar venta: 2 pulseras rojas"
test_agent "vender: 1 collar azul a Maria"
```

### Gastos:
```powershell
test_agent "registrar gasto: 5000 pesos en materiales"
```

### Cancelaciones:
```powershell
test_agent "cancelar última venta"
test_agent "cancelar último gasto"
```

## 🔧 Workflow recomendado

### 1. Modificar agentes en local

```powershell
# Editar archivos
notepad agents\router.py
notepad graph.py
```

### 2. Probar localmente

```powershell
# Modo interactivo para testing rápido
python test_agent.py -i

# Probar varios casos
test_agent "mensaje 1"
test_agent "mensaje 2"
```

### 3. Deploy al VPS cuando esté listo

```powershell
# Commit y push
git add .
git commit -m "feat: Update agent logic"
git push
```

```bash
# En el VPS
ssh root@31.97.100.1
cd /srv/apps/beans-assistant
git pull
screen -r whatsapp
# Ctrl+C, luego:
python whatsapp_server_multitenant.py
# Ctrl+A, D
```

## ⚠️ Importante

- ✅ **Los cambios en la BD son REALES** - Conecta al PostgreSQL del VPS
- ✅ **Multitenancy funciona** - Usa el phone para seleccionar tenant
- ❌ **No envía mensajes de WhatsApp** - Solo prueba la lógica

## 🐛 Debugging

Si hay errores, verás el traceback completo:

```powershell
python test_agent.py "mi mensaje"

# Si falla, verás:
# ❌ Error: ...
# Traceback (most recent call last):
#   ...
```

## 💡 Tips

1. **Usar modo interactivo** para iterar rápido
2. **Probar con diferentes tenants** cambiando el phone
3. **Verificar cambios en la BD** desde el backend:
   ```
   http://localhost:8000/docs
   ```
4. **Guardar casos de prueba** para regression testing

## 🎨 Personalización

Podés modificar `test_agent.py` para:
- Agregar más logging
- Guardar historial de tests
- Comparar outputs esperados vs reales
- Mockear llamadas a APIs externas

---

**¡Ahora podés iterar rápidamente sin deployar cada cambio!** 🚀
