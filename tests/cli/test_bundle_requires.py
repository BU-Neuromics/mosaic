"""Tests for ``hippo reference bundle-requires`` (PTS-346 item 3 / sec11 §11.6.2).

``Bundle.to_requires()`` / ``requires_yaml()`` were implemented and unit-tested
(``tests/core/test_exposure.py::TestBundle``) but not wired to any user-facing
command. This exercises the CLI surface that generates the deployment's
``requires:`` block from a bundle manifest — paste-ready YAML with a leading
comment naming the bundle and its (validated) version.
"""

import yaml
from typer.testing import CliRunner

from hippo.cli.main import app


def _write(tmp_path, manifest: dict) -> str:
    p = tmp_path / "bundle.yaml"
    p.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return str(p)


def test_generates_requires_block_with_version_header(tmp_path) -> None:
    manifest = _write(
        tmp_path,
        {
            "name": "brainbank-bundle",
            "version": "2024.1",
            "packages": {"core": "2.0.0", "subject": "1.4.0"},
        },
    )
    result = CliRunner().invoke(app, ["reference", "bundle-requires", manifest])

    assert result.exit_code == 0, result.output
    # Leading comment surfaces the bundle name + version (item 1's `version`
    # validation matters precisely because it is rendered here).
    assert "# requires: generated from bundle 'brainbank-bundle'" in result.output
    assert "(version 2024.1)" in result.output
    # The emitted block is valid YAML and carries the exact, sorted pins.
    parsed = yaml.safe_load(result.output)
    assert parsed == {"requires": {"core": "==2.0.0", "subject": "==1.4.0"}}


def test_version_header_omitted_when_absent(tmp_path) -> None:
    manifest = _write(
        tmp_path,
        {"name": "minimal-bundle", "packages": {"core": "1.0.0"}},
    )
    result = CliRunner().invoke(app, ["reference", "bundle-requires", manifest])

    assert result.exit_code == 0, result.output
    assert "# requires: generated from bundle 'minimal-bundle'" in result.output
    assert "version" not in result.output
    assert yaml.safe_load(result.output) == {"requires": {"core": "==1.0.0"}}


def test_malformed_manifest_exits_nonzero(tmp_path) -> None:
    # Missing the required `packages` mapping.
    manifest = _write(tmp_path, {"name": "broken"})
    result = CliRunner().invoke(app, ["reference", "bundle-requires", manifest])

    assert result.exit_code == 1
    assert "Error" in result.output


def test_non_string_version_surfaces_validation_error(tmp_path) -> None:
    # `version: 1.0` parses to a float — item 1's optional-field validation
    # must reject it, and the CLI must surface that rather than silently
    # rendering a float into the generated header.
    manifest = _write(
        tmp_path,
        {"name": "bb", "version": 1.0, "packages": {"core": "1.0.0"}},
    )
    result = CliRunner().invoke(app, ["reference", "bundle-requires", manifest])

    assert result.exit_code == 1
    assert "version" in result.output
