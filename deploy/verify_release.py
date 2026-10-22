from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

IMAGE_PATTERN = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")


def run(*arguments: str) -> None:
    subprocess.run(arguments, check=True)  # noqa: S603


def release_value(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key == name:
            return value.strip().strip('"').strip("'")
    return ""


def main() -> int:
    release_env = Path(os.environ.get("JARVIS_RELEASE_ENV_FILE", "/opt/jarvis/deploy/release.env"))
    image = os.environ.get("JARVIS_IMAGE") or release_value(release_env, "JARVIS_IMAGE")
    if not IMAGE_PATTERN.fullmatch(image):
        print("JARVIS_IMAGE must be an immutable registry image@sha256 reference", file=sys.stderr)
        return 2
    compose = Path(__file__).with_name("compose.production.yaml")
    run(
        "docker",
        "compose",
        "--env-file",
        str(release_env),
        "-f",
        str(compose),
        "config",
        "--quiet",
    )
    run("docker", "pull", image)
    print("Release image and Compose configuration verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
