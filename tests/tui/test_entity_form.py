"""Tests for EntityFormScreen — coercion, validation, and save flows."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip(
    "textual", reason="textual not installed; run: pip install datahelix-mosaic[tui]"
)

from textual.widgets import Input, Select, Static

from mosaic.tui.backend.protocol import FieldInfo
from mosaic.tui.views.entity_form import (
    EntityFormScreen,
    FieldCoercionError,
    coerce_field,
    editable_fields,
    format_initial,
)


# ---------------------------------------------------------------------------
# Unit tests: coercion
# ---------------------------------------------------------------------------


def test_coerce_integer():
    field = FieldInfo("n", "integer")
    assert coerce_field(field, "42") == 42


def test_coerce_float():
    field = FieldInfo("v", "float")
    assert coerce_field(field, "1.5") == 1.5


def test_coerce_boolean():
    field = FieldInfo("b", "boolean")
    assert coerce_field(field, "true") is True
    assert coerce_field(field, "No") is False


def test_coerce_string_passthrough():
    field = FieldInfo("s", "string")
    assert coerce_field(field, "hello") == "hello"


def test_coerce_empty_returns_none():
    field = FieldInfo("s", "string")
    assert coerce_field(field, "  ") is None


def test_coerce_multivalued_splits_commas():
    field = FieldInfo("tags", "string", multivalued=True)
    assert coerce_field(field, "a, b, c") == ["a", "b", "c"]


def test_coerce_multivalued_typed():
    field = FieldInfo("nums", "integer", multivalued=True)
    assert coerce_field(field, "1, 2") == [1, 2]


def test_coerce_bad_integer_raises():
    field = FieldInfo("n", "integer")
    with pytest.raises(FieldCoercionError):
        coerce_field(field, "abc")


def test_coerce_bad_boolean_raises():
    field = FieldInfo("b", "boolean")
    with pytest.raises(FieldCoercionError):
        coerce_field(field, "maybe")


def test_format_initial_round_trips():
    assert format_initial(None) == ""
    assert format_initial(True) == "true"
    assert format_initial([1, 2]) == "1, 2"
    assert format_initial("x") == "x"


def test_editable_fields_excludes_system_and_identifier(fake_backend):
    sample = fake_backend.schema.get_entity_type("Sample")
    sample.fields.append(FieldInfo("id", "string", identifier=True))
    sample.fields.append(FieldInfo("is_available", "boolean"))
    names = [f.name for f in editable_fields(sample)]
    assert "id" not in names
    assert "is_available" not in names
    assert "name" in names


# ---------------------------------------------------------------------------
# Pilot tests: form behaviour
# ---------------------------------------------------------------------------


def _form_app(backend, entity_id=None, initial=None):
    from mosaic.tui.app import MosaicTUIApp

    app = MosaicTUIApp(backend=backend)
    schema = backend.schema.get_entity_type("Sample")
    form = EntityFormScreen(
        backend=backend,
        entity_type="Sample",
        entity_schema=schema,
        entity_id=entity_id,
        initial=initial,
    )
    return app, form


def test_form_create_saves_coerced_data(fake_backend):
    app, form = _form_app(fake_backend)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(form, results.append)
            await pilot.pause()

            form.query_one("#field-name", Input).value = "S9"
            form.query_one("#field-volume_ml", Input).value = "2.5"
            form.query_one("#field-tags", Input).value = "a, b"
            form.query_one("#field-status", Select).value = "active"
            form.query_one("#field-frozen", Select).value = "true"
            await form._save()
            await pilot.pause()

    asyncio.run(run())
    creates = [c for c in fake_backend.calls if c[0] == "create_entity"]
    assert len(creates) == 1
    _, (entity_type, data) = creates[0]
    assert entity_type == "Sample"
    assert data == {
        "name": "S9",
        "volume_ml": 2.5,
        "tags": ["a", "b"],
        "status": "active",
        "frozen": True,
    }
    assert results and results[0]  # dismissed with the new entity id


def test_form_required_field_blocks_save(fake_backend):
    app, form = _form_app(fake_backend)

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(form)
            await pilot.pause()

            # leave required 'name' empty
            await form._save()
            await pilot.pause()
            error = str(form.query_one("#form-error", Static).renderable)
            assert "name" in error and "required" in error

    asyncio.run(run())
    assert not [c for c in fake_backend.calls if c[0] == "create_entity"]


def test_form_backend_error_shown_inline(fake_backend):
    app, form = _form_app(fake_backend)

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(form)
            await pilot.pause()

            # Passes client-side checks but FakeBackend rejects blank name
            form.query_one("#field-name", Input).value = " "
            form.query_one("#field-volume_ml", Input).value = "bad-number"
            await form._save()
            await pilot.pause()
            error = str(form.query_one("#form-error", Static).renderable)
            assert "volume_ml" in error

    asyncio.run(run())


def test_form_edit_prefills_and_updates(seeded_fake_backend):
    backend = seeded_fake_backend
    sample_id = next(iter(backend.entities["Sample"]))
    initial = backend.entities["Sample"][sample_id]["data"]
    app, form = _form_app(backend, entity_id=sample_id, initial=initial)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(form, results.append)
            await pilot.pause()

            name_input = form.query_one("#field-name", Input)
            assert name_input.value == "S1"
            name_input.value = "S1-renamed"
            await form._save()
            await pilot.pause()

    asyncio.run(run())
    updates = [c for c in backend.calls if c[0] == "update_entity"]
    assert len(updates) == 1
    _, (entity_type, entity_id, data) = updates[0]
    assert entity_id == sample_id
    assert data["name"] == "S1-renamed"
    assert results == [sample_id]


def test_form_escape_cancels(fake_backend):
    app, form = _form_app(fake_backend)
    results: list = []

    async def run():
        async with app.run_test(headless=True, size=(100, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(form, results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(run())
    assert results == [None]
    assert not [c for c in fake_backend.calls if c[0] == "create_entity"]
