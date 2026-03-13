## MODIFIED Requirements

### Requirement: Package structure uses generic entity routing
The sec2 package structure (§2.2) SHALL replace entity-specific REST routers (`routers/donors.py`, `routers/samples.py`, `routers/datafiles.py`, `routers/datasets.py`) with a generic entity router (`routers/entities.py`) that dispatches based on entity type strings resolved from schema config.

#### Scenario: No entity-specific router files in package structure
- **WHEN** a reader views the sec2 package structure
- **THEN** the `rest/routers/` directory contains `entities.py` (and optionally `relationships.py`, `ingestion.py`) — not per-entity-type files

### Requirement: SDK code examples use generic query API
The sec2 code examples (§2.5) SHALL demonstrate the generic query API pattern (`client.query("EntityType", field=value)`) rather than entity-specific methods (`client.query.samples(brain_region="hippocampus")`).

#### Scenario: Dependency injection example uses generic API
- **WHEN** a reader views the sec2 dependency injection and SDK usage examples
- **THEN** query calls use `client.query("<entity_type>", ...)` with a string entity type parameter, not entity-specific method names

#### Scenario: REST router example uses generic dispatch
- **WHEN** a reader views the sec2 REST router example
- **THEN** the route handler accepts an entity type as a path parameter (e.g., `/{entity_type}`) and delegates to the SDK's generic query method

### Requirement: Platform diagram is domain-neutral
The sec1 §1.3 platform diagram SHALL use generic module names if referencing future platform components. Domain-specific module names (e.g., "Tissue Registry", "Digital Histology Store") SHALL be generalized or labeled as example modules.

#### Scenario: Platform diagram does not hardcode domain modules
- **WHEN** a reader views the sec1 platform position diagram
- **THEN** future modules are either labeled generically (e.g., "Module B", "Module C") or explicitly marked as examples of what domain-specific modules could look like
