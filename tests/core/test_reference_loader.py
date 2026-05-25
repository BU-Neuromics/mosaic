"""Tests for the ReferenceLoader ABC, LoadResult, FakeReferenceLoader, and
entry-point discovery in cli.commands.reference."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

import pytest
from pydantic import BaseModel

from hippo.core.loaders.reference import EntityRef, LoadResult, ReferenceLoader


class _StubClient:
    """Tiny stand-in for HippoClient used by loader unit tests.

    Returns a deterministic synthetic UUID for each ``put`` so
    ``LoadResult.entities`` is populated without spinning up a real
    storage adapter.
    """

    def __init__(self) -> None:
        self._counter = 0
        self.puts: list[tuple[str, dict]] = []

    def put(self, entity_type: str, data: dict) -> dict:
        self._counter += 1
        entity_id = f"stub-{entity_type}-{self._counter:03d}"
        self.puts.append((entity_type, dict(data)))
        return {"id": entity_id, "entity_type": entity_type, "data": data}


# ---------------------------------------------------------------------------
# ABC enforcement
# ---------------------------------------------------------------------------


class TestReferenceLoaderABC:
    """ReferenceLoader cannot be instantiated directly or via partial subclass."""

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            ReferenceLoader()  # type: ignore[abstract]

    def test_partial_subclass_missing_versions_fails(self):
        class MissingVersions(ReferenceLoader):
            name = "x"
            description = ""

            def entity_types(self) -> list[str]:
                return []

            def schema_fragment(self) -> dict:
                return {}

            def load(self, client, version, params=None):
                return LoadResult()

        with pytest.raises(TypeError):
            MissingVersions()  # type: ignore[abstract]

    def test_partial_subclass_missing_load_fails(self):
        class MissingLoad(ReferenceLoader):
            name = "x"
            description = ""

            def versions(self) -> list[str]:
                return []

            def entity_types(self) -> list[str]:
                return []

            def schema_fragment(self) -> dict:
                return {}

        with pytest.raises(TypeError):
            MissingLoad()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self):
        class Complete(ReferenceLoader):
            name = "complete"
            description = ""

            def versions(self) -> list[str]:
                return ["test"]

            def entity_types(self) -> list[str]:
                return ["Foo"]

            def schema_fragment(self) -> dict:
                return {"default_prefix": "complete"}

            def load(self, client, version, params=None) -> LoadResult:
                return LoadResult(created=1)

        loader = Complete()
        assert loader.versions() == ["test"]
        assert loader.entity_types() == ["Foo"]


# ---------------------------------------------------------------------------
# Default method behavior
# ---------------------------------------------------------------------------


class _MinimalLoader(ReferenceLoader):
    name = "minimal"
    description = "minimal loader for testing defaults"

    def __init__(self):
        self.load_calls: list[tuple[Any, str, Any]] = []

    def versions(self) -> list[str]:
        return ["v1", "v2", "test"]

    def entity_types(self) -> list[str]:
        return ["Thing"]

    def schema_fragment(self) -> dict:
        return {"default_prefix": "minimal"}

    def load(self, client, version, params=None) -> LoadResult:
        self.load_calls.append((client, version, params))
        return LoadResult(created=1)


class TestDefaultMethods:
    def test_default_validate_raises_with_loader_name_in_message(self):
        loader = _MinimalLoader()
        with pytest.raises(NotImplementedError) as exc:
            loader.validate(user_artifact=object())
        assert "minimal" in str(exc.value)
        assert "validate" in str(exc.value)

    def test_default_upgrade_delegates_to_load_with_to_version_and_params(self):
        loader = _MinimalLoader()
        sentinel_client = object()
        sentinel_params = object()

        result = loader.upgrade(
            sentinel_client, "v1", "v2", params=sentinel_params  # type: ignore[arg-type]
        )

        assert isinstance(result, LoadResult)
        assert loader.load_calls == [(sentinel_client, "v2", sentinel_params)]


# ---------------------------------------------------------------------------
# LoadResult shape
# ---------------------------------------------------------------------------


class TestEntityRef:
    """v2 ``EntityRef`` handle (spec §2.14.8)."""

    def test_is_frozen(self):
        ref = EntityRef(id="abc", type="FakeTerm")
        with pytest.raises(Exception):
            ref.id = "xyz"  # type: ignore[misc]

    def test_equality_and_hashable(self):
        a = EntityRef(id="x", type="T")
        b = EntityRef(id="x", type="T")
        c = EntityRef(id="y", type="T")
        assert a == b
        assert hash(a) == hash(b)
        assert a != c

    def test_from_put_result_uses_id_and_entity_type(self):
        put_dict = {
            "id": "stub-FakeTerm-001",
            "entity_type": "FakeTerm",
            "data": {"label": "alpha"},
        }
        ref = EntityRef.from_put_result(put_dict)
        assert ref == EntityRef(id="stub-FakeTerm-001", type="FakeTerm")

    def test_from_put_result_missing_keys_raises(self):
        with pytest.raises(KeyError):
            EntityRef.from_put_result({"id": "x"})
        with pytest.raises(KeyError):
            EntityRef.from_put_result({"entity_type": "T"})


class TestLoadResult:
    def test_defaults_are_zero_and_empty(self):
        r = LoadResult()
        assert r.created == 0
        assert r.updated == 0
        assert r.unchanged == 0
        assert r.errors == 0
        assert r.error_messages == []
        assert r.entities == []

    def test_constructable_with_entities_and_counters(self):
        refs = [
            EntityRef(id="a", type="FakeTerm"),
            EntityRef(id="b", type="FakeTerm"),
        ]
        r = LoadResult(created=2, entities=refs)
        assert r.created == 2
        assert r.entities == refs
        # Mixed-class loaders use a heterogeneous list — D2.14.K-3.
        mixed = LoadResult(
            created=2,
            entities=[
                EntityRef(id="g1", type="Gene"),
                EntityRef(id="t1", type="Transcript"),
            ],
        )
        assert {e.type for e in mixed.entities} == {"Gene", "Transcript"}

    def test_error_messages_are_isolated_per_instance(self):
        a = LoadResult()
        b = LoadResult()
        a.error_messages.append("boom")
        assert b.error_messages == []

    def test_entities_are_isolated_per_instance(self):
        a = LoadResult()
        b = LoadResult()
        a.entities.append(EntityRef(id="x", type="T"))
        assert b.entities == []


# ---------------------------------------------------------------------------
# FakeReferenceLoader (test fixture)
# ---------------------------------------------------------------------------


class TestFakeReferenceLoader:
    def test_fake_loader_is_a_reference_loader(self):
        from hippo.testing.fake_reference_loader import FakeReferenceLoader

        loader = FakeReferenceLoader()
        assert isinstance(loader, ReferenceLoader)
        assert loader.name == "fake"
        assert "test" in loader.versions()
        assert loader.entity_types() == ["FakeTerm"]
        assert loader.schema_fragment()["default_prefix"] == "fake"

    def test_fake_loader_load_returns_loadresult(self):
        from hippo.testing.fake_reference_loader import FakeReferenceLoader

        loader = FakeReferenceLoader()
        # ``load()`` calls ``client.put()`` on each row (PTS-229 made the
        # fake actually persist so install/upgrade tests have rows to
        # query/prune). A small stub is sufficient for this unit-level
        # contract check — the integration test in
        # tests/cli/test_reference_install_upgrade.py covers the real
        # client path end-to-end.
        client = _StubClient()
        result = loader.load(client=client, version="test")
        assert isinstance(result, LoadResult)
        assert result.created == 2
        assert len(result.entities) == 2
        assert all(isinstance(e, EntityRef) for e in result.entities)
        assert all(e.type == "FakeTerm" for e in result.entities)

    def test_fake_loader_unknown_version_returns_error(self):
        from hippo.testing.fake_reference_loader import FakeReferenceLoader

        loader = FakeReferenceLoader()
        result = loader.load(client=None, version="nonexistent")
        assert result.errors == 1
        assert result.error_messages == ["unknown version: nonexistent"]

    def test_fake_loader_declares_pydantic_params_schema(self):
        from hippo.testing.fake_reference_loader import (
            FakeLoadParams,
            FakeReferenceLoader,
        )

        assert FakeReferenceLoader.load_params_schema is FakeLoadParams
        assert issubclass(FakeLoadParams, BaseModel)


# ---------------------------------------------------------------------------
# Entry-point discovery
# ---------------------------------------------------------------------------


class _FakeEntryPoint:
    """Minimal stand-in for importlib.metadata.EntryPoint used in tests."""

    def __init__(self, name: str, value: str, target: Any):
        self.name = name
        self.value = value
        self._target = target

    def load(self) -> Any:
        return self._target


class _FakeEntryPoints:
    def __init__(self, eps: list[_FakeEntryPoint]):
        self._eps = eps

    def select(self, *, group: str) -> list[_FakeEntryPoint]:
        return list(self._eps)


class TestDiscoverReferenceLoaders:
    def _patch_entry_points(self, monkeypatch, eps: list[_FakeEntryPoint]) -> None:
        import importlib.metadata as md

        monkeypatch.setattr(md, "entry_points", lambda: _FakeEntryPoints(eps))

    def test_discovery_returns_instance_for_valid_loader(self, monkeypatch):
        from hippo.cli.commands import reference as ref_cmd
        from hippo.testing.fake_reference_loader import FakeReferenceLoader

        self._patch_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint(
                    "fake",
                    "hippo.testing.fake_reference_loader:FakeReferenceLoader",
                    FakeReferenceLoader,
                )
            ],
        )

        loaders = ref_cmd.discover_reference_loaders()

        assert len(loaders) == 1
        entry = loaders[0]
        assert entry["name"] == "fake"
        assert entry["class"] == "FakeReferenceLoader"
        assert isinstance(entry["instance"], FakeReferenceLoader)
        assert isinstance(entry["instance"], ReferenceLoader)

    def test_discovery_raises_clear_error_for_non_subclass(self, monkeypatch):
        from hippo.cli.commands import reference as ref_cmd

        class NotALoader:
            pass

        self._patch_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint(
                    "bogus",
                    "some.module:NotALoader",
                    NotALoader,
                )
            ],
        )

        with pytest.raises(ref_cmd.ReferenceLoaderRegistrationError) as exc:
            ref_cmd.discover_reference_loaders()

        msg = str(exc.value)
        assert "bogus" in msg
        assert "ReferenceLoader" in msg

    def test_discovery_raises_clear_error_for_non_class_object(self, monkeypatch):
        from hippo.cli.commands import reference as ref_cmd

        self._patch_entry_points(
            monkeypatch,
            [
                _FakeEntryPoint("instance_ep", "some.module:instance", object())
            ],
        )

        with pytest.raises(ref_cmd.ReferenceLoaderRegistrationError):
            ref_cmd.discover_reference_loaders()
