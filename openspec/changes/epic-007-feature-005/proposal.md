# Server Management Commands

## Goal
Server Management Commands: Add commands to manage the Hippo server lifecycle including starting, stopping, and validating server operations.

## Acceptance Criteria
- Given a user has installed Hippo and runs 'hippo serve', when they execute the serve command, then the Hippo server starts successfully on port 8080 with INFO level logging to stdout
- Given a user has configured a custom log level and runs 'hippo serve', when they execute the serve command, then the Hippo server starts successfully with the specified log level configuration
- Given a user runs 'hippo validate' with a valid configuration file, when they execute the validate command, then all system settings are checked for correctness and compatibility with exit code 0
- Given a user runs 'hippo validate' with an invalid configuration file, when they execute the validate command, then validation fails with descriptive error messages and exit code 1
- Given a user runs 'hippo serve --port 3000', when they specify a custom port, then the Hippo server starts successfully on port 3000 rather than default port 8080
- Given a user runs 'hippo serve --port invalid-port', when they specify an invalid port value, then the Hippo server fails to start with clear error message and exit code 1
- Given a user runs 'hippo serve' with no configuration, when they execute the serve command, then the Hippo server starts using default settings with appropriate warning logs
- Given a user runs 'hippo serve --help', when they request help information, then the command displays usage instructions and available options without error

## Constraints
- Depends on: feature-001
- Complexity: medium
