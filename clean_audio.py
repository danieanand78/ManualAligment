import json
import os
from pathlib import Path

PLAN_FILE = Path("dataset/optimization_plan.json")
AUDIO_DIR = Path("audio")
TEXT_DIR  = Path("text")

def clean():
    if not PLAN_FILE.exists():
        print("Erreur: Le fichier optimization_plan.json n'existe pas.")
        return

    print("Lecture du plan d'optimisation...")
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)

    # 1. Identifier tous les fichiers MP3 nécessaires
    needed_audio_rel = set()
    for item in plan:
        # On convertit le chemin du texte en chemin audio relatif
        # ex: text/AT/01/ch_01.txt -> AT/01/ch_01.mp3
        txt_path = Path(item["path"])
        try:
            rel = txt_path.relative_to("text")
            audio_rel = rel.with_suffix(".mp3")
            needed_audio_rel.add(str(audio_rel))
        except ValueError:
            continue

    print(f"Fichiers audio nécessaires selon le plan : {len(needed_audio_rel)}")

    # 2. Lister tous les fichiers MP3 présents physiquement
    all_audio_files = list(AUDIO_DIR.rglob("*.mp3"))
    to_delete = []

    for af in all_audio_files:
        rel_af = af.relative_to(AUDIO_DIR)
        if str(rel_af) not in needed_audio_rel:
            to_delete.append(af)

    if not to_delete:
        print("Aucun fichier à supprimer. Votre dossier audio est déjà propre !")
        return

    print(f"Fichiers à supprimer : {len(to_delete)}")
    confirm = input(f"Voulez-vous vraiment supprimer ces {len(to_delete)} fichiers ? (y/n) : ")
    
    if confirm.lower() == 'y':
        for f in to_delete:
            try:
                f.unlink()
                # Optionnel: supprimer les dossiers parents s'ils sont vides
                parent = f.parent
                while parent != AUDIO_DIR and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            except Exception as e:
                print(f"Erreur lors de la suppression de {f}: {e}")
        print("Nettoyage terminé !")
    else:
        print("Opération annulée.")

if __name__ == "__main__":
    clean()
