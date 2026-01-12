import csv
import sqlite3
from pathlib import Path

try:
    from pyproj import Transformer
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    print("ADVERTENCIA: pyproj no instalado. Instalar con: pip install pyproj")

csv_file = Path(__file__).parent / "Bienes_Interes_Cultural.csv"
db_file = Path(__file__).parent / "bienes.db"

# Crear transformador de UTM zona 30N (ETRS89) a WGS84
# EPSG:25830 = ETRS89 / UTM zone 30N (usado en centro-oeste de España, incluye Extremadura)
# EPSG:4326 = WGS84 (lat/lon)
if HAS_PYPROJ:
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)


def parse_utm_coordinate(value):
    """Parsea coordenada UTM que puede tener coma decimal (formato español)."""
    if not value:
        return None
    # Reemplazar coma por punto para formato decimal
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def utm_to_latlon(x, y):
    """Convierte coordenadas UTM (ETRS89 zona 29N) a lat/lon (WGS84)."""
    if not HAS_PYPROJ:
        return None, None
    if x is None or y is None:
        return None, None
    try:
        lon, lat = transformer.transform(x, y)
        # Validar que las coordenadas están en un rango razonable para España
        if 35 < lat < 44 and -10 < lon < 5:
            return lat, lon
        else:
            return None, None
    except Exception:
        return None, None


conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS bienes")

cursor.execute("""
    CREATE TABLE bienes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_bic TEXT,
        id_regage TEXT,
        municipio TEXT,
        provincia TEXT,
        bien TEXT,
        direccion_lugar TEXT,
        x TEXT,
        y TEXT,
        lat REAL,
        lon REAL,
        categoria TEXT,
        fecha_declaracion TEXT,
        fecha_diario TEXT,
        fecha_boletin TEXT,
        hay_datos TEXT,
        entregado INTEGER DEFAULT 0,
        tiene_datos INTEGER DEFAULT 0
    )
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

        # Convertir coordenadas UTM a lat/lon
        x_utm = parse_utm_coordinate(x_str)
        y_utm = parse_utm_coordinate(y_str)
        lat, lon = utm_to_latlon(x_utm, y_utm)

        if lat is not None:
            registros_con_coords += 1
        elif x_str or y_str:
            registros_sin_coords += 1

        cursor.execute(
            """
            INSERT INTO bienes
            (codigo_bic, id_regage, municipio, provincia, bien, direccion_lugar, x, y,
             lat, lon, categoria, fecha_declaracion, fecha_diario, fecha_boletin, hay_datos,
             entregado, tiene_datos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                codigo_bic,
                id_regage,
                municipio,
                provincia,
                bien,
                direccion_lugar,
                x_str,
                y_str,
                lat,
                lon,
                categoria,
                fecha_declaracion,
                fecha_diario,
                fecha_boletin,
                hay_datos,
                entregado,
                tiene_datos,
            ),
        )

conn.commit()
total = cursor.execute("SELECT COUNT(*) FROM bienes").fetchone()[0]
print(f"Base de datos creada: {db_file}")
print(f"Registros importados: {total}")
print(f"Registros con coordenadas convertidas: {registros_con_coords}")
if registros_sin_coords > 0:
    print(f"Registros con coordenadas que no se pudieron convertir: {registros_sin_coords}")

conn.close()
