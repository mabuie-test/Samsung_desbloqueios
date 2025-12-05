"""Data recovery helpers leveraging USB/diag access to raw eMMC blocks."""
from __future__ import annotations

import logging
import time
import subprocess
from pathlib import Path
from typing import Iterable, Optional

from modules.device_support.chipset_support import ChipsetProfile


class EMMCDataRecovery:
    """Reads critical partitions over USB/diag for data salvage flows."""

    def __init__(self, connection_handler, operations):
        self.connection_handler = connection_handler
        self.operations = operations

    def recover_partitions(
        self,
        destination: Path,
        *,
        partitions: Optional[Iterable[str]] = None,
        profile: Optional[ChipsetProfile] = None,
        progress_cb=None,
        log_cb=None,
    ) -> bool:
        """Dump selected partitions to ``destination`` using the active link.

        The routine prefers diag/EDL-specific reads when available and
        gracefully falls back to shell-based ``dd`` copies on generic links.
        """

        if not self.connection_handler.is_connected():
            raise ConnectionError("Dispositivo não conectado")

        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        profile = profile or getattr(self.connection_handler, "device_profile", None)
        partitions = list(partitions or self._default_partitions(profile))

        if log_cb:
            log_cb("Recuperação USB/eMMC iniciada")
        if progress_cb:
            progress_cb(2)

        success = True
        for idx, part in enumerate(partitions):
            percent = int(((idx) / max(1, len(partitions))) * 90)
            if progress_cb:
                progress_cb(percent)
            if log_cb:
                log_cb(f"Lendo partição {part}...")

            try:
                self._dump_partition(part, destination, profile)
            except Exception as exc:  # pragma: no cover - defensive
                success = False
                logging.error("Falha ao recuperar %s: %s", part, exc)
                if log_cb:
                    log_cb(f"Erro em {part}: {exc}")

        if progress_cb:
            progress_cb(100 if success else 0)
        if log_cb:
            log_cb("Recuperação concluída" if success else "Recuperação finalizada com falhas")
        return success

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _default_partitions(self, profile: Optional[ChipsetProfile]) -> Iterable[str]:
        base = ["efs", "persist", "frp", "userdata"]
        if profile and profile.name.startswith("Samsung"):
            base.insert(0, "prism")
        if profile and profile.name.startswith("Qualcomm"):
            base.insert(0, "modem")
        if profile and profile.name.startswith("MediaTek"):
            base.insert(0, "nvram")
        return base

    def _dump_partition(self, partition: str, destination: Path, profile: Optional[ChipsetProfile]):
        current_name = getattr(self.connection_handler._handler, "current_name", "")
        remote_tmp = f"/data/local/tmp/{partition}.img"

        # Prefer specialized readers when possible
        if current_name in {"edl", "spd_diag"}:
            self.connection_handler.send(f"read_emmc --partition {partition} --output {remote_tmp}")
        elif current_name == "odin":
            # Heimdall/odin style readback
            target = destination / f"{partition}.bin"
            self.connection_handler.send(f"heimdall print-pit --no-reboot")
            self.connection_handler.send(f"heimdall download --{partition} {target}")
            return
        elif current_name == "adb":
            self._adb_shell(f"dd if=/dev/block/by-name/{partition} of={remote_tmp} bs=4096")
        elif current_name == "fastboot":
            self.connection_handler.send(f"flash:raw {partition} {remote_tmp}")
        else:
            self.connection_handler.send(f"dd if=/dev/block/by-name/{partition} of={remote_tmp} bs=4096")

        # Pull file when remote staging is used
        target = destination / f"{partition}.img"
        try:
            if current_name == "adb":
                self._adb_pull(remote_tmp, target)
            elif current_name == "fastboot":
                # Algumas ferramentas customizadas exportam via fastboot fetch
                self.connection_handler.send(f"fetch {remote_tmp} {target}")
            else:
                self.connection_handler.send(f"pull {remote_tmp} {target}")
        except Exception:
            # Em alguns modos apenas o host consegue ler via bulk; tenta leitura direta
            if current_name == "usb_raw":
                self.connection_handler.send(f"usb_raw read --partition {partition} --output {target}")
            elif current_name == "serial":
                # sem canal de leitura confiável, sinaliza falha em vez de sucesso silencioso
                raise ConnectionError("Canal serial não suporta leitura direta da partição")
            else:
                raise

        # Pequena espera para garantir flush completo em portas seriais
        time.sleep(0.5)

    def _adb_shell(self, command: str):
        strategy = getattr(self.connection_handler._handler, "current_strategy", None)
        device_id = getattr(strategy, "device_id", None)
        cmd = ["adb"]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["shell", command])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Falha ao executar comando ADB")

    def _adb_pull(self, remote: str, local: Path):
        strategy = getattr(self.connection_handler._handler, "current_strategy", None)
        device_id = getattr(strategy, "device_id", None)
        cmd = ["adb"]
        if device_id:
            cmd.extend(["-s", device_id])
        cmd.extend(["pull", remote, str(local)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Falha ao copiar partição via ADB")

