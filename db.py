"""Acceso compartido a PostgreSQL para la aplicación y sus módulos."""
import os

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bic:bic_secret@localhost:5432/bienes_bic")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)
