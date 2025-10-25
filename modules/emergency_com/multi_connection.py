"""Connection abstractions for multiple emergency communication backends."""
from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, Iterable, Optional

import serial
import usb.core
import usb.util


class ConnectionStrategy(ABC):
    """Base class for all connection strategies."""

    def __init__(self) -> None:
        self.connected: bool = False

    @abstractmethod
    def connect(self, device_info: Dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def send_command(self, command: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def emergency_recovery(self) -> bool:
        raise NotImplementedError


class AdvancedADBConnection(ConnectionStrategy):
    def __init__(self):
        super().__init__()
        self.device_id: Optional[str] = None

    def connect(self, device_info: Dict) -> bool:
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
            if device_info.get("serial") and device_info["serial"] in result.stdout:
                self.device_id = device_info["serial"]
                self.connected = True
                return True

            subprocess.run(["adb", "kill-server"], timeout=5, check=False)
            subprocess.run(["adb", "start-server"], timeout=5, check=False)
            if device_info.get("ip"):
                subprocess.run(["adb", "connect", device_info["ip"]], timeout=5, check=False)

            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
            if device_info.get("serial") and device_info["serial"] in result.stdout:
                self.device_id = device_info["serial"]
                self.connected = True
                return True

            return False
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na conexão ADB: %s", exc)
            return False

    def send_command(self, command: str) -> str:
        if not self.connected or not self.device_id:
            raise ConnectionError("Dispositivo não conectado via ADB")

        result = subprocess.run(
            ["adb", "-s", self.device_id, "shell", command],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def emergency_recovery(self) -> bool:
        if not self.device_id:
            return False
        try:
            subprocess.run(["adb", "-s", self.device_id, "reboot", "download"], timeout=15, check=False)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na recuperação de emergência ADB: %s", exc)
            return False


class EDLEmergencyConnection(ConnectionStrategy):
    def __init__(self):
        super().__init__()
        self.device = None
        self.interface = None

    def connect(self, device_info: Dict) -> bool:
        try:
            self._force_edl_mode(device_info)
            self.device = usb.core.find(idVendor=0x05C6, idProduct=0x9008)
            if self.device is None:
                return False

            self.device.set_configuration()
            self.interface = self.device[0][(0, 0)]
            usb.util.claim_interface(self.device, 0)
            self.connected = True
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na conexão EDL: %s", exc)
            return False

    def _force_edl_mode(self, device_info: Dict):
        for method in (self._edl_via_test_point, self._edl_via_key_combo, self._edl_via_software_exploit):
            if method(device_info):
                return True
        return False

    def send_command(self, command: str) -> str:
        if not self.connected or not self.device or not self.interface:
            raise ConnectionError("Dispositivo não está em modo EDL")
        try:
            payload = self._format_edl_command(command)
            endpoint_out = self.interface[0]
            endpoint_in = self.interface[1]
            self.device.write(endpoint_out, payload)
            response = self.device.read(endpoint_in, 1024)
            return self._parse_edl_response(response)
        except Exception as exc:
            logging.error("Erro ao executar comando EDL: %s", exc)
            raise

    def emergency_recovery(self) -> bool:
        try:
            self._load_vulnerable_loader()
            self._exploit_edl_vulnerability()
            self._flash_emergency_recovery()
            return True
        except Exception as exc:
            logging.error("Falha na recuperação EDL: %s", exc)
            return False

    # Placeholder internals -------------------------------------------------
    def _edl_via_test_point(self, device_info: Dict) -> bool:
        return bool(device_info.get("test_point"))

    def _edl_via_key_combo(self, device_info: Dict) -> bool:
        return bool(device_info.get("key_combo"))

    def _edl_via_software_exploit(self, device_info: Dict) -> bool:
        return device_info.get("software_exploit", False)

    def _format_edl_command(self, command: str):
        return command.encode("utf-8")

    def _parse_edl_response(self, response):
        return bytes(response).decode("utf-8", errors="ignore")

    def _load_vulnerable_loader(self):
        logging.debug("Carregando loader vulnerável para EDL")

    def _exploit_edl_vulnerability(self):
        logging.debug("Explorando vulnerabilidade EDL")

    def _flash_emergency_recovery(self):
        logging.debug("Realizando flash de recuperação em modo EDL")


class USBRawConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        try:
            dev = usb.core.find(idVendor=int(device_info.get("vid", "0"), 16), idProduct=int(device_info.get("pid", "0"), 16))
            self.connected = dev is not None
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        raise NotImplementedError("Comunicação USB raw requer implementação específica")

    def emergency_recovery(self) -> bool:
        return False


class SerialConnection(ConnectionStrategy):
    def __init__(self):
        super().__init__()
        self.ser: Optional[serial.Serial] = None

    def connect(self, device_info: Dict) -> bool:
        try:
            self.ser = serial.Serial(device_info.get("port"), device_info.get("baudrate", 115200), timeout=2)
            self.connected = self.ser.is_open
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        if not self.ser or not self.connected:
            raise ConnectionError("Porta serial não inicializada")
        self.ser.write(command.encode("utf-8"))
        response = self.ser.read(1024)
        return response.decode("utf-8", errors="ignore")

    def emergency_recovery(self) -> bool:
        return False


class FastbootConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        try:
            result = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=10)
            serial = device_info.get("serial")
            if serial:
                self.connected = serial in result.stdout
            else:
                self.connected = bool(result.stdout.strip())
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        result = subprocess.run(
            ["fastboot"] + command.split(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def emergency_recovery(self) -> bool:
        try:
            subprocess.run(["fastboot", "reboot"], timeout=10, check=False)
            return True
        except Exception:
            return False


class OdinDownloadConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        try:
            vendor = device_info.get("vendor_id", "").lower()
            self.connected = vendor == "04e8"
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        result = subprocess.run(
            ["heimdall"] + command.split(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def emergency_recovery(self) -> bool:
        try:
            subprocess.run(["heimdall", "print-pit"], timeout=30, check=False)
            return True
        except Exception:
            return False


class MTKPreloaderConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        try:
            vendor = device_info.get("vendor_id", "").lower()
            product = device_info.get("product_id", "").lower()
            self.connected = vendor in {"0e8d", "22d9"} or product in {"2000", "2001", "201c"}
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        result = subprocess.run(
            ["mtk", *command.split()],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def emergency_recovery(self) -> bool:
        try:
            subprocess.run(["mtk", "reset"], timeout=20, check=False)
            return True
        except Exception:
            return False


class SPDDiagnosticConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        try:
            vendor = device_info.get("vendor_id", "").lower()
            self.connected = vendor in {"1782", "1ebf"}
            return self.connected
        except Exception:
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        result = subprocess.run(
            ["spd", *command.split()],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout

    def emergency_recovery(self) -> bool:
        try:
            subprocess.run(["spd", "reset"], timeout=20, check=False)
            return True
        except Exception:
            return False


class ConnectionHandler:
    def __init__(self):
        self.strategies = {
            "adb": AdvancedADBConnection(),
            "usb_raw": USBRawConnection(),
            "serial": SerialConnection(),
            "edl": EDLEmergencyConnection(),
            "fastboot": FastbootConnection(),
            "odin": OdinDownloadConnection(),
            "mtk_preloader": MTKPreloaderConnection(),
            "spd_diag": SPDDiagnosticConnection(),
        }
        self.current_strategy: Optional[ConnectionStrategy] = None

    def establish_connection(self, device_info: Dict, order: Optional[Iterable[str]] = None) -> bool:
        connection_order = list(order or ["adb", "usb_raw", "serial", "edl", "fastboot"])
        for name in connection_order:
            strategy = self.strategies.get(name)
            if not strategy:
                continue
            if strategy.connect(device_info):
                self.current_strategy = strategy
                logging.info("Conexão estabelecida via %s", name)
                return True
        logging.error("Todas as estratégias de conexão falharam")
        return False

    def is_connected(self) -> bool:
        return self.current_strategy is not None and self.current_strategy.connected

    def send(self, command: str) -> str:
        if not self.current_strategy:
            raise ConnectionError("Nenhuma estratégia de conexão ativa")
        return self.current_strategy.send_command(command)

    def emergency_recover(self) -> bool:
        if not self.current_strategy:
            return False
        return self.current_strategy.emergency_recovery()

