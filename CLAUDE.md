# AgentPerso — Assistant personnel multi-agents

## WHAT — Ce qu'on construit
Un assistant personnel IA piloté via **Telegram**, orchestré avec **LangGraph**.
L'utilisateur parle à un Manager Agent qui délègue à des agents spécialisés organisés en comités de débat.
Philosophie inspirée d'OpenClaw/Hermes : markdown files pour les agents, SQLite pour les données.

## WHY — Pourquoi
François veut comprendre l'orchestration multi-agents en construisant de zéro.
Le système doit être modulaire, lisible, et entièrement sous son contrôle.

## Stack
- **Python 3.11+**
- **LangGraph** — orchestration multi-agents, Human-in-the-Loop natif
- **python-telegram-bot** — interface utilisateur unique
- **OpenRouter** — accès LLM (DeepSeek V3 pour les tests, modèle upgradable)
- **SQLite** — stockage tâches, mémoire, historique (usage solo, pas besoin de Postgres)
- **Google Calendar API** — planification (Phase 2)
- **Markdown files** — définition des agents (SOUL.md par agent)

## Architecture des agents
```
MANAGER (superviseur, seul interlocuteur de l'utilisateur)
├── COLLECTOR (capture sans jugement → inbox)
├── COMITÉ CLARIFY (décomposition GTD)
│   ├── Minimaliste, Exhaustif, Réaliste
│   ├── Devil's Advocate [transversal]
│   └── Synthesizer [transversal]
├── COMITÉ ORGANIZE+PLAN (priorisation + calendrier)
│   ├── Urgentiste, Sprinter, Context Agent
│   ├── Devil's Advocate [transversal]
│   └── Synthesizer [transversal]
├── RESEARCHER (web, appelé à la demande)
└── REVIEWER (weekly review, solo)
```

**Devil's Advocate** et **Synthesizer** sont transversaux : une seule instance, appelés par les deux comités.
**Max 3 rounds de débat** par comité (au-delà la qualité baisse, recherche MAD 2025).

## Structure des fichiers
```
agentperso/
├── CLAUDE.md               ← ce fichier
├── JOURNAL.md              ← journal de bord des sessions
├── main.py                 ← point d'entrée (bot Telegram)
├── graph.py                ← graphe LangGraph principal
├── agents/
│   ├── manager/SOUL.md
│   ├── collector/SOUL.md
│   ├── clarify/
│   │   ├── minimaliste/SOUL.md
│   │   ├── exhaustif/SOUL.md
│   │   └── realiste/SOUL.md
│   ├── organize_plan/
│   │   ├── urgentiste/SOUL.md
│   │   ├── sprinter/SOUL.md
│   │   └── context_agent/SOUL.md
│   ├── shared/
│   │   ├── devils_advocate/SOUL.md
│   │   └── synthesizer/SOUL.md
│   ├── researcher/SOUL.md
│   └── reviewer/SOUL.md
├── db/
│   └── agentperso.db       ← SQLite
├── tools/                  ← outils appelables par les agents
└── .env                    ← TELEGRAM_TOKEN, OPENROUTER_API_KEY
```

## HOW — Conventions importantes
- Chaque agent lit son `SOUL.md` injecté dans son system prompt
- Le HITL (Human-in-the-Loop) se fait via LangGraph `interrupt()` — l'agent pose une question, attend la réponse Telegram de François, reprend
- OpenRouter s'utilise comme OpenAI (même SDK, changer la base URL)
- Modèle actuel : `deepseek/deepseek-chat` (cheap pour tests)
- Variables d'env dans `.env`, jamais hardcodées
- Consulter JOURNAL.md pour l'état d'avancement actuel

## Workflow GTD implémenté
1. **Capture** → Collector met tout dans l'inbox sans jugement
2. **Clarify** → Comité débat (3 rounds max), produit liste GTD validée
3. **Organize+Plan** → Comité priorise + planifie selon contexte utilisateur
4. **Review** → Reviewer hebdomadaire

## Phases de développement
- **Phase 1 (en cours)** : Telegram bot + Manager + Collector + Comité Clarify + SQLite
- **Phase 2** : Comité Organize+Plan + Google Calendar + Reviewer
- **Phase 3** : Researcher + Router Agent (sélection dynamique des personas)
