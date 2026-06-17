FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mtlogin.py .
ENTRYPOINT ["python", "mtlogin.py"]
