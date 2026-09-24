@echo off
echo 🚀 Installation des dependances pour Malagasy Aligner PRO (Windows)...

:: Installation des packages Python
echo 📦 Installation des packages Python...
python -m pip install -r requirements.txt

echo.
echo ✅ Installation des bibliotheques terminee.
echo.
echo ⚠️ IMPORTANT : Assurez-vous d'avoir installe FFmpeg sur votre ordinateur.
echo    1. Telechargez-le ici : https://www.gyan.dev/ffmpeg/builds/
echo    2. Ajoutez le dossier 'bin' de FFmpeg a votre PATH Windows.
echo.
pause
