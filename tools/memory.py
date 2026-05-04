from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def append_to_user_profile(note: str) -> None:
    path = BASE_DIR / "memory" / "USER.md"
    content = path.read_text()
    marker = "## Informations collectées"
    if marker not in content:
        content += f"\n{marker}\n<!-- Le Manager ajoute ici les infos partagées en cours de conversation -->\n"
    content += f"- {note}\n"
    path.write_text(content)


def append_to_agent_memory(note: str) -> None:
    path = BASE_DIR / "memory" / "MEMORY.md"
    content = path.read_text() if path.exists() else "# MEMORY.md — Mémoire des agents\n"
    content += f"- {note}\n"
    path.write_text(content)
