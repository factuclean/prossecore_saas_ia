# Dockerfile (VERSION DÉFINITIVE AVEC REDIRECTION DE CACHE)

# Utiliser une image Python 3.11 légère
FROM python:3.11-slim

# Créer l'utilisateur non-root (NÉCESSAIRE pour les permissions)
RUN useradd -m appuser

# Installer dépendances systèmes et outils de compilation
# Le tout est sur une seule ligne pour éviter les avertissements de syntaxe de l'IDE
USER root
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-fra poppler-utils libgl1 libglib2.0-0 build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail pour l'utilisateur non-root
WORKDIR /home/appuser/app

# --- CORRECTION DES ERREURS DE LECTURE SEULE (OS 30) ---
# Rediriger le cache Cargo/Rust (utilisé par maturin) vers un répertoire inscriptible.
ENV CARGO_HOME /home/appuser/.cargo
ENV RUSTUP_HOME /home/appuser/.rustup

# Préparer le répertoire
RUN mkdir -p /home/appuser/.cargo /home/appuser/.rustup
RUN chown -R appuser:appuser /home/appuser

# --------------------------------------------------------

# Copier le fichier de dépendances
COPY --chown=appuser:appuser requirements.txt .

# Installer les dépendances Python en tant qu'utilisateur non-root
USER appuser
RUN python -m pip install --upgrade pip
# La construction de pandas (ou de toute autre dépendance) va maintenant utiliser les chemins non-root définis ci-dessus.
RUN pip install --user --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY --chown=appuser:appuser . .

# Exposer le port
ENV PORT=8000

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]