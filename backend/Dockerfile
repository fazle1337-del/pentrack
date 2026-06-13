FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg/bcrypt build are covered by binary wheels;
# keep image lean.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
