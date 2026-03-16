## ADDED Requirements

### Requirement: CLI help displays all commands
When a user runs `hippo --help`, the system SHALL display all available commands including init, serve, migrate, validate, ingest, reference (install, update, list), and compile-schema with their descriptions.

#### Scenario: Help shows all commands
- **WHEN** user runs `hippo --help`
- **THEN** the output includes: init, serve, migrate, validate, ingest, reference install, reference update, reference list, compile-schema

#### Scenario: Help shows command descriptions
- **WHEN** user runs `hippo --help`
- **THEN** each command has a description explaining its purpose

### Requirement: Project initialization creates directory structure
When a user runs `hippo init`, the system SHALL create a new project structure with config.toml and appropriate directory hierarchy in the current working directory.

#### Scenario: Init creates config.toml
- **WHEN** user runs `hippo init`
- **THEN** a config.toml file is created in the current directory

#### Scenario: Init creates project directories
- **WHEN** user runs `hippo init`
- **THEN** appropriate project directories are created (e.g., schemas/, data/)

### Requirement: CLI commands invoke HippoClient
When a user runs any CLI command, the system SHALL invoke the corresponding HippoClient method and execute without errors.

#### Scenario: Commands are wired to services
- **WHEN** user runs any hippo command
- **THEN** the command correctly invokes the underlying SDK service

### Requirement: CLI help displays for subcommands
When a user runs `hippo <command> --help`, the system SHALL display proper help for that specific command including all options and arguments.

#### Scenario: Subcommand help works
- **WHEN** user runs `hippo init --help`
- **THEN** help for init command is displayed

#### Scenario: Reference subcommand help works
- **WHEN** user runs `hippo reference --help`
- **THEN** help shows reference subcommands (install, update, list)