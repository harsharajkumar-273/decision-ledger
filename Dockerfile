FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[server]"
COPY data ./data
ENV DLEDGER_GRAPH=/app/data/sample/graph.json \
    DLEDGER_REPO=/app/data/sample/repo \
    PORT=8000
EXPOSE 8000
# Endpoint: web UI + API. Override the command to run the nightly sweep as a Job.
CMD ["sh", "-c", "uvicorn dledger.server:app_factory --factory --host 0.0.0.0 --port ${PORT}"]
