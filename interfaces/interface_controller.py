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
    def connect(self, model: str, serial: str, connection_type: str, prefer_edl: bool = False) -> bool:
        device_info = {
            "model": model,
            "serial": serial,
            "connection_type": connection_type,
        }
        logging.debug("Solicitação de conexão via interface: %s", device_info)
        return self.core.connection_handler.establish_connection(device_info, prefer_edl=prefer_edl)

    def discover_devices(self):
        return self.core.connection_handler._handler.discover_devices()

    def fetch_identity(self):
        return self.core.connection_handler._handler.read_identity()

    def disconnect(self) -> None:
        logging.info("Interface solicitou desconexão")
        self.core.connection_handler.emergency_recover()

    # ------------------------------------------------------------------
    # Rotinas de desbloqueio/segurança
    # ------------------------------------------------------------------
    def remove_mdm(self) -> bool:
        return self.core.mdm_remover.remove_mdm_persistence()

    def bypass_frp(self) -> bool:
        return self.core.frp_bypass.execute_advanced_bypass()

    def bypass_kg(self) -> bool:
        return self.core.kg_lock_bypass.execute_kg_lock_bypass()

    def remove_lock(self, lock_type: Optional[str] = None) -> bool:
        if lock_type == "Automático":
            lock_type = None
        return self.core.remove_screen_lock(lock_type)

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


__all__ = ["InterfaceController"]
