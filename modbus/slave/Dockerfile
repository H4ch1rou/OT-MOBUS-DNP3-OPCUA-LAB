FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY slave.py .

EXPOSE 502

CMD ["python", "-u", "slave.py"]
