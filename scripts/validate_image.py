"""Run source checks in a temporary environment inside an existing candidate image.

Invoke in an unprivileged disposable Linux container without production env/files.
The required --commit identifies both the source archive and installed app code.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import re
import subprocess
import tarfile
import tempfile
import venv
from pathlib import Path
from urllib.request import urlopen


def _run(arguments: list[str], directory: Path, environment: dict[str, str]) -> None:
    subprocess.run(arguments, cwd=directory, env=environment, check=True)  # noqa: S603


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.commit):
        parser.error("--commit must be a full lowercase Git commit SHA")
    if os.name != "posix" or os.geteuid() == 0:
        parser.error("Run inside the unprivileged candidate Linux container")

    with tempfile.TemporaryDirectory(prefix="jarvis-quality-") as temporary:
        directory = Path(temporary)
        if os.statvfs(directory).f_flag & os.ST_NOEXEC:
            raise RuntimeError(
                "Temporary test filesystem is noexec; run the disposable test container "
                "with --tmpfs /tmp:rw,exec,nosuid,nodev,size=512m"
            )
        print("TEMP_EXEC=PASS", flush=True)
        url = (
            "https://codeload.github.com/andrewt81/Jarvis-Personal-Assistant/tar.gz/"
            + arguments.commit
        )
        with urlopen(url, timeout=60) as response:  # noqa: S310 - fixed HTTPS GitHub host
            archive = response.read(20 * 1024 * 1024 + 1)
        if len(archive) > 20 * 1024 * 1024:
            raise RuntimeError("Source archive exceeds the validation limit")
        source_parent = directory / "source"
        source_parent.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as source_archive:
            if sum(member.size for member in source_archive.getmembers()) > 100 * 1024 * 1024:
                raise RuntimeError("Expanded source exceeds the validation limit")
            source_archive.extractall(source_parent, filter="data")  # noqa: S202
        roots = list(source_parent.iterdir())
        if len(roots) != 1 or not (roots[0] / "pyproject.toml").is_file():
            raise RuntimeError("Unexpected source archive layout")
        source = roots[0]

        spec = importlib.util.find_spec("jarvis")
        if spec is None or spec.origin is None:
            raise RuntimeError("Candidate application is not installed")
        installed = Path(spec.origin).parent
        expected = source / "backend" / "src" / "jarvis"
        expected_files = {path.relative_to(expected) for path in expected.rglob("*.py")}
        installed_files = {path.relative_to(installed) for path in installed.rglob("*.py")}
        if expected_files != installed_files or any(
            (expected / path).read_bytes() != (installed / path).read_bytes()
            for path in expected_files
        ):
            raise RuntimeError("Installed application does not match the requested source commit")
        print("SOURCE_MATCH=PASS", flush=True)

        checks = directory / "checks"
        venv.EnvBuilder(system_site_packages=True, with_pip=True).create(checks)
        python = str(checks / "bin" / "python")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.update(
            {
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_CACHE_DIR": "1",
                "JARVIS_AI_PROVIDER": "disabled",
            }
        )
        _run(
            [python, "-m", "pip", "install", "pytest==8.4.2", "httpx==0.28.1", "ruff==0.17.1"],
            source,
            environment,
        )
        for command in (
            [python, "-m", "ruff", "check", "."],
            [python, "-m", "ruff", "format", "--check", "."],
            [python, "-m", "compileall", "-q", "backend/src"],
            [python, "-m", "pytest", "--basetemp", str(directory / "pytest")],
        ):
            _run(command, source, environment)
        print("CANDIDATE_CHECKS=PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
