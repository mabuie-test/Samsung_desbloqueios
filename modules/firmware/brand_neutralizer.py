"""Neutralização multi-marca com assinatura e empacotamento automáticos."""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .neutralizer import FirmwareNeutralizer, SanitizationResult


@dataclass
class MultiBrandResult:
    source: Path
    sanitized: SanitizationResult
    format: str


class MultiBrandNeutralizationManager:
    """Abstrai as diferenças de extensão e prepara pacotes limpos."""

    def __init__(self, neutralizer: Optional[FirmwareNeutralizer] = None):
        self.neutralizer = neutralizer or FirmwareNeutralizer()

    def neutralize_any(self, archive: Path, destination: Optional[Path] = None) -> MultiBrandResult:
        archive = archive.expanduser().resolve()
        extension = archive.suffix.lower()
        if archive.name.endswith(".tar.md5") or extension == ".tar":
            sanitized = self.neutralizer.neutralize_archive(archive, destination)
            return MultiBrandResult(archive, sanitized, "tar")
        if extension == ".zip":
            prepared = self._extract_zip(archive, destination)
            sanitized = self.neutralizer.neutralize_directories([prepared])[0]
            return MultiBrandResult(archive, sanitized, "zip")
        if extension in {".bin", ".nb0", ".pac"}:
            prepared = self._wrap_raw_binary(archive, destination)
            sanitized = self.neutralizer.neutralize_directories([prepared])[0]
            return MultiBrandResult(archive, sanitized, extension.strip("."))
        sanitized = self.neutralizer.neutralize_archive(archive, destination)
        return MultiBrandResult(archive, sanitized, extension.strip("."))

    def neutralize_many(self, archives: List[Path], destination: Optional[Path] = None) -> List[MultiBrandResult]:
        results: List[MultiBrandResult] = []
        for archive in archives:
            try:
                results.append(self.neutralize_any(archive, destination))
            except Exception as exc:
                logging.error("Falha ao neutralizar %s: %s", archive, exc)
        return results

    def _extract_zip(self, archive: Path, destination: Optional[Path]) -> Path:
        target = self._prepare_destination(archive, destination)
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(target)
        logging.info("ZIP extraído para %s", target)
        return target

    def _wrap_raw_binary(self, archive: Path, destination: Optional[Path]) -> Path:
        target = self._prepare_destination(archive, destination)
        copied = target / archive.name
        shutil.copy2(archive, copied)
        logging.info("Binário copiado para %s", copied)
        return target

    def _prepare_destination(self, archive: Path, destination: Optional[Path]) -> Path:
        if destination:
            dest = Path(destination).expanduser().resolve()
        else:
            dest = archive.parent / f"{archive.stem}_sanitized"
        dest.mkdir(parents=True, exist_ok=True)
        return dest


__all__ = ["MultiBrandNeutralizationManager", "MultiBrandResult"]
