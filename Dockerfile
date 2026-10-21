FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM golang:1.27-bookworm AS yatori
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
COPY third_party/ /build/third_party/
COPY engine/ ./engine/
COPY scripts/ ./scripts/
RUN python3 scripts/build_original_console.py --host && python3 scripts/collect_go_licenses.py --original

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app DATA_DIR=/data COOKIE_SECURE=true
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 console \
    && useradd --uid 10001 --gid console --no-create-home console \
    && mkdir /data && chown console:console /data
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY LICENSE THIRD_PARTY_NOTICES.md UPSTREAM.md ./
COPY third_party/yatori-go-core/LICENSE ./licenses/yatori-LICENSE
COPY third_party/yatori-go-console/LICENSE ./licenses/yatori-console-LICENSE
COPY engine/licenses/ ./licenses/go/
COPY android/licenses/pyyaml-MIT.txt ./licenses/pyyaml-MIT.txt
COPY android/licenses/libyaml-MIT.txt ./licenses/libyaml-MIT.txt
COPY --from=yatori /build/bin/yatori-console ./bin/yatori-console
COPY --from=yatori /build/engine/licenses/ORIGINAL_CONSOLE_LICENSES.txt ./licenses/go/
COPY --from=frontend /build/dist ./frontend/dist/
USER console
VOLUME ["/data"]
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
