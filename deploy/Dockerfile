FROM node:24-bookworm-slim AS web-build
WORKDIR /src/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv/lightning
WORKDIR /srv/lightning
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY contracts/strategy/ contracts/strategy/
COPY scripts/migrate.py scripts/migrate.py
COPY scripts/snapshot.py scripts/snapshot.py
COPY --from=web-build /src/web/dist web/dist
RUN useradd --uid 10001 --create-home lightning
USER lightning
EXPOSE 8000
CMD ["python", "-m", "backend.app.main"]
