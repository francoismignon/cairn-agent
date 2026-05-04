# AgentPerso — Assistant personnel multi-agents

Un assistant personnel IA piloté via **Telegram**, orchestré avec **LangGraph**. L'utilisateur parle à un Manager Agent qui délègue à des agents spécialisés organisés en comités de débat.

Philosophie GTD + Multi-Agent Debate (MAD) : plusieurs agents débattent pour produire une planification réaliste, avec interruptions pour valider les décisions importantes.

## Stack

| Composant | Technologie |
|---|---|
| Orchestration | LangGraph (StateGraph + HITL natif) |
| Interface | python-telegram-bot |
| LLM | OpenRouter (DeepSeek V3 / Perplexity Sonar) |
| Stockage | SQLite |
| Calendrier & Tâches | Google Calendar API + Google Tasks API |
| Agents | Fichiers SOUL.md (Markdown) |

## Architecture

```
MANAGER (superviseur, seul interlocuteur de l'utilisateur)
├── COLLECTOR (capture sans jugement → inbox)
├── CONTEXT AGENT (questions contextuelles avant débat)
├── COMITÉ CLARIFY
│   ├── Minimaliste — minimum d'actions possible
│   ├── Exhaustif — couverture complète des risques
│   ├── Réaliste — faisabilité selon contraintes réelles
│   ├── Devil's Advocate [transversal]
│   └── Synthesizer [transversal]
├── RESEARCHER (Perplexity Sonar, à la demande)
└── COMITÉ ORGANIZE+PLAN
    ├── Urgentiste — priorisation
    ├── Sprinter — rythme et calendrier
    ├── Devil's Advocate [transversal]
    └── Synthesizer [transversal]
```

**Graphe LangGraph :**
```
START → manager → collector → context_agent → clarify ⇄ clarify_ask
                                                   ↓
                                             researcher → research_review
                                                   ↓
                                            organize_plan → END
```

## Workflow

1. **Capture** — l'utilisateur envoie un message texte ou vocal
2. **Context Agent** — pose jusqu'à 2 questions si des infos manquent
3. **Clarify** — comité de débat (max 3 rounds), peut poser des questions mid-débat
4. **Researcher** — recherche web si la capture implique achat/construction/comparaison
5. **Research Review** — présente les résultats, l'utilisateur valide
6. **Organize+Plan** — décompose en tâches concrètes avec dates, crée dans Google Tasks

## Installation

### Prérequis
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)
- Un bot Telegram (`@BotFather`)
- Un compte OpenRouter
- Un projet Google Cloud avec Calendar API + Tasks API activées

### Setup

```bash
git clone https://github.com/[username]/agentperso
cd agentperso
uv pip install -r requirements.txt
```

### Configuration `.env`

```env
TELEGRAM_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
OPENROUTER_API_KEY=...
LLM_MODEL=deepseek/deepseek-chat
```

### Google Calendar & Tasks (OAuth2)

1. Créer un projet Google Cloud
2. Activer "Google Calendar API" et "Google Tasks API"
3. Créer des credentials OAuth2 Desktop app → télécharger `credentials.json`
4. Placer `credentials.json` dans `credentials/`
5. Lancer le setup :

```bash
uv run python setup_calendar.py
```

### Remplir le profil utilisateur

Éditer `memory/USER.md` avec vos informations (nom, adresse, famille, préférences).

### Lancer le bot

```bash
uv run python main.py
```

## Commandes Telegram

| Commande | Action |
|---|---|
| Texte libre | Pipeline GTD complet |
| "j'ai fait X" | Marque la tâche comme terminée |
| `/review` | Weekly review GTD à la demande |

## Structure des fichiers

```
agentperso/
├── main.py                    # Point d'entrée
├── core/
│   ├── graph.py               # Graphe LangGraph + tous les nodes
│   └── db.py                  # SQLite
├── interfaces/
│   └── telegram.py            # Bot Telegram + JobQueue
├── agents/                    # SOUL.md par agent
│   ├── manager/
│   ├── collector/
│   ├── clarify/{minimaliste,exhaustif,realiste}/
│   ├── organize_plan/{urgentiste,sprinter,context_agent}/
│   ├── shared/{devils_advocate,synthesizer}/
│   ├── researcher/
│   └── reviewer/
├── tools/
│   ├── memory.py              # Mémoire auto USER.md
│   ├── calendar.py            # Google Calendar API
│   └── tasks_google.py        # Google Tasks API
├── memory/
│   ├── USER.md                # Profil utilisateur
│   └── MEMORY.md              # Mémoire des agents
├── db/
│   └── agentperso.db          # SQLite (gitignored)
├── credentials/               # gitignored
│   ├── credentials.json
│   └── token.json
├── setup_calendar.py          # Setup OAuth2 Google
└── requirements.txt
```

## Roadmap

- [x] Phase 1 — Pipeline GTD complet avec HITL
- [x] Phase 2 — Google Tasks + Calendar + Researcher + Weekly Reviewer
- [ ] Phase 3 — Vocaux Whisper, Google Maps pour recommandations locales, message matinal automatique
