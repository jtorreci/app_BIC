# Guía de Despliegue

## Opción 1: Despliegue en VPS (Recomendado)

### Requisitos previos
- Un VPS con Ubuntu/Debian (ej: DigitalOcean, Linode, Hetzner)
- Dominio (opcional)

### Pasos

1. Conectarte al servidor:
```bash
ssh usuario@tu-servidor.com
```

2. Instalar dependencias:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx
```

3. Clonar o subir el proyecto:
```bash
cd /var/www
git clone tu-repo bienes-culturales
# o usar scp para subir los archivos
```

4. Crear entorno virtual:
```bash
cd bienes-culturales
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

5. Importar datos:
```bash
python importar_csv.py
```

6. Crear servicio systemd:
```bash
sudo nano /etc/systemd/system/bienes-culturales.service
```

Contenido del archivo:
```ini
[Unit]
Description=App Bienes Culturales
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/bienes-culturales
Environment="PATH=/var/www/bienes-culturales/venv/bin"
ExecStart=/var/www/bienes-culturales/venv/bin/gunicorn --workers 3 --bind unix:bienes-culturales.sock app:app

[Install]
WantedBy=multi-user.target
```

7. Iniciar y habilitar el servicio:
```bash
sudo systemctl start bienes-culturales
sudo systemctl enable bienes-culturales
sudo systemctl status bienes-culturales
```

8. Configurar Nginx:
```bash
sudo nano /etc/nginx/sites-available/bienes-culturales
```

Contenido del archivo:
```nginx
server {
    listen 80;
    server_name tu-dominio.com;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/bienes-culturales/bienes-culturales.sock;
    }
}
```

9. Habilitar el sitio:
```bash
sudo ln -s /etc/nginx/sites-available/bienes-culturales /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

10. Configurar HTTPS (con certbot):
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```

---

## Opción 2: Despliegue en Render.com (Gratis/Barato)

1. Crear cuenta en https://render.com

2. Crear nuevo Web Service

3. Conectar a tu repositorio GitHub

4. Configurar:
   - Build Command: `pip install -r requirements.txt && python importar_csv.py`
   - Start Command: `gunicorn app:app`
   - Python Version: 3.10 o superior

5. Deploy!

---

## Opción 3: Despliegue en PythonAnywhere

1. Crear cuenta en https://www.pythonanywhere.com

2. Crear un nuevo Web App

3. Configurar:
   - Framework: Flask
   - Python version: 3.10 o superior
   - Worker type: *nearly unlimited* o superior

4. Subir archivos:
   - Conectarte por consola
   - Usar git pull o subir archivos

5. Instalar dependencias:
```bash
pip install -r requirements.txt
```

6. Importar datos:
```bash
python importar_csv.py
```

7. Configurar WSGI file:
   - En Files > WSGI configuration file
   - Añadir:
   ```python
   from app import app as application
   ```

---

## Opción 4: Despliegue en Railway

1. Instalar Railway CLI:
```bash
npm install -g @railway/cli
```

2. Iniciar sesión:
```bash
railway login
```

3. Crear proyecto:
```bash
railway init
railway up
```

4. Configurar variables de entorno (si es necesario)

5. Deploy!

---

## Consideraciones de Seguridad

- **Base de datos**: SQLite es seguro para este caso de uso
- **Autenticación**: Para uso público no es necesaria, pero si quieres restringir acceso, añadir:
  ```python
  from flask_httpauth import HTTPBasicAuth
  auth = HTTPBasicAuth()
  
  @app.before_request
  @auth.login_required
  def check_auth():
      pass
  ```

- **HTTPS**: Siempre usar HTTPS en producción
- **Backups**: Hacer backup periódico de bienes.db:
  ```bash
  # En crontab
  0 2 * * * cp /var/www/bienes-culturales/bienes.db /backup/bienes_$(date +\%Y\%m\%d).db
  ```

---

## Acceso a la aplicación

Una vez desplegado, tus colaboradores podrán acceder mediante:

- URL del VPS: http://tu-servidor.com o http://tu-dominio.com
- URL de Render: https://tu-app.onrender.com
- URL de PythonAnywhere: https://tuusuario.pythonanywhere.com
- URL de Railway: https://tu-app.railway.app

---

## Monitoreo

Ver logs:
```bash
# VPS con systemd
sudo journalctl -u bienes-culturales -f

# PythonAnywhere
# En la pestaña "Web" > "Log files"
```
