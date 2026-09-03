from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_is_declared_as_a_shared_rust_binary():
    cargo = (ROOT / "src/kyth-shared-rs/Cargo.toml").read_text(encoding="utf-8")
    assert 'name = "kyth-doctor"' in cargo
    assert 'path = "src/doctor_bin.rs"' in cargo


def test_doctor_is_built_and_copied_into_the_image():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--bin kyth-doctor" in dockerfile
    assert "cp /build/kyth-shared-rs/target/release/kyth-doctor /build/kyth-doctor" in dockerfile
    assert "COPY --from=hub-web-builder --chmod=0755 /build/kyth-doctor /usr/bin/kyth-doctor" in dockerfile


def test_python_doctor_launcher_is_not_installed_over_the_native_binary():
    script = (ROOT / "build_files/scripts/branding/36-misc-utility-installs.sh").read_text(encoding="utf-8")
    assert "install -m 0755 /ctx/kyth-doctor /usr/bin/kyth-doctor" not in script
    assert "kyth-doctor is the native Rust binary" in script
