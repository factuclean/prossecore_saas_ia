# Dockerfile (VERSION FINALE ET DÉFINITIVE)

# Utiliser une image de base plus complète pour assurer la compilation stable
FROM python:3.11-buster

# Installer dépendances systèmes pour Tesseract et Poppler
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root
RUN useradd -m appuser
WORKDIR /home/appuser/app

# Copier seulement le fichier de dépendances en premier pour profiter du cache Docker
COPY --chown=appuser:appuser requirements.txt .

# Installer les dépendances Python
RUN python -m pip install --upgrade pip
# COMMANDE CLÉ : --only-binary :all: force l'utilisation de roues pré-compilées (wheels)
# et empêche l'échec de compilation C++ avec pandas.
RUN pip install --user --no-cache-dir --only-binary :all: -r requirements.txt

# Copier le reste du code
COPY --chown=appuser:appuser . .

# Exposer le port
ENV PORT=8000

USER appuser

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]