import os
import re
import json
from pathlib import Path
from collections import Counter

TEXT_DIR = Path("text")
DATASET_DIR = Path("dataset")
CHARS_PER_SEC = 21.0
TARGET_SECONDS = 7200  # 2 heures
MAX_WORD_OCCURRENCE = 5 # Nombre de fois max qu'on cherche à avoir un mot

def clean_text(t):
    t = t.lower()
    t = re.sub(r'[^a-z\'àâéèêëîïôûùç\- ]', ' ', t)
    return t.split()

def split_into_sentences(text):
    # Découpage par ponctuation : . , : ? ! ;
    sentences = re.split(r'([.,:?!;])', text)
    res = []
    for i in range(0, len(sentences)-1, 2):
        s = (sentences[i] + sentences[i+1]).strip()
        if len(s) > 10: # On ignore les fragments trop courts
            res.append(s)
    # Ajouter le dernier morceau s'il reste quelque chose sans ponctuation
    if len(sentences) % 2 == 1 and len(sentences[-1].strip()) > 10:
        res.append(sentences[-1].strip())
    return res

def optimize():
    print("Étape 1: Découpage en phrases et analyse globale...")
    all_chunks = []
    
    for fp in TEXT_DIR.rglob("*.txt"):
        with open(fp, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line_idx, line_content in enumerate(lines):
                sentences = split_into_sentences(line_content)
                for s in sentences:
                    words = clean_text(s)
                    if not words: continue
                    dur = len(s) / CHARS_PER_SEC
                    all_chunks.append({
                        "path": str(fp),
                        "line": line_idx + 1,
                        "text": s,
                        "words": words,
                        "unique_words": set(words),
                        "duration": dur
                    })

    print(f"Étape 2: Sélection intelligente (limite {TARGET_SECONDS}s, quota {MAX_WORD_OCCURRENCE}x par mot)...")
    
    selected = []
    total_dur = 0
    word_coverage = Counter()
    
    # On utilise une boucle gourmande pour maximiser la diversité
    while total_dur < TARGET_SECONDS and all_chunks:
        best_idx = -1
        best_score = -1
        
        # Pour accélérer, on ne scanne que 2000 candidats aléatoires ou les premiers
        # si la liste est immense, mais ici on peut tout scanner ça reste raisonnable
        for i, chunk in enumerate(all_chunks):
            # Score = nombre de mots utiles (qui n'ont pas encore atteint le quota)
            useful_words = 0
            for w in chunk["unique_words"]:
                if word_coverage[w] < MAX_WORD_OCCURRENCE:
                    useful_words += 1
            
            if useful_words == 0:
                score = 0.00001 # Très faible priorité
            else:
                score = useful_words / chunk["duration"]
            
            if score > best_score:
                best_score = score
                best_idx = i
        
        if best_idx == -1: break
        
        winner = all_chunks.pop(best_idx)
        selected.append(winner)
        total_dur += winner["duration"]
        for w in winner["words"]:
            word_coverage[w] += 1
            
        if len(selected) % 100 == 0:
            print(f"Progression : {total_dur/3600:.2f}h / 2h | Mots couverts : {len(word_coverage)}")

    # Nettoyage pour JSON
    for s in selected:
        if "unique_words" in s: del s["unique_words"]
        if "words" in s: del s["words"]
        
    # Tri par fichier pour le workflow
    selected.sort(key=lambda x: (x["path"], x["text"]))

    with open(DATASET_DIR / "optimization_plan.json", "w", encoding="utf-8") as f:
        json.dump(selected, f, indent=2)
    
    print(f"\nPLAN TERMINÉ !")
    print(f"Durée totale : {total_dur/3600:.2f} heures")
    print(f"Vocabulaire unique : {len(word_coverage)} mots")
    print(f"Plan sauvegardé dans dataset/optimization_plan.json")

if __name__ == "__main__":
    optimize()
