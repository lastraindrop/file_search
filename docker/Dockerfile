# FileCortex Web — 轻量完整发行镜像
# 构建: docker build -f docker/Dockerfile -t filecortex:7.0.0 .
# 运行约束: 必须单 worker（ProgressTracker 为进程内存态）
FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
RUN useradd -m -u 1000 cortex
ENV FCTX_CONFIG_DIR=/data \
    PYTHONUNBUFFERED=1
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
RUN mkdir -p /data && chown cortex:cortex /data
USER cortex
WORKDIR /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
