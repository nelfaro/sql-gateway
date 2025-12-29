FROM python:3.11-slim

# 1. Dependencias del sistema (CLAVE)
RUN apt-get update && apt-get install -y \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Directorio de trabajo
WORKDIR /app

# 3. Copiar requirements primero (mejor cache)
COPY requirements.txt .

# 4. Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar código
COPY . .

# 6. Exponer puerto
EXPOSE 8000

# 7. Arranque
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
