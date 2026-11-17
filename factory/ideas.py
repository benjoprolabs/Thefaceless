"""Idea backlog stored in ideas/ideas.csv."""

import csv


def load_ideas(paths):
    if not paths.ideas_csv.exists():
        return []
    with open(paths.ideas_csv, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_idea(paths, idea_id):
    for idea in load_ideas(paths):
        if idea["id"].lower() == idea_id.lower():
            return idea
    return None


def score(demand, competition, effort):
    """Higher demand is good; lower competition and effort are good. Result is 1-5."""
    return round((demand * 2 + (6 - competition) + (6 - effort)) / 4, 1)
