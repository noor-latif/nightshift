# Holdout scenarios

Independent composed scenarios for the pastebin service. The producer must establish
isolation and start a fresh environment for this pass. No factory Python helper enforces
a private holdout boundary.

## Overwrite-independence and id uniqueness

1. POST /paste {"content": "alpha"} and note the id.
2. POST /paste {"content": "beta"} and note the id.
3. GET both ids.
4. Expect: both contents correct, ids distinct, and no cross-contamination
   (reading one does not affect the other).

**What would make this fail:** both ids resolving to the same content, the second
POST overwriting the first, or ids colliding.

## Content with awkward bytes round-trips

1. POST /paste with content containing quotes, a newline, and a unicode character
   (e.g. `line1\n"quoted" café`).
2. GET the id back.
3. Expect byte-exact round-trip of the content.

**What would make this fail:** JSON escaping mangling the content, truncation at a
newline, or encoding loss.

## Concurrent-ish creation does not lose pastes

1. POST three pastes rapidly (sequentially, no delay).
2. GET all three back.
3. Expect all three to resolve with their own contents.

**What would make this fail:** storage keyed by a counter that collides, or a shared
mutable state losing entries.
