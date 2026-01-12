# Despliegue rápido en Render.com

## Pasos para desplegar

### 1. Crear cuenta en Render
- Ve a https://render.com
- Crea una cuenta gratuita usando tu cuenta de GitHub
- Autoriza Render a acceder a tus repositorios

### 2. Crear el Web Service
- Clic en "New+" → "Web Service"
- Render te mostrará una lista de tus repositorios de GitHub
- Busca y selecciona el repositorio `jtorreci/app_BIC`

### 3. Configuración automática
Render detectará automáticamente:
- Framework: Python (por requirements.txt)
- Build Command: `pip install -r requirements.txt && python importar_csv.py`
- Start Command: `gunicorn app:app` (configurado en render.yaml)

### 4. Nombre y región
- Name: `app-BIC` (o el que prefieras)
- Region: Elige la región más cercana (ej: Frankfurt o Ireland)

### 5. Plan
- Plan: Free (gratis)
- El plan gratuito incluye:
  - 750 horas/mes
  - Dormant después de 15 minutos sin uso
  - Despierta en menos de 30 segundos

### 6. Crear y desplegar
- Clic en "Create Web Service"
- Render comenzará a construir y desplegar tu aplicación
- Este proceso puede tardar unos 3-5 minutos

### 7. Acceder a la aplicación
- Una vez completado el despliegue, verás la URL de tu aplicación
- Será algo como: `https://app-bic.onrender.com`
- Haz clic en la URL para acceder a tu aplicación

## Actualizaciones futuras

Cada vez que hagas cambios en el repositorio y hagas push:
```bash
git add .
git commit -m "Descripción del cambio"
git push
```

Render detectará automáticamente los cambios y redeployará.

## Limitaciones del plan gratuito

- La aplicación duerme después de 15 minutos de inactividad
- La primera petición puede tardar hasta 30 segundos
- No hay base de datos persistente (pero SQLite funciona para este caso)
- Logs se conservan por tiempo limitado

## Planes de pago

Si necesitas mejor rendimiento, puedes actualizar a:
- **Starter**: $7/mes - Sin límite de inactividad
- **Standard**: $25/mes - Más recursos
- **Pro**: Custom - Para aplicaciones grandes

## Monitoreo

En el dashboard de Render puedes:
- Ver logs en tiempo real
- Monitorizar métricas de uso
- Ver historial de despliegues
- Revisar errores

## Solución de problemas

### Si el despliegue falla
1. Revisa la pestaña "Logs" para ver el error
2. Verifica que todos los archivos necesarios estén en el repo
3. Asegúrate de que el CSV esté incluido

### Si la aplicación no carga
1. Verifica que el servicio esté "Live" en el dashboard
2. Revisa los logs de los últimos eventos
3. Intenta manual deploy: clic en "Manual Deploy" → "Clear build cache & deploy"

### Importante: El CSV debe estar en el repositorio
El archivo `Bienes_Interes_Cultural.csv` se incluye en el repositorio para que Render pueda importar los datos durante el build.
