import importlib.resources
import json
import tomllib
from pathlib import Path

import jsonschema


def test_importlib_resources_contains_all_machine_readable_schemas():
    schema_dir = importlib.resources.files("samsung_find.schemas")

    # 1. Master state schema
    master_schema_file = schema_dir.joinpath("master-state-v1.schema.json")
    assert master_schema_file.is_file()
    master_schema = json.loads(master_schema_file.read_text(encoding="utf-8"))
    assert "$id" in master_schema
    assert master_schema["properties"]["schema"]["const"] == "io.github.charlesbel.samsung-account.master"

    # Compare with root schemas/master-state-v1.schema.json
    root_master = json.loads(Path("schemas/master-state-v1.schema.json").read_text(encoding="utf-8"))
    assert master_schema == root_master

    # 2. CLI response envelope schema
    cli_dir = schema_dir.joinpath("cli").joinpath("v1")
    envelope_file = cli_dir.joinpath("cli-response-envelope.schema.json")
    assert envelope_file.is_file()
    envelope_schema = json.loads(envelope_file.read_text(encoding="utf-8"))
    assert "$id" in envelope_schema

    # 3. All CLI schemas
    for schema_name in [
        "status-response.schema.json",
        "devices-response.schema.json",
        "capabilities-response.schema.json",
        "location-response.schema.json",
        "operation-response.schema.json",
    ]:
        schema_file = cli_dir.joinpath(schema_name)
        assert schema_file.is_file()
        content = json.loads(schema_file.read_text(encoding="utf-8"))
        assert "$schema" in content or "title" in content
        # Validate schema itself is valid JSON schema
        jsonschema.Draft202012Validator.check_schema(content)


def test_package_entry_points_include_canonical_and_compatibility_aliases():
    import importlib.metadata

    entry_points = {ep.name: ep.value for ep in importlib.metadata.entry_points(group="console_scripts")}

    # Canonical entry points
    assert "samsung-re-find" in entry_points
    assert entry_points["samsung-re-find"] == "samsung_find.cli:main"

    assert "samsung-re-find-mcp" in entry_points
    assert entry_points["samsung-re-find-mcp"] == "samsung_find.mcp_server:main"

    # Compatibility legacy aliases
    assert "samsung-find" in entry_points
    assert entry_points["samsung-find"] == "samsung_find.cli:main"

    assert "samsung-find-mcp" in entry_points
    assert entry_points["samsung-find-mcp"] == "samsung_find.mcp_server:main"


def test_windows_runtime_has_iana_timezone_database():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert 'tzdata>=2025.2; sys_platform == "win32"' in project["dependencies"]
