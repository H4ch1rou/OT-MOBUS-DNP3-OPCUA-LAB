FROM python:3.11-slim

WORKDIR /app

# Sin dependencias externas: el codec DNP3 (common/dnp3lib.py) es Python
# puro (stdlib), sin necesidad de compilar nada.
COPY common/dnp3lib.py .
COPY outstation/outstation.py .

CMD ["python", "-u", "outstation.py"]
