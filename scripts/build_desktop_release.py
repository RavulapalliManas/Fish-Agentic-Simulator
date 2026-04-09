"""Build downloadable desktop release artifacts for the current platform."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAURI_CONFIG_PATH = ROOT / "src-tauri" / "tauri.conf.json"
TAURI_BUNDLE_ROOT = ROOT / "src-tauri" / "target" / "release" / "bundle"
RELEASE_ROOT = ROOT / "release"


def main() -> None:
    config = json.loads(TAURI_CONFIG_PATH.read_text(encoding="utf-8"))
    product_name = str(config["productName"])
    version = str(config["version"])
    platform_key = detect_platform_key()

    build_backend()
    build_tauri_app_bundle()

    artifacts = package_release_artifacts(product_name=product_name, version=version, platform_key=platform_key)
    manifest = {
        "product_name": product_name,
        "version": version,
        "platform": platform_key,
        "artifacts": [
            {
                "artifact_path": str(path.resolve()),
                "artifact_name": path.name,
                "sha256": sha256_file(path),
            }
            for path in artifacts
        ],
    }

    manifest_path = RELEASE_ROOT / platform_key / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for artifact in artifacts:
        print(f"Release artifact: {artifact}")
        print(f"Checksum (sha256): {sha256_file(artifact)}")
    print(f"Manifest: {manifest_path}")


def detect_platform_key() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    raise RuntimeError(f"Unsupported release platform: {sys.platform}")


def build_backend() -> None:
    run([sys.executable, "backend/build_backend.py"])


def build_tauri_app_bundle() -> None:
    if sys.platform == "darwin":
        run(["npx", "tauri", "build", "--bundles", "app"])
        return

    if sys.platform.startswith("win"):
        run(["npx", "tauri", "build", "--bundles", "nsis"])
        return

    raise RuntimeError(f"Unsupported release platform: {sys.platform}")


def package_release_artifacts(product_name: str, version: str, platform_key: str) -> list[Path]:
    release_dir = RELEASE_ROOT / platform_key
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    if platform_key == "macos":
        app_bundle = TAURI_BUNDLE_ROOT / "macos" / f"{product_name}.app"
        if not app_bundle.exists():
            raise FileNotFoundError(f"Expected app bundle was not produced: {app_bundle}")

        app_copy = release_dir / app_bundle.name
        shutil.copytree(app_bundle, app_copy)

        arch = normalize_arch(platform.machine())
        artifact_path = release_dir / f"{product_name}_{version}_{arch}.zip"
        if artifact_path.exists():
            artifact_path.unlink()
        run(
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                app_copy.name,
                artifact_path.name,
            ],
            cwd=release_dir,
        )
        return [artifact_path]

    if platform_key == "windows":
        bundle_dir = TAURI_BUNDLE_ROOT / "nsis"
        artifact = first_file(bundle_dir, "*.exe")
        return [copy_file_to_release(artifact, release_dir)]

    raise RuntimeError(f"Unsupported release platform: {platform_key}")


def copy_file_to_release(source: Path, release_dir: Path) -> Path:
    release_dir.mkdir(parents=True, exist_ok=True)
    destination = release_dir / source.name
    shutil.copy2(source, destination)
    return destination


def first_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No artifact matching {pattern} found in {directory}")
    return matches[0]


def normalize_arch(value: str) -> str:
    lowered = value.lower()
    if lowered in {"arm64", "aarch64"}:
        return "aarch64"
    if lowered in {"x86_64", "amd64"}:
        return "x64"
    return lowered


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], cwd: Path | None = None) -> None:
    resolved_command = command.copy()
    resolved_command[0] = resolve_command(command[0])
    print(f"+ {' '.join(command)}")
    subprocess.run(resolved_command, check=True, cwd=str(cwd or ROOT))


def resolve_command(command_name: str) -> str:
    if Path(command_name).name != command_name:
        return command_name

    if sys.platform.startswith("win") and command_name in {"npm", "npx"}:
        command_name = f"{command_name}.cmd"

    resolved = shutil.which(command_name)
    if resolved is None:
        raise FileNotFoundError(f"Unable to locate required command: {command_name}")
    return resolved


if __name__ == "__main__":
    main()
