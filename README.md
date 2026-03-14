# Hippo — Metadata Tracking Service

SDK-first, infrastructure-agnostic metadata tracking service for bioinformatics research.

## Design Spec

See [`design/`](design/) for the full architecture and implementation specification.
Start with [`design/INDEX.md`](design/INDEX.md).

## Implementation Plan

See [`plan/`](plan/) for the OpenPlan roadmap, epics, and features.
OpenSpec feature specs live in [`plan/openspec/`](plan/openspec/).

## Quick Start

```bash
pip install hippo

hippo init          # scaffold hippo.yaml + schema.yaml
hippo serve         # start REST server (default: http://127.0.0.1:8000)
```

## Development

```bash
uv sync --extra dev
uv run pytest
```
