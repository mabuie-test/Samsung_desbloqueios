"""Advanced automation helpers to extract Samsung firmware .tar.md5 packages."""
from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


@dataclass
class ExtractionResult:
    """Metadata returned after a successful extraction."""

    source: Path
    destination: Path
    extracted_files: List[Path]
    verified: bool


class TarMD5Extractor:
    """Utility responsible for extracting and verifying .tar.md5 archives."""

    def __init__(self, firmware_root: Optional[Path] = None):
        self.firmware_root = firmware_root or Path.cwd() / "firmware"
        self.firmware_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def extract(self, archive: Path, destination: Optional[Path] = None, *, verify: bool = True) -> ExtractionResult:
        """Extract the provided archive into ``destination``.

        Parameters
        ----------
        archive:
            Path to the ``.tar.md5`` file.
        destination:
            Optional directory to which the contents will be extracted. Defaults to ``firmware_root``.
        verify:
            Whether to verify the MD5 suffix present in the file name.
        """

        archive = archive.expanduser().resolve()
        if destination is None:
            destination = self.firmware_root / archive.stem
        destination.mkdir(parents=True, exist_ok=True)

        verified, tar_size = (False, None)
        if verify:
            verified, tar_size = self._verify_archive(archive)
        if tar_size is None:
            tar_size = archive.stat().st_size

        extracted_files = self._extract_tar(archive, destination, tar_size)
        verification_state = verified if verify else True
        return ExtractionResult(archive, destination, extracted_files, verification_state)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _verify_archive(self, archive: Path) -> Tuple[bool, Optional[int]]:
        """Verify MD5 checksum appended to the archive.

        Returns a tuple (is_valid, tar_size) where ``tar_size`` corresponds to the
        size of the tar payload excluding the checksum footer.
        """

        tar_size, checksum = self._split_checksum(archive)
        if tar_size is None or checksum is None:
            return False, tar_size

        md5 = hashlib.md5()
        with archive.open("rb") as fh:
            remaining = tar_size
            while remaining > 0:
                chunk = fh.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                md5.update(chunk)
                remaining -= len(chunk)
        calculated = md5.hexdigest()
        return calculated == checksum, tar_size

    def _extract_tar(self, archive: Path, destination: Path, tar_size: int) -> List[Path]:
        """Extract tar payload and return the list of created files."""
        extracted: List[Path] = []
        with self._temporary_tar(archive, tar_size) as tar_path:
            with tarfile.open(tar_path, "r:*") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    tar.extract(member, path=destination)
                    extracted.append(destination / member.name)
        return extracted

    def _split_checksum(self, archive: Path) -> Tuple[Optional[int], Optional[str]]:
        """Return the tar payload size and checksum appended to the file."""
        file_size = archive.stat().st_size
        if file_size <= 32:
            return file_size, None

        with archive.open("rb") as fh:
            footer_len = min(64, file_size)
            fh.seek(file_size - footer_len)
            footer = fh.read(footer_len)

        decoded = footer.decode("ascii", errors="ignore").strip()
        checksum = "".join(ch for ch in decoded if ch.isalnum())[-32:]
        if len(checksum) == 32:
            return file_size - len(checksum), checksum.lower()
        return file_size, None

    def _temporary_tar(self, archive: Path, tar_size: int):
        """Create a temporary TAR file without checksum footer."""

        class _TarContext:
            def __init__(self, src: Path, size: int):
                self.src = src
                self.size = size
                self.handle: Optional[tempfile.NamedTemporaryFile] = None

            def __enter__(self):
                self.handle = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
                with self.src.open("rb") as fh:
                    remaining = self.size
                    while remaining > 0:
                        chunk = fh.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.handle.write(chunk)
                        remaining -= len(chunk)
                self.handle.flush()
                self.handle.close()
                return Path(self.handle.name)

            def __exit__(self, exc_type, exc, tb):
                if self.handle is not None:
                    try:
                        os.unlink(self.handle.name)
                    except OSError:
                        pass
                return False

        return _TarContext(archive, tar_size)

    # ------------------------------------------------------------------
    # Batch helpers
    # ------------------------------------------------------------------
    def extract_many(self, archives: Iterable[os.PathLike[str] | str], *, verify: bool = True) -> List[ExtractionResult]:
        results: List[ExtractionResult] = []
        for archive in archives:
            results.append(self.extract(Path(archive), verify=verify))
        return results
