FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements-gnn.txt /app/
ARG INSTALL_GNN=0
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_GNN" = "1" ]; then pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements-gnn.txt; fi \
    && useradd -r -u 10001 appuser && mkdir -p /data/uploads && chown -R appuser:appuser /data
COPY backend/ /app/
USER appuser
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
