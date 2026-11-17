# Fact Check: {{title}}

- **Project:** {{project_id}}
- **Checked by:**
- **Date checked:**

| Ref | Claim (as written in script) | Source(s) (IDs from sources.csv, e.g. S1, S3) | Verdict | Fix applied |
|-----|------------------------------|-----------------------------------------------|---------|-------------|
| F1  |                              |                                               | ✅ / ⚠️ / ❌ |           |

Verdicts: ✅ confirmed · ⚠️ needs softer wording · ❌ remove or replace (also accepted: ok / soft / remove)

`python -m factory factcheck sync {{project_id}}` adds a row for each new [F#] claim in the script;
`factcheck check {{project_id}}` checks verdicts and sources.

## Division notes
{{division_notes}}

## Stage checklist
- [ ] Every [F#] in the script has a row here
- [ ] No ❌ claims left in the script
- [ ] ⚠️ claims reworded
- [ ] Speculation and theories are labelled as such
