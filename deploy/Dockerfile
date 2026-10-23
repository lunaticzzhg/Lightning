FROM python:3.13-slim AS contract
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/lightning
WORKDIR /srv/lightning
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY contracts/strategy/ contracts/strategy/
COPY scripts/export_openapi.py scripts/export_openapi.py
COPY scripts/export_manifest_schema.py scripts/export_manifest_schema.py
RUN python -m scripts.export_manifest_schema --check && python -m scripts.export_openapi > /tmp/lightning-openapi.json

FROM node:24-bookworm-slim AS web-build
WORKDIR /src/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
COPY --from=contract /tmp/lightning-openapi.json /tmp/lightning-openapi.json
RUN npm run generate:api -- --schema /tmp/lightning-openapi.json && npm run build

FROM contract AS app
COPY scripts/migrate.py scripts/migrate.py
COPY scripts/snapshot.py scripts/snapshot.py
COPY --from=web-build /src/web/dist web/dist
RUN useradd --uid 10001 --create-home lightning
USER lightning
EXPOSE 8000
CMD ["python", "-m", "backend.app.main"]
