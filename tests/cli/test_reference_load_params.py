"""Tests for the ``load_params_schema`` → ``--flag`` CLI rendering (PTS-230).

Decision D2.14.D: loaders that declare a Pydantic v2 ``load_params_schema``
get their fields auto-rendered as ``--<field-name>`` flags on
``hippo reference install`` / ``upgrade``. The CLI validates user input
before invoking ``load()``.

These tests cover the acceptance criteria from PTS-230:

- Round-trip per supported field type (``str``, ``int``, ``bool``,
  ``list[str]``, ``Optional[str]``).
- Required field without a default raises a clear error naming the field.
- Pydantic validation errors surface with the field path.
- Loaders that declare no schema receive ``params=None`` and reject any
  unexpected ``--flag``.
- Unsupported field types raise at *registration time*, not at use.
- Default values from the model are preserved when the flag is omitted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field
from typer.testing import CliRunner

from hippo.cli.commands.reference import (
    ReferenceLoaderRegistrationError,
    _classify_load_params_field,
    _validate_load_params_schema,
    find_loader,
    parse_load_params,
)
from hippo.cli.main import app
from hippo.testing.fake_reference_loader import (
    BareReferenceLoader,
    RichParams,
    RichParamsLoader,
)


@pytest.fixture
def hippo_workspace(tmp_path: Path) -> dict[str, Path]:
    db_path = tmp_path / "hippo.db"
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()
    return {"db": db_path, "schemas": schema_dir}


@pytest.fixture(autouse=True)
def _reset_loader_state():
    """The fixture loaders stash the most-recent params on the class.

    Reset before every test so assertions on ``last_params`` aren't
    polluted by leakage from a sibling test.
    """
    RichParamsLoader.last_params = None
    BareReferenceLoader.last_params_was_none = None


# ---------------------------------------------------------------------------
# Round-trips through the helper (``parse_load_params``).
# ---------------------------------------------------------------------------


class TestParseLoadParams:
    """Drive ``parse_load_params`` directly so per-type behaviour is
    asserted in isolation from the rest of the install lifecycle."""

    def test_all_supported_types_round_trip(self):
        loader = RichParamsLoader()
        params = parse_load_params(
            loader,
            [
                "--organism",
                "mus_musculus",
                "--release",
                "110",
                "--cleanup",
                "--gene-biotypes",
                "protein_coding",
                "--gene-biotypes",
                "lncRNA",
                "--optional-tag",
                "ensembl",
            ],
        )
        assert isinstance(params, RichParams)
        assert params.organism == "mus_musculus"
        assert params.release == 110
        assert params.cleanup is True
        assert params.gene_biotypes == ["protein_coding", "lncRNA"]
        assert params.optional_tag == "ensembl"

    def test_bool_no_flag_yields_false(self):
        loader = RichParamsLoader()
        params = parse_load_params(
            loader, ["--organism", "homo_sapiens", "--no-cleanup"]
        )
        assert params.cleanup is False

    def test_defaults_preserved_when_flags_omitted(self):
        loader = RichParamsLoader()
        params = parse_load_params(loader, ["--organism", "homo_sapiens"])
        # release default
        assert params.release == 110
        # bool default
        assert params.cleanup is False
        # list default preserved when no --gene-biotypes is passed
        assert params.gene_biotypes == ["protein_coding"]
        # Optional[str] default
        assert params.optional_tag is None

    def test_list_user_values_replace_default(self):
        loader = RichParamsLoader()
        params = parse_load_params(
            loader,
            [
                "--organism",
                "homo_sapiens",
                "--gene-biotypes",
                "miRNA",
            ],
        )
        # The model default is ["protein_coding"]; the user passed one
        # explicit value. The result MUST be just ["miRNA"], not the
        # default with the user's value appended.
        assert params.gene_biotypes == ["miRNA"]

    def test_missing_required_field_errors_with_field_name(self):
        loader = RichParamsLoader()
        with pytest.raises(ValueError, match=r"Invalid --flag.*rich"):
            parse_load_params(loader, ["--release", "110"])

    def test_pydantic_constraint_violation_surfaces_field_path(self):
        loader = RichParamsLoader()
        # release has Field(ge=1, le=1000) — 9999 violates le.
        with pytest.raises(ValueError) as exc_info:
            parse_load_params(
                loader, ["--organism", "homo_sapiens", "--release", "9999"]
            )
        # The Pydantic error message names the offending field so the
        # user can fix it without reading the source.
        assert "release" in str(exc_info.value)

    def test_argparse_type_error_surfaces_cleanly(self):
        loader = RichParamsLoader()
        with pytest.raises(ValueError, match=r"Invalid --flag"):
            # release expects an int — "abc" should be rejected by
            # argparse before Pydantic sees it.
            parse_load_params(
                loader,
                ["--organism", "homo_sapiens", "--release", "abc"],
            )

    def test_loader_without_schema_accepts_no_flags(self):
        loader = BareReferenceLoader()
        assert parse_load_params(loader, []) is None

    def test_loader_without_schema_rejects_extra_flags(self):
        loader = BareReferenceLoader()
        with pytest.raises(ValueError, match=r"accepts no --flag"):
            parse_load_params(loader, ["--organism", "human"])


# ---------------------------------------------------------------------------
# Registration-time validation of unsupported types.
# ---------------------------------------------------------------------------


class TestRegistrationValidation:
    """Loader-author errors must surface at registration, not first use."""

    def test_unsupported_field_type_raises_at_registration(self):
        # dict[str, int] isn't in the v1 supported set; the validator
        # MUST flag it so the loader author finds out at install time
        # rather than when an end user tries `hippo reference install`.
        class BadModel(BaseModel):
            mapping: dict[str, int] = Field(default_factory=dict)

        with pytest.raises(ReferenceLoaderRegistrationError) as exc_info:
            _validate_load_params_schema("badloader", BadModel)
        msg = str(exc_info.value)
        assert "badloader" in msg
        assert "mapping" in msg
        assert "not supported" in msg

    def test_classify_field_handles_optional_unwrap(self):
        # Optional[str] should be treated as str.
        kind, base = _classify_load_params_field(str | None)
        assert kind == "str"
        assert base is str

        kind, base = _classify_load_params_field(int | None)
        assert kind == "int"

        kind, base = _classify_load_params_field(bool | None)
        assert kind == "bool"

        # Optional[list[str]] should resolve to list_str
        kind, base = _classify_load_params_field(list[str] | None)
        assert kind == "list_str"

    def test_classify_field_rejects_exotic_unions(self):
        # Union of two non-None types is out of scope.
        kind, _ = _classify_load_params_field(str | int)
        assert kind == "unsupported"

    def test_discover_loaders_validates_each_schema(self):
        # The good loaders (fake, rich, bare) MUST be discoverable
        # without errors. If a loader with a bad schema is registered
        # via entry points, discover_reference_loaders() raises with the
        # loader and field named. We assert the green path here; the
        # red path is covered by the unit test above so we don't have
        # to pollute the entry-point registry with a deliberately broken
        # loader.
        from hippo.cli.commands.reference import discover_reference_loaders

        loaders = {info["name"] for info in discover_reference_loaders()}
        assert {"fake", "rich", "bare"} <= loaders


# ---------------------------------------------------------------------------
# End-to-end via Typer (the install/upgrade verbs).
# ---------------------------------------------------------------------------


class TestCliRoundTrip:
    """Drive the actual Typer commands so the
    ``allow_extra_args + ignore_unknown_options`` wiring is exercised."""

    def test_install_passes_flags_to_loader(self, hippo_workspace):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "rich",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
                "--organism",
                "mus_musculus",
                "--release",
                "112",
                "--cleanup",
                "--gene-biotypes",
                "protein_coding",
                "--gene-biotypes",
                "lncRNA",
                "--optional-tag",
                "ensembl",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Installed rich@v1" in result.output

        params = RichParamsLoader.last_params
        assert params is not None
        assert params.organism == "mus_musculus"
        assert params.release == 112
        assert params.cleanup is True
        assert params.gene_biotypes == ["protein_coding", "lncRNA"]
        assert params.optional_tag == "ensembl"

    def test_install_loader_flags_interleaved_with_known_options(
        self, hippo_workspace
    ):
        # Click+Typer parse known options regardless of position when
        # ignore_unknown_options=True. Cover both orderings explicitly:
        # the parser must not consume `--organism human` as a value for
        # the preceding known option.
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "rich",
                "--organism",
                "homo_sapiens",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
            ],
        )
        assert result.exit_code == 0, result.output
        assert RichParamsLoader.last_params.organism == "homo_sapiens"

    def test_install_missing_required_flag_fails_cleanly(self, hippo_workspace):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "rich",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
            ],
        )
        assert result.exit_code != 0
        # The CLI must surface "organism" somewhere in the error output
        # so the user knows which flag they forgot.
        assert "organism" in result.output

    def test_install_pydantic_constraint_violation(self, hippo_workspace):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "rich",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
                "--organism",
                "homo_sapiens",
                "--release",
                "9999",
            ],
        )
        assert result.exit_code != 0
        assert "release" in result.output

    def test_install_bare_loader_with_no_flags(self, hippo_workspace):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "bare",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
            ],
        )
        assert result.exit_code == 0, result.output
        assert BareReferenceLoader.last_params_was_none is True

    def test_install_bare_loader_rejects_extra_flag(self, hippo_workspace):
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "reference",
                "install",
                "bare",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
                "--organism",
                "human",
            ],
        )
        assert result.exit_code != 0
        assert "accepts no --flag" in result.output

    def test_upgrade_passes_flags_to_loader(self, hippo_workspace):
        runner = CliRunner()
        runner.invoke(
            app,
            [
                "reference",
                "install",
                "rich",
                "--version",
                "test",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
                "--organism",
                "homo_sapiens",
            ],
        )
        RichParamsLoader.last_params = None  # reset between invocations

        result = runner.invoke(
            app,
            [
                "reference",
                "upgrade",
                "rich",
                "--version",
                "v1",
                "--db-path",
                str(hippo_workspace["db"]),
                "--schema-dir",
                str(hippo_workspace["schemas"]),
                "--organism",
                "mus_musculus",
                "--release",
                "112",
            ],
        )
        assert result.exit_code == 0, result.output
        params = RichParamsLoader.last_params
        assert params is not None
        assert params.organism == "mus_musculus"
        assert params.release == 112


# ---------------------------------------------------------------------------
# find_loader smoke (used by the Typer command pre-parse hook).
# ---------------------------------------------------------------------------


def test_find_loader_returns_instance_for_rich():
    info = find_loader("rich")
    assert isinstance(info["instance"], RichParamsLoader)
    assert info["instance"].load_params_schema is RichParams
