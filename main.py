import os
import json
import re
import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SQL Agent Gateway")

# =========================
# CONFIGURACIÓN (ENV)
# =========================

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DB_SSL_DISABLED = os.getenv("DB_SSL_DISABLED", "false").lower() == "true"

ALLOWED_TABLES = json.loads(os.getenv("ALLOWED_TABLES", "[]"))
ALLOWED_COLUMNS = json.loads(os.getenv("ALLOWED_COLUMNS", "{}"))

# =========================
# MODELOS
# =========================

class QueryRequest(BaseModel):
    sql: str

# =========================
# HELPERS
# =========================

def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.Cursor,
        ssl_disabled=DB_SSL_DISABLED
    )

def validate_sql(sql: str):
    sql_clean = sql.strip().lower()

    if not sql_clean.startswith("select"):
        raise HTTPException(status_code=403, detail="Only SELECT queries are allowed")

    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate"]
    if any(word in sql_clean for word in forbidden):
        raise HTTPException(status_code=403, detail="Forbidden SQL operation")

def execute_client_query(sql: str):
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306)),
        ssl_disabled=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return columns, rows
    finally:
        conn.close()



def extract_tables(sql: str):
    return re.findall(r'from\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)

def extract_columns(sql: str):
    """
    Extrae columnas reales aunque estén dentro de funciones:
    SUM(sales_m) -> sales_m
    """
    select_part = re.split(r'from', sql, flags=re.IGNORECASE)[0]
    cols = re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)', select_part)

    ignore = {
        "select", "sum", "avg", "min", "max", "count",
        "as", "distinct"
    }

    return [c for c in cols if c.lower() not in ignore]

SQL_KEYWORDS = {
    "select", "from", "where", "group", "by", "order",
    "limit", "as", "sum", "avg", "min", "max", "count"
}

def validate_sql_permissions(sql: str, allowed_tables: list, allowed_columns: dict):
    sql_lower = sql.lower()

    # 1. Validar tablas
    tables = re.findall(r'\bfrom\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql_lower)
    tables += re.findall(r'\bjoin\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql_lower)

    for table in tables:
        if table not in allowed_tables:
            raise HTTPException(
                status_code=403,
                detail=f"Table '{table}' is not allowed"
            )

    # 2. Extraer columnas reales (incluye funciones)
    raw_columns = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', sql_lower)

    for col in raw_columns:
        if col in SQL_KEYWORDS:
            continue

        # verificar si la columna está permitida en alguna tabla
        if not any(col in cols for cols in allowed_columns.values()):
            raise HTTPException(
                status_code=403,
                detail=f"Column '{col}' is not allowed"
            )

# =========================
# ENDPOINT
# =========================

@app.post("/query")
def query_db(req: QueryRequest):

    #validate_sql(req.sql)

    print("SQL:", req.sql)

    allowed_tables = ["stores_fact"]
    allowed_columns = {
        "stores_fact": ["state", "sales_m", "gross_profit"]
    }

    validate_sql_permissions(req.sql, allowed_tables, allowed_columns)

    columns, rows = execute_client_query(req.sql)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows)
    }










