"""Fixtures de pruebas. Requieren un PostgreSQL real indicado en TEST_DATABASE_URL."""
import os
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:test@127.0.0.1:55433/test"
)
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas")
os.environ["SESSION_COOKIE_SECURE"] = "0"
os.environ.pop("URL_PREFIX", None)

import psycopg2  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

import esquema  # noqa: E402
from db import get_db_connection  # noqa: E402

PASSWORD = "contraseña-segura-123"
PATRON_CSRF = re.compile(r'name="csrf-token" content="([^"]+)"')


def _crear_tablas_base(cur):
    cur.execute("DROP TABLE IF EXISTS documentos, bienes, usuarios CASCADE")
    cur.execute("""
        CREATE TABLE bienes (
            id SERIAL PRIMARY KEY, codigo_bic TEXT, id_regage TEXT, municipio TEXT,
            provincia TEXT, bien TEXT, direccion_lugar TEXT, x TEXT, y TEXT,
            lat DOUBLE PRECISION, lon DOUBLE PRECISION, categoria TEXT,
            fecha_declaracion TEXT, fecha_diario TEXT, fecha_boletin TEXT, hay_datos TEXT,
            entregado INTEGER DEFAULT 0, tiene_datos INTEGER DEFAULT 0,
            planificado INTEGER DEFAULT 0, fecha_inicio_toma TEXT, fecha_fin_toma TEXT,
            fecha_inicio_proceso TEXT, fecha_fin_proceso TEXT, udes INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE documentos (
            id SERIAL PRIMARY KEY, bien_id INTEGER NOT NULL REFERENCES bienes(id),
            tipo TEXT NOT NULL, titulo TEXT NOT NULL, enlace TEXT NOT NULL,
            comentario TEXT, autor TEXT, fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sustituido_por INTEGER REFERENCES documentos(id)
        )
    """)


@pytest.fixture(scope="session", autouse=True)
def esquema_bd():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn, conn.cursor() as cur:
            _crear_tablas_base(cur)
    finally:
        conn.close()
    # Dos ejecuciones para comprobar que es idempotente
    esquema.asegurar_esquema()
    esquema.asegurar_esquema()
    yield


@pytest.fixture(autouse=True)
def datos_limpios(esquema_bd):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("TRUNCATE documentos, bienes, usuarios RESTART IDENTITY CASCADE")
            cur.execute(
                "INSERT INTO bienes (bien, municipio, provincia) VALUES "
                "('Catedral de prueba', 'Cáceres', 'Cáceres')"
            )
    finally:
        conn.close()
    yield


@pytest.fixture
def flask_app():
    import app as modulo_app

    modulo_app.app.config.update(TESTING=True)
    return modulo_app.app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


def crear_usuario(email="usuario@uex.es", nombre="Usuario Prueba", organizacion="UEx",
                  es_admin=False, activo=True, password=PASSWORD):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuarios (email, nombre, organizacion, password_hash, es_admin, activo)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (email, nombre, organizacion, generate_password_hash(password), es_admin, activo),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def consultar(sql, params=()):
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def token_csrf(client, ruta="/login"):
    respuesta = client.get(ruta)
    coincidencia = PATRON_CSRF.search(respuesta.get_data(as_text=True))
    assert coincidencia, f"No se encontró token CSRF en {ruta}"
    return coincidencia.group(1)


def iniciar_sesion(client, email="usuario@uex.es", password=PASSWORD, **extra):
    token = token_csrf(client)
    datos = {"email": email, "password": password, "csrf_token": token}
    datos.update(extra)
    return client.post("/login", data=datos)
