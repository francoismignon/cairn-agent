---
name: debate
description: Décision complexe tranchée par un comité d'agents aux perspectives opposées
when_to_use: >
  Quand une décision est complexe et mérite plusieurs perspectives avant de
  trancher : choix stratégique, arbitrage entre options, évaluation d'un risque.
  Ne pas utiliser pour des questions simples ou factuelles — le débat a un coût
  en tokens, il doit être justifié.
---

# Skill — Débat multi-agents (MAD)

## Principe
Le débat entre agents spécialisés produit de meilleures décisions qu'un seul agent omniscient. Chaque agent défend une perspective, le Devil's Advocate crée de la friction, le Synthesizer conclut.

## Structure d'un round de débat

```
Round N :
  1. Chaque agent de position propose sa réponse
  2. Devil's Advocate challenge la proposition la plus fragile
  3. Les agents répondent à l'objection (optionnel si consensus clair)
  4. Synthesizer conclut le round
```

## Règles

**Nombre de rounds : maximum 3**
Au-delà de 3 rounds, la qualité du débat baisse (phénomène de "position lock"). Si pas de consensus après 3 rounds, le Synthesizer tranche quand même.

**Chaque agent parle une fois par round**
Pas de back-and-forth infini. Un argument, une réponse, une conclusion.

**Le Devil's Advocate ne bloque pas**
S'il ne trouve pas d'objection solide, il le dit : "La proposition tient."

**Le Synthesizer a le dernier mot**
Sa conclusion est finale pour ce round.

## Conditions d'arrêt anticipé
- Consensus clair dès le Round 1 → Synthesizer conclut sans aller à 3
- Item trop simple pour débattre → Manager gère directement

## Output final du comité
```
Action retenue : [formulation concrète]
Raison : [une phrase]
Point ouvert : [si applicable, sinon rien]
```
