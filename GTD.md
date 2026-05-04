# GTD — Getting Things Done (référence implémentation)

## Les 5 étapes

### 1. Capture
Tout ce qui a l'attention de l'utilisateur → inbox, sans jugement, sans tri.

### 2. Clarify — arbre de décision
```
Item de l'inbox
  │
  ├── Actionnable ?
  │     │
  │     ├── NON
  │     │     ├── Plus jamais utile   → Poubelle (delete)
  │     │     ├── Info à garder       → Référence (reference)
  │     │     └── Peut-être un jour   → Someday/Maybe
  │     │
  │     └── OUI
  │           ├── < 2 minutes ?       → FAIRE MAINTENANT (pas dans le système)
  │           ├── Quelqu'un d'autre ? → WAITING FOR (avec date de relance)
  │           ├── Plusieurs étapes ?  → PROJET → définir 1 next action
  │           └── Une seule étape ?   → NEXT ACTION
```

**Clarify ne planifie pas.** Il identifie seulement ce qu'est l'item et quelle est
la prochaine action physique concrète.

### 3. Organize
Placer chaque item dans la bonne liste :
- **Next Actions** → par contexte (@téléphone, @ordi, @dehors, @maison, @énergie-faible)
- **Projects** → toute chose nécessitant plus d'une action (chaque projet a toujours 1 next action active)
- **Waiting For** → délégué ou bloqué par quelqu'un d'autre
- **Someday/Maybe** → pas maintenant, peut-être un jour
- **Calendar** → à faire à une date/heure précise
- **Reference** → info à conserver sans action

### 4. Reflect (weekly review — remplacée dans ce système)
Dans le GTD classique : revue hebdomadaire pour s'assurer que chaque projet
a une next action active.

**Dans notre système :** le trigger est automatique.
Quand l'utilisateur dit "c'est fait" → le système vérifie si c'est un projet →
si oui, Organize+Plan se relance immédiatement pour définir la next action suivante.
Pas de weekly review nécessaire pour ça. Le Reviewer hebdomadaire se concentre
sur les ajustements stratégiques (priorités, projets à abandonner, etc.)

### 5. Engage
l'utilisateur reçoit chaque matin 3-4 next actions.
Il fait, il dit "fait", le système avance automatiquement.

---

## Règles de formulation d'une next action
- Commence par un **verbe d'action physique** : Appeler, Acheter, Écrire, Ouvrir, Envoyer
- Spécifique et atteignable en une session
- ❌ "Avancer sur le projet serre"
- ✅ "Acheter des pinceaux chez Leroy Merlin"

## Contextes
| Contexte | Quand |
|----------|-------|
| `@téléphone` | Appels à passer |
| `@ordi` | Nécessite un ordinateur |
| `@dehors` | Courses, rendez-vous, déplacements |
| `@maison` | Travaux, bricolage, rangement |
| `@énergie-faible` | Faisable même fatigué |

## Règle des 2 minutes
Si une action prend moins de 2 minutes → faire immédiatement, ne pas mettre dans le système.

## Boucle continue (notre adaptation)
```
Capture → Clarify → Organize → Engage
                                  ↓
                             "c'est fait"
                                  ↓
                    projet parent ? → Organize+Plan relance
                                      → next action suivante planifiée
```
