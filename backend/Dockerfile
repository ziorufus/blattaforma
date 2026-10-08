
FROM python:3.12-slim

WORKDIR /app

# Crea un virtual environment Python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Installa le dipendenze
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
