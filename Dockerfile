# Vera — container image for the brain + web UI (Linux/server deployment).
#
# She still thinks on a LOCAL model via Ollama — point her at one with
# CTWIN_OLLAMA_HOST (e.g. http://host.docker.internal:11434, or a sibling ollama
# container). Nothing is uploaded; all her state is sealed under /data (mount a
# volume to persist it). The native voice (Kokoro) + the macOS menu-bar app are
# out of scope here — this is the headless brain + web chat.
#
#   docker build -t vera .
#   docker run -p 7878:7878 -v vera-data:/data \
#     -e CTWIN_OLLAMA_HOST=http://host.docker.internal:11434 vera
#   # then open http://127.0.0.1:7878
FROM python:3.12-slim

# Build deps for the native crypto wheel (fast ChaCha20 — the pure-Python path is
# a CPU hog) and curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install Vera + the native cryptography backend.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . cryptography

# Sealed, owner-only state lives here — mount a volume to persist across runs.
ENV VERA_HOME=/data \
    CTWIN_MEMORY_DIR=/data \
    CTWIN_VOICE_KOKORO_ONLY=1
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 7878
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7878/api/health || exit 1

# Bind 0.0.0.0 so the mapped port is reachable from the host.
ENV VERA_HOST=0.0.0.0
CMD ["python", "-m", "cognitive_twin.voice.server", "--no-open", "--port", "7878"]
