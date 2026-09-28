FROM python:3.11-slim

WORKDIR /app

COPY webhmi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# dnp3lib.py vive en dnp3/common/ (compartido con los servicios DNP3);
# el contexto de build de este servicio es la raiz del repo para poder
# copiarlo desde aqui sin duplicar el archivo.
COPY dnp3/common/dnp3lib.py .
COPY webhmi/app.py .
COPY webhmi/templates/ templates/

EXPOSE 8080

CMD ["python", "-u", "app.py"]
