#!/bin/bash

echo "🚀 Installation des dépendances pour Malagasy Aligner PRO..."

# 1. Vérification de FFmpeg
if ! command -v ffmpeg &> /dev/null
then
    echo "⚠️ FFmpeg n'est pas installé. Installation en cours..."
    sudo apt update && sudo apt install -y ffmpeg
else
    echo "✅ FFmpeg est déjà installé."
fi

# 2. Installation des packages Python
echo "📦 Installation des packages Python..."
pip install -r requirements.txt

echo "✨ Installation terminée ! Vous pouvez lancer l'application avec : python3 aligner.py"
