---
name: calendar
description: Écriture et lecture de l'agenda Google Calendar — planification, vue semaine, report de tâches
when_to_use: >
  Quand une tâche planifiée doit être écrite dans l'agenda, quand l'utilisateur
  demande sa vue semaine, quand il reporte ou annule un item prévu, ou quand
  le comité Organize+Plan a finalisé un plan et doit le matérialiser dans
  le calendrier.
---

# Skill — Google Calendar

## Principe
Le calendrier est la mémoire externe du planning. Ce qui est planifié par les agents doit y être écrit — c'est ce que l'utilisateur voit s'il ouvre son agenda. Rien d'autre ne doit y être écrit sans que l'utilisateur l'ait validé.

## Opérations disponibles
- **Créer un événement** : tâche planifiée par le comité Organize+Plan
- **Lire la semaine** : vue des événements à venir (demandée par l'utilisateur ou par le Reviewer)
- **Déplacer un événement** : quand l'utilisateur dit "je reporte" ou "pas possible aujourd'hui"
- **Supprimer un événement** : quand une tâche est annulée ou terminée

## Règles d'écriture dans le calendrier
- Chaque next action planifiée → un événement avec titre = formulation GTD ("Appeler X", "Envoyer Y")
- Durée estimée par le Sprinter → durée de l'événement
- Pas d'événement sans durée (minimum 30 min par défaut si non estimé)
- Les tâches `@énergie-faible` sont placées en fin de journée

## Quand l'utilisateur dit "je reporte"
1. L'événement est supprimé du calendrier
2. La tâche retourne dans le backlog (SQLite)
3. Le comité Organize+Plan est relancé pour replanifier
4. Nouveau créneau proposé à l'utilisateur avant écriture

## Quand l'utilisateur dit "c'est fait"
1. L'événement est marqué terminé (ou supprimé)
2. La tâche est archivée dans SQLite
3. Pas de replanification nécessaire
