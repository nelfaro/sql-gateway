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

@app.post("/query")
def query_db(req: QueryRequest):
    validate_sql(req.sql)
    client = get_client_config(req.client_id)
    columns, rows = execute_client_query(client, req.sql)
    return {"columns": columns, "rows": rows, "row_count": len(rows)}
