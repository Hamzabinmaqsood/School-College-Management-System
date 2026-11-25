from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_customer_package_excludes_vendor_and_rejects_embedded_keys(tmp_path):
    spec = spec_from_file_location("customer_package", ROOT / "scripts/package-customer.py")
    packaging = module_from_spec(spec)
    spec.loader.exec_module(packaging)
    files = [
        "backend/apps/licensing/protocol.py",
        "backend/config/settings.py",
        "backend/manage.py",
        "backend/.env.example",
        "backend/requirements/production.txt",
        "docs/DEPLOYMENT.md",
        "docs/LICENSING.md",
        "frontend/dist/school/browser/index.html",
        "vendor-tools/license-generator/private/private.pem",
        "backend/.env",
    ]
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    exported = packaging.stage(tmp_path)
    assert set(exported) == set(files[:8])
    (tmp_path / "frontend/dist/school/browser/index.html").write_bytes(
        b"test fixture -----BEGIN ENCRYPTED PRIVATE KEY-----"
    )
    with pytest.raises(ValueError, match="Private key material"):
        packaging.stage(tmp_path)
