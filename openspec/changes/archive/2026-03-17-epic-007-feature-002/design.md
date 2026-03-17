## Context

This change implements the `hippo init` command for the Hippo Metadata Tracking Service. The goal is to enable users to initialize new Hippo projects with proper configuration and directory structure. This is a foundational feature needed before users can start using Hippo to track metadata.

**Current State:**
- Hippo core SDK exists but lacks project initialization
- No CLI command exists to set up new projects
- Users must manually create configuration files

**Dependencies:**
- feature-001: Assumed to provide the core SDK structure and configuration schema

## Goals / Non-Goals

**Goals:**
- Implement `hippo init` CLI command that creates a new project directory
- Generate default configuration files: config.json, README.md, .gitignore
- Support template-based initialization with `--template` flag
- Implement proper error handling for conflicts, invalid templates, and permission issues

**Non-Goals:**
- Remote project creation (future feature)
- Project migration tools (future feature)
- IDE integrations (future feature)

## Decisions

### 1. CLI Framework
**Decision:** Use Click for CLI implementation
**Rationale:** Click is the standard Python CLI framework, integrates well with the existing codebase, and provides built-in support for options, commands, and help text.

### 2. Template Storage
**Decision:** Templates stored as embedded data in the CLI package
**Rationale:** Simplifies distribution - no separate template files to manage. Templates can be versioned with the CLI.

### 3. Directory Creation Strategy
**Decision:** Create project in current directory or named subdirectory
**Rationale:** Matches common CLI patterns (e.g., `npm init`, `cargo init`). Allows flexibility in project placement.

### 4. Error Handling Approach
**Decision:** Fail fast with clear, actionable error messages
**Rationale:** Prevents partial initialization and provides users with immediate guidance for resolution.

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Template system too rigid | Medium | Allow templates to include variable placeholders |
| Permission errors on Windows | Low | Test cross-platform, use appropriate error messages |
| Config schema changes breaking init | Low | Version config file, provide migration path |

## Migration Plan

1. Deploy CLI with `hippo init` command
2. Document new command in user guides
3. Existing projects unaffected (no migration needed)
4. Rollback: Uninstall new CLI version, existing projects continue working

## Open Questions

- Should `hippo init` support interactive mode for configuration?
- Should we validate the generated config against the schema?
