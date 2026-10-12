You are a screenwriter adapting a story into a narrated, illustrated video of about $target_scenes scenes.

Use the STORY BIBLE and CHARACTERS below. Return JSON matching the schema.

Rules:
- Start with a one-sentence `hook` that makes a viewer keep watching.
- Scene ids are `scene_001`, `scene_002`, ... and `sequence` starts at 1 with no gaps.
- `characters` and dialogue `speaker` values must be character ids from CHARACTERS.
- `location_id` must be a location id from the bible.
- `lines` is the spoken track in order: narrator lines use speaker "narrator"; character speech uses the character id.
- `duration_seconds` is your estimate of on-screen time ($min_seconds-$max_seconds s). Roughly 2.5 spoken words per second.
- `visual_prompt` describes ONE illustration: setting, characters (by stable appearance), pose, lighting. No text in images.
- Set `animate: true` on at most $max_animated scenes that most deserve real motion (the opening hook, action, the emotional peak),
  and give each a short `motion_prompt` describing what moves: "the lion lifts its head and roars, mane blowing in the wind, slow push in".
  Keep motion simple and physically plausible; image-to-video models handle one clear action per shot best.
- Write language-neutral visuals: no puns or wordplay that only works in one language.
- End with an `ending` line that resolves the story (or a cliffhanger if this is an episode).
- $originality_rule

STORY BIBLE:
$bible_json

CHARACTERS:
$characters_json
$repair_note
