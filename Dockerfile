# Dockerfile (VERSION FINALE PRÊTE À DÉPLOYER)

# 1. Image de base stable
FROM python:3.11-slim

# 2. Installer les dépendances système et outils de compilation
USER root
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-fra poppler-utils libgl1 libglib2.0-0 build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. Préparation de l'utilisateur et du répertoire de travail
RUN useradd -m appuser
WORKDIR /home/appuser/app
RUN chown -R appuser:appuser /home/appuser

# 4. Redirection du cache Cargo/Rust (FIX pour l'erreur OS 30)
ENV CARGO_HOME /home/appuser/.cargo
ENV RUSTUP_HOME /home/appuser/.rustup
RUN mkdir -p $CARGO_HOME $RUSTUP_HOME

# 5. Passer à l'utilisateur non-root pour TOUTES les installations
USER appuser

# 6. Copier les deux fichiers de dépendances
COPY requirements.txt .
COPY requirements_pandas.txt .

# 7. Installer les dépendances (la première commande est pour la cohérence, la seconde est le point critique)
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements_pandas.txt

# 8. Copier le reste du code
COPY . .

# 9. Configuration de l'exécution
ENV PORT=8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]