# Dockerfile (corrigé : installe tesseract, poppler, rust/cargo et crée un CARGO_HOME écrivable)
FROM python:3.11-slim

# 1) Installer dépendances système (root)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    git \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    rustc \
    cargo \
    pkg-config \
    libssl-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2) Créer un utilisateur non-root
RUN useradd -m appuser
WORKDIR /home/appuser/app
RUN chown -R appuser:appuser /home/appuser

# 3) Définir dossiers Cargo/Rust écrivables dans /tmp (évite /usr/local en lecture seule)
ENV CARGO_HOME=/tmp/cargo
ENV RUSTUP_HOME=/tmp/rustup
RUN mkdir -p $CARGO_HOME $RUSTUP_HOME && chown -R appuser:appuser $CARGO_HOME $RUSTUP_HOME

# 4) Passer à l'utilisateur non-root
USER appuser

# 5) Copier les fichiers requirements puis installer (et upgrade pip)
COPY --chown=appuser:appuser requirements.txt requirements.txt
RUN python -m pip install --upgrade pip
RUN pip install --user --no-warn-script-location -r requirements.txt

# 6) Copier le code source
COPY --chown=appuser:appuser . .

# 7) Exposer port et config
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PORT=8000

# 8) Lancer l'app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]