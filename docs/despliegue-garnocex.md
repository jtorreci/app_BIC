# Despliegue de DIGIBIC en garnocex

Guía paso a paso para poner DIGIBIC en `https://garnocex.unex.es/digibic/`.

- **Referencia del servidor:** nodo PCC `desarrollo.garnocex_infra`
  (`/mnt/nas/Dropbox/Universidad/Desarrollo/garnocex-infra/README.md`).
- **Contrato de rutas y cambio de nginx a Caddy:** repositorio `jtorreci/garnocex-proxy`
  (`CONTRACT.md` y `README.md`).

Todos los comandos se ejecutan en garnocex como root salvo que se indique lo contrario.

## Visión general

| Fase | Qué se consigue | Corte de servicio |
|---|---|---|
| 0. Comprobaciones | El servidor cumple los requisitos | No |
| 1. Stack de DIGIBIC | App y base de datos funcionando en la red `proxy`, sin publicar | No |
| 2. Primer administrador y backups | Acceso inicial y copia diaria verificada | No |
| 3. Proxy y cambio de nginx a Caddy | DIGIBIC publicada junto a la agenda | No (runbook de `garnocex-proxy`) |

DIGIBIC no es accesible desde fuera hasta la fase 3. Como la aplicación ya tiene su propio
inicio de sesión, **no se usa `basic_auth` en Caddy** en ningún momento.

## Fase 0. Comprobaciones

```bash
docker version --format '{{.Server.Version}}'      # Docker instalado
docker compose version                              # Compose v2
docker network inspect proxy --format '{{.Name}}'   # red compartida (ya creada)
docker inspect agenda_app \
  --format '{{json .NetworkSettings.Networks.proxy.Aliases}}'   # contiene "agenda-app"
df -h /var/lib/docker /opt /srv                     # espacio libre
timedatectl | rg 'synchronized'                     # hora sincronizada (TLS y sesiones)
```

Si `docker network inspect proxy` falla, crearla con `docker network create proxy`.

## Fase 1. Stack de DIGIBIC

### 1.1 Código

El repositorio `jtorreci/app_BIC` es público: no necesita credenciales.

```bash
git clone https://github.com/jtorreci/app_BIC /opt/digibic
cd /opt/digibic
git log --oneline -1          # debe incluir la autenticación (merge del PR #2)
```

### 1.2 Carpeta de archivos

`/archivos/` sirve ficheros de solo lectura. Hoy no hay documentos que apunten a rutas locales,
así que basta con una carpeta vacía hasta decidir si los ficheros se sincronizan desde el NAS.

```bash
mkdir -p /srv/digibic/archivos
```

### 1.3 Variables de entorno

Los secretos se generan en el propio servidor y nunca se copian a Git, Engram ni notas.

```bash
umask 077
cat > /opt/digibic/.env <<EOF
POSTGRES_DB=bienes_bic
POSTGRES_USER=bic
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 32)
SESSION_COOKIE_SECURE=1
URL_PREFIX=/digibic
NAS_BIC_PATH=/srv/digibic/archivos
EOF
chmod 600 /opt/digibic/.env
```

`POSTGRES_PASSWORD` solo se usa la primera vez que se crea el volumen de datos. Cambiarla después
exige cambiarla también dentro de PostgreSQL.

### 1.4 Arranque

```bash
cd /opt/digibic
docker compose config --quiet && echo "compose OK"
docker compose up -d --build
docker compose ps
docker compose logs app | tail -20
```

En los logs deben aparecer, en este orden:

1. `Registros importados: 256` (solo en el primer arranque; después,
   `Base de datos ya tiene 256 registros. Saltando importación.`)
2. `Esquema de usuarios verificado`
3. el arranque de gunicorn (`Listening at: http://0.0.0.0:5000`) sin errores

### 1.5 Prueba interna

La app no publica puertos. Se prueba desde un contenedor conectado a la red `proxy`, igual que
la verá Caddy:

```bash
C="docker run --rm --network proxy curlimages/curl:8.10.1 -s -o /dev/null -w %{http_code}"
$C http://digibic-app:5000/digibic/login; echo          # 200
$C http://digibic-app:5000/digibic/; echo               # 302 (al login)
$C http://digibic-app:5000/digibic/api/estadisticas; echo   # 401
```

## Fase 2. Primer administrador y backups

### 2.1 Administrador

```bash
cd /opt/digibic
docker compose exec app flask --app app crear-admin
```

Usar el modo interactivo: la opción `--password` deja la contraseña en el historial de la shell.
El resto de cuentas (personal UEx y DGAP) se crea desde **Usuarios** una vez publicada la app.

### 2.2 Backup diario

```bash
chmod +x /opt/digibic/scripts/backup_db.sh
/opt/digibic/scripts/backup_db.sh                       # primera copia manual
ls -lh /srv/backups/digibic/
gunzip -t /srv/backups/digibic/digibic_*.sql.gz && echo "backup legible"
```

Añadir al crontab de root (`crontab -e`):

```cron
30 3 * * * /opt/digibic/scripts/backup_db.sh >> /var/log/digibic-backup.log 2>&1
```

### 2.3 Prueba de restauración

Una copia que no se ha restaurado nunca no es una copia. Se restaura en un PostgreSQL desechable,
sin tocar la base de producción:

```bash
docker run -d --name digibic_restore_test -e POSTGRES_PASSWORD=test postgres:16-alpine
sleep 15
docker exec digibic_restore_test psql -q -U postgres -c "CREATE ROLE bic"
gunzip -c "$(ls -t /srv/backups/digibic/digibic_*.sql.gz | head -1)" \
  | docker exec -i digibic_restore_test psql -q -U postgres > /dev/null
docker exec digibic_restore_test psql -U postgres -tAc \
  "select count(*) from bienes; select count(*) from usuarios;"   # 256 y 1
docker rm -f digibic_restore_test
```

El volcado asigna las tablas al usuario `bic`; por eso se crea antes en la base desechable.
Si `psql` responde `the database system is starting up`, aumentar la espera.

## Fase 3. Publicación con el proxy

La publicación la hace el cambio de nginx a Caddy, que es compartido con la agenda y sigue el
runbook de `garnocex-proxy/README.md`. Antes de empezarlo:

- [ ] Fases 0 a 2 completadas
- [ ] `garnocex-proxy` #1 (conciliación de la agenda) mergeado
- [ ] `garnocex-proxy` #2 mergeado: quita el `basic_auth` de DIGIBIC y obtiene el certificado
      TLS antes del cambio (nginx reenvía el reto ACME a Caddy), con lo que el corte dura segundos
- [ ] Agenda avisada del momento del cambio (pestaña `desarrollo.agenda_estudiante`)

Comprobaciones específicas de DIGIBIC tras el cambio. garnocex **no puede conectarse a su
propia IP pública** (`curl` devuelve `000` aunque todo funcione), así que desde el servidor se
fuerza `127.0.0.1`; desde cualquier otro equipo se omite `--resolve`:

```bash
R="--resolve garnocex.unex.es:443:127.0.0.1"
curl -s -o /dev/null -w '%{http_code}\n' $R https://garnocex.unex.es/digibic/        # 302
curl -s -o /dev/null -w '%{http_code}\n' $R https://garnocex.unex.es/digibic/login   # 200
curl -sI $R https://garnocex.unex.es/digibic/login | grep -i set-cookie
# digibic_session con Path=/digibic; Secure; HttpOnly
```

Después, iniciar sesión en el navegador con el administrador y crear las cuentas del personal
(ver [Gestión de usuarios](#gestión-de-usuarios)).

**Navegador que redirige a la agenda.** Antes del cambio, nginx respondía a cualquier ruta
desconocida (incluida `/digibic`) con un `301` permanente a `/agenda/`, y el navegador lo guarda.
Si el servidor responde bien pero el navegador sigue yendo a la agenda, abrir
`https://garnocex.unex.es/digibic/login` directamente, usar una ventana privada o borrar la
caché del navegador para `garnocex.unex.es`.

## Gestión de usuarios

Solo los administradores ven el enlace **Usuarios** en la barra de navegación
(`https://garnocex.unex.es/digibic/admin/usuarios`).

| Tarea | Cómo |
|---|---|
| Alta | **Nuevo usuario** → correo, nombre, organización (`UEx` o `DGAP`), contraseña inicial y, si procede, **Administrador** → **Guardar** |
| Editar nombre, organización o rol | Icono del lápiz en la fila del usuario → **Guardar** |
| Restablecer contraseña | Icono del lápiz → bloque **Restablecer contraseña** → **Restablecer**. Cierra las sesiones abiertas de ese usuario |
| Dar de baja | Icono de desactivar en la fila. No se borra: se conserva la autoría de sus documentos y se puede reactivar |
| Cambiar la propia contraseña | Menú con el propio nombre (arriba a la derecha) → **Cambiar contraseña** |

Reglas:

- No hay registro público: todas las cuentas las crea un administrador.
- El correo es el identificador de acceso y no se puede cambiar después del alta.
- Un administrador no puede desactivarse ni quitarse el rol a sí mismo, y siempre queda al
  menos un administrador activo.
- Tras 5 intentos fallidos la cuenta se bloquea 15 minutos.
- La contraseña inicial conviene enviarla por un canal distinto al del enlace de acceso y pedir
  a cada persona que la cambie en su primer acceso (la aplicación no lo obliga).

## Actualizaciones

```bash
cd /opt/digibic
/opt/digibic/scripts/backup_db.sh
git pull --ff-only
docker compose up -d --build
docker compose logs app | tail
```

## Vuelta atrás

- **Antes de la fase 3:** `docker compose down` en `/opt/digibic`. No afecta a nada público.
  Añadir `-v` solo si se quiere borrar también la base de datos.
- **Después de la fase 3:** seguir la vuelta atrás del runbook de `garnocex-proxy`, que
  restaura nginx para todo el servidor.
- **Versión anterior de la app:** `git checkout <commit>` + `docker compose up -d --build`,
  y restaurar el backup previo si la versión nueva cambió el esquema.

## Cuestiones abiertas

- **Ficheros de `/archivos/`:** están en el NAS, no en garnocex. Decidir si se sincronizan
  (por ejemplo con `rsync` programado) o si los documentos usan solo enlaces externos.
- **Datos de Render:** no hace falta restaurarlos. Los 7 bienes entregados ya vienen marcados
  en la columna `ENTREGADO` del CSV.
