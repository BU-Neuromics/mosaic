# Hippo

A runtime for LinkML schemas. Point it at a schema and you get a typed Python SDK, a REST API, a relational database with append-only PROV-O provenance, and CEL-based dynamic validation — without writing any of that infrastructure yourself. **The schema defines the application; Hippo runs it.**

## Start here

- **[Why Hippo?](why-hippo.md)** — the elevator pitch and core idea.
- **[Introduction](introduction.md)** — what Hippo does and how it fits together.
- **[Installation](installation.md)** — install from PyPI or source.
- **[Quick Start](quickstart.md)** — your first schema, store, and query in 10 minutes.

## Build

- **[Schema Guide](schema-guide.md)** — author entities, attributes, and relationships in LinkML.
- **[Data Model](data-model.md)** — how schemas map to relational storage and the graph-shaped API.
- **[Configuration](configuration.md)** — `hippo.yaml`, storage backends, and adapters.

## Use

- **[CLI Reference](cli-reference.md)** — `hippo` command surface.
- **[API Reference](api-reference.md)** — `HippoClient` Python SDK.
- **[Typed Client](reference_typed_client.md)** — schema-derived typed client.

## Extend

- **[Reference Loaders](reference-loaders.md)** and **[Writing a Reference Loader](writing-a-reference-loader.md)** — pull static reference data into Hippo.
- **[Writing a Recipe](writing-a-recipe.md)**, **[Installing Recipes](installing-recipes.md)**, **[Recipe Reference](recipe-reference.md)** — package and share schema fragments.

## Background

- **[Design Principles](design-principles.md)** — what Hippo is opinionated about, and why.
- **[Comparison](comparison.md)** — how Hippo relates to LinkML, Datasette, and friends.

---

Hippo is open source under the MIT license. Source at [github.com/BU-Neuromics/hippo](https://github.com/BU-Neuromics/hippo).
