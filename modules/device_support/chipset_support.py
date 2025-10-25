"""Chipset support matrix and helpers for multi-vendor Android devices."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List


@dataclass(slots=True)
class ChipsetProfile:
    """Represents the capabilities and tooling required for a chipset family."""

    name: str
    manufacturers: List[str]
    vendor_ids: List[str] = field(default_factory=list)
    product_ids: List[str] = field(default_factory=list)
    board_patterns: List[str] = field(default_factory=list)
    preferred_connections: List[str] = field(default_factory=list)
    bootloader_unlock_methods: List[str] = field(default_factory=list)
    firmware_tooling: List[str] = field(default_factory=list)
    notes: str = ""

    def matches(self, device_info: Dict[str, str]) -> bool:
        """Return True if the provided ``device_info`` matches this profile."""
        manufacturer = device_info.get("manufacturer", "").lower()
        hardware = device_info.get("hardware", "").lower()
        board = device_info.get("board", "").lower()
        vendor_id = device_info.get("vendor_id", "").lower()
        product_id = device_info.get("product_id", "").lower()

        if manufacturer and any(manufacturer.startswith(prefix) for prefix in self.manufacturers):
            return True

        if vendor_id and vendor_id in self.vendor_ids:
            return True

        if product_id and product_id in self.product_ids:
            return True

        haystack = " ".join(filter(None, [manufacturer, hardware, board]))
        for pattern in self.board_patterns:
            if re.search(pattern, haystack):
                return True

        return False


class ChipsetSupportMatrix:
    """Provides chipset detection and capability mapping."""

    def __init__(self):
        self._profiles: List[ChipsetProfile] = [
            ChipsetProfile(
                name="Qualcomm Snapdragon",
                manufacturers=["samsung", "xiaomi", "motorola", "oneplus", "lg"],
                vendor_ids=["05c6"],
                product_ids=["9008", "9025", "9091"],
                board_patterns=[r"sdm\d+", r"sm\d+"],
                preferred_connections=["adb", "edl", "fastboot"],
                bootloader_unlock_methods=["fastboot_oem", "firehose"],
                firmware_tooling=["edl", "fastboot"],
                notes="Handles EDL (9008) and fastboot for Snapdragon devices.",
            ),
            ChipsetProfile(
                name="Samsung Exynos",
                manufacturers=["samsung"],
                vendor_ids=["04e8"],
                product_ids=["685d", "6860"],
                board_patterns=[r"exynos", r"universal\d+"],
                preferred_connections=["adb", "odin", "fastboot"],
                bootloader_unlock_methods=["odin_download", "fastboot_oem"],
                firmware_tooling=["odin", "heimdall"],
                notes="Samsung proprietary download/Odin workflow.",
            ),
            ChipsetProfile(
                name="MediaTek (MTK)",
                manufacturers=["xiaomi", "realme", "oppo", "vivo", "tecno", "infinix"],
                vendor_ids=["0e8d", "22d9"],
                product_ids=["2000", "2001", "201c", "201d"],
                board_patterns=[r"mt\d{3,4}", r"mediatek", r"mtk"],
                preferred_connections=["adb", "mtk_preloader", "fastboot"],
                bootloader_unlock_methods=["mtk_da", "fastboot_oem"],
                firmware_tooling=["spflash", "mtkclient"],
                notes="Supports Preloader handshake and Download Agent workflow.",
            ),
            ChipsetProfile(
                name="Spreadtrum / Unisoc",
                manufacturers=["zte", "motorola", "nokia", "itel", "hisense"],
                vendor_ids=["1782", "1ebf"],
                product_ids=["4d00", "4d10", "4d11"],
                board_patterns=[r"sc\d+", r"unisoc"],
                preferred_connections=["adb", "spd_diag", "fastboot"],
                bootloader_unlock_methods=["spd_diag", "fastboot_oem"],
                firmware_tooling=["researchdownload", "upgrade_download"],
                notes="Diagnostic interface for Unisoc/Spreadtrum.",
            ),
            ChipsetProfile(
                name="HiSilicon / Kirin",
                manufacturers=["huawei", "honor"],
                vendor_ids=["12d1"],
                product_ids=["3609", "360b"],
                board_patterns=[r"kirin", r"balong"],
                preferred_connections=["adb", "fastboot"],
                bootloader_unlock_methods=["fastboot_oem"],
                firmware_tooling=["hisuite"],
                notes="Limited official bootloader unlock support, fallback to fastboot.",
            ),
            ChipsetProfile(
                name="Generic Android",
                manufacturers=["google", "sony", "asus", "lenovo"],
                preferred_connections=["adb", "fastboot"],
                bootloader_unlock_methods=["fastboot_oem"],
                firmware_tooling=["fastboot"],
                notes="Fallback profile when no chipset signature is detected.",
            ),
        ]

    @property
    def profiles(self) -> Iterable[ChipsetProfile]:
        return tuple(self._profiles)

    def identify(self, device_info: Dict[str, str]) -> ChipsetProfile:
        """Identify the most appropriate chipset profile for ``device_info``."""
        for profile in self._profiles:
            if profile.matches(device_info):
                logging.debug("Chipset identificado: %s", profile.name)
                return profile

        logging.debug("Nenhum chipset específico detectado, usando perfil genérico")
        return self._profiles[-1]

    def describe_support(self, profile: ChipsetProfile) -> str:
        """Return a human readable summary of the chipset capabilities."""
        return (
            f"Perfil: {profile.name} | conexões: {', '.join(profile.preferred_connections)} | "
            f"ferramentas: {', '.join(profile.firmware_tooling)}"
        )


def merge_device_info(*sources: Dict[str, str]) -> Dict[str, str]:
    """Merge multiple ``device_info`` dictionaries into a single mapping."""
    merged: Dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            if value and key not in merged:
                merged[key] = value
    return merged


def build_default_matrix() -> ChipsetSupportMatrix:
    """Return a default ``ChipsetSupportMatrix`` instance."""
    return ChipsetSupportMatrix()

