"""Conversion engines.

Each engine turns one document into one PDF inside a scratch folder. The CLI
picks the most faithful engine that is installed, so adding an engine means
adding a class here and listing it in ENGINES, best first.

Microsoft Word is the reference renderer for Word files and will go first in
ENGINES once its automation has been tested against a licensed copy (an
unlicensed Word for Mac runs read-only and refuses to save, PDF included).
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional


class EngineError(Exception):
    """A conversion failed. The message says why, in plain words."""


class Engine:
    name = ""
    label = ""
    # Set by convert() when the run worked but something the user should know
    # about happened along the way (e.g. a fallback was used).
    note: Optional[str] = None

    def available(self) -> bool:
        raise NotImplementedError

    def location(self) -> Optional[str]:
        raise NotImplementedError

    def version(self) -> Optional[str]:
        return None

    def convert(self, src: Path, workdir: Path, timeout: float) -> Path:
        """Convert src to a PDF inside workdir and return the PDF's path."""
        raise NotImplementedError


class LibreOffice(Engine):
    name = "libreoffice"
    label = "LibreOffice"

    def __init__(self) -> None:
        self._soffice = _find_soffice()

    def available(self) -> bool:
        return self._soffice is not None

    def location(self) -> Optional[str]:
        return self._soffice

    def version(self) -> Optional[str]:
        if not self._soffice:
            return None
        if platform.system() == "Darwin":
            plist = Path(self._soffice).parents[1] / "Info.plist"
            if plist.exists():
                import plistlib

                with plist.open("rb") as f:
                    return plistlib.load(f).get("CFBundleShortVersionString")
        profile = Path(tempfile.mkdtemp(prefix="docpdf-profile-"))
        try:
            code, out = _run(self._command(profile, ["--version"]), _env(), 60)
        except EngineError:
            return None
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        parts = out.split()
        return parts[1] if len(parts) > 1 and parts[0] == "LibreOffice" else (out.strip() or None)

    def _command(self, profile: Path, args: List[str]) -> List[str]:
        return [
            self._soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            *args,
        ]

    def convert(self, src: Path, workdir: Path, timeout: float) -> Path:
        if not self._soffice:
            raise EngineError("LibreOffice isn't installed.")
        self.note = None
        if platform.system() != "Darwin":
            return self._convert(src, workdir, timeout, _env())
        try:
            return self._convert(src, workdir, timeout, _env())
        except EngineError as first:
            if "longer than" in str(first):
                raise
            # The macOS backend needs a window-server session; in some
            # restricted launch contexts it aborts at startup. The plain
            # headless backend always starts, but can't see macOS's fonts, so
            # the font check will report any substitution it causes.
            fallback = dict(os.environ, SAL_USE_VCLPLUGIN="svp")
            pdf = self._convert(src, workdir, timeout, fallback)
            self.note = (
                "LibreOffice's macOS renderer couldn't start here, so the plain headless renderer was used. "
                "It can't see the Mac's own fonts; check the font warnings."
            )
            return pdf

    def _convert(self, src: Path, workdir: Path, timeout: float, env: dict) -> Path:
        # A private, throwaway profile per run: conversions never collide with a
        # LibreOffice window that is already open, or with each other.
        profile = Path(tempfile.mkdtemp(prefix="docpdf-profile-"))
        try:
            cmd = self._command(profile, ["--convert-to", "pdf", "--outdir", str(workdir), str(src)])
            code, out = _run(cmd, env, timeout)
            pdf = workdir / (src.stem + ".pdf")
            if not pdf.exists():
                detail = _last_lines(out)
                raise EngineError(
                    "LibreOffice didn't produce a PDF"
                    + (f" (exit code {code})" if code else "")
                    + (f". It said: {detail}" if detail else ".")
                )
            return pdf
        finally:
            shutil.rmtree(profile, ignore_errors=True)


ENGINES = [LibreOffice]


def all_engines() -> List[Engine]:
    return [cls() for cls in ENGINES]


def get_engine(name: str) -> Engine:
    for engine in all_engines():
        if engine.name == name:
            return engine
    raise KeyError(name)


def _env() -> dict:
    env = dict(os.environ)
    if platform.system() == "Darwin":
        # On macOS, --headless alone switches LibreOffice to a renderer that
        # can't see the system's fonts, so it silently swaps in lookalikes
        # (Tahoma came out as Linux Libertine G in testing). The macOS backend
        # still runs headless (no window, no Dock icon, no focus change) and
        # sees every font the Mac has.
        env["SAL_USE_VCLPLUGIN"] = "osx"
    return env


def _find_soffice() -> Optional[str]:
    override = os.environ.get("DOCPDF_SOFFICE")
    if override:
        return override if Path(override).exists() else None
    candidates: List[Path] = []
    system = platform.system()
    if system == "Darwin":
        for apps in (Path("/Applications"), Path.home() / "Applications"):
            candidates.append(apps / "LibreOffice.app" / "Contents" / "MacOS" / "soffice")
    elif system == "Windows":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = os.environ.get(var)
            if base:
                program = Path(base) / "LibreOffice" / "program"
                # soffice.com waits for the conversion; soffice.exe may not.
                candidates += [program / "soffice.com", program / "soffice.exe"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run(cmd: List[str], env: dict, timeout: float):
    kwargs = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        proc = subprocess.Popen(
            cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
        )
    except OSError as exc:
        raise EngineError(f"couldn't start {cmd[0]}: {exc}") from exc
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise EngineError(f"took longer than {timeout:g} s and was stopped.")
    return proc.returncode, out.decode("utf-8", errors="replace")


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    except (ProcessLookupError, OSError):
        pass


def _last_lines(text: str, n: int = 3) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("Fontconfig warning")
    ]
    return " / ".join(lines[-n:])
