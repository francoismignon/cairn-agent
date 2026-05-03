# Journal de bord — AgentPerso

## Comment utiliser ce fichier
À chaque session de code, Claude met à jour ce fichier :
- Ce qui a été décidé / construit
- Les décisions architecturales et pourquoi
- L'état exact du projet
- Ce qui reste à faire

---

## Session 1 — 2026-05-01 — Architecture & Design

### Décisions prises

**Stack choisie :**
- LangGraph (vs CrewAI) → choisi pour le HITL natif (`interrupt()`) indispensable au workflow
- Python + python-telegram-bot → interface unique via Telegram
- SQLite (pas PostgreSQL) → usage solo, zéro overhead
- OpenRouter + DeepSeek V3 → cheap pour les tests, upgradable
- Markdown files (SOUL.md) → définition des agents, inspiré OpenClaw/Hermes

**Architecture multi-agents :**
- Inspirée des meilleures pratiques Multi-Agent Debate (MAD, recherche 2025)
- Devil's Advocate et Synthesizer = agents transversaux (1 instance, 2 comités)
- Max 3 rounds de débat (au-delà, qualité baisse selon recherche A-HMAD)
- Pas de web app pour l'instant — Telegram suffit

**Workflow GTD :**
- 5 étapes GTD mappées sur des agents spécialisés
- ORGANIZE et PLAN fusionnés en un seul comité (économie de tokens)
- Comité CLARIFY : Minimaliste + Exhaustif + Réaliste + Devil's Advocate + Synthesizer
- Comité ORGANIZE+PLAN : Urgentiste + Sprinter + Context Agent + Devil's Advocate + Synthesizer

**Agents définis (12 au total) :**
| Agent | Rôle | Comité |
|---|---|---|
| Manager | Superviseur, interface Telegram | — |
| Collector | Capture sans jugement | solo |
| Minimaliste | Minimum d'actions possible | CLARIFY |
| Exhaustif | Couverture complète des risques | CLARIFY |
| Réaliste | Faisabilité selon contraintes réelles | CLARIFY |
| Urgentiste | Priorisation / ordre | ORGANIZE+PLAN |
| Sprinter | Rythme / calendrier | ORGANIZE+PLAN |
| Context Agent | Pose questions à l'utilisateur (énergie, dispo) | ORGANIZE+PLAN |
| Devil's Advocate | Challenge tous les agents (transversal) | CLARIFY + O+P |
| Synthesizer | Conclut les débats (transversal) | CLARIFY + O+P |
| Researcher | Recherche web à la demande | solo |
| Reviewer | Weekly review | solo |

### État du projet
- [ ] Code : rien de codé
- [x] Architecture : validée
- [x] CLAUDE.md : créé
- [x] JOURNAL.md : créé
- [ ] Structure de dossiers : à créer
- [ ] Phase 1 : à démarrer

### Prochaine session
Démarrer Phase 1 :
1. Créer la structure de dossiers
2. Écrire les SOUL.md de chaque agent
3. Configurer `.env`
4. `main.py` — bot Telegram basique
5. `graph.py` — graphe LangGraph : Manager → Collector → Comité Clarify
6. SQLite schema (inbox, projects, tasks, next_actions)

---

## Session 2 — 2026-05-03 — Affinage architecture

### Décisions prises

**GTD = skill, pas du code**
- Le workflow GTD est un fichier markdown (`skills/gtd.md`) injecté dans les agents
- L'app core est générique : orchestration + interface + tools Python
- Swapper GTD contre une autre méthodo = changer le markdown, zéro code

**Calm technology — interface unique**
- Seul output visible : message Telegram chaque matin avec 3-4 actions du jour
- François répond (texte ou vocal), l'agent adapte en silence
- Pas de dashboard, pas d'inbox visible, toute la logistique est interne (SQLite)
- Vocaux Telegram supportés dès le début (Whisper pour STT)

**Interface découplée du core**
```
interfaces/telegram.py   ← Phase 1
interfaces/sms.py        ← Phase 3 (Twilio)
interfaces/voice.py      ← Phase 3 (Twilio + Whisper)
```
Les agents ne savent pas par quelle interface le message est arrivé.

**Tools : pas de code custom si ça existe déjà**
- Gmail → `langchain-community` GmailToolkit
- Google Calendar → `langchain-google-community` GoogleCalendarToolkit
- SQLite → sqlite3 natif Python
- Web search → TavilySearch
- Telegram vocaux → Whisper (OpenAI API)

**Structure finale retenue**
```
agentperso/
├── core/
│   ├── graph.py          ← routing LangGraph
│   └── db.py             ← accès SQLite
├── interfaces/
│   └── telegram.py       ← bot Telegram (point d'entrée)
├── agents/               ← SOUL.md par agent
├── skills/               ← markdown chargés à la demande
│   ├── gtd.md
│   └── debate.md
├── tools/                ← fonctions Python custom (inbox, tasks)
├── main.py               ← point d'entrée
└── .env
```

### Prochaine session
1. Créer la structure de dossiers
2. Écrire les SOUL.md (Manager, Collector, agents Clarify)
3. Écrire les skills markdown (gtd.md, debate.md)
4. `main.py` + `interfaces/telegram.py` — bot basique
5. `core/graph.py` — graphe LangGraph minimal
6. `core/db.py` + schema SQLite

---
<!-- Les sessions suivantes s'ajoutent ici, au-dessus de ce commentaire -->
