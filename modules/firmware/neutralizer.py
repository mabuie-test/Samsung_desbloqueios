"""Sanitização, assinatura e empacotamento de firmware.

Este módulo remove apps Google/MDM, neutraliza FRP e garante que os pacotes
assumam um formato aceito pelo Odin e ferramentas equivalentes.
"""

from __future__ import annotations

import hashlib
import logging
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .tar_md5_extractor import TarMD5Extractor


@dataclass
class SanitizationPlan:
    google_packages: List[str] = field(default_factory=lambda: [
        "com.google.android.gms",
        "com.google.android.gsf",
        "com.google.android.apps.photos",
        "com.android.vending",
    ])
    mdm_artifacts: List[str] = field(default_factory=lambda: [
        "mdm",
        "knox",
        "workprofile",
    ])
    frp_flags: List[str] = field(default_factory=lambda: [
        "persistent_data.bin",
        "frp",
    ])


@dataclass
class SanitizationResult:
    source: Path
    prepared_directory: Path
    signed_package: Path
    removed_items: List[Path]


class FirmwareSigner:
    """Responsável por gerar assinaturas simples aceitas pelo Odin."""

    def sign_directory(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory / "SIGNATURE.MANIFEST"
        md5 = hashlib.md5()
        entries: List[str] = []
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                relative = path.relative_to(directory)
                entries.append(f"{relative}: {digest}")
                md5.update(digest.encode())
        manifest.write_text("\n".join(entries))
        checksum_file = directory / "MD5SUMS"
        checksum_file.write_text(md5.hexdigest())
        logging.debug("Manifesto de assinatura criado em %s", manifest)
        return manifest


class FirmwarePackager:
    """Cria pacotes .tar.md5 compatíveis com Odin."""

    def package_directory(self, directory: Path, target_name: Optional[str] = None) -> Path:
        directory = directory.resolve()
        if not target_name:
            target_name = directory.name
        tar_path = directory.parent / f"{target_name}.tar"
        with tarfile.open(tar_path, "w") as tar:
            for item in directory.iterdir():
                tar.add(item, arcname=item.name)
        md5 = hashlib.md5(tar_path.read_bytes()).hexdigest()
        md5_path = tar_path.with_suffix(".tar.md5")
        with md5_path.open("wb") as handle:
            handle.write(tar_path.read_bytes())
            handle.write(md5.encode())
        logging.info("Pacote assinado para Odin: %s", md5_path)
        try:
            tar_path.unlink()
        except OSError:
            pass
        return md5_path


class FirmwareNeutralizer:
    """Remove apps indesejados, neutraliza FRP/MDM e repacota."""

    def __init__(self, extractor: Optional[TarMD5Extractor] = None):
        self.extractor = extractor or TarMD5Extractor()
        self.signer = FirmwareSigner()
        self.packager = FirmwarePackager()

    def neutralize_archive(
        self,
        archive: Path,
        destination: Optional[Path] = None,
        *,
        verify: bool = True,
        plan: Optional[SanitizationPlan] = None,
        progress_cb=None,
        cancel_event=None,
    ) -> SanitizationResult:
        plan = plan or SanitizationPlan()
        archive = archive.expanduser().resolve()
        if progress_cb:
            progress_cb(10)
        extracted = self.extractor.extract(archive, destination, verify=verify, progress_cb=progress_cb, cancel_event=cancel_event)
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Operação cancelada")
        if progress_cb:
            progress_cb(55)
        cleaned = self._neutralize_directory(extracted.destination, plan, cancel_event, progress_cb)
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Operação cancelada")
        self.signer.sign_directory(extracted.destination)
        if progress_cb:
            progress_cb(85)
        packaged = self.packager.package_directory(extracted.destination, archive.stem)
        if progress_cb:
            progress_cb(100)
        return SanitizationResult(archive, extracted.destination, packaged, cleaned)

    def neutralize_directories(
        self, directories: Iterable[Path], *, plan: Optional[SanitizationPlan] = None, progress_cb=None, cancel_event=None
    ) -> List[SanitizationResult]:
        results: List[SanitizationResult] = []
        plan = plan or SanitizationPlan()
        for directory in directories:
            directory = directory.expanduser().resolve()
            cleaned = self._neutralize_directory(directory, plan, cancel_event, progress_cb)
            self.signer.sign_directory(directory)
            packaged = self.packager.package_directory(directory)
            results.append(SanitizationResult(directory, directory, packaged, cleaned))
        return results

    def _neutralize_directory(self, directory: Path, plan: SanitizationPlan, cancel_event=None, progress_cb=None) -> List[Path]:
        removed: List[Path] = []
        patterns = plan.google_packages + plan.mdm_artifacts + plan.frp_flags
        total = len(patterns) or 1
        for idx, pattern in enumerate(patterns, 1):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Operação cancelada")
            for target in directory.rglob(f"*{pattern}*"):
                try:
                    if target.is_file():
                        target.unlink()
                        removed.append(target)
                    elif target.is_dir():
                        for child in target.rglob("*"):
                            if child.is_file():
                                child.unlink()
                        try:
                            target.rmdir()
                        except OSError:
                            pass
                        removed.append(target)
                except OSError as exc:
                    logging.debug("Falha ao remover %s: %s", target, exc)
            if progress_cb:
                progress_cb(55 + int((idx / total) * 20))
        logging.info("Itens neutralizados: %s", len(removed))
        return removed


class FirmwareWorkspace:
    """Cria pastas temporárias para pipelines automatizados."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(tempfile.gettempdir()) / "firmware_workspace"
        self.root.mkdir(parents=True, exist_ok=True)

    def allocate(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path


__all__ = [
    "FirmwareNeutralizer",
    "FirmwarePackager",
    "FirmwareSigner",
    "FirmwareWorkspace",
    "SanitizationPlan",
    "SanitizationResult",
]
