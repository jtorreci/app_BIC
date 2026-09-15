import psycopg2.extras
import pytest

import usuarios
from conftest import PASSWORD, consultar, crear_usuario, iniciar_sesion, token_csrf
from db import get_db_connection


def _admin(client, email="admin@dgap.es"):
    admin_id = crear_usuario(email=email, nombre="Admin", organizacion="DGAP", es_admin=True)
    iniciar_sesion(client, email=email)
    return admin_id


def test_usuario_normal_recibe_403(client):
    usuario_id = crear_usuario()
    iniciar_sesion(client)
    assert client.get("/admin/usuarios").status_code == 403
    token = token_csrf(client, "/")
    assert client.post(
        f"/admin/usuarios/{usuario_id}/editar",
        data={"csrf_token": token, "nombre": "X", "organizacion": "UEx", "es_admin": "1"},
    ).status_code == 403
    assert consultar("SELECT es_admin FROM usuarios WHERE id = %s", (usuario_id,))[0][0] is False


def test_enlace_admin_solo_para_administradores(client):
    crear_usuario()
    iniciar_sesion(client)
    assert "/admin/usuarios" not in client.get("/").get_data(as_text=True)

    admin = client.application.test_client()
    _admin(admin)
    assert "/admin/usuarios" in admin.get("/").get_data(as_text=True)


def test_admin_crea_edita_y_restablece(client):
    _admin(client)
    assert client.get("/admin/usuarios").status_code == 200
    token = token_csrf(client, "/admin/usuarios")

    respuesta = client.post("/admin/usuarios/nuevo", data={
        "csrf_token": token, "email": "Nuevo@UEx.es", "nombre": "Nuevo", "organizacion": "UEx",
        "password": PASSWORD, "password_confirmacion": PASSWORD,
    })
    assert respuesta.status_code == 302
    nuevo_id, email, es_admin = consultar(
        "SELECT id, email, es_admin FROM usuarios WHERE lower(email) = 'nuevo@uex.es'"
    )[0]
    assert email == "nuevo@uex.es" and es_admin is False

    duplicado = client.post("/admin/usuarios/nuevo", data={
        "csrf_token": token, "email": "NUEVO@uex.es", "nombre": "Otro", "organizacion": "UEx",
        "password": PASSWORD, "password_confirmacion": PASSWORD,
    })
    assert duplicado.status_code == 400
    org_invalida = client.post("/admin/usuarios/nuevo", data={
        "csrf_token": token, "email": "otro@uex.es", "nombre": "Otro", "organizacion": "Otra",
        "password": PASSWORD, "password_confirmacion": PASSWORD,
    })
    assert org_invalida.status_code == 400

    assert client.post(f"/admin/usuarios/{nuevo_id}/editar", data={
        "csrf_token": token, "nombre": "Renombrado", "organizacion": "DGAP", "es_admin": "1",
    }).status_code == 302
    assert consultar(
        "SELECT nombre, organizacion, es_admin FROM usuarios WHERE id = %s", (nuevo_id,)
    )[0] == ("Renombrado", "DGAP", True)

    nuevo_cliente = client.application.test_client()
    assert iniciar_sesion(nuevo_cliente, email="nuevo@uex.es").status_code == 302
    nueva = "restablecida-000111"
    assert client.post(f"/admin/usuarios/{nuevo_id}/password", data={
        "csrf_token": token, "password": nueva, "password_confirmacion": nueva,
    }).status_code == 302
    # Las sesiones abiertas del usuario quedan invalidadas
    assert nuevo_cliente.get("/api/estadisticas").status_code == 401
    assert iniciar_sesion(nuevo_cliente, email="nuevo@uex.es", password=nueva).status_code == 302


def test_admin_desactiva_y_reactiva(client):
    _admin(client)
    usuario_id = crear_usuario()
    token = token_csrf(client, "/admin/usuarios")
    client.post(f"/admin/usuarios/{usuario_id}/activo", data={"csrf_token": token, "activo": "0"})
    assert consultar("SELECT activo FROM usuarios WHERE id = %s", (usuario_id,))[0][0] is False
    client.post(f"/admin/usuarios/{usuario_id}/activo", data={"csrf_token": token, "activo": "1"})
    assert consultar("SELECT activo FROM usuarios WHERE id = %s", (usuario_id,))[0][0] is True


def test_no_puede_desactivarse_a_si_mismo(client):
    admin_id = _admin(client)
    crear_usuario(email="otro-admin@dgap.es", es_admin=True)
    token = token_csrf(client, "/admin/usuarios")
    client.post(f"/admin/usuarios/{admin_id}/activo", data={"csrf_token": token, "activo": "0"})
    assert consultar("SELECT activo FROM usuarios WHERE id = %s", (admin_id,))[0][0] is True


def test_no_puede_quitarse_admin_a_si_mismo(client):
    admin_id = _admin(client)
    crear_usuario(email="otro-admin@dgap.es", es_admin=True)
    token = token_csrf(client, "/admin/usuarios")
    respuesta = client.post(f"/admin/usuarios/{admin_id}/editar", data={
        "csrf_token": token, "nombre": "Admin", "organizacion": "DGAP",
    })
    assert respuesta.status_code == 400
    assert consultar("SELECT es_admin FROM usuarios WHERE id = %s", (admin_id,))[0][0] is True


def test_guardia_de_ultimo_administrador(client):
    admin_id = _admin(client)
    otro_id = crear_usuario(email="otro-admin@dgap.es", es_admin=True)
    token = token_csrf(client, "/admin/usuarios")
    # Con dos administradores activos se puede quitar el rol al otro
    assert client.post(f"/admin/usuarios/{otro_id}/editar", data={
        "csrf_token": token, "nombre": "Otro", "organizacion": "UEx",
    }).status_code == 302
    assert consultar("SELECT es_admin FROM usuarios WHERE id = %s", (otro_id,))[0][0] is False

    # La regla se evalúa sobre la base de datos: con un único administrador activo se rechaza
    conn = get_db_connection()
    try:
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM usuarios WHERE id = %s", (admin_id,))
            fila = cur.fetchone()
            with pytest.raises(usuarios.ErrorValidacion):
                usuarios._comprobar_admins_restantes(cur, fila, quedara_admin_activo=False)
            # Mantenerlo como administrador activo sí es válido
            usuarios._comprobar_admins_restantes(cur, fila, quedara_admin_activo=True)
    finally:
        conn.close()


def test_cli_crear_admin(flask_app):
    runner = flask_app.test_cli_runner()
    resultado = runner.invoke(
        args=["crear-admin"],
        input=f"Admin@DGAP.es\nAdministradora\nDGAP\n{PASSWORD}\n{PASSWORD}\n",
    )
    assert resultado.exit_code == 0, resultado.output
    assert consultar("SELECT email, es_admin, organizacion FROM usuarios")[0] == (
        "admin@dgap.es", True, "DGAP"
    )

    corta = runner.invoke(args=["crear-admin"], input="b@uex.es\nB\nUEx\ncorta\ncorta\n")
    assert corta.exit_code == 0, corta.output

    vacia = runner.invoke(
        args=["crear-admin", "--email", "c@uex.es", "--nombre", "C",
              "--organizacion", "UEx", "--password", ""]
    )
    assert vacia.exit_code != 0
    assert "no puede estar vacía" in vacia.output
