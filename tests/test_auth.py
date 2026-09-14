import os
import subprocess
import sys

from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client

from auth import leer_bool_entorno, siguiente_seguro
from conftest import PASSWORD, RAIZ, consultar, crear_usuario, iniciar_sesion, token_csrf


def test_html_sin_sesion_redirige_a_login(client):
    respuesta = client.get("/planificacion?page=2")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/login?next=/planificacion?page%3D2"


def test_archivos_sin_sesion_redirige_a_login(client):
    respuesta = client.get("/archivos/informe.pdf")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].startswith("/login")


def test_api_sin_sesion_devuelve_401_json(client):
    respuesta = client.get("/api/estadisticas")
    assert respuesta.status_code == 401
    assert respuesta.is_json
    assert respuesta.get_json()["success"] is False

    respuesta = client.post("/api/toggle_entregado/1")
    assert respuesta.status_code == 401
    assert respuesta.is_json


def test_login_correcto_actualiza_ultimo_acceso(client):
    usuario_id = crear_usuario()
    respuesta = iniciar_sesion(client, email="USUARIO@uex.es")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/"
    assert client.get("/api/estadisticas").status_code == 200
    ultimo_acceso, intentos = consultar(
        "SELECT ultimo_acceso, intentos_fallidos FROM usuarios WHERE id = %s", (usuario_id,)
    )[0]
    assert ultimo_acceso is not None
    assert intentos == 0


def test_login_fallido_mensaje_generico(client):
    crear_usuario()
    incorrecta = iniciar_sesion(client, password="otra-contraseña-mala")
    inexistente = iniciar_sesion(client, email="nadie@uex.es")
    assert incorrecta.status_code == inexistente.status_code == 401
    texto = "No se ha podido iniciar sesión"
    assert texto in incorrecta.get_data(as_text=True)
    assert texto in inexistente.get_data(as_text=True)
    assert client.get("/api/estadisticas").status_code == 401


def test_bloqueo_tras_cinco_fallos(client):
    usuario_id = crear_usuario()
    for _ in range(5):
        assert iniciar_sesion(client, password="incorrecta-000000").status_code == 401
    bloqueado, intentos = consultar(
        "SELECT bloqueado_hasta > now() + interval '14 minutes', intentos_fallidos "
        "FROM usuarios WHERE id = %s",
        (usuario_id,),
    )[0]
    assert bloqueado is True
    assert intentos == 5
    # Ni siquiera la contraseña correcta permite entrar mientras dura el bloqueo
    assert iniciar_sesion(client).status_code == 401
    assert client.get("/api/estadisticas").status_code == 401


def test_bloqueo_expirado_permite_login_y_reinicia_contador(client):
    usuario_id = crear_usuario()
    for _ in range(4):
        iniciar_sesion(client, password="incorrecta-000000")
    assert consultar("SELECT intentos_fallidos FROM usuarios WHERE id = %s", (usuario_id,))[0][0] == 4
    assert iniciar_sesion(client).status_code == 302
    assert consultar("SELECT intentos_fallidos FROM usuarios WHERE id = %s", (usuario_id,))[0][0] == 0

    consultar(
        "UPDATE usuarios SET intentos_fallidos = 5, bloqueado_hasta = now() - interval '1 minute' "
        "WHERE id = %s RETURNING id",
        (usuario_id,),
    )
    otro = client.application.test_client()
    assert iniciar_sesion(otro, password="incorrecta-000000").status_code == 401
    assert consultar(
        "SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE id = %s", (usuario_id,)
    )[0] == (1, None)


def test_usuario_inactivo_no_puede_entrar(client):
    crear_usuario(activo=False)
    assert iniciar_sesion(client).status_code == 401
    assert client.get("/").status_code == 302


def test_sesion_de_usuario_desactivado_se_rechaza(client):
    usuario_id = crear_usuario()
    iniciar_sesion(client)
    assert client.get("/api/estadisticas").status_code == 200
    consultar("UPDATE usuarios SET activo = FALSE WHERE id = %s RETURNING id", (usuario_id,))
    assert client.get("/api/estadisticas").status_code == 401


def test_next_seguro_redirige_dentro_de_la_app(client):
    crear_usuario()
    respuesta = iniciar_sesion(client, next="/mapa?search=x")
    assert respuesta.headers["Location"] == "/mapa?search=x"


def test_next_externo_rechazado(client):
    crear_usuario()
    for malicioso in ("https://evil.example/", "//evil.example/", "/\\evil.example", "javascript:alert(1)"):
        cliente = client.application.test_client()
        respuesta = iniciar_sesion(cliente, next=malicioso)
        assert respuesta.status_code == 302
        assert respuesta.headers["Location"] == "/", malicioso


def test_siguiente_seguro_unitario():
    assert siguiente_seguro("/detalle/1") == "/detalle/1"
    assert siguiente_seguro("//evil.example") is None
    assert siguiente_seguro("http://evil.example") is None
    assert siguiente_seguro("/\\evil.example") is None
    assert siguiente_seguro("/ok\r\nSet-Cookie: x") is None
    assert siguiente_seguro("relativo") is None
    assert siguiente_seguro(None) is None


def test_post_sin_csrf_devuelve_400(client):
    crear_usuario()
    iniciar_sesion(client)
    respuesta = client.post("/api/toggle_entregado/1")
    assert respuesta.status_code == 400
    assert respuesta.is_json
    assert consultar("SELECT entregado FROM bienes WHERE id = 1")[0][0] == 0

    token = token_csrf(client, "/")
    respuesta = client.post("/api/toggle_entregado/1", headers={"X-CSRFToken": token})
    assert respuesta.status_code == 200
    assert consultar("SELECT entregado FROM bienes WHERE id = 1")[0][0] == 1


def test_login_sin_csrf_devuelve_400(client):
    crear_usuario()
    respuesta = client.post("/login", data={"email": "usuario@uex.es", "password": PASSWORD})
    assert respuesta.status_code == 400


def test_logout_exige_post_con_csrf(client):
    crear_usuario()
    iniciar_sesion(client)
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 400
    token = token_csrf(client, "/")
    respuesta = client.post("/logout", data={"csrf_token": token})
    assert respuesta.status_code == 302
    assert client.get("/api/estadisticas").status_code == 401


def test_cambiar_password(client):
    crear_usuario()
    iniciar_sesion(client)
    token = token_csrf(client, "/cuenta/password")
    nueva = "nueva-contraseña-456"

    corta = client.post("/cuenta/password", data={
        "csrf_token": token, "password_actual": PASSWORD,
        "password_nueva": "corta", "password_confirmacion": "corta",
    })
    assert corta.status_code == 400
    mala_actual = client.post("/cuenta/password", data={
        "csrf_token": token, "password_actual": "no-es-la-actual",
        "password_nueva": nueva, "password_confirmacion": nueva,
    })
    assert mala_actual.status_code == 400
    distinta = client.post("/cuenta/password", data={
        "csrf_token": token, "password_actual": PASSWORD,
        "password_nueva": nueva, "password_confirmacion": nueva + "x",
    })
    assert distinta.status_code == 400

    correcta = client.post("/cuenta/password", data={
        "csrf_token": token, "password_actual": PASSWORD,
        "password_nueva": nueva, "password_confirmacion": nueva,
    })
    assert correcta.status_code == 302
    # La sesión actual sigue siendo válida tras el cambio
    assert client.get("/api/estadisticas").status_code == 200

    otro = client.application.test_client()
    assert iniciar_sesion(otro).status_code == 401
    assert iniciar_sesion(otro, password=nueva).status_code == 302


def test_documento_guarda_autor_y_creado_por_del_servidor(client):
    usuario_id = crear_usuario(nombre="Ana Autora")
    iniciar_sesion(client)
    token = token_csrf(client, "/")
    respuesta = client.post(
        "/api/documento",
        json={"bien_id": 1, "tipo": "Informe", "titulo": "Informe inicial",
              "enlace": "https://ejemplo.es/doc.pdf", "autor": "Suplantador"},
        headers={"X-CSRFToken": token},
    )
    assert respuesta.status_code == 200
    autor, creado_por = consultar("SELECT autor, creado_por FROM documentos")[0]
    assert autor == "Ana Autora"
    assert creado_por == usuario_id


def test_configuracion_cookie_de_sesion(flask_app):
    assert flask_app.config["SESSION_COOKIE_NAME"] == "digibic_session"
    assert flask_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert flask_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_cookie_segura_por_defecto(monkeypatch):
    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    assert leer_bool_entorno("SESSION_COOKIE_SECURE", True) is True
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "0")
    assert leer_bool_entorno("SESSION_COOKIE_SECURE", True) is False


def test_arranque_sin_secret_key_falla():
    entorno = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    resultado = subprocess.run(
        [sys.executable, "-c", "import app"], cwd=RAIZ, env=entorno,
        capture_output=True, text=True,
    )
    assert resultado.returncode != 0
    assert "SECRET_KEY" in resultado.stderr


def test_configuracion_con_prefijo_en_proceso_nuevo():
    entorno = dict(os.environ, URL_PREFIX="/digibic", SESSION_COOKIE_SECURE="")
    resultado = subprocess.run(
        [sys.executable, "-c",
         "import app; c = app.app.config; "
         "print(c['SESSION_COOKIE_PATH'], c['SESSION_COOKIE_SECURE'], type(app.create_app()).__name__)"],
        cwd=RAIZ, env=entorno, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.split() == ["/digibic", "True", "DispatcherMiddleware"]


def test_login_bajo_prefijo_url(flask_app, monkeypatch):
    import app as modulo_app

    crear_usuario()
    monkeypatch.setattr(modulo_app, "URL_PREFIX", "/digibic")
    monkeypatch.setitem(flask_app.config, "SESSION_COOKIE_PATH", "/digibic")
    monkeypatch.setitem(flask_app.config, "APPLICATION_ROOT", "/digibic")
    cliente = Client(DispatcherMiddleware(NotFound(), {"/digibic": flask_app}))

    respuesta = cliente.get("/digibic/detalle/1")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/digibic/login?next=/detalle/1"

    pagina = cliente.get("/digibic/login")
    assert pagina.status_code == 200
    assert "Path=/digibic" in pagina.headers["Set-Cookie"]
    assert 'action="/digibic/login"' in pagina.get_data(as_text=True)
    token = token_csrf(cliente, "/digibic/login")

    respuesta = cliente.post("/digibic/login", data={
        "email": "usuario@uex.es", "password": PASSWORD, "csrf_token": token, "next": "/detalle/1",
    })
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/digibic/detalle/1"
    assert "Path=/digibic" in respuesta.headers["Set-Cookie"]
    assert cliente.get("/digibic/api/estadisticas").status_code == 200


def test_paginas_se_renderizan_con_sesion(client):
    usuario_id = crear_usuario(es_admin=True)
    iniciar_sesion(client)
    for ruta in ("/", "/?vista=tabla", "/detalle/1", "/mapa", "/planificacion", "/agenda",
                 "/bitacora", "/cuenta/password", "/admin/usuarios", "/admin/usuarios/nuevo",
                 f"/admin/usuarios/{usuario_id}/editar", "/api/coordenadas", "/api/eventos",
                 "/api/documentos/1", "/api/tipos_documento"):
        respuesta = client.get(ruta)
        assert respuesta.status_code == 200, ruta
    detalle = client.get("/detalle/1").get_data(as_text=True)
    assert 'name="csrf-token"' in detalle
    assert 'id="doc-autor"' not in detalle
