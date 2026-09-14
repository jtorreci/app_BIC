"""Administración de usuarios y comando CLI para crear el primer administrador."""
import re

import click
import psycopg2
import psycopg2.errors
import psycopg2.extras
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from auth import ORGANIZACIONES, validar_password
from db import get_db_connection

PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/admin/usuarios")


class ErrorValidacion(Exception):
    pass


@usuarios_bp.before_request
def solo_administradores():
    if not current_user.is_authenticated or not current_user.es_admin:
        abort(403)


def _conexion_dict():
    conn = get_db_connection()
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _obtener(cur, usuario_id):
    cur.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    fila = cur.fetchone()
    if fila is None:
        abort(404)
    return fila


def _validar_datos(nombre, organizacion, email=None):
    if email is not None and not PATRON_EMAIL.match(email):
        raise ErrorValidacion("El correo electrónico no es válido.")
    if not nombre:
        raise ErrorValidacion("El nombre es obligatorio.")
    if organizacion not in ORGANIZACIONES:
        raise ErrorValidacion("La organización debe ser UEx o DGAP.")


def _comprobar_admins_restantes(cur, usuario, quedara_admin_activo):
    """Impide dejar la aplicación sin ningún administrador activo."""
    if quedara_admin_activo or not (usuario["es_admin"] and usuario["activo"]):
        return
    cur.execute(
        "SELECT COUNT(*) AS n FROM usuarios WHERE es_admin AND activo AND id <> %s",
        (usuario["id"],),
    )
    if cur.fetchone()["n"] == 0:
        raise ErrorValidacion("Debe quedar al menos un administrador activo.")


def insertar_usuario(email, nombre, organizacion, password, es_admin):
    email = (email or "").strip().lower()
    nombre = (nombre or "").strip()
    _validar_datos(nombre, organizacion, email)
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuarios (email, nombre, organizacion, password_hash, es_admin)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
                """,
                (email, nombre, organizacion, generate_password_hash(password), es_admin),
            )
            return cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        raise ErrorValidacion("Ya existe un usuario con ese correo electrónico.")
    finally:
        conn.close()


@usuarios_bp.route("")
def listado():
    conn, cur = _conexion_dict()
    try:
        cur.execute("SELECT * FROM usuarios ORDER BY lower(nombre), id")
        usuarios = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("admin/usuarios.html", usuarios=usuarios)


@usuarios_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    datos = {"email": "", "nombre": "", "organizacion": "", "es_admin": False}
    if request.method == "POST":
        datos = {
            "email": request.form.get("email", ""),
            "nombre": request.form.get("nombre", ""),
            "organizacion": request.form.get("organizacion", ""),
            "es_admin": request.form.get("es_admin") == "1",
        }
        try:
            error = validar_password(
                request.form.get("password", ""), request.form.get("password_confirmacion", "")
            )
            if error:
                raise ErrorValidacion(error)
            insertar_usuario(password=request.form.get("password", ""), **datos)
        except ErrorValidacion as exc:
            flash(str(exc), "danger")
            return render_template(
                "admin/usuario_form.html", usuario=None, datos=datos,
                organizaciones=ORGANIZACIONES,
            ), 400
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("usuarios.listado"))
    return render_template(
        "admin/usuario_form.html", usuario=None, datos=datos, organizaciones=ORGANIZACIONES
    )


@usuarios_bp.route("/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar(usuario_id):
    conn, cur = _conexion_dict()
    try:
        with conn:
            # Bloqueo de tabla para que las comprobaciones de administradores sean consistentes
            cur.execute("LOCK TABLE usuarios IN SHARE ROW EXCLUSIVE MODE")
            usuario = _obtener(cur, usuario_id)
            datos = dict(usuario)
            if request.method == "POST":
                datos.update(
                    nombre=request.form.get("nombre", "").strip(),
                    organizacion=request.form.get("organizacion", ""),
                    es_admin=request.form.get("es_admin") == "1",
                )
                try:
                    _validar_datos(datos["nombre"], datos["organizacion"])
                    if usuario_id == current_user.id and usuario["es_admin"] and not datos["es_admin"]:
                        raise ErrorValidacion("No puedes quitarte el rol de administrador.")
                    _comprobar_admins_restantes(cur, usuario, datos["es_admin"])
                except ErrorValidacion as exc:
                    flash(str(exc), "danger")
                    return render_template(
                        "admin/usuario_form.html", usuario=usuario, datos=datos,
                        organizaciones=ORGANIZACIONES,
                    ), 400
                cur.execute(
                    "UPDATE usuarios SET nombre = %s, organizacion = %s, es_admin = %s WHERE id = %s",
                    (datos["nombre"], datos["organizacion"], datos["es_admin"], usuario_id),
                )
                flash("Usuario actualizado correctamente.", "success")
                return redirect(url_for("usuarios.listado"))
    finally:
        cur.close()
        conn.close()
    return render_template(
        "admin/usuario_form.html", usuario=usuario, datos=datos, organizaciones=ORGANIZACIONES
    )


@usuarios_bp.route("/<int:usuario_id>/password", methods=["POST"])
def restablecer_password(usuario_id):
    password = request.form.get("password", "")
    error = validar_password(password, request.form.get("password_confirmacion", ""))
    if error:
        flash(error, "danger")
        return redirect(url_for("usuarios.editar", usuario_id=usuario_id))
    conn, cur = _conexion_dict()
    try:
        with conn:
            _obtener(cur, usuario_id)
            cur.execute(
                """
                UPDATE usuarios SET password_hash = %s, intentos_fallidos = 0,
                    bloqueado_hasta = NULL
                WHERE id = %s
                """,
                (generate_password_hash(password), usuario_id),
            )
    finally:
        cur.close()
        conn.close()
    flash("Contraseña restablecida. Las sesiones abiertas de ese usuario se han cerrado.", "success")
    return redirect(url_for("usuarios.listado"))


@usuarios_bp.route("/<int:usuario_id>/activo", methods=["POST"])
def cambiar_activo(usuario_id):
    activar = request.form.get("activo") == "1"
    conn, cur = _conexion_dict()
    try:
        with conn:
            cur.execute("LOCK TABLE usuarios IN SHARE ROW EXCLUSIVE MODE")
            usuario = _obtener(cur, usuario_id)
            try:
                if not activar and usuario_id == current_user.id:
                    raise ErrorValidacion("No puedes desactivar tu propia cuenta.")
                if not activar:
                    _comprobar_admins_restantes(cur, usuario, False)
            except ErrorValidacion as exc:
                flash(str(exc), "danger")
                return redirect(url_for("usuarios.listado"))
            cur.execute(
                """
                UPDATE usuarios SET activo = %s, intentos_fallidos = 0, bloqueado_hasta = NULL
                WHERE id = %s
                """,
                (activar, usuario_id),
            )
    finally:
        cur.close()
        conn.close()
    flash("Usuario activado." if activar else "Usuario desactivado.", "success")
    return redirect(url_for("usuarios.listado"))


@click.command("crear-admin")
@click.option("--email", prompt="Correo electrónico")
@click.option("--nombre", prompt="Nombre")
@click.option("--organizacion", prompt="Organización", type=click.Choice(ORGANIZACIONES))
@click.password_option("--password", prompt="Contraseña", confirmation_prompt="Repite la contraseña")
def crear_admin(email, nombre, organizacion, password):
    """Crea una cuenta de administrador (útil para el primer arranque)."""
    error = validar_password(password, password)
    if error:
        raise click.ClickException(error)
    try:
        usuario_id = insertar_usuario(email, nombre, organizacion, password, es_admin=True)
    except ErrorValidacion as exc:
        raise click.ClickException(str(exc))
    click.echo(f"Administrador creado con id {usuario_id}.")
