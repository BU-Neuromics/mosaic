## Context

The Hippo metadata tracking service requires a configuration system to load and validate hippo.yaml files. Currently, there is no formal configuration model—the system needs a Pydantic-based configuration loader with environment variable substitution support to enable flexible deployment configurations.

This change implements the HippoConfig Pydantic model with validation and a YAML loader that supports environment variable substitution.

## Goals / Non-Goals

**Goals:**
- Implement HippoConfig Pydantic model with field validation
- Create hippo.yaml loader with environment variable substitution (${VAR} syntax)
- Support required field validation with clear ConfigError messages
- Support type validation with descriptive ValidationError messages
- Handle undefined environment variables gracefully with ConfigError

**Non-Goals:**
- Schema compilation or schema loading (future capability)
- Database connection configuration (future capability)
- CLI argument parsing (future capability)
- Configuration hot-reloading (future capability)

## Decisions

1. **Pydantic v2 over v1**: Use Pydantic v2 for better performance and updated validation API.
   - Alternative: Pydantic v1 - deprecated, less performant.

2. **Environment variable syntax ${VAR}**: Use shell-style variable substitution.
   - Alternative: `{{VAR}}` Jinja-style - less familiar to ops teams.
   - Alternative: `$VAR` - harder to distinguish from plain strings.

3. **Validation error hierarchy**: ConfigError for configuration issues, ValidationError for type mismatches.
   - Alternative: Single error type - less granular for debugging.

4. **Strict validation mode**: All fields required unless explicitly optional.
   - Alternative: Partial validation - less clear contract.

## Risks / Trade-offs

- **[Risk] Environment variable expansion order**: Environment variables may not be available at import time.
  - **Mitigation**: Perform expansion at load time, not at class definition.

- **[Risk] Circular dependency in validation**: Config validation may need to import schema objects.
  - **Mitigation**: Keep config module independent; import schema types lazily if needed.

- **[Risk] YAML anchors/aliases**: Environment variable substitution may conflict with YAML anchors.
  - **Mitigation**: Process substitution after YAML parsing, on resolved values only.

## Migration Plan

1. Deploy new HippoConfig class and loader
2. Update any existing code that reads config to use new loader
3. No database migrations required (configuration-only change)

**Rollback**: Revert to previous config handling if issues arise; no data changes.

## Open Questions

- Should we support default values via environment variables (${VAR:-default})?
- Should we support secrets (encrypted values or env var masking in logs)?