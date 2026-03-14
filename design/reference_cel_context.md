## Reference: CEL Evaluation Context

**Document status:** Draft v0.1
**Depends on:** sec2_architecture.md §2.13, reference_validators_yaml.md

This document specifies the exact variables available in CEL expressions used in
`validators.yaml` — both `when` pre-conditions and `condition` expressions.

CEL library: `cel-python` (`pip install cel-python`). CEL spec: https://cel.dev

---

### Available Variables

| Variable | Type (CEL) | Nullable | Description |
|---|---|---|---|
| `entity` | map(string, any) | never null | The proposed entity state after this write, with any expanded fields merged in. Contains user-defined fields + system field `__type__`. Does NOT contain system temporal fields (`created_at`, `updated_at`, `schema_version`) — those live in provenance only. |
| `existing` | map(string, any) \| null | null on creates | The current stored state of the entity before this write. Same structure as `entity`. `null` for create operations. Always present (non-null) for update and delete operations. |
| `operation` | string | never null | The operation being performed: `"create"`, `"update"`, or `"delete"`. |

---

### `entity` Map Structure

`entity` contains exactly the fields declared in the schema for this entity type, plus
system fields. Field values reflect the proposed state — the merged result of current
stored values and the incoming write.

**User-defined fields** appear with their schema-declared names and values coerced to
CEL types:

| Schema type | CEL type | Null value | Notes |
|---|---|---|---|
| `string` | `string` | `null` | |
| `int` | `int` | `null` | |
| `float` | `double` | `null` | |
| `bool` | `bool` | `null` | |
| `date` | `string` | `null` | ISO 8601 date string e.g. `"2024-06-01"` |
| `datetime` | `string` | `null` | ISO 8601 UTC string e.g. `"2024-06-01T10:30:00Z"` |
| `enum` | `string` | `null` | The string value of the enum |
| `json` | `map(string, any)` or `list(any)` | `null` | Parsed JSON object or array |
| `uri` | `string` | `null` | |
| `ref` | `string` | `null` | Before expansion: the ref string `"EntityType:uuid"`. After expansion: the full entity map (see §Expanded Fields). |

**System fields always present in `entity`:**

| Field | CEL type | Description |
|---|---|---|
| `__type__` | `string` | Concrete entity type name e.g. `"BrainSample"`. Never null. |
| `id` | `string` | The entity's Hippo UUID. Never null. |
| `is_available` | `bool` | Availability flag. Never null. |

**Fields NOT present in `entity`:**
- `created_at`, `updated_at`, `schema_version` — these are provenance-derived and never
  stored on entities; they are not available in the CEL context
- Fields from parent types ARE included — a `BrainSample` entity map contains both
  `Sample` fields and `BrainSample`-specific fields (joined at read time)

---

### Expanded Fields

When an `expand:` path is declared, the named field's value is replaced in `entity`
with the full resolved entity map (for single refs) or a list of full entity maps
(for list refs).

**Before expansion** — `entity.subject` is a ref string:
```
"Subject:abc-123-def-456"
```

**After `expand: [{path: subject}]`** — `entity.subject` is a full entity map:
```
{
  "id": "abc-123-def-456",
  "__type__": "Subject",
  "is_available": true,
  "external_id": "SL-999",
  "species": "Homo sapiens",
  "diagnosis": "Huntington's disease",
  ...
}
```

**After `expand: [{path: samples[]}]`** — `entity.samples` is a list of entity maps:
```
[
  {"id": "...", "__type__": "Sample", "tissue_type": "brain", ...},
  {"id": "...", "__type__": "BrainSample", "tissue_type": "brain", "brain_region": "hippocampus", ...}
]
```

**Null ref handling:** If a `ref` field is `null` (not set), it remains `null` after
expansion — no error is raised. Validators that access fields on an expanded ref must
guard against null: `entity.subject != null && entity.subject.diagnosis == "HD"`.

**Missing expansion:** Accessing a `ref` field in CEL that was NOT declared in `expand:`
returns the raw ref string, not the entity map. This is intentional — CEL expressions
must declare all I/O upfront. A validator that tries to navigate `entity.subject.diagnosis`
without expanding `subject` will receive the ref string `"Subject:uuid"`, and `.diagnosis`
will return `null` (CEL map access on a non-map type returns null). This is a silent
mis-configuration; implementers should consider emitting a startup warning when a condition
expression navigates a path that isn't declared in `expand:`.

---

### `existing` Map Structure

`existing` has the same structure as `entity` but represents the current stored state
before the write. For updates, fields not included in the incoming write are present
with their current values. `existing` is never expanded — it always contains raw ref
strings, not entity maps.

```
# For an update that changes only tissue_type:
existing = {
  "id": "...",
  "__type__": "Sample",
  "is_available": true,
  "external_id": "SL-123",
  "tissue_type": "liver",      # ← the value being changed
  "subject": "Subject:abc-123" # ← raw ref string, not expanded
  ...
}

entity = {
  "id": "...",
  "__type__": "Sample",
  "is_available": true,
  "external_id": "SL-123",
  "tissue_type": "brain",      # ← the proposed new value
  "subject": "Subject:abc-123" # ← raw ref string; or expanded map if declared in expand:
  ...
}
```

---

### Available CEL Functions

The CEL sandbox has **no I/O-capable functions registered**. The following standard CEL
functions are available:

**Comparison:** `==`, `!=`, `<`, `<=`, `>`, `>=`  
**Logical:** `&&`, `||`, `!`  
**String:** `contains()`, `startsWith()`, `endsWith()`, `matches()` (regex), `size()`  
**List:** `size()`, `in` operator, `all()`, `exists()`, `filter()`, `map()`  
**Map:** `has()` (field presence check), key access via `.field` or `["field"]`  
**Type:** `type()`, `int()`, `double()`, `string()`, `bool()`  
**Null:** `== null`, `!= null`  
**Ternary:** `condition ? true_val : false_val`  

**NOT available** (stripped from sandbox):
- `http.*` — no HTTP calls
- `io.*` — no file I/O
- Any function that could cause side effects or non-deterministic results

**Custom functions registered by Hippo:**

| Function | Signature | Description |
|---|---|---|
| `hippo.now()` | `() → string` | Current UTC timestamp as ISO 8601 string. Use sparingly — makes validators time-dependent. |
| `hippo.matches_type(entity, type_name)` | `(map, string) → bool` | True if entity's `__type__` is `type_name` or a subtype of it. |

---

### Common Patterns

**Check a field is set:**
```cel
entity.tissue_type != null && entity.tissue_type != ""
```

**Check enum value:**
```cel
entity.execution_state in ["pending", "running"]
```

**Conditional on operation type:**
```cel
operation == "create" ? entity.external_id != null : true
```

**Use existing value in update check (immutable field):**
```cel
existing == null || existing.external_id == null || entity.external_id == existing.external_id
```

**Expanded ref navigation:**
```cel
entity.subject != null && entity.subject.is_available == true && entity.subject.species == "Homo sapiens"
```

**Expanded list — check all elements:**
```cel
entity.samples.all(s, s.tissue_type == "brain")
```

**Expanded list — check count:**
```cel
entity.samples.size() >= 1
```

**Expanded list — check any element:**
```cel
entity.samples.exists(s, s.is_available == true)
```

**Subtype check:**
```cel
hippo.matches_type(entity, "Sample")   # true for Sample and BrainSample, CellLine, etc.
entity.__type__ == "BrainSample"        # exact type check
```

---

### CEL Type Coercion Notes

- CEL integers are 64-bit signed. Schema `int` values map directly.
- CEL `double` (float64) is used for schema `float`. Comparisons like `entity.age > 18`
  work correctly; `entity.age > 18.0` is equivalent.
- Schema `date` and `datetime` values are strings in CEL. To compare dates, compare
  the strings lexicographically (ISO 8601 dates sort correctly as strings).
- Schema `json` fields become CEL maps or lists depending on the JSON value type.
  Accessing a key on a `null` json field returns `null` (not an error) in CEL.

---
