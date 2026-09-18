FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# scripts/receipts.py is imported for the price normalisation, so the two can
# never disagree about what "per kg" means.
COPY scripts/receipts.py scripts/receipts.py
COPY server/ server/

ENV PORT=8080
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
