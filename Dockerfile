# Dockerfile (SOLUTION MULTI-ÉTAPES DÉFINITIVE)

# ÉTAPE 1: L'ÉTAPE DE CONSTRUCTION (BUILDER)
# Utiliser une image complète (buster) pour garantir que tous les outils de compilation sont présents.
FROM python:3.11-bullseye AS builder

# Installer les dépendances système nécessaires pour la compilation et l'exécution
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app
# Copier uniquement le fichier de dépendances
COPY requirements.txt .

# Installer les dépendances Python dans un dossier temporaire
# Nous utilisons --only-binary :all: pour forcer l'utilisation des roues quand c'est possible
RUN pip install --no-cache-dir --only-binary :all: -r requirements.txt


# ----------------------------------------------------------------------

# ÉTAPE 2: L'ÉTAPE D'EXÉCUTION FINALE (RUNTIME)
# Utiliser l'image slim (plus petite) pour le déploiement final.
FROM python:3.11-slim

# Installer uniquement les dépendances système nécessaires pour l'exécution
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

# Copier les dépendances Python compilées de l'étape 'builder'
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# Copier le reste du code
COPY --chown=appuser:appuser . .

# Exposer le port
ENV PORT=8000

USER appuser

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]