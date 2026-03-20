# DRS Router and Self-URI in Entity Responses

## Why

Two related capabilities needed for federation and interoperability:

1. **`self` field in entity responses** — every entity returned by the Hippo API should
   include a `self` field containing its canonical DRS URI (`drs://host/{id}`). This makes
   entities self-describing: a JSON dump of entities can be re-imported by any Hippo
   instance and traced back to the authoritative source without additional metadata. Inspired
   by the email thread analogy — each message carries the address of every participant so
   the chain is reconstructible from any node.

2. **DRS router in `hippo serve`** — implement the GA4GH Data Repository Service (DRS) v1
   API as an optional router alongside the existing REST API. Enables standard cross-tool
   and cross-institution resolution of Hippo entities via `drs://` URIs.

## What Changes

### `self` field

Every entity response gains a computed `self` field:

```json
{
  "id": "abc-123",
  "entity_type": "AlignmentFile",
  "self": "drs://bass.brainbank-a.org/abc-123",
  "data": { ... },
  "version": 3,
  "created_at": "...",
  "updated_at": "..."
}
```

- Computed at response time from `drs.base_url` config + entity ID. Never stored.
- Falls back to `https://{api_host}/entities/{id}` when DRS is disabled.
- Present in all entity responses: single-entity get, list, query, history, search results.

### DRS router

New endpoints added to the FastAPI app when `drs.enabled: true`:

```
GET /ga4gh/drs/v1/objects/{entity_id}
→ DRS object: id, self_uri, name, aliases, access_methods[], checksums (if available)

GET /ga4gh/drs/v1/objects/{entity_id}/access/{access_id}
→ { url: "s3://..." } or { url: "https://..." }  (the physical access URL)
```

For file-bearing entities (those with a `uri` field in their data): `access_methods`
includes the entity's `uri` as an access method. For pure-metadata entities: `access_methods`
is empty — the DRS object resolves to JSON metadata only.

### Configuration

```yaml
# hippo.yaml
drs:
  enabled: true
  base_url: "https://bass.brainbank-a.org"  # used to construct drs:// URIs
  auth: bearer                               # passport_visa: deferred to v0.3
  public: false                              # if true, no auth required for DRS endpoints
```

### `uri` field placement

`uri` is NOT a system field. Entity types that represent physical artifacts declare it
in their schema:

```yaml
entities:
  DataFile:
    fields:
      uri:
        type: uri
        required: true
```

Pure-metadata entity types (DESeqResult, QCMetrics, etc.) declare no `uri` field.

## Capabilities

### New Capabilities
- `drs-router` — GA4GH DRS v1 endpoints in hippo serve
- `self-uri` — computed self field in all entity responses

### Modified Capabilities
- `hippo-architecture` — DRS as optional router, config schema update
- `hippo-data-model` — self field documented

## Open Questions

### Passport/Visa auth (deferred to v0.3)
Full GA4GH Passport/Visa auth for cross-institution controlled-access data sharing.
Bearer token is sufficient for v0.1 and v0.2 single-institution deployments.

### DRS sidecar process (deferred)
For deployments that need DRS on a separate public-facing port with different auth
policy than the main API — split DRS router into a standalone sidecar process.
The router isolation in this change makes that a config-level change when needed.

## Impact

- New `drs/` router module in `src/hippo/serve/routers/`
- `hippo.yaml` gains `drs:` config block (validated by HippoConfig)
- Entity response serializer adds computed `self` field
- All existing tests unaffected (self field is additive)
- New tests: DRS endpoint responses, self field presence, access method resolution
