FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl for pod lifecycle and exec operations.
RUN curl -fsSL "https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

COPY app/sandbox_provisioner /app/sandbox_provisioner

ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["uvicorn", "sandbox_provisioner.main:app", "--host", "0.0.0.0", "--port", "8002"]
