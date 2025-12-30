from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pymysql
import json
import re
import os

app = FastAPI(title="SQL Gateway MVP")

# =========================
# Configuración CONTROL DB
# =========================

CONTROL_DB_HOST = os.getenv("CONTROL_DB_HOST", "mysql-control")
CONTROL_DB_PORT = int(os.getenv("CONTROL_DB_PORT", 3306))
CONTROL_DB_USER = os.getenv("CONTROL_DB_USER", "control_user")
CONTROL_DB_PASSWORD = os.getenv("CONTROL_DB_PASSWORD", "root")
CONTROL_DB_NAME = os.getenv("CONTROL_DB_NAME", "control_db")


# =========================
# Models
# =========================

class QueryRequest(BaseModel):
    client_id: str
    sql: str


# =========================
# Helpers DB
# =========================

def get_control_connection():
    return pymysql.connect(
        host=CONTROL_DB_HOST,
        port=CONTROL_DB_PORT,
        user=CONTROL_DB_USER,
        password=CONTROL_DB_PASSWORD,
        database=CONTROL_DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        ssl_disabled=True,
    )


def get_client_config(client_id: str) -> dict:
    with get_control_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM clients
                WHERE client_id = %s AND active = 1
                """,
                (client_id,),
            )
            client = cur.fetchone()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found or inactive")

    return client


# =========================
# Seguridad SQL
# =========================

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|replace)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str):
    if FORBIDDEN_SQL.search(sql):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed",
        )


def parse_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def validate_sql_permissions(sql: str, allowed_tables: list, allowed_columns: dict):
    tables_in_sql = re.findall(r"from\s+([a-zA-Z0-9_]+)", sql, re.IGNORECASE)

    for table in tables_in_sql:
        if table not in allowed_tables:
            raise HTTPException(
                status_code=403,
                detail=f"Table '{table}' is not allowed",
            )

    columns_in_sql = re.findall(r"select\s+(.*?)\s+from", sql, re.IGNORECASE)
    if not columns_in_sql:
        return

    raw_cols = columns_in_sql[0]
    if raw_cols.strip() == "*":
        return

    cols = [c.strip().split(" ")[0] for c in raw_cols.split(",")]

    for col in cols:
        allowed = any(col in allowed_columns.get(t, []) for t in allowed_tables)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Column '{col}' is not allowed",
            )


# =========================
# Ejecutar query cliente
# =========================

def execute_client_query(client: dict, sql: str):
    conn = pymysql.connect(
        host=client["db_host"],
        port=client.get("db_port", 3306),
        user=client["db_user"],
        password=client["db_password"],
        database=client["db_name"],
        cursorclass=pymysql.cursors.DictCursor,
        ssl_disabled=True,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            columns = list(rows[0].keys()) if rows else []
            return columns, rows
    finally:
        conn.close()


# =========================
# Endpoint principal
# =========================

@app.post("/query")
def query_db(req: QueryRequest):
    # 1. Validar SQL básica
    validate_sql(req.sql)

    # 2. Obtener config cliente
    client = get_client_config(req.client_id)

    # 3. Parse permisos
    allowed_tables = parse_json_field(client.get("allowed_tables"), [])
    allowed_columns = parse_json_field(client.get("allowed_columns"), {})

    if not isinstance(allowed_tables, list) or not isinstance(allowed_columns, dict):
        raise HTTPException(
            status_code=500,
            detail="Invalid permissions configuration",
        )

    # 4. Validar permisos
    validate_sql_permissions(req.sql, allowed_tables, allowed_columns)

    # 5. Ejecutar query
    columns, rows = execute_client_query(client, req.sql)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }


# =========================
# Healthcheck
# =========================

@app.get("/health")
def health():
    return {"status": "ok"}















