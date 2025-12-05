"""Connection abstractions for multiple emergency communication backends."""
from __future__ import annotations

import logging
import logging
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional

import serial
from serial.tools import list_ports
import usb.core
import usb.util
from usb.core import NoBackendError


_VENDOR_BRANDS = {
    "04e8": "Samsung",
    "18d1": "Google / Pixel",
    "0e8d": "MediaTek",
    "22d9": "MediaTek",
    "05c6": "Qualcomm",
    "1782": "Spreadtrum",
    "1ebf": "Unisoc",
}


def _binary_available(binary: str) -> bool:
    """Check if a required binary is available in PATH."""
    return shutil.which(binary) is not None


def _safe_usb_string(device: usb.core.Device, index: int) -> str:
    try:
        return usb.util.get_string(device, index) or ""
    except Exception:
        return ""


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
        if not _binary_available("adb"):
            logging.debug("ADB não encontrado no PATH; ignorando tentativa de conexão ADB")
            return False
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
        except FileNotFoundError:
            logging.debug("ADB não localizado durante tentativa de conexão")
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
    def __init__(self):
        super().__init__()
        self.device: Optional[usb.core.Device] = None

    def connect(self, device_info: Dict) -> bool:
        try:
            vid = int(device_info.get("vid", "0"), 16)
            pid = int(device_info.get("pid", "0"), 16)
            self.device = usb.core.find(idVendor=vid, idProduct=pid)
            self.connected = self.device is not None
            if self.connected:
                logging.info("Conexão USB raw estabelecida para VID:%04x PID:%04x", vid, pid)
            return self.connected
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na conexão USB raw: %s", exc)
            self.connected = False
            return False

    def send_command(self, command: str) -> str:
        if not self.connected or not self.device:
            raise ConnectionError("Comunicação USB raw não inicializada")
        try:
            payload = command.encode("utf-8")
            endpoint_out = self.device[0][(0, 0)][0]
            endpoint_in = self.device[0][(0, 0)][1]
            self.device.write(endpoint_out, payload)
            response = self.device.read(endpoint_in, 1024)
            return bytes(response).decode("utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - USB behavior varies
            logging.error("Erro ao enviar comando USB raw: %s", exc)
            raise

    def emergency_recovery(self) -> bool:
        if not self.device:
            return False
        try:
            usb.util.dispose_resources(self.device)
            self.connected = False
            logging.info("Dispositivo USB raw reiniciado (dispose resources)")
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha ao reiniciar dispositivo USB raw: %s", exc)
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
        self.ser.reset_input_buffer()
        self.ser.write((command + "\n").encode("utf-8"))
        response = self.ser.read_until(b"\n")
        return response.decode("utf-8", errors="ignore")

    def emergency_recovery(self) -> bool:
        try:
            if self.ser and self.connected:
                self.ser.setDTR(False)
                self.ser.setRTS(False)
                self.ser.send_break(duration=0.25)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na recuperação serial: %s", exc)
            return False


class FastbootConnection(ConnectionStrategy):
    def connect(self, device_info: Dict) -> bool:
        if not _binary_available("fastboot"):
            logging.debug("Fastboot não encontrado no PATH; ignorando tentativa de conexão fastboot")
            return False
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
            if self.connected:
                self._clear_download_password()
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

    def _clear_download_password(self) -> None:
        """Tenta remover qualquer senha de proteção em modo download."""
        if not _binary_available("heimdall"):
            logging.debug("Heimdall não encontrado; não é possível limpar senha em modo Odin")
            return
        subprocess.run(["heimdall", "oem", "unlock"], timeout=20, check=False)


class MTPConnection(ConnectionStrategy):
    """Permite detectar dispositivos expostos via MTP para leitura básica."""

    def __init__(self):
        super().__init__()
        self._device: Optional[usb.core.Device] = None

    def connect(self, device_info: Dict) -> bool:
        try:
            # Prioridade para informações já descobertas
            if device_info.get("connection_type") == "mtp":
                self.connected = True
                return True

            self._device = usb.core.find(custom_match=lambda d: self._is_mtp(d))
            self.connected = self._device is not None
            return self.connected
        except Exception:
            self.connected = False
            return False

    def _is_mtp(self, device: usb.core.Device) -> bool:
        try:
            if device.bDeviceClass == 6:  # Still Image / MTP
                return True
            for cfg in device:
                for intf in cfg:
                    if intf.bInterfaceClass == 6:
                        return True
        except Exception:
            return False
        return False

    def send_command(self, command: str) -> str:
        # Operações MTP não são textuais; oferecemos stub para integridade de fluxo
        return "MTP operation not interactive"

    def emergency_recovery(self) -> bool:
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
            "mtp": MTPConnection(),
        }
        self.current_strategy: Optional[ConnectionStrategy] = None
        self.current_name: Optional[str] = None
        self._last_discovered: List[Dict[str, str]] = []
        self._last_connected_identity: Dict[str, str] = {}
        self._usb_backend_available: bool = True
        self._warned_usb_backend: bool = False
        self._usb_backend_failures: int = 0
        self._warned_adb_missing: bool = False
        self._warned_fastboot_missing: bool = False
        self._ultra_mode: bool = False
        self._ultra_order: List[str] = [
            "usb_raw",
            "odin",
            "mtp",
            "adb",
            "spd_diag",
            "fastboot",
            "serial",
            "edl",
        ]

    def enable_ultra_mode(self, *, order: Optional[Iterable[str]] = None):
        if order:
            self._ultra_order = list(order)
        self._ultra_mode = True
        logging.info("Modo ultra ativado: ordem %s", self._ultra_order)

    def disable_ultra_mode(self):
        self._ultra_mode = False
        logging.info("Modo ultra desativado")

    def _base_order(self) -> List[str]:
        return ["adb", "mtp", "odin", "usb_raw", "serial", "edl", "fastboot"]

    def _prefill_from_discovery(self, device_info: Dict, preferred: str) -> Dict:
        enriched = dict(device_info)
        # Usa cache atual; se vazio, força descoberta antes de conectar.
        if not self._last_discovered:
            self.discover_devices()
        for dev in self._last_discovered:
            if preferred and dev.get("connection_type", "").lower() == preferred:
                enriched = {**dev, **enriched}
                break
            if dev.get("serial") and enriched.get("serial") and dev["serial"] == enriched["serial"]:
                enriched = {**dev, **enriched}
                break
        return enriched

    def establish_connection(self, device_info: Dict, order: Optional[Iterable[str]] = None) -> bool:
        preferred = (device_info.get("connection_type") or "").lower()
        if self._ultra_mode:
            device_info = self._prefill_from_discovery(device_info, preferred)
        connection_order = list(order or (self._ultra_order if self._ultra_mode else self._base_order()))
        if preferred and preferred in connection_order:
            connection_order = [preferred] + [n for n in connection_order if n != preferred]
        for name in connection_order:
            strategy = self.strategies.get(name)
            if not strategy or not self._strategy_available(name):
                continue
            if strategy.connect(device_info):
                self.current_strategy = strategy
                self.current_name = name
                self._last_connected_identity = self._merge_identity(device_info)
                logging.info("Conexão estabelecida via %s", name)
                return True
        logging.error("Todas as estratégias de conexão falharam")
        return False

    def wait_and_connect(
        self,
        device_template: Dict,
        *,
        max_wait: float = 35.0,
        poll_interval: float = 2.0,
        progress_cb=None,
    ) -> bool:
        """Aguarda um dispositivo aparecer e tenta conexão assim que detectado.

        Útil para fluxos onde o usuário coloca o aparelho em modo desejado após
        iniciar o processo. Opcionalmente, emite progresso para a UI.
        """

        waited = 0.0
        while waited <= max_wait:
            devices = self.discover_devices()
            # Encontra o primeiro que combine com o tipo solicitado ou pega o primeiro disponível
            match = None
            for dev in devices:
                if device_template.get("connection_type") and dev.get("connection_type", "").lower() == device_template[
                    "connection_type"
                ].lower():
                    match = dev
                    break
            if not match and devices:
                match = devices[0]

            if match:
                merged = {**match, **device_template}
                if progress_cb:
                    progress_cb(min(95, int((waited / max_wait) * 100)))
                if self.establish_connection(merged):
                    if progress_cb:
                        progress_cb(100)
                    return True
            waited += poll_interval
            if progress_cb:
                progress_cb(min(90, int((waited / max_wait) * 100)))
            time.sleep(poll_interval)
        return False

    def is_connected(self) -> bool:
        return self.current_strategy is not None and self.current_strategy.connected

    def send(self, command: str) -> str:
        if not self.current_strategy:
            raise ConnectionError("Nenhuma estratégia de conexão ativa")
        return self.current_strategy.send_command(command)

    def _strategy_available(self, name: str) -> bool:
        if name == "adb":
            available = _binary_available("adb")
            if not available and not self._warned_adb_missing:
                logging.warning("ADB indisponível durante descoberta/conexão; verifique PATH ou instalação")
                self._warned_adb_missing = True
            return available
        if name == "fastboot":
            available = _binary_available("fastboot")
            if not available and not self._warned_fastboot_missing:
                logging.warning("Fastboot indisponível durante descoberta/conexão; verifique PATH ou instalação")
                self._warned_fastboot_missing = True
            return available
        if name == "odin":
            return True
        return True

    def emergency_recover(self) -> bool:
        if not self.current_strategy:
            return False
        return self.current_strategy.emergency_recovery()

    def wait_for_reboot(self, *, timeout: float = 60.0, reconnect: bool = True) -> bool:
        """Aguarda o ciclo de reinício para confirmar operações destrutivas.

        A rotina tenta detectar a desconexão do dispositivo e, opcionalmente,
        a reconexão subsequente dentro do tempo limite informado.
        """

        start = time.time()
        # Espera sumir
        while time.time() - start < timeout:
            if not self.is_connected():
                break
            time.sleep(1)
        else:
            logging.debug("Dispositivo não sinalizou desligamento dentro do timeout de reboot")
            return False

        if not reconnect:
            return True

        # Espera voltar
        while time.time() - start < timeout:
            found = self.discover_devices()
            if found:
                return True
            time.sleep(1)

        logging.debug("Dispositivo não reconectou dentro do tempo limite de reboot")
        return False

    def discover_devices(self) -> List[Dict[str, str]]:
        """Lista dispositivos disponíveis em ADB, Fastboot, USB e Serial."""
        devices: List[Dict[str, str]] = []

        # ADB
        if _binary_available("adb"):
            try:
                result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
                for line in result.stdout.splitlines():
                    if not line or "List of devices" in line or "offline" in line:
                        continue
                    parts = line.split()
                    if not parts:
                        continue
                    serial = parts[0]
                    model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), "")
                    brand = next((p.split(":", 1)[1] for p in parts if p.startswith("device:")), "")
                    devices.append(
                        {
                            "connection_type": "adb",
                            "serial": serial,
                            "model": model,
                            "brand": brand,
                            "label": " ".join(filter(None, ["ADB", serial, model])).strip(),
                        }
                    )
            except Exception:
                if not self._warned_adb_missing:
                    logging.info("ADB indisponível durante descoberta (instale platform-tools)")
                    self._warned_adb_missing = True
        else:
            if not self._warned_adb_missing:
                logging.info("ADB indisponível durante descoberta (instale platform-tools)")
                self._warned_adb_missing = True

        # Fastboot
        if _binary_available("fastboot"):
            try:
                result = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
                for line in result.stdout.splitlines():
                    if not line.strip():
                        continue
                    serial = line.split()[0]
                    devices.append(
                        {
                            "connection_type": "fastboot",
                            "serial": serial,
                            "label": f"Fastboot - {serial}",
                        }
                    )
            except Exception:
                if not self._warned_fastboot_missing:
                    logging.info("Fastboot indisponível durante descoberta (instale platform-tools)")
                    self._warned_fastboot_missing = True
        else:
            if not self._warned_fastboot_missing:
                logging.info("Fastboot indisponível durante descoberta (instale platform-tools)")
                self._warned_fastboot_missing = True

        # Serial/EDL enumerations
        try:
            for port in list_ports.comports():
                label = f"Serial {port.device} ({port.description})"
                connection_type = "serial"
                description_lower = (port.description or "").lower()
                if "diag" in description_lower or "serial diagnostic" in description_lower:
                    connection_type = "spd_diag"
                    label = f"Diag/SPD {port.device} ({port.description})"
                devices.append(
                    {
                        "connection_type": connection_type,
                        "port": port.device,
                        "label": label,
                    }
                )
        except Exception:
            logging.debug("Falha ao listar portas seriais")

        # USB based detection (MTP/Odin/MTK/Qualcomm)
        if self._usb_backend_available:
            try:
                for dev in usb.core.find(find_all=True):
                    vendor_id = f"{dev.idVendor:04x}"
                    product_id = f"{dev.idProduct:04x}"
                    bus = getattr(dev, "bus", None)
                    port_numbers = getattr(dev, "port_numbers", None)
                    port_path = "-".join(str(p) for p in port_numbers) if port_numbers else ""
                    port_hint = f" @bus{bus}:{port_path}" if bus or port_path else ""
                    brand = _VENDOR_BRANDS.get(vendor_id, "")
                    manufacturer = _safe_usb_string(dev, dev.iManufacturer)
                    product = _safe_usb_string(dev, dev.iProduct)
                    serial = _safe_usb_string(dev, dev.iSerialNumber)
                    readable_name = next(filter(None, [product, manufacturer, brand]), "")
                    label = " ".join(filter(None, [readable_name, f"({vendor_id}:{product_id}{port_hint})"])) or f"USB {vendor_id}:{product_id}{port_hint}"
                    connection_type = "usb_raw"
                    # Heurística para identificar modos específicos
                    if vendor_id == "04e8":
                        connection_type = "odin"
                        label = f"Odin/Download - {label}"
                    elif any(intf.bInterfaceClass == 6 for cfg in dev for intf in cfg):
                        connection_type = "mtp"
                        label = f"MTP - {label}"
                    elif vendor_id in {"1782", "1ebf"} and any(intf.bInterfaceClass in (255, 224) for cfg in dev for intf in cfg):
                        # Diagnóstico SPD/Unisoc costuma aparecer como interface vendor-specific
                        connection_type = "spd_diag"
                        label = f"SPD/Diag - {label}"
                    devices.append(
                        {
                            "connection_type": connection_type,
                            "vendor_id": vendor_id,
                            "product_id": product_id,
                            "brand": brand or manufacturer,
                            "model": readable_name,
                            "serial": serial,
                            "label": label,
                        }
                    )
            except NoBackendError:
                self._usb_backend_available = False
                if not self._warned_usb_backend:
                    logging.warning("Backend USB ausente ou libusb não instalada; detecção USB limitada")
                    self._warned_usb_backend = True
            except Exception:
                self._usb_backend_failures += 1
                logging.debug("Falha ao enumerar dispositivos USB")
                if self._usb_backend_failures >= 3:
                    self._usb_backend_available = False
                    logging.debug("Desativando enumeração USB após falhas repetidas")

        self._last_discovered = devices

        return devices

    def read_identity(self) -> Dict[str, str]:
        """Tenta obter modelo/serial automaticamente da estratégia ativa."""
        if not self.current_strategy:
            return dict(self._last_connected_identity)
        if self.current_name == "adb":
            try:
                serial = subprocess.run(["adb", "get-serialno"], capture_output=True, text=True, timeout=5).stdout.strip()
                model = subprocess.run(
                    ["adb", "shell", "getprop", "ro.product.model"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                brand = subprocess.run(
                    ["adb", "shell", "getprop", "ro.product.brand"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                return {"serial": serial, "model": model, "brand": brand}
            except Exception:
                return dict(self._last_connected_identity)
        if self.current_name == "fastboot":
            try:
                product_out = subprocess.run(
                    ["fastboot", "getvar", "product"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                serial_out = subprocess.run(
                    ["fastboot", "getvar", "serialno"], capture_output=True, text=True, timeout=5
                ).stdout.strip()
                model = product_out.split("product:")[-1].strip() if "product:" in product_out else product_out
                serial = serial_out.split("serialno:")[-1].strip() if "serialno:" in serial_out else serial_out
                return {"serial": serial, "model": model}
            except Exception:
                return dict(self._last_connected_identity)
        if self.current_name in {"odin", "mtp"}:
            return dict(self._last_connected_identity) or {"serial": "", "model": "Samsung (Download/MTP)"}
        return dict(self._last_connected_identity)

    def _merge_identity(self, device_info: Dict[str, str]) -> Dict[str, str]:
        """Mescla dados capturados durante descoberta para enriquecer identidade."""
        base = {k: v for k, v in device_info.items() if v}
        match = None
        serial = device_info.get("serial")
        vendor = device_info.get("vendor_id")
        product = device_info.get("product_id")
        for dev in self._last_discovered:
            if serial and dev.get("serial") == serial:
                match = dev
                break
            if vendor and product and dev.get("vendor_id") == vendor and dev.get("product_id") == product:
                match = dev
                break
        if match:
            for key in ("brand", "model", "serial", "connection_type"):
                base.setdefault(key, match.get(key, ""))
            # Se ainda faltar modelo, derive a partir do rótulo para evitar "android generic"
            if not base.get("model") and match.get("label"):
                base["model"] = match.get("label")
            if not base.get("brand") and match.get("vendor_id"):
                base["brand"] = _VENDOR_BRANDS.get(match.get("vendor_id", ""), "")
        else:
            # fallback extra com map de vendors
            if not base.get("brand") and base.get("vendor_id"):
                base["brand"] = _VENDOR_BRANDS.get(base.get("vendor_id", ""), "")
        return base

