import csv
import sqlite3
from pathlib import Path

csv_file = Path(__file__).parent / "Bienes_Interes_Cultural.csv"
db_file = Path(__file__).parent / "bienes.db"

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

    for row_num, row in enumerate(reader, start=1):
        if row_num == 1:
            continue

        codigo_bic = row.get("CÓDIGO BIC", "").strip()
        id_regage = row.get("ID_REGAGE", "").strip()
        municipio = row.get("MUNICIPIO", "").strip()
        provincia = row.get("PROVINCIA", "").strip()
        bien = row.get("BIEN", "").strip()
        direccion_lugar = row.get("DIRECCIÓN/LUGAR", "").strip()
        x = row.get("X", "").strip()
        y = row.get("Y", "").strip()
        categoria = row.get("CATEGORÍA", "").strip()
        fecha_declaracion = row.get("FECHA DECLARACIÓN", "").strip()
        fecha_diario = row.get("FECHA DIARIO", "").strip()
        fecha_boletin = row.get("FECHA BOLETÍN", "").strip()
        hay_datos = row.get("HAY DATOS", "").strip()
        entregado_value = row.get("ENTREGADO", "").strip()

        entregado = 1 if entregado_value and entregado_value not in ["", "0"] else 0
        tiene_datos = 1 if hay_datos and hay_datos not in ["", "0"] else 0

        cursor.execute(
            """
            INSERT INTO bienes 
            (codigo_bic, id_regage, municipio, provincia, bien, direccion_lugar, x, y, 
             categoria, fecha_declaracion, fecha_diario, fecha_boletin, hay_datos, 
             entregado, tiene_datos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                codigo_bic,
                id_regage,
                municipio,
                provincia,
                bien,
                direccion_lugar,
                x,
                y,
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
print(f"Base de datos creada: {db_file}")
print(
    f"Registros importados: {cursor.execute('SELECT COUNT(*) FROM bienes').fetchone()[0]}"
)

conn.close()
