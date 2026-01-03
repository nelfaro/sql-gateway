from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pymysql
import re

app = FastAPI()

# =========================
# CONFIGURACIÓN DB (MVP)
# =========================
DB_CONFIG = {
    "host": "mysql-foodmart",
    "port": 3306,
    "user": "foodmart_user",
    "password": "foodmart_pass",
    "database": "foodmart",
    "ssl_disabled": True
}

# =========================
# PERMISOS MVP (HARDCODE)
# =========================
ALLOWED_TABLES = ["stores_fact"]

ALLOWED_COLUMNS = {
    "stores_fact": [
        "store_id",
        "state",
        "sales_m",
        "gross_profit"
    ]
}

# =========================
# REQUEST MODEL
# =========================
class QueryRequest(BaseModel):
    sql: str

# =========================
# VALIDACIONES SQL
# =========================
FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop",
    "alter", "truncate", "create"
]

AGG_FUNCTIONS = ["sum", "avg", "count", "min", "max"]

def validate_sql(sql: str):
    sql_lower = sql.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", sql_lower):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden keyword '{kw}' detected"
            )

def extract_aliases(sql: str) -> set:
    """
    Detecta aliases tipo:
    SUM(x) AS total
    x AS total
    """
    aliases = set()
    matches = re.findall(r'\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
    for m in matches:
        aliases.add(m.lower())
    return aliases

def extract_tables(sql: str) -> set:
    matches = re.findall(r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
    return {m.lower() for m in matches}

def extract_columns(sql: str) -> set:
    """
    Extrae columnas reales ignorando:
    - funciones
    - aliases
    - nombres de tabla
    """
    tables = extract_tables(sql)

    # elimina contenido de funciones
    sql_clean = re.sub(r'\([^)]*\)', '', sql)

    tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', sql_clean)

    blacklist = {
        "select", "from", "where", "group", "by",
        "order", "limit", "as", "and", "or"
    } | set(AGG_FUNCTIONS)

    columns = set()

    for t in tokens:
        tl = t.lower()
        if tl in blacklist:
            continue
        if tl in tables:
            continue  # 👈 CLAVE: excluye nombres de tabla
        columns.add(tl)

    return columns

def validate_sql_permissions(sql: str):
    tables = extract_tables(sql)
    aliases = extract_aliases(sql)
    columns = extract_columns(sql)

    # Validar tablas
    for table in tables:
        if table not in ALLOWED_TABLES:
            raise HTTPException(
                status_code=403,
                detail=f"Table '{table}' is not allowed"
            )

    # Validar columnas reales
    for column in columns:
        if column in aliases:
            continue  # 👈 alias SIEMPRE permitido

        allowed = False
        for table, cols in ALLOWED_COLUMNS.items():
            if column in cols:
                allowed = True
                break

        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Column '{column}' is not allowed"
            )

# =========================
# EJECUCIÓN SQL
# =========================
def execute_query(sql: str):
    conn = pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        ssl_disabled=DB_CONFIG["ssl_disabled"],
        cursorclass=pymysql.cursors.DictCursor
    )

    with conn.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = list(rows[0].keys()) if rows else []

    conn.close()
    return columns, rows

# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.post("/query")
def query_db(req: QueryRequest):
    print("SQL:", req.sql)

    validate_sql(req.sql)
    validate_sql_permissions(req.sql)

    columns, rows = execute_query(req.sql)

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows)
    }













