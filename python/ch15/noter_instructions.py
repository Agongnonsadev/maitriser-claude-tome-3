"""Chapitre 15 : le hook InstructionsLoaded de Yao, pour savoir quels fichiers d'instructions Claude Code charge.

Claude Code lance ce programme à chaque CLAUDE.md ou règle chargé, et lui passe sur l'entrée standard un JSON :
le fichier (file_path), sa portée (memory_type : User, Project, Local, Managed), la raison du chargement
(load_reason : session_start, path_glob_match, include…), et le fichier qui l'a déclenché. Le programme
ajoute une ligne au journal donné en argument. Sans dépendance : Python seul.

Dans .claude/settings.local.json (réglage local, qui ne part pas dans le dépôt partagé) :
    {"hooks": {"InstructionsLoaded": [{"hooks": [{"type": "command",
        "command": "python ch15/noter_instructions.py journal-instructions.jsonl"}]}]}}
"""

import json
import sys

GARDES = ("file_path", "memory_type", "load_reason", "globs", "trigger_file_path", "parent_file_path")


def principal() -> None:
    journal = sys.argv[1]
    entree = json.loads(sys.stdin.read() or "{}")
    ligne = {cle: entree[cle] for cle in GARDES if cle in entree}
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    principal()
