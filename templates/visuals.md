# Visual Production: {{title}}

- **Visual style:** {{visual_style}}
- **Format:** {{aspect_ratio}} at {{resolution}}

Plan one row per script scene in `shotlist.csv`. Reusable files go in `assets/`
and are registered with `python -m factory assets add`.

`python -m factory shots generate {{project_id}}` fills the shot list from the script (rows you
filled in are kept); `shots link {{project_id}} SCENE --asset AS0001` links a registered asset;
`shots check {{project_id}}` checks it.

## Stage checklist
- [ ] Every script scene has a shot list row
- [ ] Every row has a file and status `done`
- [ ] Every external visual has source + licence recorded
- [ ] Thumbnail / cover created
