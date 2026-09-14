"""Restore manually edited data exported from the old Render deployment.

Render row ids are not stable across CSV imports, so rows are matched by
(bien, municipio). Safe to run more than once.

Usage (from the app_BIC directory on the server):
    docker compose exec -T app python scripts/restaurar_render.py < render_export_2026-09-14.json
"""
import json
import os
import sys

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    export = json.load(sys.stdin)
    entregados = export.get("entregados_detalle", [])

    if export.get("tiene_datos_ids") or export.get("planificado_ids") or export.get("documentos"):
        sys.exit("Export contains data this script does not restore (datos/planificacion/documentos).")

    conn = psycopg2.connect(DATABASE_URL)
    not_found = []
    try:
        with conn, conn.cursor() as cur:
            for item in entregados:
                cur.execute(
                    "UPDATE bienes SET entregado = 1 WHERE bien = %s AND municipio = %s",
                    (item["bien"], item["municipio"]),
                )
                if cur.rowcount != 1:
                    not_found.append((item, cur.rowcount))
            if not_found:
                raise RuntimeError(f"Unexpected matches, rolling back: {not_found}")
    finally:
        conn.close()

    print(f"Restored entregado=1 on {len(entregados)} bienes.")


if __name__ == "__main__":
    main()
