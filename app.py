import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from flask_login import current_user

from auth import init_auth
from db import get_db_connection
from usuarios import crear_admin, usuarios_bp

URL_PREFIX = os.environ.get("URL_PREFIX", "")  # Ej: "/DIGIBIC" para jtorrecilla.es/DIGIBIC

app = Flask(__name__)

NAS_FILES_PATH = os.environ.get("NAS_FILES_PATH", "/data/BIC")


@app.template_filter("fecha_corta")
def fecha_corta(value):
    """Convierte datetime o string a formato YYYY-MM-DD."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


# Tipos de documentos predefinidos (fácil de ampliar)
TIPOS_DOCUMENTO = [
    "Informe",
    "Modelo 3D",
    "Ortofoto",
    "Nube de puntos",
    "Plano",
    "Fotografias",
    "Video",
    "Ficha tecnica",
    "Memoria",
    "Otro",
]


# Autenticación: todas las rutas exigen sesión salvo el login y los estáticos
init_auth(app, URL_PREFIX)
app.register_blueprint(usuarios_bp)
app.cli.add_command(crear_admin)


@app.context_processor
def inject_prefix():
    return dict(prefix=URL_PREFIX)


@app.route("/archivos/<path:filepath>")
def servir_archivo(filepath):
    """Sirve archivos del NAS montado en /data/BIC."""
    base = Path(NAS_FILES_PATH).resolve()
    full = (base / filepath).resolve()
    # Prevenir path traversal
    if not str(full).startswith(str(base)):
        abort(403)
    if not full.is_file():
        abort(404)
    return send_from_directory(str(full.parent), full.name)


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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = "SELECT * FROM bienes WHERE 1=1"
    params = []

    if search:
        query += " AND (bien ILIKE %s OR municipio ILIKE %s OR provincia ILIKE %s)"
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

    cur.execute(f"SELECT COUNT(*) as count FROM ({query}) sub", params)
    total = cur.fetchone()["count"]

    query += " ORDER BY bien LIMIT %s OFFSET %s"
    params.extend([per_page, (page - 1) * per_page])

    cur.execute(query, params)
    bienes = cur.fetchall()
    cur.close()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM bienes WHERE id = %s", (id,))
    bien = cur.fetchone()
    # Obtener documentos con info del documento que los sustituye
    cur.execute("""
        SELECT d.*,
               s.titulo as sustituido_por_titulo,
               s.id as sustituido_por_id
        FROM documentos d
        LEFT JOIN documentos s ON d.sustituido_por = s.id
        WHERE d.bien_id = %s
        ORDER BY d.fecha_creacion DESC
    """, (id,))
    documentos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "detalle.html",
        bien=bien,
        documentos=documentos,
        tipos_documento=TIPOS_DOCUMENTO
    )


@app.route("/api/toggle_entregado/<int:id>", methods=["POST"])
def toggle_entregado(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT entregado FROM bienes WHERE id = %s", (id,))
    bien = cur.fetchone()
    nuevo_valor = 0 if bien["entregado"] else 1
    cur.execute("UPDATE bienes SET entregado = %s WHERE id = %s", (nuevo_valor, id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "entregado": nuevo_valor})


@app.route("/api/toggle_datos/<int:id>", methods=["POST"])
def toggle_datos(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT tiene_datos FROM bienes WHERE id = %s", (id,))
    bien = cur.fetchone()
    nuevo_valor = 0 if bien["tiene_datos"] else 1
    cur.execute("UPDATE bienes SET tiene_datos = %s WHERE id = %s", (nuevo_valor, id))
    conn.commit()
    cur.close()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT b.id, b.bien, b.municipio, b.provincia, b.lat, b.lon,
               (SELECT COUNT(*) FROM documentos d WHERE d.bien_id = b.id) as num_docs
        FROM bienes b
        WHERE b.lat IS NOT NULL AND b.lon IS NOT NULL
    """
    params = []

    if search:
        query += " AND (b.bien ILIKE %s OR b.municipio ILIKE %s OR b.provincia ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if filter_entregado == "1":
        query += " AND b.entregado = 1"
    elif filter_entregado == "0":
        query += " AND b.entregado = 0"

    if filter_datos == "1":
        query += " AND b.tiene_datos = 1"
    elif filter_datos == "0":
        query += " AND b.tiene_datos = 0"

    cur.execute(query, params)
    bienes = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {
            "id": b["id"],
            "bien": b["bien"],
            "municipio": b["municipio"],
            "provincia": b["provincia"],
            "lat": b["lat"],
            "lon": b["lon"],
            "num_docs": b["num_docs"],
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = "SELECT * FROM bienes WHERE 1=1"
    params = []

    if search:
        query += " AND (bien ILIKE %s OR municipio ILIKE %s OR provincia ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if filter_planificado == "1":
        query += " AND planificado = 1"
    elif filter_planificado == "0":
        query += " AND planificado = 0"

    cur.execute(f"SELECT COUNT(*) as count FROM ({query}) sub", params)
    total = cur.fetchone()["count"]

    query += " ORDER BY planificado DESC, fecha_inicio_toma ASC, bien LIMIT %s OFFSET %s"
    params.extend([per_page, (page - 1) * per_page])

    cur.execute(query, params)
    bienes = cur.fetchall()
    cur.close()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT planificado FROM bienes WHERE id = %s", (id,))
    bien = cur.fetchone()
    nuevo_valor = 0 if bien["planificado"] else 1
    if nuevo_valor == 0:
        cur.execute("""
            UPDATE bienes SET planificado = 0, fecha_inicio_toma = NULL,
            fecha_fin_toma = NULL, fecha_inicio_proceso = NULL,
            fecha_fin_proceso = NULL, udes = 0 WHERE id = %s
        """, (id,))
    else:
        cur.execute("UPDATE bienes SET planificado = %s WHERE id = %s", (nuevo_valor, id))
    conn.commit()
    cur.close()
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
    cur = conn.cursor()
    cur.execute("""
        UPDATE bienes SET
            planificado = 1,
            fecha_inicio_toma = %s,
            fecha_fin_toma = %s,
            fecha_inicio_proceso = %s,
            fecha_fin_proceso = %s,
            udes = %s
        WHERE id = %s
    """, (fecha_inicio_toma, fecha_fin_toma, fecha_inicio_proceso, fecha_fin_proceso, udes, id))
    conn.commit()
    cur.close()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT id, bien, municipio, fecha_inicio_toma, fecha_fin_toma,
               fecha_inicio_proceso, fecha_fin_proceso, udes
        FROM bienes
        WHERE planificado = 1
    """

    cur.execute(query)
    bienes = cur.fetchall()
    cur.close()
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


@app.route("/api/documentos/<int:bien_id>")
def api_documentos(bien_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM documentos WHERE bien_id = %s ORDER BY fecha_creacion DESC",
        (bien_id,)
    )
    documentos = cur.fetchall()
    cur.close()
    conn.close()
    # Serializar fecha_creacion a string si es datetime
    result = []
    for d in documentos:
        row = dict(d)
        if isinstance(row.get("fecha_creacion"), datetime):
            row["fecha_creacion"] = row["fecha_creacion"].isoformat()
        result.append(row)
    return jsonify(result)


@app.route("/api/documento", methods=["POST"])
def api_crear_documento():
    data = request.get_json()
    bien_id = data.get("bien_id")
    tipo = data.get("tipo")
    titulo = data.get("titulo")
    enlace = data.get("enlace")
    comentario = data.get("comentario", "")
    # El autor se toma de la sesión; se ignora cualquier valor enviado por el cliente
    autor = current_user.nombre

    if not all([bien_id, tipo, titulo, enlace]):
        return jsonify({"success": False, "error": "Faltan campos obligatorios"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documentos (bien_id, tipo, titulo, enlace, comentario, autor, creado_por)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (bien_id, tipo, titulo, enlace, comentario, autor, current_user.id)
    )
    documento_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "id": documento_id})


@app.route("/api/documento/<int:id>", methods=["DELETE"])
def api_eliminar_documento(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM documentos WHERE id = %s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/tipos_documento")
def api_tipos_documento():
    return jsonify(TIPOS_DOCUMENTO)


@app.route("/api/documento/<int:id>/sustituir", methods=["POST"])
def api_sustituir_documento(id):
    data = request.get_json()
    sustituido_por = data.get("sustituido_por")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE documentos SET sustituido_por = %s WHERE id = %s",
        (sustituido_por, id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True})


@app.route("/bitacora")
def bitacora():
    periodo = request.args.get("periodo", "mes")
    fecha_desde = request.args.get("desde", "")
    fecha_hasta = request.args.get("hasta", "")
    mostrar_sustituidos = request.args.get("sustituidos", "0")

    # Calcular fechas por defecto segun el periodo
    hoy = datetime.now()
    if not fecha_desde or not fecha_hasta:
        if periodo == "semana":
            inicio = hoy - timedelta(days=hoy.weekday())
            fin = inicio + timedelta(days=6)
        elif periodo == "mes":
            inicio = hoy.replace(day=1)
            if hoy.month == 12:
                fin = hoy.replace(year=hoy.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                fin = hoy.replace(month=hoy.month + 1, day=1) - timedelta(days=1)
        else:  # todo
            inicio = hoy.replace(month=1, day=1)
            fin = hoy
        fecha_desde = inicio.strftime("%Y-%m-%d")
        fecha_hasta = fin.strftime("%Y-%m-%d")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT d.*, b.bien, b.municipio, b.provincia,
               s.titulo as sustituido_por_titulo
        FROM documentos d
        JOIN bienes b ON d.bien_id = b.id
        LEFT JOIN documentos s ON d.sustituido_por = s.id
        WHERE d.fecha_creacion::date >= %s AND d.fecha_creacion::date <= %s
    """
    params = [fecha_desde, fecha_hasta]

    if mostrar_sustituidos != "1":
        query += " AND d.sustituido_por IS NULL"

    query += " ORDER BY d.fecha_creacion DESC"

    cur.execute(query, params)
    documentos = cur.fetchall()

    # Agrupar por fecha
    docs_por_fecha = {}
    for doc in documentos:
        fc = doc["fecha_creacion"]
        if isinstance(fc, datetime):
            fecha = fc.strftime("%Y-%m-%d")
        elif fc:
            fecha = str(fc)[:10]
        else:
            fecha = "Sin fecha"
        if fecha not in docs_por_fecha:
            docs_por_fecha[fecha] = []
        docs_por_fecha[fecha].append(doc)

    # Estadisticas del periodo
    total_docs = len(documentos)
    total_activos = len([d for d in documentos if not d["sustituido_por"]])

    cur.close()
    conn.close()

    return render_template(
        "bitacora.html",
        docs_por_fecha=docs_por_fecha,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        periodo=periodo,
        mostrar_sustituidos=mostrar_sustituidos,
        total_docs=total_docs,
        total_activos=total_activos,
    )


@app.route("/api/estadisticas")
def estadisticas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*) as count FROM bienes")
    total = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) as count FROM bienes WHERE entregado = 1")
    entregados = cur.fetchone()["count"]
    cur.execute("SELECT COUNT(*) as count FROM bienes WHERE tiene_datos = 1")
    con_datos = cur.fetchone()["count"]

    cur.execute("""
        SELECT provincia, COUNT(*) as count
        FROM bienes
        WHERE provincia != ''
        GROUP BY provincia
        ORDER BY count DESC
        LIMIT 10
    """)
    por_provincia = cur.fetchall()

    cur.execute("""
        SELECT categoria, COUNT(*) as count
        FROM bienes
        WHERE categoria != ''
        GROUP BY categoria
        ORDER BY count DESC
    """)
    por_categoria = cur.fetchall()

    cur.close()
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


def create_app():
    """Aplica URL_PREFIX si está configurado (ej: /DIGIBIC)."""
    if URL_PREFIX:
        from werkzeug.middleware.dispatcher import DispatcherMiddleware
        from werkzeug.exceptions import NotFound
        app.config["APPLICATION_ROOT"] = URL_PREFIX
        return DispatcherMiddleware(NotFound(), {URL_PREFIX: app})
    return app


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
