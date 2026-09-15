"""Autenticación con cuentas locales: sesión, bloqueo por intentos y CSRF."""
import hashlib
import os
from urllib.parse import urlsplit

import psycopg2.extras
from flask import (
    Blueprint, flash, jsonify, redirect, render_template, request, session, url_for,
)
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db_connection

ORGANIZACIONES = ("UEx", "DGAP")
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
MENSAJE_LOGIN_FALLIDO = (
    "No se ha podido iniciar sesión. Revisa el correo y la contraseña "
    "o inténtalo de nuevo más tarde."
)
# Endpoints accesibles sin sesión iniciada
ENDPOINTS_PUBLICOS = {"auth.login", "static"}

# Hash ficticio para igualar el tiempo de respuesta cuando el email no existe
_HASH_FICTICIO = generate_password_hash("contraseña-ficticia-no-valida")

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()
csrf = CSRFProtect()


class Usuario(UserMixin):
    def __init__(self, fila):
        self.id = fila["id"]
        self.email = fila["email"]
        self.nombre = fila["nombre"]
        self.organizacion = fila["organizacion"]
        self.password_hash = fila["password_hash"]
        self.es_admin = fila["es_admin"]
        self.activo = fila["activo"]

    @property
    def is_active(self):
        return bool(self.activo)

    def get_id(self):
        # La huella del hash invalida las sesiones abiertas al cambiar la contraseña
        return f"{self.id}:{huella_password(self.password_hash)}"


def huella_password(password_hash):
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def leer_bool_entorno(nombre, por_defecto):
    valor = os.environ.get(nombre)
    if valor is None or valor.strip() == "":
        return por_defecto
    return valor.strip().lower() not in ("0", "false", "no", "off")


def validar_password(password, confirmacion):
    """Devuelve un mensaje de error o None si la contraseña es aceptable."""
    if not password:
        return "La contraseña no puede estar vacía."
    if password != confirmacion:
        return "La confirmación no coincide con la contraseña."
    return None


def siguiente_seguro(valor):
    """Acepta solo rutas relativas dentro de la aplicación para evitar redirecciones abiertas."""
    if not valor or not valor.startswith("/") or valor.startswith("//"):
        return None
    if "\\" in valor or any(ord(c) < 32 or ord(c) == 127 for c in valor):
        return None
    partes = urlsplit(valor)
    if partes.scheme or partes.netloc:
        return None
    return valor


def obtener_usuario(usuario_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
            fila = cur.fetchone()
    finally:
        conn.close()
    return Usuario(fila) if fila else None


@login_manager.user_loader
def cargar_usuario(identificador):
    usuario_id, _, huella = identificador.partition(":")
    if not usuario_id.isdigit():
        return None
    usuario = obtener_usuario(int(usuario_id))
    if usuario is None or not usuario.activo:
        return None
    if huella != huella_password(usuario.password_hash):
        return None
    return usuario


@login_manager.unauthorized_handler
def no_autorizado():
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Autenticación requerida"}), 401
    siguiente = request.full_path.rstrip("?") if request.method == "GET" else None
    return redirect(url_for("auth.login", next=siguiente_seguro(siguiente)))


def exigir_sesion():
    if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
        return None
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    return None


def error_csrf(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Token CSRF no válido o caducado"}), 400
    return render_template("auth/error_csrf.html", motivo=error.description), 400


def init_auth(app, url_prefix=""):
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("La variable de entorno SECRET_KEY es obligatoria")

    ruta_cookie = url_prefix or "/"
    cookie_segura = leer_bool_entorno("SESSION_COOKIE_SECURE", True)
    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="digibic_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cookie_segura,
        SESSION_COOKIE_PATH=ruta_cookie,
        # No se ofrece "recordarme"; se configura la cookie por coherencia
        REMEMBER_COOKIE_NAME="digibic_remember",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=cookie_segura,
        REMEMBER_COOKIE_PATH=ruta_cookie,
        # El token dura lo que la sesión; evita errores en páginas abiertas mucho tiempo
        WTF_CSRF_TIME_LIMIT=None,
    )

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    login_manager.init_app(app)
    # El guardia de sesión se registra antes que CSRF: sin sesión se responde 401/redirección
    app.before_request(exigir_sesion)
    csrf.init_app(app)
    app.register_error_handler(CSRFError, error_csrf)
    app.register_blueprint(auth_bp)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    siguiente = siguiente_seguro(request.values.get("next"))
    if current_user.is_authenticated:
        return redirect(request.script_root + siguiente if siguiente else url_for("index"))

    if request.method == "GET":
        return render_template("auth/login.html", siguiente=siguiente, email="")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    usuario = autenticar(email, password)
    if usuario is None:
        flash(MENSAJE_LOGIN_FALLIDO, "danger")
        return render_template("auth/login.html", siguiente=siguiente, email=email), 401

    session.clear()
    login_user(usuario)
    return redirect(request.script_root + siguiente if siguiente else url_for("index"))


def autenticar(email, password):
    """Valida credenciales aplicando el bloqueo temporal. Devuelve Usuario o None."""
    conn = get_db_connection()
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *, (bloqueado_hasta IS NOT NULL AND bloqueado_hasta > now()) AS bloqueado
                FROM usuarios WHERE lower(email) = %s FOR UPDATE
                """,
                (email,),
            )
            fila = cur.fetchone()
            if fila is None or fila["bloqueado"]:
                check_password_hash(_HASH_FICTICIO, password)
                return None

            if not check_password_hash(fila["password_hash"], password):
                cur.execute(
                    """
                    UPDATE usuarios SET
                        intentos_fallidos = CASE
                            WHEN bloqueado_hasta IS NOT NULL THEN 1
                            ELSE intentos_fallidos + 1 END,
                        bloqueado_hasta = CASE
                            WHEN bloqueado_hasta IS NULL AND intentos_fallidos + 1 >= %s
                            THEN now() + make_interval(mins => %s)
                            ELSE NULL END
                    WHERE id = %s
                    """,
                    (MAX_INTENTOS, MINUTOS_BLOQUEO, fila["id"]),
                )
                return None

            if not fila["activo"]:
                return None

            cur.execute(
                """
                UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL,
                    ultimo_acceso = now()
                WHERE id = %s
                """,
                (fila["id"],),
            )
            return Usuario(fila)
    finally:
        conn.close()


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    flash("Has cerrado la sesión.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/cuenta/password", methods=["GET", "POST"])
def cambiar_password():
    if request.method == "GET":
        return render_template("auth/cambiar_password.html")

    actual = request.form.get("password_actual") or ""
    nueva = request.form.get("password_nueva") or ""
    confirmacion = request.form.get("password_confirmacion") or ""

    if not check_password_hash(current_user.password_hash, actual):
        flash("La contraseña actual no es correcta.", "danger")
        return render_template("auth/cambiar_password.html"), 400
    error = validar_password(nueva, confirmacion)
    if error:
        flash(error, "danger")
        return render_template("auth/cambiar_password.html"), 400

    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s",
                (generate_password_hash(nueva), current_user.id),
            )
    finally:
        conn.close()

    # La sesión se renueva con la nueva huella de contraseña
    login_user(obtener_usuario(current_user.id))
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("index"))
