from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_health_check_is_declared_and_packaged_as_native():
    cargo = (ROOT / "src/kyth-shared-rs/Cargo.toml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'name = "kyth-health-check"' in cargo
    assert 'path = "src/health_check_bin.rs"' in cargo
    assert "--bin kyth-health-check" in dockerfile
    assert "COPY --from=hub-web-builder --chmod=0755 /build/kyth-health-check /usr/bin/kyth-health-check" in dockerfile


def test_python_health_launcher_is_not_installed_over_native_binary():
    script = (ROOT / "build_files/scripts/sysconfig.sh").read_text(encoding="utf-8")
    assert "install -Dm0755 /ctx/kyth-health-check /usr/bin/kyth-health-check" not in script
    assert "kyth-health-check is the native Rust binary" in script
