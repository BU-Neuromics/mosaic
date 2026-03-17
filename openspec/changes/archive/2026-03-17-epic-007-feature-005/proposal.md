## Why

This change introduces server management commands to the Hippo CLI tool, allowing users to start, stop, and validate Hippo server operations. This provides essential lifecycle management capabilities for deploying and managing Hippo in various environments.

## What Changes

- Introduce `hippo serve` command to start the Hippo server with default or custom configuration
- Add `hippo validate` command to verify configuration files before starting the server
- Implement command-line options for port specification and log level configuration
- Add help functionality to display usage instructions

## Capabilities

### New Capabilities
- `server-management`: Defines the contract for server lifecycle management commands including start, stop, and validation operations

### Modified Capabilities
- `cli-commands`: Extends the command line interface with new subcommands and options

## Impact

- Adds new CLI commands to hippo tool
- Extends existing configuration and command parsing mechanisms
- Requires updated documentation for new commands