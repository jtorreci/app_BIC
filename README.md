# Bienes de Interés Cultural - Aplicación Web

Aplicación web para gestionar y visualizar el listado de bienes de interés cultural.

## Instalación

1. Crear entorno virtual:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Instalar dependencias:
```bash
pip install -r requirements.txt
```

3. Importar datos del CSV a la base de datos:
```bash
python importar_csv.py
```

## Uso

Iniciar la aplicación:
```bash
python app.py
```

Abrir el navegador en: http://localhost:5000

## Funcionalidades

- **Dos vistas de listado**:
  - Vista de tarjetas (20 por página)
  - Vista de tabla (50 por página) para visualización rápida
- Búsqueda por nombre, municipio o provincia
- Filtros por estado de entrega y disponibilidad de datos
- Vista detallada de cada bien
- Campos "Entregado" y "Datos" editables directamente en el listado y en la vista de detalle
- Estadísticas generales
- Enlace a Google Maps para ubicación

## Archivos

- `Bienes_Interes_Cultural.csv` - Datos originales
- `importar_csv.py` - Script de importación
- `app.py` - Aplicación Flask
- `bienes.db` - Base de datos SQLite (se crea al ejecutar importar_csv.py)
- `templates/` - Plantillas HTML
- `DESPLIEGUE.md` - Guía completa de despliegue

## Despliegue para colaboradores

### Opción rápida: Render.com (Recomendado)

1. Crear cuenta en https://render.com
2. Clic en "New" → "Web Service"
3. Conectar a GitHub: seleccionar el repositorio `jtorreci/app_BIC`
4. Render detectará automáticamente la configuración del archivo `render.yaml`
5. Clic en "Create Web Service"
6. Esperar unos minutos y listo

Ver `DESPLIEGUE.md` para instrucciones detalladas de despliegue en:
- VPS propio (DigitalOcean, Linode, Hetzner)
- Render.com (gratuito/bara
- PythonAnywhere
- Railway
