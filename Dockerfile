# Dockerfile
FROM python:3.11-slim

# installer dépendances systèmes, y compris les outils de construction
# build-essential est nécessaire pour compiler pandas et d'autres dépendances C/C++
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# créer user non-root (optionnel mais recommandé)
RUN useradd -m appuser
WORKDIR /home/appuser/app
COPY --chown=appuser:appuser . .

ENV PATH="/home/appuser/.local/bin:${PATH}"

# installer deps python
RUN python -m pip install --upgrade pip
# Utilisation de --no-cache-dir pour réduire la taille finale de l'image Docker
RUN pip install --user --no-cache-dir -r requirements.txt

# exposer port
ENV PORT=8000

USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]