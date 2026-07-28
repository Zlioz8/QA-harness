# The web interface. Dependencies live in here, so the host still needs only Docker.
#
# It gets the docker CLI and the compose plugin because its whole job is to run `make`, and the
# lab's make goals are docker compose invocations. It does NOT get its own analysis logic.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        make curl ca-certificates gnupg git \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "fastapi==0.115.6" "uvicorn==0.34.0" "python-multipart==0.0.20"

# NOTHING from the lab is copied in. The image is a runtime — Python, its dependencies and the
# docker CLI — and the code is read from the bind mount at $LAB_DIR/ui, exactly as tools/ is.
#
# Copying the sources in would create a failure mode with no signal: edit ui/app.py, restart the
# container, and watch the old code run because the image was never rebuilt.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "exec python \"$LAB_DIR/ui/app.py\""]
