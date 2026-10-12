You write YouTube metadata for a narrated, illustrated story video in $language.

Return JSON matching the schema:
- `title`: under 90 characters, honest, no clickbait claims the video does not deliver.
- `description`: 2 short paragraphs about the story (no spoilers of the ending), max 800 characters.
  Do NOT include attribution or chapters; those are appended automatically.
- `tags`: 5-12 short tags.

STORY TITLE: $title
SYNOPSIS: $synopsis
GENRE: $genre
AUDIENCE: $audience
