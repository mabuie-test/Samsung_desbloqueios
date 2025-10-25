"""High level orchestration layer for Samsung Unlock Pro."""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from modules.device_support.chipset_support import (
    ChipsetProfile,
    ChipsetSupportMatrix,
    build_default_matrix,
    merge_device_info,
)
from modules.device_support.operations import ChipsetOperations
from modules.emergency_com.multi_connection import ConnectionHandler
from modules.firmware import TarMD5Extractor
from modules.frp_bypass.android_14_frp import Android14FRPBypass
from modules.lock_screen.lock_remover import LockScreenRemover as ModuleLockScreenRemover


class DeviceState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    DOWNLOAD_MODE = 2
    RECOVERY_MODE = 3
    EDL_MODE = 4
    ROOTED = 5
    UNLOCKED = 6


class SamsungUnlockCore:
    def __init__(self):
        self.device_state = DeviceState.DISCONNECTED
        self.chipset_matrix: ChipsetSupportMatrix = build_default_matrix()
        self.operations = ChipsetOperations()
        self.connection_handler = AdvancedConnectionHandler(self.chipset_matrix, self.operations)
        self.firmware_tools = FirmwareTools(self.operations)
        self.partition_manager = AdvancedPartitionManager(self.connection_handler, self.firmware_tools, self.operations)
        self.mdm_remover = AdvancedMDMRemover(self.connection_handler, self.operations)
        self.kg_lock_bypass = AdvancedKGLockBypass(self.connection_handler, self.operations)
        self.frp_bypass = FRPBypassAndroid14(self.connection_handler)
        self.security_manager = EnhancedSecurityManager(self.connection_handler, self.operations)
        self.pattern_analyzer = SecurityPatternAnalyzer(self.connection_handler)
        self.lock_remover = LockScreenRemovalOrchestrator(self.connection_handler)

        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("samsung_unlock.log"),
                logging.StreamHandler(),
            ],
        )

    def initialize_system(self):
        """Inicialização completa do sistema"""
        try:
            logging.info("Inicializando sistema de desbloqueio com matriz multi-chipset")
            self._load_custom_drivers()
            self._check_hardware_requirements()
            self.security_manager.initialize()
            self._start_device_monitoring()
            logging.info("Sistema inicializado com sucesso")
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na inicialização: %s", exc)
            return False

    def execute_complete_unlock(self, device_info: Dict):
        """Executar processo completo de desbloqueio"""
        merged_info = merge_device_info(device_info)
        try:
            if not self.connection_handler.establish_connection(merged_info):
                raise ConnectionError("Falha na conexão com o dispositivo")

            profile = self.connection_handler.device_profile
            if not profile:
                raise RuntimeError("Não foi possível identificar o chipset do dispositivo")

            logging.info("Perfil detectado: %s", self.chipset_matrix.describe_support(profile))

            if not self.security_manager.ensure_device_ready(profile):
                raise RuntimeError("Falha ao preparar o dispositivo para o desbloqueio")

            backup_dir = Path("backups") / profile.name.replace(" ", "_")
            self.partition_manager.create_backups(backup_dir)

            if not self.firmware_tools.unlock_bootloader(self.connection_handler.current_strategy, profile):
                raise RuntimeError("Falha no desbloqueio do bootloader")

            self.partition_manager.flash_critical_images(Path("firmware") / profile.name.replace(" ", "_"))

            if not self.force_routing_and_remount():
                raise RuntimeError("Falha no roteamento e remontagem")

            if not self.frp_bypass.execute_advanced_bypass():
                raise RuntimeError("Falha no bypass FRP")

            if not self.mdm_remover.remove_mdm_persistence():
                raise RuntimeError("Falha na remoção de MDM")

            if not self.kg_lock_bypass.execute_kg_lock_bypass():
                raise RuntimeError("Falha no bypass KG Lock")

            analysis = self.pattern_analyzer.analyze_security()
            logging.debug("Resumo de integridade pós-desbloqueio: %s", analysis)

            self.device_state = DeviceState.UNLOCKED
            logging.info("Desbloqueio completo realizado com sucesso!")
            return True
        except Exception as exc:
            logging.error("Erro durante o desbloqueio: %s", exc)
            return False

    def remove_screen_lock(self, lock_type=None):
        """Remove bloqueio de tela com um clique"""
        try:
            return self.lock_remover.remove_lock_screen(lock_type)
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na remoção de bloqueio de tela: %s", exc)
            return False

    def force_routing_and_remount(self):
        """Forçar roteamento e remontagem de partições do sistema"""
        try:
            logging.info("Iniciando processo de roteamento e remontagem")
            self._execute_privileged_command("mount -o remount,rw /system")
            self._execute_privileged_command("mount -o remount,rw /vendor")
            self._execute_privileged_command("mount -o remount,rw /odm")
            self._setup_network_routing()
            self._rewrite_system_partitions()
            self._configure_selinux_policies()
            logging.info("Roteamento e remontagem concluídos com sucesso")
            return True
        except Exception as exc:
            logging.error("Erro no roteamento: %s", exc)
            return False

    def _setup_network_routing(self):
        commands = [
            "iptables -t nat -A OUTPUT -p tcp --dport 443 -j REDIRECT --to-port 8080",
            "iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 8080",
            "ip rule add from all lookup main pref 9999",
        ]
        for command in commands:
            self._execute_privileged_command(command)

    def _rewrite_system_partitions(self):
        profile = self.connection_handler.device_profile
        if not profile:
            return
        critical_partitions = self.operations.partitions_to_flash(profile)
        for partition in critical_partitions:
            mount_point = f"/mnt/{partition}"
            self._execute_privileged_command(f"mkdir -p {mount_point}")
            self._execute_privileged_command(f"mount /dev/block/by-name/{partition} {mount_point}")

    def _execute_privileged_command(self, command):
        if not self.connection_handler.is_connected():
            raise ConnectionError("Dispositivo não conectado")
        current = self.connection_handler.current_strategy
        if not current:
            raise ConnectionError("Estratégia de conexão indisponível")
        logging.debug("Executando comando privilegiado: %s", command)
        return current.send_command(command)

    def _load_custom_drivers(self):
        required_modules = ["diag_bridge", "sec_config", "usb_serial"]
        for module in required_modules:
            try:
                self._execute_host_command(["modprobe", module])
            except FileNotFoundError:
                logging.warning("Módulo %s não encontrado no host", module)

    def _execute_host_command(self, command: List[str]):
        logging.debug("Executando comando no host: %s", " ".join(command))
        return subprocess.run(command, check=False)

    def _check_hardware_requirements(self):
        binaries = ["adb", "fastboot", "heimdall", "mtk", "spd"]
        missing = [binary for binary in binaries if not self.operations.ensure_binary(binary)]
        if missing:
            logging.warning("Ferramentas ausentes: %s", ", ".join(missing))

    def _start_device_monitoring(self):
        def monitor():
            while True:
                time.sleep(2)
                if not self.connection_handler.is_connected():
                    self.device_state = DeviceState.DISCONNECTED
                    continue
                self.device_state = DeviceState.CONNECTED
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def _configure_selinux_policies(self):
        commands = [
            "setenforce 0",
            "magiskpolicy --live 'allow system_server * * *'",
        ]
        for command in commands:
            try:
                self._execute_privileged_command(command)
            except Exception as exc:
                logging.debug("Falha ao ajustar política SELinux: %s", exc)


class AdvancedConnectionHandler:
    def __init__(self, matrix: ChipsetSupportMatrix, operations: ChipsetOperations):
        self._handler = ConnectionHandler()
        self._matrix = matrix
        self._operations = operations
        self.device_profile: Optional[ChipsetProfile] = None

    def establish_connection(self, device_info: Dict[str, str]) -> bool:
        profile = self._matrix.identify(device_info)
        order = self._operations.connection_sequence(profile)
        if self._handler.establish_connection(device_info, order):
            self.device_profile = profile
            return True
        return False

    def is_connected(self) -> bool:
        return self._handler.is_connected()

    @property
    def current_strategy(self):
        return self._handler.current_strategy

    def send(self, command: str) -> str:
        return self._handler.send(command)

    def emergency_recover(self) -> bool:
        return self._handler.emergency_recover()


class AdvancedPartitionManager:
    def __init__(self, connection_handler: AdvancedConnectionHandler, firmware_tools: "FirmwareTools", operations: ChipsetOperations):
        self.connection_handler = connection_handler
        self.firmware_tools = firmware_tools
        self.operations = operations

    def create_backups(self, destination: Path) -> List[Path]:
        if not self.connection_handler.is_connected() or not self.connection_handler.device_profile:
            raise ConnectionError("Dispositivo não conectado")
        destination.mkdir(parents=True, exist_ok=True)
        profile = self.connection_handler.device_profile
        produced: List[Path] = []
        for partition in self.operations.partitions_to_backup(profile):
            remote_path = f"/data/local/tmp/{partition}.img"
            try:
                self.connection_handler.send(f"dd if=/dev/block/by-name/{partition} of={remote_path} bs=4096")
                produced.append(destination / f"{partition}.img")
                logging.info("Backup planejado para partição %s", partition)
            except Exception as exc:
                logging.warning("Falha ao criar backup da partição %s: %s", partition, exc)
        return produced

    def flash_critical_images(self, firmware_dir: Path) -> bool:
        if not self.connection_handler.is_connected() or not self.connection_handler.device_profile:
            raise ConnectionError("Dispositivo não conectado")
        profile = self.connection_handler.device_profile
        firmware_dir.mkdir(parents=True, exist_ok=True)
        return self.firmware_tools.flash_firmware(self.connection_handler.current_strategy, profile, firmware_dir)


class AdvancedMDMRemover:
    def __init__(self, connection_handler: AdvancedConnectionHandler, operations: ChipsetOperations):
        self.connection_handler = connection_handler
        self.operations = operations

    def remove_mdm_persistence(self) -> bool:
        if not self.connection_handler.is_connected() or not self.connection_handler.device_profile:
            return False
        profile = self.connection_handler.device_profile
        success = True
        for package in self.operations.mdm_packages(profile):
            try:
                self.connection_handler.send(f"pm uninstall --user 0 {package}")
            except Exception as exc:
                logging.debug("Não foi possível remover pacote %s: %s", package, exc)
                success = False
        self.connection_handler.send("pm clear com.android.managedprovisioning")
        return success


class AdvancedKGLockBypass:
    def __init__(self, connection_handler: AdvancedConnectionHandler, operations: ChipsetOperations):
        self.connection_handler = connection_handler
        self.operations = operations

    def execute_kg_lock_bypass(self) -> bool:
        if not self.connection_handler.is_connected() or not self.connection_handler.device_profile:
            return False
        profile = self.connection_handler.device_profile
        try:
            for service in self.operations.kg_services(profile):
                self.connection_handler.send(f"stop {service}")
                self.connection_handler.send(f"setprop persist.security.{service} disabled")
            self.connection_handler.send("settings put global device_provisioned 1")
            return True
        except Exception as exc:
            logging.error("Falha no bypass KG Lock: %s", exc)
            return False


class FRPBypassAndroid14:
    def __init__(self, connection_handler: AdvancedConnectionHandler):
        self.connection_handler = connection_handler

    def execute_advanced_bypass(self) -> bool:
        if not self.connection_handler.is_connected():
            logging.error("Dispositivo não conectado para bypass FRP")
            return False
        strategy = Android14FRPBypass(self.connection_handler.current_strategy)
        return strategy.execute_advanced_bypass()


class EnhancedSecurityManager:
    def __init__(self, connection_handler: AdvancedConnectionHandler, operations: ChipsetOperations):
        self.connection_handler = connection_handler
        self.operations = operations

    def initialize(self):
        logging.info("Inicializando verificações de segurança")
        return True

    def ensure_device_ready(self, profile: ChipsetProfile) -> bool:
        if not self.connection_handler.is_connected():
            return False
        try:
            self.connection_handler.send("settings put global adb_enabled 1")
            self.connection_handler.send("svc usb setFunctions mtp,adb")
            tool = self.operations.recommended_firmware_tool(profile)
            if not self.operations.ensure_binary(tool):
                logging.warning("Ferramenta %s ausente no host", tool)
            return True
        except Exception as exc:
            logging.error("Falha ao preparar dispositivo: %s", exc)
            return False


class FirmwareTools:
    """High level helpers that wrap firmware management utilities."""

    def __init__(self, operations: ChipsetOperations):
        self.extractor = TarMD5Extractor()
        self.operations = operations

    def extract_firmware_package(self, archive_path: str, destination: Optional[str] = None, *, verify: bool = True):
        archive = Path(archive_path)
        dest = Path(destination) if destination else None
        result = self.extractor.extract(archive, dest, verify=verify)
        logging.info(
            "Extração concluída: %s arquivos para %s (verificado=%s)",
            len(result.extracted_files),
            result.destination,
            result.verified,
        )
        return result

    def extract_multiple_packages(self, archives: List[str], *, verify: bool = True):
        results = self.extractor.extract_many(archives, verify=verify)
        logging.info("Extração em lote finalizada: %s pacotes", len(results))
        return results

    def prepare_chipset_tooling(self, profile: ChipsetProfile) -> str:
        tool = self.operations.recommended_firmware_tool(profile)
        if not self.operations.ensure_binary(tool):
            logging.warning("Ferramenta %s não disponível no PATH", tool)
        return tool

    def unlock_bootloader(self, connection_strategy, profile: ChipsetProfile) -> bool:
        return self.operations.unlock_bootloader(connection_strategy, profile)

    def flash_firmware(self, connection_strategy, profile: ChipsetProfile, firmware_dir: Path) -> bool:
        tool = self.prepare_chipset_tooling(profile)
        partitions = self.operations.partitions_to_flash(profile)
        mapping = self.operations.locate_images(firmware_dir, partitions)
        success = True
        for partition in partitions:
            image = mapping.get(partition)
            if not image:
                logging.debug("Imagem não encontrada para %s", partition)
                continue
            try:
                connection_strategy.send_command(f"{tool} flash {partition} {image}")
            except Exception as exc:
                logging.error("Falha ao enviar flash de %s: %s", partition, exc)
                success = False
        return success


class SecurityPatternAnalyzer:
    def __init__(self, connection_handler: AdvancedConnectionHandler):
        self.connection_handler = connection_handler

    def analyze_security(self) -> Dict[str, str]:
        if not self.connection_handler.is_connected():
            return {"status": "desconhecido"}
        indicators = {}
        try:
            indicators["verified_boot"] = self.connection_handler.send("getprop ro.boot.verifiedbootstate").strip()
            indicators["oem_unlock"] = self.connection_handler.send("getprop sys.oem_unlock_allowed").strip()
            indicators["kg_state"] = self.connection_handler.send("getprop ro.security.vaultkeeper.state").strip()
        except Exception as exc:
            logging.debug("Falha ao coletar indicadores de segurança: %s", exc)
        return indicators


class LockScreenRemovalOrchestrator:
    def __init__(self, connection_handler: AdvancedConnectionHandler):
        self.connection_handler = connection_handler

    def remove_lock_screen(self, lock_type=None):
        if not self.connection_handler.is_connected():
            logging.error("Dispositivo não conectado")
            return False
        remover = ModuleLockScreenRemover(self.connection_handler.current_strategy)
        return remover.remove_lock_screen(lock_type)

