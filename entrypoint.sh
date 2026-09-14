#!/bin/sh
set -e

echo "Comprobando si la base de datos necesita inicialización..."
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'bienes')\")
exists = cur.fetchone()[0]
if exists:
    cur.execute('SELECT COUNT(*) FROM bienes')
    count = cur.fetchone()[0]
    if count > 0:
        print(f'Base de datos ya tiene {count} registros. Saltando importación.')
    else:
        print('Tabla vacía. Importando datos...')
        conn.close()
        exit(1)
else:
    print('Tabla no existe. Importando datos...')
    conn.close()
    exit(1)
conn.close()
" || python importar_csv.py

echo "Verificando esquema de usuarios..."
python esquema.py

echo "Iniciando aplicación..."
exec gunicorn --bind 0.0.0.0:5000 --workers 3 "app:create_app()"
