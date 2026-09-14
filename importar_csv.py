import csv
import os
import time
from pathlib import Path

import psycopg2

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    print("ADVERTENCIA: pyproj no instalado. Instalar con: pip install pyproj")

csv_file = Path(__file__).parent / "Bienes_Interes_Cultural.csv"

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bic:bic_secret@localhost:5432/bienes_bic")

# Crear transformador de UTM zona 30N (ETRS89) a WGS84
if HAS_PYPROJ:
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)


def parse_utm_coordinate(value):
    """Parsea coordenada UTM que puede tener coma decimal (formato español)."""
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def utm_to_latlon(x, y):
    """Convierte coordenadas UTM (ETRS89 zona 30N) a lat/lon (WGS84)."""
    if not HAS_PYPROJ:
        return None, None
    if x is None or y is None:
        return None, None
    try:
        lon, lat = transformer.transform(x, y)
        if 35 < lat < 44 and -10 < lon < 5:
            return lat, lon
        else:
            return None, None
    except Exception:
        return None, None


def wait_for_db(max_retries=30, delay=2):
    """Espera a que PostgreSQL esté disponible."""
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.close()
            return True
        except psycopg2.OperationalError:
            print(f"Esperando a PostgreSQL... ({i + 1}/{max_retries})")
            time.sleep(delay)
    raise RuntimeError("No se pudo conectar a PostgreSQL")


def importar():
    wait_for_db()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Crear tabla de documentos si no existe (NO se borra al reimportar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documentos (
            id SERIAL PRIMARY KEY,
            bien_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            enlace TEXT NOT NULL,
            comentario TEXT,
            autor TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sustituido_por INTEGER,
            FOREIGN KEY (sustituido_por) REFERENCES documentos(id)
        )
    """)

    # Añadir columna sustituido_por si no existe (migración)
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documentos' AND column_name = 'sustituido_por'
            ) THEN
                ALTER TABLE documentos ADD COLUMN sustituido_por INTEGER;
            END IF;
        END $$;
    """)

    # Recrear tabla bienes (DROP + CREATE)
    # Primero quitar FK de documentos temporalmente
    cur.execute("DROP TABLE IF EXISTS bienes CASCADE")

    cur.execute("""
        CREATE TABLE bienes (
            id SERIAL PRIMARY KEY,
            codigo_bic TEXT,
            id_regage TEXT,
            municipio TEXT,
            provincia TEXT,
            bien TEXT,
            direccion_lugar TEXT,
            x TEXT,
            y TEXT,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            categoria TEXT,
            fecha_declaracion TEXT,
            fecha_diario TEXT,
            fecha_boletin TEXT,
            hay_datos TEXT,
            entregado INTEGER DEFAULT 0,
            tiene_datos INTEGER DEFAULT 0,
            planificado INTEGER DEFAULT 0,
            fecha_inicio_toma TEXT,
            fecha_fin_toma TEXT,
            fecha_inicio_proceso TEXT,
            fecha_fin_proceso TEXT,
            udes INTEGER DEFAULT 0
        )
    """)

    # Restaurar FK en documentos
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'documentos_bien_id_fkey'
            ) THEN
                ALTER TABLE documentos
                ADD CONSTRAINT documentos_bien_id_fkey
                FOREIGN KEY (bien_id) REFERENCES bienes(id);
            END IF;
        END $$;
    """)

    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        registros_con_coords = 0
        registros_sin_coords = 0

        for row_num, row in enumerate(reader, start=1):
            if row_num == 1:
                continue

            codigo_bic = row.get("CÓDIGO BIC", "").strip()
            id_regage = row.get("ID_REGAGE", "").strip()
            municipio = row.get("MUNICIPIO", "").strip()
            provincia = row.get("PROVINCIA", "").strip()
            bien = row.get("BIEN", "").strip()
            direccion_lugar = row.get("DIRECCIÓN/LUGAR", "").strip()
            x_str = row.get("X", "").strip()
            y_str = row.get("Y", "").strip()
            categoria = row.get("CATEGORÍA", "").strip()
            fecha_declaracion = row.get("FECHA DECLARACIÓN", "").strip()
            fecha_diario = row.get("FECHA DIARIO", "").strip()
            fecha_boletin = row.get("FECHA BOLETÍN", "").strip()
            hay_datos = row.get("HAY DATOS", "").strip()
            entregado_value = row.get("ENTREGADO", "").strip()

            entregado = 1 if entregado_value and entregado_value not in ["", "0"] else 0
            tiene_datos = 1 if hay_datos and hay_datos not in ["", "0"] else 0

            x_utm = parse_utm_coordinate(x_str)
            y_utm = parse_utm_coordinate(y_str)
            lat, lon = utm_to_latlon(x_utm, y_utm)

            if lat is not None:
                registros_con_coords += 1
            elif x_str or y_str:
                registros_sin_coords += 1

            cur.execute(
                """
                INSERT INTO bienes
                (codigo_bic, id_regage, municipio, provincia, bien, direccion_lugar, x, y,
                 lat, lon, categoria, fecha_declaracion, fecha_diario, fecha_boletin, hay_datos,
                 entregado, tiene_datos)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    codigo_bic, id_regage, municipio, provincia, bien, direccion_lugar,
                    x_str, y_str, lat, lon, categoria, fecha_declaracion, fecha_diario,
                    fecha_boletin, hay_datos, entregado, tiene_datos,
                ),
            )

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM bienes")
    total = cur.fetchone()[0]
    print(f"Base de datos PostgreSQL actualizada")
    print(f"Registros importados: {total}")
    print(f"Registros con coordenadas convertidas: {registros_con_coords}")
    if registros_sin_coords > 0:
        print(f"Registros con coordenadas que no se pudieron convertir: {registros_sin_coords}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    importar()
