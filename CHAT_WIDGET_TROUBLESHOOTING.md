# Chat Widget - Troubleshooting Guide

## Error: 404 Not Found

### Causa
El número de teléfono con el símbolo `+` no estaba siendo codificado correctamente en la URL.

### Solución Aplicada
✅ Actualizado `chat_widget.js` para usar `encodeURIComponent()` al construir la URL del endpoint.

**Antes:**
```javascript
const response = await fetch(`/api/tenants/${this.tenantPhone}/chat`, {
```

**Después:**
```javascript
const response = await fetch(`/api/tenants/${encodeURIComponent(this.tenantPhone)}/chat`, {
```

### Verificación

1. **Refresca la página** en el navegador (Ctrl+F5 o Cmd+Shift+R)
2. **Abre la consola del navegador** (F12)
3. **Busca el mensaje de inicialización**:
   ```
   [Chat Widget] Initialized for tenant: +541153695627
   [Chat Widget] API endpoint will be: /api/tenants/%2B541153695627/chat
   ```
4. **Envía un mensaje** y verifica que no haya error 404

### Otros Problemas Comunes

#### Backend no está corriendo
**Síntoma**: Error de conexión o 404

**Solución**:
```bash
python backend/app.py
```

#### Falta GOOGLE_API_KEY
**Síntoma**: Error 500 al procesar mensaje

**Solución**: Agrega tu API key en `.env`:
```
GOOGLE_API_KEY=tu_api_key_aqui
```

#### Tenant no existe
**Síntoma**: Error 404 con mensaje "Tenant not found"

**Solución**: Verifica que el tenant existe en `configs/tenant_registry.json`

#### Dependencias faltantes
**Síntoma**: ImportError o ModuleNotFoundError

**Solución**:
```bash
pip install -r requirements.txt
```

### Test Manual

Puedes probar el endpoint directamente con PowerShell:

```powershell
$body = @{message="cuántos productos tengo?"} | ConvertTo-Json
$phone = [System.Web.HttpUtility]::UrlEncode("+541153695627")
Invoke-RestMethod -Uri "http://localhost:8000/api/tenants/$phone/chat" -Method POST -Body $body -ContentType "application/json"
```

O con el script de prueba:
```bash
python test_chat_endpoint.py
```

### Logs Útiles

**Consola del navegador**:
- Mensajes de inicialización del widget
- Errores de red
- Respuestas del servidor

**Terminal del backend**:
- Requests recibidos
- Errores del agente
- Stack traces

### Próximos Pasos

Si el problema persiste después de refrescar:
1. Verifica que el archivo `chat_widget.js` se haya actualizado
2. Limpia la caché del navegador completamente
3. Revisa los logs del backend para ver si el request llega
4. Usa las herramientas de desarrollo del navegador (Network tab) para ver la URL exacta que se está llamando
