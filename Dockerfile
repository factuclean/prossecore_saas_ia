# Dockerfile (SOLUTION MINICONDA ULTIME)

# Utiliser l'image Miniconda (base pour la science des données)
FROM continuumio/miniconda3 AS builder

# Installer les dépendances système Tesseract et Poppler
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Créer un environnement Conda stable avec Python 3.11
RUN conda create --name app_env python=3.11 -y
ENV PATH /opt/conda/envs/app_env/bin:$PATH

# Définir le répertoire de travail
WORKDIR /app
COPY requirements.txt .

# Installer les dépendances Python DANS l'environnement Conda
# Conda gère les dépendances complexes (pandas) en binaires stables
RUN pip install --no-cache-dir -r requirements.txt

# --- Optimisation de l'image (Éliminer les fichiers de construction) ---
# Utiliser une image Python minimaliste pour l'exécution finale
FROM python:3.11-slim

# Installer les dépendances système d'exécution (Tesseract, etc.)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Créer l'utilisateur non-root (pour les erreurs de permission)
RUN useradd -m appuser
WORKDIR /home/appuser/app

# Copier l'environnement Conda complet (y compris pandas pré-compilé) de l'étape builder
COPY --from=builder /opt/conda/envs/app_env /usr/local/lib/app_env
ENV PATH /usr/local/lib/app_env/bin:$PATH

# Copier le reste du code
COPY --chown=appuser:appuser . .

# Exposer le port
ENV PORT=8000
USER appuser

# Commande de démarrage (uvicorn est maintenant dans le PATH de l'environnement copié)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]