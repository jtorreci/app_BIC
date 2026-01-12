from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from pathlib import Path

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
