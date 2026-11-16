# Runs the whole pipeline in a clean container:
#   docker build -t credit-gap .
#   docker run --rm -v "$PWD/data:/app/data" -v "$PWD/outputs:/app/outputs" credit-gap
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY tests/ tests/
COPY data/ data/
COPY outputs/ outputs/

CMD ["python", "src/run_all.py"]
