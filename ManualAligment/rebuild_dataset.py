import json
import csv
from pathlib import Path
from pydub import AudioSegment, effects

AUDIO_DIR = Path("audio")
DATASET_DIR = Path("dataset")
WAVS_DIR = DATASET_DIR / "wavs"
HISTORY_DIR = DATASET_DIR / "history"
METADATA_FILE = DATASET_DIR / "metadata.csv"

def rebuild():
    WAVS_DIR.mkdir(exist_ok=True, parents=True)
    count = 0
    all_metadata = []
    
    # 1. Charger tout l'historique éparpillé
    history_files = list(HISTORY_DIR.glob("*.json"))
    if not history_files:
        print("Aucun historique trouvé dans dataset/history/")
        return 0

    print(f"Analyse de {len(history_files)} fichiers d'historique...")
    
    for hf in history_files:
        stem = hf.stem
        if stem.startswith("completed_tasks") or stem.startswith("success_tasks"):
            continue
            
        # Extraire le chemin du chapitre (on enlève le ___user à la fin)
        parts = stem.split("___")
        if len(parts) < 2: continue
        
        chapter_key = "/".join(parts[:-1]).replace(".mp3", "") + ".mp3"
        audio_path = AUDIO_DIR / chapter_key
        
        try:
            with open(hf, encoding="utf-8") as f:
                data = json.load(f)
            
            audio = None
            segments = data if isinstance(data, list) else data.get("segments", [])
            
            for seg in segments:
                wav_name = seg.get("wav_name")
                text = seg.get("text", "")
                start_ms = int(seg["start"] * 1000)
                end_ms = int(seg["end"] * 1000)
                
                if not wav_name:
                    # Reconstruction du nom si manquant
                    prefix = "-".join(chapter_key.replace(".mp3", "").split("/"))
                    wav_name = f"{prefix}-T{start_ms:07d}.wav"

                all_metadata.append((wav_name, text))
                out_path = WAVS_DIR / wav_name
                
                # Génération audio si manquant
                if not out_path.exists() and audio_path.exists():
                    if audio is None:
                        print(f"Extraction depuis {chapter_key}...")
                        audio = AudioSegment.from_file(str(audio_path))
                    
                    cut = audio[start_ms:end_ms]
                    cut = effects.normalize(cut)
                    cut.export(str(out_path), format="wav")
                    count += 1
        except Exception as e:
            print(f"Erreur sur {hf.name}: {e}")

    # 2. Régénérer metadata.csv (Trié et sans doublons)
    all_metadata = sorted(list(set(all_metadata)))
    with open(METADATA_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for wav_name, text in all_metadata:
            writer.writerow([f"wavs/{wav_name}", text])
            
    print(f"Fichier metadata.csv régénéré ({len(all_metadata)} entrées).")
    return count

if __name__ == "__main__":
    c = rebuild()
    print(f"\nTerminé ! {c} nouveaux fichiers audio générés.")
