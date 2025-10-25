"""High level operations orchestrated per chipset."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List

from .chipset_support import ChipsetProfile


class ChipsetOperations:
    """Implements chipset aware operations used across the unlock workflow."""

    def __init__(self):
        self._connection_sequences = {
            "Qualcomm Snapdragon": ["adb", "edl", "fastboot"],
            "Samsung Exynos": ["adb", "odin", "fastboot"],
            "MediaTek (MTK)": ["adb", "mtk_preloader", "fastboot"],
            "Spreadtrum / Unisoc": ["adb", "spd_diag", "fastboot"],
            "HiSilicon / Kirin": ["adb", "fastboot"],
            "Generic Android": ["adb", "fastboot"],
        }

    # ------------------------------------------------------------------
    # Connection planning
    # ------------------------------------------------------------------
    def connection_sequence(self, profile: ChipsetProfile) -> List[str]:
        return list(self._connection_sequences.get(profile.name, profile.preferred_connections or ["adb"]))

    # ------------------------------------------------------------------
    # Bootloader unlock helpers
    # ------------------------------------------------------------------
    def unlock_bootloader(self, connection, profile: ChipsetProfile) -> bool:
        """Execute chipset specific bootloader unlock commands."""
        for method in profile.bootloader_unlock_methods:
            handler = getattr(self, f"_unlock_with_{method}", None)
            if handler and handler(connection):
                return True
        logging.warning("Nenhum método de desbloqueio funcionou para %s", profile.name)
        return False

    def _unlock_with_fastboot_oem(self, connection) -> bool:
        try:
            logging.info("Executando desbloqueio via fastboot oem unlock")
            connection.send_command("fastboot flashing unlock")
            connection.send_command("fastboot oem unlock")
            return True
        except Exception as exc:
            logging.error("Falha no desbloqueio fastboot: %s", exc)
            return False

    def _unlock_with_firehose(self, connection) -> bool:
        try:
            logging.info("Enviando firehose programmer para modo EDL")
            connection.send_command("edl loader upload")
            connection.send_command("edl oem unlock")
            return True
        except Exception as exc:
            logging.error("Falha no fluxo firehose: %s", exc)
            return False

    def _unlock_with_odin_download(self, connection) -> bool:
        try:
            logging.info("Utilizando modo Odin para liberar bootloader")
            connection.send_command("odin unlock_bl")
            return True
        except Exception as exc:
            logging.error("Erro ao usar Odin: %s", exc)
            return False

    def _unlock_with_mtk_da(self, connection) -> bool:
        try:
            logging.info("Executando Download Agent para dispositivos MTK")
            connection.send_command("mtk da auth")
            connection.send_command("mtk da unlock")
            return True
        except Exception as exc:
            logging.error("Download Agent falhou: %s", exc)
            return False

    def _unlock_with_spd_diag(self, connection) -> bool:
        try:
            logging.info("Injetando comandos de diagnóstico Unisoc")
            connection.send_command("spd diag unlock")
            return True
        except Exception as exc:
            logging.error("Falha no modo diagnóstico SPD: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Partition helpers
    # ------------------------------------------------------------------
    def partitions_to_backup(self, profile: ChipsetProfile) -> Iterable[str]:
        if profile.name.startswith("Qualcomm"):
            return ("modem", "persist", "efs")
        if profile.name.startswith("Samsung"):
            return ("efs", "persist", "prism")
        if profile.name.startswith("MediaTek"):
            return ("nvram", "nvdata", "protect1", "protect2")
        if profile.name.startswith("Spreadtrum"):
            return ("prodnv", "persist", "sysinfo")
        return ("persist", "metadata")

    def partitions_to_flash(self, profile: ChipsetProfile) -> Iterable[str]:
        common = ("boot", "vbmeta", "system", "vendor")
        if profile.name.startswith("Samsung"):
            return common + ("dtbo", "optics")
        if profile.name.startswith("MediaTek"):
            return common + ("preloader", "lk")
        if profile.name.startswith("Spreadtrum"):
            return common + ("fdl1", "fdl2")
        return common

    # ------------------------------------------------------------------
    # Security cleanup helpers
    # ------------------------------------------------------------------
    def mdm_packages(self, profile: ChipsetProfile) -> Iterable[str]:
        packages = [
            "com.samsung.android.kgclient",
            "com.google.android.apps.work.oobconfig",
            "com.android.managedprovisioning",
        ]
        if profile.name.startswith("MediaTek"):
            packages.append("com.mediatek.factorymode")
        if profile.name.startswith("Spreadtrum"):
            packages.append("com.unisoc.mdm")
        return packages

    def kg_services(self, profile: ChipsetProfile) -> Iterable[str]:
        services = ["kg.client", "kg.eds" ]
        if profile.name.startswith("Samsung"):
            services.extend(["kg.longpress", "kg.service"])
        if profile.name.startswith("Qualcomm"):
            services.append("qti.esim" )
        return services

    def recommended_firmware_tool(self, profile: ChipsetProfile) -> str:
        if profile.firmware_tooling:
            return profile.firmware_tooling[0]
        return "fastboot"

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def ensure_binary(self, binary: str) -> bool:
        """Return True if ``binary`` is available in PATH."""
        result = subprocess.run(["which", binary], capture_output=True, text=True)
        return result.returncode == 0

    def locate_images(self, firmware_dir: Path, partitions: Iterable[str]) -> Dict[str, Path]:
        mapping: Dict[str, Path] = {}
        for partition in partitions:
            for candidate in (
                firmware_dir / f"{partition}.img",
                firmware_dir / f"{partition}.bin",
                firmware_dir / f"{partition}.tar",
            ):
                if candidate.exists():
                    mapping[partition] = candidate
                    break
        return mapping

