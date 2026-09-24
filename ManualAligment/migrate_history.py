import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
HISTORY_DIR = BASE_DIR / "dataset" / "history"
OLD_FILE = BASE_DIR / "dataset" / "alignment_data.json"

def migrate():
    if not OLD_FILE.exists():
        print("Rien à migrer.")
        return

    HISTORY_DIR.mkdir(exist_ok=True, parents=True)
    
    with open(OLD_FILE, "r", encoding="utf-8") as f:
        full_data = json.load(f)
    
    # On éclate le gros fichier en petits fichiers
    for key, data in full_data.items():
        # Remplacer les / par des _ pour le nom de fichier
        safe_key = key.replace("/", "___") 
        target = HISTORY_DIR / f"{safe_key}.json"
        
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    print(f"Migration terminée ! {len(full_data)} fichiers créés dans dataset/history/")
    print("Vous pouvez maintenant tester la nouvelle version de l'app.")

if __name__ == "__main__":
    migrate()
