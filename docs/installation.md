# Installation

Hippo is a metadata tracking service. This guide covers installing Hippo in production and development environments.

## Requirements

- Python 3.11 or later
- pip or uv package manager (uv recommended for faster installs)

## Install Methods

### Using pip

```bash
pip install hippo
```

### Using uv

```bash
uv add hippo
```

## Development Install

To set up Hippo for local development:

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/hippo.git
   cd hippo
   ```

2. Install with development dependencies:
   ```bash
   uv sync --extra dev
   ```

3. Verify the installation by running the test suite:
   ```bash
   uv run pytest
   ```

## Verify Installation

After installation, verify the CLI is working:

```bash
hippo --help
```

This should display the Hippo CLI help message with available commands.
