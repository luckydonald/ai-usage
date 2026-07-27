FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/yarn.lock frontend/.yarnrc.yml ./
RUN corepack enable && yarn install --immutable
COPY frontend/ ./
RUN yarn build

FROM python:3.14-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AI_USAGE_HOME=/data
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 aiusage && mkdir /data && chown aiusage:aiusage /data
USER aiusage
EXPOSE 4458
ENTRYPOINT ["ai-usage"]
CMD ["up", "--host", "0.0.0.0", "--port", "4458"]
