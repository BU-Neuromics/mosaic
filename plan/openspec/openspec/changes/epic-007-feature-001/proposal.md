# CLI Core Infrastructure Setup

## Goal
CLI Core Infrastructure Setup: Establish the basic CLI framework with Typer integration, command structure, and HippoClient wiring for core operations.

## Acceptance Criteria
- Given a user runs 'hippo --help', when they see the command list, then all commands including init, serve, migrate, validate, ingest, reference install/update/list, and validate-schema are properly displayed in the help output
- Given a user executes 'hippo init', when they run the initialization command, then a new project structure is created with proper configuration files including config.toml and project directory structure
- Given a user runs any CLI command, when the HippoClient is invoked, then commands are correctly wired to underlying services and execute without errors
- Given a user runs 'hippo --help', when they see the command list, then the help output includes proper descriptions for each command including init, serve, migrate, validate, ingest, reference install/update/list, and validate-schema
- Given a user executes 'hippo init', when they run the initialization command, then the project structure is created within the current working directory with appropriate file permissions and ownership

## Constraints
- Complexity: low
