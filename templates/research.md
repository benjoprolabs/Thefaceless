# Research: {{title}}

- **Project:** {{project_id}}
- **Brand / channel:** {{brand_name}} · {{language_name}}
- **Division:** {{division_name}}
- **Idea ID:** {{idea_id}}

## One-sentence pitch
<!-- What is this video about, in one sentence a 12-year-old would understand? -->

## Target viewer
<!-- Who is watching, and why do they care? -->

## Key findings
1.
2.
3.

## Sources
Sources are tracked in `sources.csv` in this folder (one row per source: title, URL,
publication date, access date, verification status, notes). Every fact used in the
script must come from a source there. Prefer primary sources.

Add one with:
`python -m factory research add-source {{project_id}} --title "..." --url https://... --type study --accessed today`

List them with `python -m factory research sources {{project_id}}`; check them with
`python -m factory research check {{project_id}}`.

## Competition check
| Title | Channel | Views | What we'll do differently |
|-------|---------|-------|---------------------------|

## Division notes
{{division_notes}}

## Stage checklist
- [ ] At least 2 credible sources recorded
- [ ] Competition checked
- [ ] Pitch is clear in one sentence
