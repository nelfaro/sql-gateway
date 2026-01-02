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

def validate_sql_basic(sql: str):
    sql_clean = sql.strip().lower()

    if not sql_clean.startswith("select"):
        raise HTTPException(status_code=403, detail="Only SELECT queries are allowed")

    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate"]
    if any(word in sql_clean for word in forbidden):
        raise HTTPException(status_code=403, detail="Forbidden SQL operation")

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

def validate_permissions(sql: str):
    tables = extract_tables(sql)
    columns = extract_columns(sql)

    for table in tables:
        if table not in ALLOWED_TABLES:
            raise HTTPException(
                status_code=403,
                detail=f"Table '{table}' is not allowed"
            )

    for col in columns:
        allowed = False
        for table, cols in ALLOWED_COLUMNS.items():
            if col in cols:
                allowed = True
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Column '{col}' is not allowed"
            )

# =========================
# ENDPOINT
# =========================

@app.post("/query")
def query_db(req: QueryRequest):
    validate_sql_basic(req.sql)
    validate_permissions(req.sql)

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(req.sql)
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
