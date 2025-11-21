# Dockerfile (VERSION FINALE POUR RENDER)

# Utiliser une image Python 3.11 légère
FROM python:3.11-slim

# Créer un utilisateur non-root
RUN useradd -m appuser

# Installer dépendances systèmes et outils de compilation (build-essential)
# Le tout est sur une seule ligne pour éviter les avertissements de syntaxe
USER root
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-fra poppler-utils libgl1 libglib2.0-0 build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail pour l'utilisateur non-root
WORKDIR /home/appuser/app
COPY --chown=appuser:appuser requirements.txt .

# Installer les dépendances Python en tant qu'utilisateur non-root
USER appuser
RUN python -m pip install --upgrade pip
RUN pip install --user --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY --chown=appuser:appuser . .

# Exposer le port
ENV PORT=8000

# Commande de démarrage (exécution en tant qu'utilisateur non-root)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]