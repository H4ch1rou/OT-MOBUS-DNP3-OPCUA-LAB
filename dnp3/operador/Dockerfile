FROM python:3.11-slim

WORKDIR /app

COPY common/dnp3lib.py .
COPY operador/operador.py .

CMD ["python", "-u", "operador.py"]
