"""Template registry and loaders for hippo init."""

from dataclasses import dataclass
from typing import Any


TEMPLATES = {
    "basic": {
        "name": "Basic",
        "description": "Minimal Hippo project with core configuration",
        "files": {
            "config.json": "basic_config",
            ".gitignore": "basic_gitignore",
        },
    },
    "minimal": {
        "name": "Minimal",
        "description": "Lightweight setup with just config.json",
        "files": {
            "config.json": "minimal_config",
            ".gitignore": "minimal_gitignore",
        },
    },
    "full": {
        "name": "Full",
        "description": "Complete project with config, schemas, and sample data",
        "files": {
            "config.json": "full_config",
            "README.md": "full_readme",
            ".gitignore": "full_gitignore",
            "schemas/.keep": "empty",
        },
    },
}


@dataclass
class Template:
    name: str
    description: str
    files: dict[str, str]


def get_template(name: str) -> Template | None:
    """Get a template by name."""
    template_data = TEMPLATES.get(name)
    if template_data is None:
        return None
    return Template(
        name=name,
        description=template_data["description"],
        files=template_data["files"],
    )


def list_templates() -> list[dict[str, str]]:
    """List all available templates."""
    return [
        {"name": name, "description": data["description"]}
        for name, data in TEMPLATES.items()
    ]


def get_template_file_content(file_key: str) -> str | None:
    """Get the content for a template file by key."""
    contents = {
        "basic_config": """{
  "version": "0.1",
  "storage": {
    "type": "sqlite",
    "path": "hippo.db"
  },
  "schema": {
    "type": "linkml"
  }
}
""",
        "minimal_config": """{
  "version": "0.1",
  "storage": {
    "type": "sqlite",
    "path": "hippo.db"
  }
}
""",
        "full_config": """{
  "version": "0.1",
  "name": "hippo-project",
  "description": "Hippo Metadata Tracking Service Project",
  "storage": {
    "type": "sqlite",
    "path": "hippo.db"
  },
  "schema": {
    "type": "linkml",
    "path": "schemas"
  },
  "validation": {
    "enabled": true,
    "strict": false
  },
  "api": {
    "host": "127.0.0.1",
    "port": 8000
  }
}
""",
        "basic_gitignore": """# Hippo
*.db
*.db-journal
*.log

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
""",
        "minimal_gitignore": """# Hippo
*.db
""",
        "full_gitignore": """# Hippo
*.db
*.db-journal
*.log

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Data
data/*.tmp
""",
        "full_readme": """# Hippo Project

This is a Hippo Metadata Tracking Service project.

## Quick Start

```bash
# Start the server
hippo serve

# Validate schemas
hippo validate

# Ingest data
hippo ingest data/sample.csv --entity-type sample
```

## Project Structure

- `config.json` - Project configuration
- `schemas/` - LinkML schema files
- `data/` - Data files for ingestion
""",
        "empty": "",
    }
    return contents.get(file_key)
