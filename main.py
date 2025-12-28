from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pymysql
import os
import re

app = FastAPI()

CONTROL_DB = {
    "host": os.getenv("CONTROL_DB_HOST"),
    "user": os.getenv("CONTROL_DB_USER"),
    "password": os.getenv("CONTROL_DB_PASSWORD"),
    "database": os.getenv("CONTROL_DB_NAME"),
}

class QueryRequest(BaseModel):
    client_id: str
    sql: str

FORBIDDEN = re.compile(r"(insert|update|delete|drop|alter|truncate|grant|revoke|;)", re.IGNORECASE)

def get_control_connection():
    return pymysql.connect(**CONTROL_DB, cursorclass=pymysql.cursors.DictCursor)

def validate_sql(sql: str):
    if FORBIDDEN.search(sql):
        raise HTTPException(status_code=400, detail="SQL no permitido")

def get_client_config(client_id: str):
    with get_control_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM clients
                WHERE client_id = %s AND active = 1
            """, (client_id,))
            client = cur.fetchone()

    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado o inactivo")

    # ==============================
    # NORMALIZACIÓN DE SCHEMA
    # ==============================

    raw_tables = client.get("allowed_tables")
    raw_columns = client.get("allowed_columns")

    try:
        allowed_tables = (
            json.loads(raw_tables)
            if isinstance(raw_tables, str)
            else raw_tables
        ) or []

        allowed_columns = (
            json.loads(raw_columns)
            if isinstance(raw_columns, str)
            else raw_columns
        ) or {}

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="allowed_tables / allowed_columns inválidos"
        )

    if not allowed_tables:
        raise HTTPException(
            status_code=400,
            detail="Cliente sin schema permitido configurado"
        )

    # Inyectamos schema ya limpio
    client["allowed_tables"] = allowed_tables
    client["allowed_columns"] = allowed_columns

    return client


def execute_client_query(client, sql):
    conn = pymysql.connect(
        host=client["db_host"],
        user=client["db_user"],
        password=client["db_password"],
        database=client["db_name"],
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = list(rows[0].keys()) if rows else []
    return columns, rows

def safe_json(value, default):
    try:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)
    except Exception:
        return default

@app.post("/query")
def query_db(req: QueryRequest):
    validate_sql(req.sql)
    client = get_client_config(req.client_id)
    columns, rows = execute_client_query(client, req.sql)
    return {"columns": columns, "rows": rows, "row_count": len(rows)}

import json

class SchemaResponse(BaseModel):
    client_id: str
    tables: list
    columns: dict

@app.post("/schema")
def get_schema(client_id: str):
    client = get_client_config(client_id)

    try:
        tables = json.loads(client["allowed_tables"] or "[]")
        columns = json.loads(client["allowed_columns"] or "{}")
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="allowed_tables / allowed_columns inválidos"
        )

    return {
        "client_id": client_id,
        "tables": tables,
        "columns": columns
    }


