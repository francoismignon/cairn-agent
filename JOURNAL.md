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

---

## Session 2 — 2026-05-03 — Affinage architecture

**GTD = skill, pas du code** — workflow dans des fichiers markdown, core générique.
**Calm technology** — output unique : message Telegram matin avec 3-4 actions.
**Interface découplée** — `interfaces/telegram.py`, les agents ignorent le canal d'entrée.

---

## Sessions 3-4 — 2026-05-03/04 — Phase 1 + Phase 2 complètes

### Ce qui a été construit

#### Phase 1 — Infrastructure de base
- `main.py` + `interfaces/telegram.py` — bot Telegram avec HITL (`interrupt()`)
- `core/graph.py` — graphe LangGraph complet
- `core/db.py` — SQLite (inbox, projects, tasks)
- Tous les SOUL.md rédigés (13 agents)

#### Graphe LangGraph (ordre d'exécution)
```
START → manager → collector → context_agent → clarify ⇄ clarify_ask
                                                  ↓
                                            researcher → research_review
                                                  ↓
                                           organize_plan → END
                              complete (tâche terminée) → END ou organize_plan
```

#### Agents implémentés
| Node | Rôle |
|---|---|
| `manager_node` | Routing + sauvegarde mémoire auto + détection recherche |
| `collector_node` | Inbox SQLite |
| `context_agent_node` | Questions contextuelles (HITL interrupt) |
| `clarify_node` | Débat MAD 3 rounds (Minimaliste/Exhaustif/Réaliste + DA + Synthesizer) |
| `clarify_ask_node` | Pause mid-débat si Synthesizer a besoin d'une info (HITL) |
| `researcher_node` | Perplexity `sonar` via OpenRouter |
| `research_review_node` | Présente les résultats à l'utilisateur (HITL) |
| `organize_plan_node` | Débat MAD 1 round (Urgentiste + Sprinter + DA + Synthesizer) |
| `complete_node` | Marque tâche done SQLite + Google Tasks |
| `run_review()` | Weekly review standalone (appelée par JobQueue ou `/review`) |

#### Tools créés
- `tools/memory.py` — `append_to_user_profile()` (mémoire auto depuis Manager)
- `tools/calendar.py` — `list_events()`, `create_event()`, OAuth2 Google Calendar
- `tools/tasks_google.py` — `get_or_create_task_list()`, `create_task()`, `complete_task_by_title()`

#### Features Telegram
- Messages texte → pipeline GTD complet
- HITL multi-niveaux : Context Agent, mid-débat Clarify, Research Review
- `/review` command → weekly review à la demande
- Job planifié chaque vendredi 18h (APScheduler via JobQueue)

### Décisions architecturales

**Google Tasks (pas Calendar) pour les tâches GTD**
- 1 liste Google Tasks = 1 projet GTD → archivage naturel des tâches terminées
- Google Calendar = événements uniquement (rendez-vous, deadlines fixes)
- `organize_plan_node` lit le Calendar avant de planifier pour éviter les conflits

**Researcher : query affinée post-Clarify**
- Le Manager fixe une query initiale
- Le Synthesizer de Clarify produit une `research_query_refined` avec tout ce qu'on a appris
- Si la query devient vide (l'utilisateur avait déjà les infos), la recherche est annulée

**Scheduling time-aware**
- Heure courante injectée dans le contexte d'Organize+Plan
- Règle explicite : si après 18h → pas de tâche `day_offset=0`

**Mémoire auto**
- Manager extrait `user_note` de chaque message et appelle `append_to_user_profile()`
- USER.md enrichi automatiquement au fil des conversations

### État actuel — Phase 2 complète ✅

**Fonctionnel et testé :**
- [x] Pipeline GTD complet : Capture → Clarify → Researcher → Review → Organize+Plan
- [x] HITL à 3 niveaux (Context Agent / mid-débat / Research Review)
- [x] Google Tasks : création avec dates d'échéance, completion automatique
- [x] Google Calendar : lecture des événements existants avant planification
- [x] Mémoire auto USER.md
- [x] Weekly Reviewer (manuel `/review` + automatique vendredi 18h)

### Reste à faire (Phase 3)
- [ ] **Vocaux Whisper** — transcrire les vocaux Telegram avant le pipeline
- [ ] **Google Maps API** — calculer distance + coût diesel pour recommander les magasins les plus avantageux (adresse : Rue Désiré Maroille 13A, 7300 Boussu)
- [ ] **Router Agent** — sélection dynamique des personas selon le type de projet
- [ ] **Matin automatique** — message quotidien avec les 3-4 actions du jour
