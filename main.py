from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import MySQLdb
import os
import re
import json

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
    return pymysql.connect(
        host=CONTROL_DB["host"],
        user=CONTROL_DB["user"],
        password=CONTROL_DB["password"],
        database=CONTROL_DB["database"],
        cursorclass=pymysql.cursors.DictCursor
    )



def validate_sql(sql: str):
    if FORBIDDEN.search(sql):
        raise HTTPException(status_code=400, detail="SQL no permitido")

def validate_sql_permissions(sql: str, allowed_tables, allowed_columns):
    sql_lower = sql.lower()

    # Validar tablas
    for table in allowed_tables:
        if table.lower() not in sql_lower:
            continue

    # Extraer columnas usadas (heurística simple)
    for table, columns in allowed_columns.items():
        for col in columns:
            if col.lower() in sql_lower:
                return

    # Si no pasó ninguna validación
    raise HTTPException(
        status_code=403,
        detail="Consulta fuera de las tablas/columnas permitidas"
    )


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

    #raw_tables = client.get("allowed_tables")
    #raw_columns = client.get("allowed_columns")

    #try:
       # allowed_tables = (
        #    json.loads(raw_tables)
        #    if isinstance(raw_tables, str)
        #    else raw_tables
       # ) or []

     #   allowed_columns = (
     #       json.loads(raw_columns)
    #        if isinstance(raw_columns, str)
     #       else raw_columns
     #   ) or {}

    #except Exception:
    #    raise HTTPException(
    #        status_code=500,
    #        detail="allowed_tables / allowed_columns inválidos"
    #    )

   # if not allowed_tables:
   #    raise HTTPException(
   #         status_code=400,
   #         detail="Cliente sin schema permitido configurado"
   #     )

    # Inyectamos schema ya limpio
  #  client["allowed_tables"] = allowed_tables
  # client["allowed_columns"] = allowed_columns

    return client


def execute_client_query(client, sql):
    conn = MySQLdb.connect(
        host=client["db_host"],
        user=client["db_user"],
        passwd=client["db_password"],
        db=client["db_name"],
        charset="utf8mb4"
    )

    cur = conn.cursor(MySQLdb.cursors.DictCursor)
    cur.execute(sql)
    rows = cur.fetchall()
    columns = list(rows[0].keys()) if rows else []

    cur.close()
    conn.close()

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
    # 1. SQL básica
    validate_sql(req.sql)

    # 2. Config cliente
    client = get_client_config(req.client_id)

    # 3. Parse seguro de permisos
   # allowed_tables = parse_json_field(client.get("allowed_tables"), [])
   # allowed_columns = parse_json_field(client.get("allowed_columns"), {})

   # if not isinstance(allowed_tables, list) or not isinstance(allowed_columns, dict):
   #    raise HTTPException(
   #         status_code=500,
   #         detail="allowed_tables / allowed_columns inválidos"
   #    )

    # 4. Validar permisos
   # validate_sql_permissions(req.sql, allowed_tables, allowed_columns)

    # 5. Ejecutar
    columns, rows = execute_client_query(client, req.sql)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows)
    }


class SchemaResponse(BaseModel):
    client_id: str
    tables: list
    columns: dict

@app.post("/schema")
def get_schema(client_id: str):
    client = get_client_config(client_id)

    def clean_json(value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value.strip())
        except Exception as e:
            print("JSON inválido:", repr(value))
            raise HTTPException(
                status_code=500,
                detail="allowed_tables / allowed_columns inválidos"
            )

    tables = clean_json(client.get("allowed_tables"), [])
    columns = clean_json(client.get("allowed_columns"), {})

    return {
        "client_id": client_id,
        "tables": tables,
        "columns": columns
    }
    
def parse_json_field(value, default):
    if value is None:
        return default

    if isinstance(value, (list, dict)):
        return value

    try:
        return json.loads(value)
    except Exception:
        return default











