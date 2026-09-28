FROM python:3.11-slim

WORKDIR /app

COPY common/dnp3lib.py .
COPY master/master.py .

CMD ["python", "-u", "master.py"]
