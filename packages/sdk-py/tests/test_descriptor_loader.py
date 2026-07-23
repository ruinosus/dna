"""F3 (spec D3): load_descriptors — kinds/*.kind.yaml as package data."""
from __future__ import annotations

import sys
import textwrap

import pytest

from dna.kernel.source.descriptor_loader import load_descriptors


@pytest.fixture()
def tmp_package(tmp_path, monkeypatch):
    """A throwaway importable package with a kinds/ dir."""
    pkg = tmp_path / "f3_tmp_pkg"
    (pkg / "kinds").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield pkg
    sys.modules.pop("f3_tmp_pkg", None)


def _write_descriptor(pkg, name: str, target_kind: str) -> None:
    (pkg / "kinds" / name).write_text(textwrap.dedent(f"""\
        apiVersion: github.com/ruinosus/dna/core/v1
        kind: KindDefinition
        metadata:
          name: {target_kind.lower()}
        spec:
          target_api_version: github.com/ruinosus/dna/test/v1
          target_kind: {target_kind}
          alias: test-{target_kind.lower()}
          origin: github.com/ruinosus/dna/test
          storage:
            type: yaml
            container: {target_kind.lower()}s
    """))


def test_load_descriptors_parses_kind_yamls_sorted(tmp_package):
    _write_descriptor(tmp_package, "zeta.kind.yaml", "Zeta")
    _write_descriptor(tmp_package, "alpha.kind.yaml", "Alpha")
    # non-descriptor files in the dir are ignored
    (tmp_package / "kinds" / "README.md").write_text("not a descriptor")

    raws = load_descriptors("f3_tmp_pkg")
    assert [r["spec"]["target_kind"] for r in raws] == ["Alpha", "Zeta"]
    assert all(r["kind"] == "KindDefinition" for r in raws)


def test_load_descriptors_missing_kinds_dir_is_empty(tmp_package):
    import shutil

    shutil.rmtree(tmp_package / "kinds")
    assert load_descriptors("f3_tmp_pkg") == []


def test_load_descriptors_non_mapping_yaml_raises(tmp_package):
    (tmp_package / "kinds" / "broken.kind.yaml").write_text("- just\n- a list\n")
    with pytest.raises(ValueError, match="broken.kind.yaml"):
        load_descriptors("f3_tmp_pkg")
