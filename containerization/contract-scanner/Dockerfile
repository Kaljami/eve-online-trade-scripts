FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC
WORKDIR /app

COPY containerization/contract-scanner/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY contracts_data.py contract_browser.py ./
COPY data_processing ./data_processing
COPY data_retrieval ./data_retrieval
COPY render/contract_browser ./render/contract_browser
COPY containerization/contract-scanner ./containerization/contract-scanner
RUN mkdir -p cache logs static config

CMD ["python", "containerization/contract-scanner/service.py", "run"]
