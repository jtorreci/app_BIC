"""Creación idempotente del esquema de autenticación.

Se ejecuta en cada arranque del contenedor, después de la importación del CSV,
para que la tabla de usuarios nunca se vea afectada por el borrado de `bienes`.
"""
import time

import psycopg2

from db import get_db_connection


def esperar_bd(max_intentos=30, espera=2):
    for intento in range(max_intentos):
        try:
            get_db_connection().close()
            return
        except psycopg2.OperationalError:
            print(f"Esperando a PostgreSQL... ({intento + 1}/{max_intentos})")
            time.sleep(espera)
    raise RuntimeError("No se pudo conectar a PostgreSQL")


def asegurar_esquema():
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    organizacion TEXT NOT NULL CHECK (organizacion IN ('UEx', 'DGAP')),
                    password_hash TEXT NOT NULL,
                    es_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    activo BOOLEAN NOT NULL DEFAULT TRUE,
                    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
                    bloqueado_hasta TIMESTAMPTZ,
                    ultimo_acceso TIMESTAMPTZ,
                    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            # Unicidad del email sin distinguir mayúsculas y minúsculas
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_lower_key ON usuarios (lower(email))"
            )
            cur.execute("SELECT to_regclass('public.documentos') IS NOT NULL")
            if cur.fetchone()[0]:
                cur.execute(
                    "ALTER TABLE documentos ADD COLUMN IF NOT EXISTS "
                    "creado_por INTEGER REFERENCES usuarios(id)"
                )
    finally:
        conn.close()


if __name__ == "__main__":
    esperar_bd()
    asegurar_esquema()
    print("Esquema de usuarios verificado")
