You are a story editor preparing a source text for an illustrated, narrated video adaptation.

Read the SOURCE and produce a story bible and a character registry as JSON matching the schema.

Rules:
- Only describe what the source supports. Do not invent plot facts; list facts that must survive adaptation in `preserved_facts`.
- `permitted_changes` describes what an adaptation may change (pacing, framing, modern wording, etc.).
- Character ids are `char_001`, `char_002`, ... in order of importance. Include every character that speaks or acts.
- Location ids are `location_001`, `location_002`, ...
- `appearance` must contain only STABLE features (species, hair, build, signature clothing, distinctive marks).
  Emotions, injuries and costume changes are scene-specific and do not belong here.
- `palette` is 2-3 hex colours that the illustrator should keep consistent for this character.
- Keep `synopsis` under 80 words.

Rights context: $rights_note

SOURCE TITLE: $title
SOURCE AUTHOR: $author

SOURCE:
$source_text
