"""High level orchestration layer for Samsung Unlock Pro."""
from __future__ import annotations

import base64
import logging
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac

from modules.device_support.chipset_support import (
    ChipsetProfile,
    ChipsetSupportMatrix,
    build_default_matrix,
    merge_device_info,
)
from modules.device_support.operations import ChipsetOperations
from modules.emergency_com.multi_connection import ConnectionHandler
from modules.firmware import (
    FirmwareNeutralizer,
    MultiBrandNeutralizationManager,
    SanitizationResult,
    TarMD5Extractor,
)
from modules.frp_bypass.android_14_frp import Android14FRPBypass
from modules.lock_screen.lock_remover import LockScreenRemover as ModuleLockScreenRemover
from modules.native import NativeBridge, NativeStrategyCoordinator


class DeviceState(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    DOWNLOAD_MODE = 2
    RECOVERY_MODE = 3
    EDL_MODE = 4
    ROOTED = 5
    UNLOCKED = 6


class SecurityError(RuntimeError):
    """Erro de segurança genérico mantido para compatibilidade."""


class DeviceCryptoSuite:
    """Utilitário simples para derivar e validar HMACs do dispositivo."""

    def __init__(self):
        self.backend = default_backend()

    def derive_device_key(self, token: bytes) -> bytes:
        h = hashes.Hash(hashes.SHA256(), backend=self.backend)
        h.update(token)
        return h.finalize()

    def compute_hmac(self, key: bytes, payload: bytes) -> bytes:
        handler = hmac.HMAC(key, hashes.SHA256(), backend=self.backend)
        handler.update(payload)
        return handler.finalize()


class SamsungUnlockCore:
    def __init__(self):
        self.device_state = DeviceState.DISCONNECTED
        self.crypto_suite = DeviceCryptoSuite()
        self.chipset_matrix: ChipsetSupportMatrix = build_default_matrix()
        self.operations = ChipsetOperations()
        self.native_bridge = NativeBridge()
        self.connection_handler = AdvancedConnectionHandler(self.chipset_matrix, self.operations)
        self.native_coordinator = NativeStrategyCoordinator(self.connection_handler, self.native_bridge)
        self.firmware_tools = FirmwareTools(self.operations)
        self.partition_manager = AdvancedPartitionManager(
            self.connection_handler,
            self.firmware_tools,
            self.operations,
        )
        self.security_partitions = SecurityPartitionAccessManager(
            self.connection_handler,
            self.operations,
        )
        self.mdm_remover = AdvancedMDMRemover(self.connection_handler, self.operations)
        self.kg_lock_bypass = AdvancedKGLockBypass(self.connection_handler, self.operations)
        self.frp_bypass = UniversalFRPManager(self.connection_handler, self.operations, self.chipset_matrix)
        self.security_manager = EnhancedSecurityManager(
            self.connection_handler,
            self.operations,
            self.crypto_suite,
        )
        self.test_point_unlocker = TestPointUnlockCoordinator(
            self.chipset_matrix,
            self.connection_handler,
            self.operations,
        )
        self.pattern_analyzer = SecurityPatternAnalyzer(
            self.connection_handler, self.native_bridge
        )
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
            self.native_coordinator.warmup_channels()
            self.security_manager.initialize()
            self._start_device_monitoring()
            logging.info("Sistema inicializado com sucesso")
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha na inicialização: %s", exc)
            return False

    def execute_complete_unlock(self, device_info: Dict):
        """Executar processo completo de desbloqueio"""
        enriched_info = self.test_point_unlocker.prepare(device_info)
        merged_info = merge_device_info(enriched_info)
        try:
            if not self.connection_handler.establish_connection(merged_info):
                logging.warning("Tentativa inicial falhou, reforçando fluxo via test-point")
                tp_info = self.test_point_unlocker.force_test_point_profile(merged_info)
                if not self.connection_handler.establish_connection(tp_info, prefer_edl=True):
                    raise ConnectionError("Falha na conexão com o dispositivo")

            profile = self.connection_handler.device_profile
            if not profile:
                raise RuntimeError("Não foi possível identificar o chipset do dispositivo")

            logging.info("Perfil detectado: %s", self.chipset_matrix.describe_support(profile))

            self.native_coordinator.reinforce_connection(profile.name)

            if not self.security_manager.ensure_device_ready(profile):
                raise RuntimeError("Falha ao preparar o dispositivo para o desbloqueio")

            if not self.security_manager.perform_secure_attestation(profile):
                raise SecurityError("Falha na verificação criptográfica do dispositivo")

            backup_dir = Path("backups") / profile.name.replace(" ", "_")
            self.partition_manager.create_backups(backup_dir)

            prepared = self.firmware_tools.prepare_sanitized_package(profile)
            target_dir = prepared.prepared_directory if prepared else Path("firmware") / profile.name.replace(" ", "_")
            if prepared:
                logging.info("Pacote sanitizado pronto para flash: %s", prepared.signed_package)

            self.security_partitions.unlock_security_partitions(profile)

            if not self.firmware_tools.unlock_bootloader(self.connection_handler.current_strategy, profile):
                raise RuntimeError("Falha no desbloqueio do bootloader")

            self.partition_manager.flash_critical_images(target_dir)

            if not self.force_routing_and_remount():
                raise RuntimeError("Falha no roteamento e remontagem")

            if not self.frp_bypass.execute_advanced_bypass():
                raise RuntimeError("Falha no bypass FRP")

            self.security_partitions.normalize_frp_flags(profile)

            if not self.mdm_remover.remove_mdm_persistence():
                raise RuntimeError("Falha na remoção de MDM")

            if not self.kg_lock_bypass.execute_kg_lock_bypass():
                raise RuntimeError("Falha no bypass KG Lock")

            analysis = self.pattern_analyzer.analyze_security(profile)
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

    def hard_reset_device(self) -> bool:
        """Força um hard reset/factory reset com múltiplas estratégias."""
        try:
            return self.lock_remover.hard_reset_all()
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Falha ao executar hard reset: %s", exc)
            return False

    def force_routing_and_remount(self):
        """Forçar roteamento e remontagem de partições do sistema"""
        try:
            logging.info("Iniciando processo de roteamento e remontagem")
            self.native_coordinator.ensure_privileged_mounts(["/system", "/vendor", "/odm"])
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
        self.connection_handler.send_batch(commands)

    def _rewrite_system_partitions(self):
        profile = self.connection_handler.device_profile
        if not profile:
            return
        critical_partitions = self.operations.partitions_to_flash(profile)
        for partition in critical_partitions:
            mount_point = f"/mnt/{partition}"
            self._execute_privileged_command(f"mkdir -p {mount_point}")
            self._execute_privileged_command(f"mount /dev/block/by-name/{partition} {mount_point}")
        self._modify_partition_structures(profile, critical_partitions)

    def _modify_partition_structures(self, profile: ChipsetProfile, partitions: List[str]):
        blueprint = self.operations.partition_tweaks(profile)
        for partition in partitions:
            commands = blueprint.get(partition, [])
            if not commands:
                continue
            mount_point = f"/mnt/{partition}"
            for command in commands:
                try:
                    self._execute_privileged_command(command.format(mount=mount_point))
                except Exception as exc:
                    logging.debug(
                        "Falha ao aplicar ajuste em %s (%s): %s",
                        partition,
                        command,
                        exc,
                    )

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

    def establish_connection(self, device_info: Dict[str, str], prefer_edl: bool = False) -> bool:
        profile = self._matrix.identify(device_info)
        order = self._operations.connection_sequence(profile)
        if prefer_edl and "edl" in order:
            order = ["edl"] + [step for step in order if step != "edl"]
        if self._handler.establish_connection(device_info, order):
            self.device_profile = profile
            return True
        return False

    def wait_and_connect(self, device_info: Dict[str, str], *, prefer_edl: bool = False, progress_cb=None) -> bool:
        profile = self._matrix.identify(device_info)
        order = self._operations.connection_sequence(profile)
        if prefer_edl and "edl" in order:
            order = ["edl"] + [step for step in order if step != "edl"]
        if self._handler.wait_and_connect(device_info, progress_cb=progress_cb):
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

    def send_batch(self, commands: Iterable[str]) -> List[str]:
        responses: List[str] = []
        for command in commands:
            try:
                responses.append(self.send(command))
            except Exception as exc:
                logging.debug("Falha ao executar comando em lote %s: %s", command, exc)
        return responses

    def emergency_recover(self) -> bool:
        return self._handler.emergency_recover()

    def device_information(self) -> Dict[str, str]:
        info: Dict[str, str] = {}
        try:
            info.update(self._handler.read_identity())
        except Exception:
            pass
        if self.is_connected():
            try:
                info.setdefault("brand", self.send("getprop ro.product.brand").strip())
                info.setdefault("model", self.send("getprop ro.product.model").strip())
                info.setdefault("serial", self.send("getprop ro.serialno").strip())
                info["android_version"] = self.send("getprop ro.build.version.release").strip()
                info["bootloader"] = self.send("getprop ro.bootloader").strip()
            except Exception:
                logging.debug("Falha ao coletar propriedades do dispositivo")
        if self.device_profile:
            info.setdefault("chipset", self.device_profile.name)
        return info


class AdvancedPartitionManager:
    def __init__(
        self,
        connection_handler: AdvancedConnectionHandler,
        firmware_tools: "FirmwareTools",
        operations: ChipsetOperations,
    ):
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


class SecurityPartitionAccessManager:
    def __init__(self, connection_handler: AdvancedConnectionHandler, operations: ChipsetOperations):
        self.connection_handler = connection_handler
        self.operations = operations

    def unlock_security_partitions(self, profile: ChipsetProfile) -> bool:
        if not self.connection_handler.is_connected():
            return False
        success = True
        for partition in self.operations.security_partitions(profile):
            try:
                self.connection_handler.send(
                    f"if [ -e /dev/block/by-name/{partition} ]; then dd if=/dev/zero of=/dev/block/by-name/{partition} bs=4096 count=1; fi"
                )
                self.connection_handler.send(
                    f"if [ -e /dev/block/by-name/{partition} ]; then chmod 0660 /dev/block/by-name/{partition}; fi"
                )
                logging.info("Partição crítica %s liberada para escrita", partition)
            except Exception as exc:
                logging.debug("Não foi possível ajustar partição %s: %s", partition, exc)
                success = False
        return success

    def normalize_frp_flags(self, profile: ChipsetProfile) -> bool:
        if not self.connection_handler.is_connected():
            return False
        commands = [
            "settings put global device_provisioned 1",
            "settings put secure user_setup_complete 1",
            "setprop persist.sys.frp.pst 0",
        ]
        if profile.name.startswith("Samsung"):
            commands.append("content delete --uri content://settings/secure --where \"name='lock_screen_owner_info'\"")
        self.connection_handler.send_batch(commands)
        return True


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


class UniversalFRPManager:
    """Camada de FRP que tenta diferentes rotas para qualquer Android/chipset."""

    def __init__(
        self,
        connection_handler: AdvancedConnectionHandler,
        operations: ChipsetOperations,
        matrix: ChipsetSupportMatrix,
    ):
        self.connection_handler = connection_handler
        self.operations = operations
        self.matrix = matrix
        self.android14 = FRPBypassAndroid14(connection_handler)

    def execute_advanced_bypass(self) -> bool:
        if not self.connection_handler.is_connected():
            logging.error("Dispositivo não conectado para bypass FRP")
            return False

        profile = self.connection_handler.device_profile or self.matrix.identify({})
        android_version = ""
        try:
            android_version = self.connection_handler.send("getprop ro.build.version.release").strip()
        except Exception:
            logging.debug("Não foi possível ler versão do Android para FRP")

        # 1) Estratégia especializada Android 14+ quando aplicável
        if android_version and android_version.startswith("14"):
            if self.android14.execute_advanced_bypass():
                return True

        # 2) Estratégias universais por partição e propriedades
        base_commands = self.operations.frp_reset_commands(profile)
        self.connection_handler.send_batch(base_commands)

        # 3) Ajustes adicionais para Samsung/Odin (quando possível)
        if self.connection_handler.current_name == "odin":
            try:
                self.connection_handler.send("heimdall wipe FRP")
            except Exception:
                logging.debug("Heimdall indisponível para wipe FRP")

        # 4) Verificação leve: se o FRP foi sinalizado como limpo
        try:
            marker = self.connection_handler.send("getprop persist.sys.frp.pst").strip()
            if marker == "0" or not marker:
                return True
        except Exception:
            pass

        # 5) Último recurso: remover contas Google e serviços de proteção
        rescue_commands = [
            "pm uninstall --user 0 com.google.android.gms",
            "pm uninstall --user 0 com.google.android.gsf",
            "settings delete secure android_id",
        ]
        self.connection_handler.send_batch(rescue_commands)
        return True


class EnhancedSecurityManager:
    def __init__(
        self,
        connection_handler: AdvancedConnectionHandler,
        operations: ChipsetOperations,
        crypto_suite: DeviceCryptoSuite,
    ):
        self.connection_handler = connection_handler
        self.operations = operations
        self.crypto_suite = crypto_suite
        self._device_key: Optional[bytes] = None

    def initialize(self):
        logging.info("Inicializando verificações de segurança")
        self._device_key = None
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

    def perform_secure_attestation(self, profile: ChipsetProfile) -> bool:
        if not self.connection_handler.is_connected():
            return False
        try:
            token = self.connection_handler.send("getprop ro.boot.bl_unlock_token").encode()
            if not token:
                logging.debug("Token de boot vazio, ignorando attestation")
                return True
            self._device_key = self.crypto_suite.derive_device_key(token)
            payload = self._build_attestation_payload(profile)
            b64_payload = base64.b64encode(payload).decode()
            response_raw = self.connection_handler.send(
                f"attestor --payload {b64_payload}"
            ).strip()
            try:
                response = base64.b64decode(response_raw)
            except Exception:
                response = response_raw.encode()
            expected = self.crypto_suite.compute_hmac(self._device_key, payload)
            if expected != response:
                logging.error("Attestation HMAC divergente")
                return False
            return True
        except Exception as exc:
            logging.error("Falha na verificação criptográfica: %s", exc)
            return False

    def _build_attestation_payload(self, profile: ChipsetProfile) -> bytes:
        primary_manufacturer = profile.manufacturers[0] if profile.manufacturers else "generic"
        seed = "|".join(
            [
                profile.name,
                primary_manufacturer,
                ",".join(profile.preferred_connections),
            ]
        ).encode()
        handler = hmac.HMAC(b"unlock", hashes.SHA256(), backend=self.crypto_suite.backend)
        handler.update(seed)
        return handler.finalize()


class FirmwareTools:
    """High level helpers that wrap firmware management utilities."""

    def __init__(self, operations: ChipsetOperations):
        self.extractor = TarMD5Extractor()
        self.operations = operations
        self.neutralizer = FirmwareNeutralizer(self.extractor)
        self.multi_brand_manager = MultiBrandNeutralizationManager(self.neutralizer)

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

    # ------------------------------------------------------------------
    # Novas rotinas de sanitização
    # ------------------------------------------------------------------
    def prepare_sanitized_package(
        self, profile: ChipsetProfile, raw_archives: Optional[List[Path]] = None
    ) -> Optional[SanitizationResult]:
        archive_dir = Path("firmware/raw")
        archive_dir.mkdir(parents=True, exist_ok=True)
        if raw_archives is None:
            pattern = f"{profile.name.replace(' ', '_')}*"
            raw_archives = list(archive_dir.glob(pattern))
        if not raw_archives:
            logging.info("Nenhum pacote bruto encontrado em %s", archive_dir)
            return None
        target = Path("firmware") / profile.name.replace(" ", "_") / "sanitized"
        target.mkdir(parents=True, exist_ok=True)
        result = self.multi_brand_manager.neutralize_any(raw_archives[0], target).sanitized
        return result


class SecurityPatternAnalyzer:
    def __init__(
        self,
        connection_handler: AdvancedConnectionHandler,
        native_bridge: Optional[NativeBridge] = None,
    ):
        self.connection_handler = connection_handler
        self.native_bridge = native_bridge

    def analyze_security(self, profile: Optional[ChipsetProfile] = None) -> Dict[str, str]:
        if not self.connection_handler.is_connected():
            return {"status": "desconhecido"}
        indicators = {}
        try:
            indicators["verified_boot"] = self.connection_handler.send("getprop ro.boot.verifiedbootstate").strip()
            indicators["oem_unlock"] = self.connection_handler.send("getprop sys.oem_unlock_allowed").strip()
            indicators["kg_state"] = self.connection_handler.send("getprop ro.security.vaultkeeper.state").strip()
            log_tail = self.connection_handler.send("dmesg | tail -n 200")
            patterns = []
            if self.native_bridge:
                patterns = self.native_bridge.match_security_patterns(
                    log_tail, profile.name if profile else None
                )
            if patterns:
                indicators["native_patterns"] = ",".join(patterns)
        except Exception as exc:
            logging.debug("Falha ao coletar indicadores de segurança: %s", exc)
        return indicators


class TestPointUnlockCoordinator:
    def __init__(self, matrix: ChipsetSupportMatrix, connection_handler: AdvancedConnectionHandler, operations: ChipsetOperations):
        self.matrix = matrix
        self.connection_handler = connection_handler
        self.operations = operations

    def prepare(self, device_info: Dict[str, str]) -> Dict[str, str]:
        profile = self.matrix.identify(device_info)
        for tip in self.operations.test_point_guides(profile):
            logging.info("Dica de test-point (%s): %s", profile.name, tip)
        enriched = dict(device_info)
        enriched.setdefault("test_point", device_info.get("test_point", False))
        return enriched

    def force_test_point_profile(self, device_info: Dict[str, str]) -> Dict[str, str]:
        profile = self.matrix.identify(device_info)
        forced = dict(device_info)
        forced["test_point"] = True
        forced.setdefault("key_combo", True)
        forced.setdefault("software_exploit", False)
        logging.info("Forçando conexão por test-point para %s", profile.name)
        return forced


class LockScreenRemovalOrchestrator:
    def __init__(self, connection_handler: AdvancedConnectionHandler):
        self.connection_handler = connection_handler

    def remove_lock_screen(self, lock_type=None):
        if not self.connection_handler.is_connected():
            logging.error("Dispositivo não conectado")
            return False
        remover = ModuleLockScreenRemover(self.connection_handler.current_strategy)
        return remover.remove_lock_screen(lock_type)

    def hard_reset_all(self) -> bool:
        if not self.connection_handler.is_connected():
            logging.error("Dispositivo não conectado")
            return False
        remover = ModuleLockScreenRemover(self.connection_handler.current_strategy)
        return remover.hard_reset_device()

