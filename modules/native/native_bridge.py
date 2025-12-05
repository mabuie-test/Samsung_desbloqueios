"""Bridges optional native helpers that accelerate privileged workflows."""
from __future__ import annotations

import ctypes
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional


class NativeBridge:
    """Abstrai bibliotecas nativas opcionais para rotinas de baixo nível.

    Cada componente é carregado sob demanda, com fallback transparente quando o
    artefato (.so/.dll) não estiver disponível. Isso permite incorporar as
    otimizações sem quebrar execuções em ambientes onde a compilação nativa
    ainda não foi feita.
    """

    def __init__(self):
        self._base_dir = Path(__file__).resolve().parents[2] / "native"
        self._libraries: Dict[str, ctypes.CDLL] = {}
        self._load_optional("kernel_module")
        self._load_optional("usb_controller")
        self._load_optional("pattern_matcher")
        self._load_optional("edl_controller")

    def _load_optional(self, name: str):
        """Carrega a lib se existir ou tenta construir rapidamente no Windows.

        Em ambientes Windows o MinGW costuma produzir DLLs sem o prefixo
        ``lib``. Por isso, verificamos variações com e sem o prefixo e,
        na ausência do artefato, tentamos compilar automaticamente caso o
        ``gcc`` do MinGW esteja disponível no PATH (via Chocolatey, como
        mencionado pelo usuário).
        """

        candidates = []
        for extension in ("so", "dll", "dylib"):
            candidates.append(self._base_dir / f"lib{name}.{extension}")
            candidates.append(self._base_dir / f"{name}.{extension}")

        for candidate in candidates:
            if candidate.exists():
                try:
                    self._libraries[name] = ctypes.CDLL(str(candidate))
                    logging.info("Biblioteca nativa carregada: %s", candidate)
                    self._configure_signatures(name, self._libraries[name])
                    return
                except OSError as exc:
                    logging.debug("Falha ao carregar %s: %s", candidate, exc)

        # Auto-build best effort no Windows: tenta MinGW e depois MSVC Build Tools
        if self._try_autobuild(name):
            return self._load_optional(name)

        logging.debug("Biblioteca %s não encontrada; fallback em Python", name)

    def _try_autobuild(self, name: str) -> bool:
        """Tenta compilar o helper nativo usando MinGW ou MSVC (Build Tools)."""

        import os
        import platform
        import subprocess

        if platform.system().lower() != "windows":
            return False

        source = self._base_dir / f"{name}.c"
        if not source.exists():
            logging.debug("Fonte C ausente para %s", name)
            return False

        output = self._base_dir / f"lib{name}.dll"

        gcc = shutil.which("gcc") or shutil.which("x86_64-w64-mingw32-gcc")
        if gcc and self._build_with_mingw(gcc, source, output):
            return True

        msvc = self._discover_msvc_toolchain()
        if msvc:
            return self._build_with_msvc(msvc, source, output)

        logging.info(
            "Compilação nativa não realizada: instale MinGW (Chocolatey) ou VS Build Tools"
        )
        return False

    def _build_with_mingw(self, gcc: str, source: Path, output: Path) -> bool:
        import subprocess

        cmd = [
            gcc,
            "-shared",
            "-o",
            str(output),
            str(source),
            "-O2",
            "-Wall",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            logging.info("Compilação MinGW concluída para %s", output.name)
            return True
        except Exception as exc:  # pragma: no cover - best effort
            logging.debug("Compilação MinGW falhou para %s: %s", source.name, exc)
            return False

    def _discover_msvc_toolchain(self) -> Optional[dict]:
        """Tenta localizar o Build Tools da Microsoft (vsbuildtools)."""

        import os
        import platform

        if platform.system().lower() != "windows":
            return None

        cl_path = shutil.which("cl")
        vcvars_path: Optional[Path] = None

        # Procura vcvarsall.bat nas instalações padrões 2019/2022 Build Tools
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\\Program Files (x86)")
        for pattern in (
            "Microsoft Visual Studio/2022/BuildTools/VC/Auxiliary/Build/vcvarsall.bat",
            "Microsoft Visual Studio/2019/BuildTools/VC/Auxiliary/Build/vcvarsall.bat",
        ):
            candidate = Path(program_files_x86) / pattern
            if candidate.exists():
                vcvars_path = candidate
                break

        # Tentativa de localizar via VSINSTALLDIR (quando VsDevCmd já foi configurado)
        if not vcvars_path:
            vsinstall = os.environ.get("VSINSTALLDIR")
            if vsinstall:
                fallback = Path(vsinstall) / "VC/Auxiliary/Build/vcvarsall.bat"
                if fallback.exists():
                    vcvars_path = fallback

        if not cl_path and vcvars_path:
            # vcvarsall ajustará o PATH; o cl será chamado dentro do shell
            return {"vcvars": vcvars_path}
        if cl_path:
            return {"cl": Path(cl_path), "vcvars": vcvars_path}
        return None

    def _build_with_msvc(self, toolchain: dict, source: Path, output: Path) -> bool:
        import subprocess

        vcvars = toolchain.get("vcvars")
        cl_exe = toolchain.get("cl")

        # Comando via cmd para garantir que o ambiente do VS seja carregado
        if vcvars:
            cl_cmd = "cl" if not cl_exe else str(cl_exe)
            cmd = (
                f'"{vcvars}" amd64 && {cl_cmd} /nologo /LD /O2 /W3 "{source}" '
                f'/link /OUT:"{output}"'
            )
            exec_cmd = ["cmd", "/d", "/c", cmd]
        else:
            # cl já está no PATH com ambiente configurado
            cl_cmd = str(cl_exe)
            exec_cmd = [
                cl_cmd,
                "/nologo",
                "/LD",
                "/O2",
                "/W3",
                str(source),
                "/link",
                f"/OUT:{output}",
            ]

        try:
            subprocess.run(exec_cmd, check=True, capture_output=True, timeout=90)
            logging.info("Compilação MSVC concluída para %s", output.name)
            return True
        except Exception as exc:  # pragma: no cover - best effort
            logging.debug("Compilação MSVC falhou para %s: %s", source.name, exc)
            return False

    def _configure_signatures(self, name: str, lib: ctypes.CDLL):
        if name == "kernel_module":
            if hasattr(lib, "km_init"):
                lib.km_init.restype = ctypes.c_int
            if hasattr(lib, "km_mount_rw"):
                lib.km_mount_rw.argtypes = [ctypes.c_char_p]
                lib.km_mount_rw.restype = ctypes.c_int
            if hasattr(lib, "km_set_flag"):
                lib.km_set_flag.argtypes = [ctypes.c_char_p]
                lib.km_set_flag.restype = ctypes.c_int
            if hasattr(lib, "km_dump_ring_buffer"):
                lib.km_dump_ring_buffer.argtypes = [ctypes.c_char_p]
                lib.km_dump_ring_buffer.restype = ctypes.c_int
        elif name == "usb_controller":
            if hasattr(lib, "usb_initialize"):
                lib.usb_initialize.restype = ctypes.c_int
            if hasattr(lib, "usb_open_device"):
                lib.usb_open_device.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
                lib.usb_open_device.restype = ctypes.c_int
            if hasattr(lib, "usb_bulk_ping"):
                lib.usb_bulk_ping.argtypes = [
                    ctypes.c_ubyte,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_uint,
                ]
                lib.usb_bulk_ping.restype = ctypes.c_int
            if hasattr(lib, "usb_control_probe"):
                lib.usb_control_probe.argtypes = [
                    ctypes.c_ubyte,
                    ctypes.c_ubyte,
                    ctypes.c_uint16,
                    ctypes.c_uint16,
                    ctypes.c_char_p,
                    ctypes.c_uint16,
                    ctypes.c_uint,
                ]
                lib.usb_control_probe.restype = ctypes.c_int
        elif name == "pattern_matcher":
            if hasattr(lib, "pm_find_patterns"):
                lib.pm_find_patterns.argtypes = [
                    ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_char_p),
                    ctypes.c_char_p,
                    ctypes.c_size_t,
                ]
                lib.pm_find_patterns.restype = ctypes.c_int
        elif name == "edl_controller":
            if hasattr(lib, "edl_init"):
                lib.edl_init.restype = ctypes.c_int
            if hasattr(lib, "edl_open"):
                lib.edl_open.argtypes = [ctypes.c_uint16, ctypes.c_uint16]
                lib.edl_open.restype = ctypes.c_int
            if hasattr(lib, "edl_hello"):
                lib.edl_hello.argtypes = [ctypes.c_char_p, ctypes.c_int]
                lib.edl_hello.restype = ctypes.c_int
            if hasattr(lib, "edl_execute"):
                lib.edl_execute.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_uint,
                ]
                lib.edl_execute.restype = ctypes.c_int

    # ------------------------------------------------------------------
    # Kernel helpers
    # ------------------------------------------------------------------
    def ensure_privileged_kernel_interface(self) -> bool:
        lib = self._libraries.get("kernel_module")
        if not lib:
            logging.debug("kernel_module ausente; seguir com comandos ADB")
            return False
        result = lib.km_init()
        if result != 0:
            logging.warning("km_init falhou com código %s", result)
            return False
        logging.info("Contexto privilegiado ativado via kernel_module")
        return True

    def mount_rw(self, mountpoint: str) -> bool:
        lib = self._libraries.get("kernel_module")
        if not lib:
            return False
        result = lib.km_mount_rw(mountpoint.encode())
        if result != 0:
            logging.debug("km_mount_rw falhou em %s com código %s", mountpoint, result)
            return False
        return True

    def set_kernel_flag(self, flag: str) -> bool:
        lib = self._libraries.get("kernel_module")
        if not lib:
            return False
        result = lib.km_set_flag(flag.encode())
        return result == 0

    # ------------------------------------------------------------------
    # USB helpers
    # ------------------------------------------------------------------
    def initialize_usb(self) -> bool:
        lib = self._libraries.get("usb_controller")
        if not lib:
            return False
        return lib.usb_initialize() == 0

    def open_usb_device(self, vid: int, pid: int) -> bool:
        lib = self._libraries.get("usb_controller")
        if not lib:
            return False
        return lib.usb_open_device(ctypes.c_uint16(vid), ctypes.c_uint16(pid)) == 0

    def bulk_ping(self, endpoint: int, payload: bytes, timeout_ms: int = 500) -> int:
        lib = self._libraries.get("usb_controller")
        if not lib:
            logging.debug("bulk_ping fallback (sem usb_controller)")
            return 0
        buffer = ctypes.create_string_buffer(payload, len(payload))
        return lib.usb_bulk_ping(ctypes.c_ubyte(endpoint), buffer, len(payload), timeout_ms)

    def control_probe(
        self,
        request_type: int,
        request: int,
        value: int,
        index: int,
        length: int = 64,
    ) -> int:
        lib = self._libraries.get("usb_controller")
        if not lib:
            return 0
        buffer = ctypes.create_string_buffer(length)
        return lib.usb_control_probe(
            ctypes.c_ubyte(request_type),
            ctypes.c_ubyte(request),
            ctypes.c_uint16(value),
            ctypes.c_uint16(index),
            buffer,
            ctypes.c_uint16(length),
            ctypes.c_uint(250),
        )

    # ------------------------------------------------------------------
    # Pattern helpers
    # ------------------------------------------------------------------
    def match_security_patterns(self, payload: str, profile_hint: Optional[str] = None) -> List[str]:
        lib = self._libraries.get("pattern_matcher")
        if not payload:
            return []
        if lib and hasattr(lib, "pm_find_patterns"):
            out_buffer = ctypes.create_string_buffer(512)
            ptr = ctypes.cast((ctypes.c_char_p * 1)(), ctypes.POINTER(ctypes.c_char_p))
            lib.pm_find_patterns(payload.encode(), ptr, out_buffer, ctypes.c_size_t(len(out_buffer)))
            raw = out_buffer.value.decode()
            return [p for p in raw.split(",") if p]
        # fallback simples em Python
        patterns = [
            "verity",
            "dm-verity",
            "boot_fail",
            "secureboot",
            "kgsl",
            "frp",
            "vaultkeeper",
            "edl",
        ]
        if profile_hint and "Samsung" in profile_hint:
            patterns.append("odin")
        return [p for p in patterns if p in payload]

    # ------------------------------------------------------------------
    # EDL helpers
    # ------------------------------------------------------------------
    def ensure_edl_bridge(self, vid: int = 0x05C6, pid: int = 0x9008) -> bool:
        lib = self._libraries.get("edl_controller")
        if not lib:
            return False
        if lib.edl_init() != 0:
            return False
        return lib.edl_open(ctypes.c_uint16(vid), ctypes.c_uint16(pid)) == 0

    def edl_handshake(self) -> bool:
        lib = self._libraries.get("edl_controller")
        if not lib:
            return False
        buffer = ctypes.create_string_buffer(256)
        result = lib.edl_hello(buffer, ctypes.c_int(len(buffer)))
        if result < 0:
            logging.debug("edl_hello retornou %s", result)
            return False
        return True

    def edl_execute(self, command: bytes, timeout_ms: int = 1000) -> bool:
        lib = self._libraries.get("edl_controller")
        if not lib:
            return False
        resp = ctypes.create_string_buffer(256)
        result = lib.edl_execute(command, len(command), resp, len(resp), ctypes.c_uint(timeout_ms))
        if result < 0:
            logging.debug("edl_execute falhou com %s", result)
            return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def has_library(self, name: str) -> bool:
        return name in self._libraries


class NativeStrategyCoordinator:
    """Coordena fluxos que combinam estratégias Python e nativas."""

    def __init__(self, connection_handler, native_bridge: NativeBridge):
        self.connection_handler = connection_handler
        self.native_bridge = native_bridge

    def warmup_channels(self):
        self.native_bridge.ensure_privileged_kernel_interface()
        self.native_bridge.initialize_usb()

    def reinforce_connection(self, profile_hint: Optional[str] = None):
        if self.native_bridge.ensure_edl_bridge() and self.native_bridge.edl_handshake():
            logging.info("Canal EDL nativo pronto para contingência")
        if profile_hint and "Samsung" in profile_hint:
            self.native_bridge.set_kernel_flag("unlock_samsung")

    def ensure_privileged_mounts(self, mountpoints: List[str]):
        for mount in mountpoints:
            if self.native_bridge.mount_rw(mount):
                logging.debug("Montagem privilegiada aplicada via kernel_module: %s", mount)

    def usb_health_probe(self):
        if not self.native_bridge.has_library("usb_controller"):
            return
        payload = b"ping"
        self.native_bridge.bulk_ping(0x01, payload, 250)
        self.native_bridge.control_probe(0x80, 0x06, 0x0100, 0, 64)
