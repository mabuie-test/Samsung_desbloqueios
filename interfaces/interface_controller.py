"""Controlador compartilhado para as interfaces gráficas.

Este módulo centraliza chamadas do :class:`SamsungUnlockCore` para que as
interfaces (Tkinter e PyQt) usem o mesmo fluxo robusto e coerente.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.system_controller import SamsungUnlockCore


class InterfaceController:
    """Ponto único para operações acionadas pela interface."""

    def __init__(self, core: Optional[SamsungUnlockCore] = None):
        self.core = core or SamsungUnlockCore()

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------
    def connect(self, model: str, serial: str, connection_type: str, prefer_edl: bool = False, extra: Optional[dict] = None) -> bool:
        device_info = {
            "model": model,
            "serial": serial,
            "connection_type": connection_type,
        }
        if extra:
            device_info.update(extra)
        logging.debug("Solicitação de conexão via interface: %s", device_info)
        return self.core.connection_handler.establish_connection(device_info, prefer_edl=prefer_edl)

    def wait_and_connect(self, model: str, serial: str, connection_type: str, *, prefer_edl: bool = False, extra: Optional[dict] = None, progress_cb=None) -> bool:
        device_info = {
            "model": model,
            "serial": serial,
            "connection_type": connection_type,
        }
        if extra:
            device_info.update(extra)
        logging.debug("Aguardando conexão automática: %s", device_info)
        return self.core.connection_handler.wait_and_connect(device_info, prefer_edl=prefer_edl, progress_cb=progress_cb)

    def discover_devices(self):
        return self.core.connection_handler._handler.discover_devices()

    def fetch_identity(self):
        return self.core.connection_handler._handler.read_identity()

    def set_ultra_mode(self, enabled: bool):
        self.core.enable_ultra_mode(enabled)

    def disconnect(self) -> None:
        logging.info("Interface solicitou desconexão")
        self.core.connection_handler.emergency_recover()

    # ------------------------------------------------------------------
    # Rotinas de desbloqueio/segurança
    # ------------------------------------------------------------------
    def remove_mdm(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Remoção MDM",
            self.core.mdm_remover.remove_mdm_persistence,
            progress_cb,
            log_cb,
        )

    def _with_feedback(self, label: str, func, progress_cb=None, log_cb=None) -> bool:
        if log_cb:
            log_cb(f"{label}: iniciado")
        if progress_cb:
            progress_cb(5)
        ok = func()
        if progress_cb:
            progress_cb(100 if ok else 0)
        if log_cb:
            log_cb(f"{label}: {'sucesso' if ok else 'falhou'}")
        return ok

    def bypass_frp(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "FRP automático",
            self.core.frp_bypass.execute_advanced_bypass,
            progress_cb,
            log_cb,
        )

    def bypass_frp_version(self, target: str, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            f"FRP Android {target}",
            lambda: self.core.frp_bypass.execute_version_strategy(target),
            progress_cb,
            log_cb,
        )

    def bypass_kg(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Bypass KG",
            self.core.kg_lock_bypass.execute_kg_lock_bypass,
            progress_cb,
            log_cb,
        )

    def remove_lock(self, lock_type: Optional[str] = None, *, progress_cb=None, log_cb=None) -> bool:
        if lock_type == "Automático":
            lock_type = None
        return self._with_feedback(
            "Remoção de bloqueio",
            lambda: self.core.remove_screen_lock(lock_type),
            progress_cb,
            log_cb,
        )

    def hard_reset(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Hard reset universal",
            self.core.hard_reset_device,
            progress_cb,
            log_cb,
        )

    def hard_reset_chipset(self, chipset: str, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            f"Hard reset {chipset or 'genérico'}",
            lambda: self.core.hard_reset_by_chipset(chipset),
            progress_cb,
            log_cb,
        )

    def controlled_reset(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Reset controlado",
            self.core.controlled_reset,
            progress_cb,
            log_cb,
        )

    def recover_data(self, destination: str, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Recuperação USB/eMMC",
            lambda: self.core.recover_emmc_data(Path(destination), progress_cb=progress_cb, log_cb=log_cb),
            progress_cb,
            log_cb,
        )

    def read_samsung_pin(self, *, progress_cb=None, log_cb=None) -> bool:
        return self._with_feedback(
            "Leitura de PIN/padrão (Odin)",
            self.core.read_samsung_pin_via_odin,
            progress_cb,
            log_cb,
        )

    # ------------------------------------------------------------------
    # Firmware
    # ------------------------------------------------------------------
    def sanitize_firmware(self, archive_path: str, destination: Optional[str] = None, *, progress_cb=None, cancel_event=None) -> bool:
        archive = Path(archive_path).expanduser()
        dest = Path(destination).expanduser() if destination else None
        result = self.core.firmware_tools.neutralizer.neutralize_archive(
            archive, dest, progress_cb=progress_cb, cancel_event=cancel_event
        )
        logging.info("Pacote sanitizado em %s", result.prepared_directory)
        return result.signed_package.exists()

    def sanitize_multi_brand(
        self, archive_path: str, destination: Optional[str] = None, *, progress_cb=None, cancel_event=None
    ) -> bool:
        archive = Path(archive_path).expanduser()
        dest = Path(destination).expanduser() if destination else None
        result = self.core.firmware_tools.multi_brand_manager.neutralize_any(
            archive, dest, progress_cb=progress_cb, cancel_event=cancel_event
        )
        logging.info("Pacote multi-brand pronto em %s", result.signed_package)
        return result.signed_package.exists()

    # ------------------------------------------------------------------
    # Informações
    # ------------------------------------------------------------------
    def device_information(self):
        return self.core.connection_handler.device_information()


__all__ = ["InterfaceController"]
