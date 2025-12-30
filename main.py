import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class QueryRequest(BaseModel):
    sql: str

def get_connection():
    return pymysql.connect(
        host="mysql-foodmart",
        user="foodmart_user",
        password="foodmart_pass",
        database="foodmart",
        port=3306,
        cursorclass=pymysql.cursors.DictCursor
    )

@app.post("/query")
def query_db(req: QueryRequest):
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(req.sql)
            rows = cursor.fetchall()
            columns = list(rows[0].keys()) if rows else []
        conn.close()

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))















