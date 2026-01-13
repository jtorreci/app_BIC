from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)
db_path = Path(__file__).parent / "bienes.db"


def get_db_connection():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    vista = request.args.get("vista", "tarjetas")
    per_page = 20 if vista == "tarjetas" else 50
    search = request.args.get("search", "")
    filter_entregado = request.args.get("entregado", "")
    filter_datos = request.args.get("datos", "")
    filter_planificado = request.args.get("planificado", "")

    conn = get_db_connection()

    query = "SELECT * FROM bienes WHERE 1=1"
    params = []

    if search:
        query += " AND (bien LIKE ? OR municipio LIKE ? OR provincia LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if filter_entregado == "1":
        query += " AND entregado = 1"
    elif filter_entregado == "0":
        query += " AND entregado = 0"

    if filter_datos == "1":
        query += " AND tiene_datos = 1"
    elif filter_datos == "0":
        query += " AND tiene_datos = 0"

    if filter_planificado == "1":
        query += " AND planificado = 1"
    elif filter_planificado == "0":
        query += " AND planificado = 0"

    total = conn.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]

    query += " ORDER BY bien LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    bienes = conn.execute(query, params).fetchall()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "index.html",
        bienes=bienes,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        filter_entregado=filter_entregado,
        filter_datos=filter_datos,
        filter_planificado=filter_planificado,
        vista=vista,
        per_page=per_page,
    )


@app.route("/detalle/<int:id>")
def detalle(id):
    conn = get_db_connection()
    bien = conn.execute("SELECT * FROM bienes WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template("detalle.html", bien=bien)


@app.route("/api/toggle_entregado/<int:id>", methods=["POST"])
def toggle_entregado(id):
    conn = get_db_connection()
    bien = conn.execute("SELECT entregado FROM bienes WHERE id = ?", (id,)).fetchone()
    nuevo_valor = 0 if bien["entregado"] else 1
    conn.execute("UPDATE bienes SET entregado = ? WHERE id = ?", (nuevo_valor, id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "entregado": nuevo_valor})


@app.route("/api/toggle_datos/<int:id>", methods=["POST"])
def toggle_datos(id):
    conn = get_db_connection()
    bien = conn.execute("SELECT tiene_datos FROM bienes WHERE id = ?", (id,)).fetchone()
    nuevo_valor = 0 if bien["tiene_datos"] else 1
    conn.execute("UPDATE bienes SET tiene_datos = ? WHERE id = ?", (nuevo_valor, id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "tiene_datos": nuevo_valor})


@app.route("/mapa")
def mapa():
    search = request.args.get("search", "")
    filter_entregado = request.args.get("entregado", "")
    filter_datos = request.args.get("datos", "")

    return render_template(
        "mapa.html",
        search=search,
        filter_entregado=filter_entregado,
        filter_datos=filter_datos,
    )


@app.route("/api/coordenadas")
def api_coordenadas():
    search = request.args.get("search", "")
    filter_entregado = request.args.get("entregado", "")
    filter_datos = request.args.get("datos", "")

    conn = get_db_connection()

    query = "SELECT id, bien, municipio, provincia, lat, lon FROM bienes WHERE lat IS NOT NULL AND lon IS NOT NULL"
    params = []

    if search:
        query += " AND (bien LIKE ? OR municipio LIKE ? OR provincia LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if filter_entregado == "1":
        query += " AND entregado = 1"
    elif filter_entregado == "0":
        query += " AND entregado = 0"

    if filter_datos == "1":
        query += " AND tiene_datos = 1"
    elif filter_datos == "0":
        query += " AND tiene_datos = 0"

    bienes = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([
        {
            "id": b["id"],
            "bien": b["bien"],
            "municipio": b["municipio"],
            "provincia": b["provincia"],
            "lat": b["lat"],
            "lon": b["lon"],
        }
        for b in bienes
    ])


@app.route("/planificacion")
def planificacion():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search", "")
    filter_planificado = request.args.get("planificado", "")

    conn = get_db_connection()

    query = "SELECT * FROM bienes WHERE 1=1"
    params = []

    if search:
        query += " AND (bien LIKE ? OR municipio LIKE ? OR provincia LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if filter_planificado == "1":
        query += " AND planificado = 1"
    elif filter_planificado == "0":
        query += " AND planificado = 0"

    total = conn.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]

    query += " ORDER BY planificado DESC, fecha_inicio_toma ASC, bien LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    bienes = conn.execute(query, params).fetchall()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "planificacion.html",
        bienes=bienes,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search,
        filter_planificado=filter_planificado,
    )


@app.route("/agenda")
def agenda():
    return render_template("agenda.html")


@app.route("/api/toggle_planificado/<int:id>", methods=["POST"])
def toggle_planificado(id):
    conn = get_db_connection()
    bien = conn.execute("SELECT planificado FROM bienes WHERE id = ?", (id,)).fetchone()
    nuevo_valor = 0 if bien["planificado"] else 1
    if nuevo_valor == 0:
        conn.execute("""
            UPDATE bienes SET planificado = 0, fecha_inicio_toma = NULL,
            fecha_fin_toma = NULL, fecha_inicio_proceso = NULL,
            fecha_fin_proceso = NULL, udes = 0 WHERE id = ?
        """, (id,))
    else:
        conn.execute("UPDATE bienes SET planificado = ? WHERE id = ?", (nuevo_valor, id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "planificado": nuevo_valor})


@app.route("/api/guardar_planificacion/<int:id>", methods=["POST"])
def guardar_planificacion(id):
    data = request.get_json()
    fecha_inicio_toma = data.get("fecha_inicio_toma") or None
    udes = int(data.get("udes", 0) or 0)
    fecha_inicio_proceso = data.get("fecha_inicio_proceso") or None
    fecha_fin_proceso = data.get("fecha_fin_proceso") or None

    fecha_fin_toma = None
    if fecha_inicio_toma and udes > 0:
        fecha_inicio = datetime.strptime(fecha_inicio_toma, "%Y-%m-%d")
        fecha_fin = fecha_inicio + timedelta(days=udes - 1)
        fecha_fin_toma = fecha_fin.strftime("%Y-%m-%d")

    conn = get_db_connection()
    conn.execute("""
        UPDATE bienes SET
            planificado = 1,
            fecha_inicio_toma = ?,
            fecha_fin_toma = ?,
            fecha_inicio_proceso = ?,
            fecha_fin_proceso = ?,
            udes = ?
        WHERE id = ?
    """, (fecha_inicio_toma, fecha_fin_toma, fecha_inicio_proceso, fecha_fin_proceso, udes, id))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "fecha_fin_toma": fecha_fin_toma
    })


@app.route("/api/eventos")
def api_eventos():
    fecha_inicio = request.args.get("start", "")
    fecha_fin = request.args.get("end", "")

    conn = get_db_connection()

    query = """
        SELECT id, bien, municipio, fecha_inicio_toma, fecha_fin_toma,
               fecha_inicio_proceso, fecha_fin_proceso, udes
        FROM bienes
        WHERE planificado = 1
    """
    params = []

    bienes = conn.execute(query, params).fetchall()
    conn.close()

    eventos = []
    for b in bienes:
        if b["fecha_inicio_toma"]:
            eventos.append({
                "id": f"toma_{b['id']}",
                "title": f"Toma: {b['bien'][:30]}",
                "start": b["fecha_inicio_toma"],
                "end": b["fecha_fin_toma"] if b["fecha_fin_toma"] else b["fecha_inicio_toma"],
                "color": "#0d6efd",
                "extendedProps": {
                    "tipo": "toma",
                    "bien_id": b["id"],
                    "municipio": b["municipio"],
                    "udes": b["udes"]
                }
            })
        if b["fecha_inicio_proceso"]:
            eventos.append({
                "id": f"proceso_{b['id']}",
                "title": f"Proceso: {b['bien'][:30]}",
                "start": b["fecha_inicio_proceso"],
                "end": b["fecha_fin_proceso"] if b["fecha_fin_proceso"] else b["fecha_inicio_proceso"],
                "color": "#198754",
                "extendedProps": {
                    "tipo": "proceso",
                    "bien_id": b["id"],
                    "municipio": b["municipio"]
                }
            })

    return jsonify(eventos)


@app.route("/api/estadisticas")
def estadisticas():
    conn = get_db_connection()

    total = conn.execute("SELECT COUNT(*) FROM bienes").fetchone()[0]
    entregados = conn.execute(
        "SELECT COUNT(*) FROM bienes WHERE entregado = 1"
    ).fetchone()[0]
    con_datos = conn.execute(
        "SELECT COUNT(*) FROM bienes WHERE tiene_datos = 1"
    ).fetchone()[0]

    por_provincia = conn.execute("""
        SELECT provincia, COUNT(*) as count 
        FROM bienes 
        WHERE provincia != '' 
        GROUP BY provincia 
        ORDER BY count DESC 
        LIMIT 10
    """).fetchall()

    por_categoria = conn.execute("""
        SELECT categoria, COUNT(*) as count 
        FROM bienes 
        WHERE categoria != '' 
        GROUP BY categoria 
        ORDER BY count DESC
    """).fetchall()

    conn.close()

    return jsonify(
        {
            "total": total,
            "entregados": entregados,
            "con_datos": con_datos,
            "por_provincia": [dict(p) for p in por_provincia],
            "por_categoria": [dict(c) for c in por_categoria],
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
