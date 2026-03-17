## ADDED Requirements

### Requirement: hippo init creates project directory
When a user runs 'hippo init' in an empty directory, the system SHALL create a new project directory with default configuration files including config.json, README.md, and .gitignore.

#### Scenario: Successful initialization in empty directory
- **WHEN** user runs 'hippo init' in an empty directory
- **THEN** a new project directory is created with config.json, README.md, and .gitignore

#### Scenario: Successful initialization with project name
- **WHEN** user runs 'hippo init my-project' with a valid project name
- **THEN** a directory named 'my-project' is created with default configuration files

### Requirement: hippo init with template flag
When a user runs 'hippo init --template <template>' with a valid template name, the system SHALL generate appropriate project files based on the selected template without overwriting existing files.

#### Scenario: Valid template specified
- **WHEN** user runs 'hippo init --template basic' with a valid template name
- **THEN** project files are generated based on the 'basic' template

#### Scenario: Template does not overwrite existing files
- **WHEN** user runs 'hippo init --template basic' in a directory that already has config.json
- **THEN** existing files are preserved and only missing files are created

### Requirement: Error handling for existing config
When a user runs 'hippo init' in an existing directory that already contains a hippo config file, the system SHALL display a clear error message indicating the conflict and provides guidance for resolution.

#### Scenario: Config file already exists
- **WHEN** user runs 'hippo init' in a directory that already contains config.json
- **THEN** error message "Project already initialized. Use 'hippo status' to view project details." is displayed

### Requirement: Error handling for invalid template
When a user runs 'hippo init' with an invalid template name, the system SHALL return an informative error message listing available templates.

#### Scenario: Invalid template name provided
- **WHEN** user runs 'hippo init --template nonexistent' with an invalid template name
- **THEN** error message "Template 'nonexistent' not found. Available templates: basic, minimal, full" is displayed

### Requirement: Error handling for insufficient permissions
When a user runs 'hippo init' in a directory with insufficient permissions, the system SHALL display an appropriate permission denied message.

#### Scenario: Permission denied on directory creation
- **WHEN** user runs 'hippo init' in a directory without write permissions
- **THEN** error message "Permission denied: cannot create project in this location" is displayed
