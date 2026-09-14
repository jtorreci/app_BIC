# DIGIBIC - Bienes de Interés Cultural

Aplicación web para gestionar el listado de bienes de interés cultural y la planificación
de los trabajos de digitalización.

## Funcionalidades

- Listado en tarjetas (20 por página) o tabla (50 por página), con búsqueda y filtros
- Vista de detalle con campos "Entregado" y "Datos" editables
- Mapa de bienes (coordenadas UTM convertidas a WGS84)
- Planificación de toma de datos y procesado, con agenda
- Documentos por bien con versionado (sustitución) y bitácora
- Estadísticas generales
- Cuentas locales con inicio de sesión, bloqueo temporal tras 5 intentos fallidos
  y administración de usuarios (UEx / DGAP) en `/admin/usuarios`

## Arquitectura

- Flask + gunicorn, PostgreSQL 16, todo en Docker Compose
- `entrypoint.sh` importa `Bienes_Interes_Cultural.csv` solo si la tabla `bienes` está vacía
- La app se sirve bajo un prefijo configurable (`URL_PREFIX`, p. ej. `/digibic`)
- En producción no publica puertos: el proxy compartido de garnocex la alcanza por la red
  Docker externa `proxy` con el alias `digibic-app`

## Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `POSTGRES_PASSWORD` | Obligatoria. Solo caracteres válidos en URL (`openssl rand -hex 24`) |
| `POSTGRES_DB`, `POSTGRES_USER` | Opcionales (`bienes_bic`, `bic`) |
| `URL_PREFIX` | Prefijo de publicación, p. ej. `/digibic`. Vacío si se sirve en la raíz |
| `SECRET_KEY` | Obligatoria. Firma la cookie de sesión y los tokens CSRF (`openssl rand -hex 32`). Cambiarla cierra todas las sesiones |
| `SESSION_COOKIE_SECURE` | Opcional (`1` por defecto): la cookie de sesión solo viaja por HTTPS. Usar `0` solo en local por HTTP |
| `NAS_BIC_PATH` | Carpeta del host con los archivos que sirve `/archivos/` |

## Autenticación

Todas las páginas, la API (`/api/*`) y los archivos (`/archivos/*`) exigen iniciar sesión.
El esquema de usuarios (`esquema.py`) se crea o verifica en cada arranque del contenedor.

Crear el primer administrador (pide correo, nombre, organización y contraseña):

```bash
docker compose exec app flask --app app crear-admin
```

El resto de usuarios se gestiona desde **Usuarios** en la barra de navegación (solo
administradores): alta, edición, restablecimiento de contraseña y activación/desactivación.

Una vez desplegada esta versión, se elimina el `basic_auth` de Caddy para la ruta de
DIGIBIC en `garnocex-proxy`: la aplicación ya controla el acceso con sus propias cuentas.

## Desarrollo local

```bash
docker network create proxy   # una sola vez
docker compose up -d --build
```

Para trabajar por HTTP sin proxy, definir `SESSION_COOKIE_SECURE=0` en `.env`. Sin proxy delante, añadir temporalmente `ports: ["127.0.0.1:5000:5000"]` al servicio `app`
en un `docker-compose.override.yml` y abrir http://localhost:5000.

## Despliegue en garnocex

El proxy (Caddy) es un stack independiente compartido con otras aplicaciones del servidor.
Su runbook y el contrato de rutas están en `garnocex-proxy/README.md` y
`garnocex-proxy/CONTRACT.md` (fuera de este repositorio).

```bash
git clone https://github.com/jtorreci/app_BIC /opt/digibic
cd /opt/digibic && $EDITOR .env
docker compose up -d --build
docker compose logs app | tail   # "Registros importados: 256"
docker compose exec app flask --app app crear-admin   # solo la primera vez
```

## Pruebas

Requieren un PostgreSQL desechable (las tablas se recrean en cada ejecución):

```bash
docker run -d --name digibic_test_pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \
  -p 127.0.0.1:55433:5432 postgres:16-alpine
pip install -r requirements-dev.txt
pytest   # TEST_DATABASE_URL permite usar otra base de datos
```

## Scripts

- `scripts/backup_db.sh`: volcado diario de PostgreSQL con retención de 30 días (cron)
- `scripts/restaurar_render.py`: reaplica los datos editados exportados de Render
  (`docker compose exec -T app python scripts/restaurar_render.py < export.json`)

Restaurar un backup:

```bash
gunzip -c digibic_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T db psql -U bic -d bienes_bic
```
