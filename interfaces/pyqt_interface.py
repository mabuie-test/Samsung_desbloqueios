"""PyQt5-based graphical interface for Samsung Unlock Pro."""
from __future__ import annotations

import logging
import threading
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from interfaces.interface_controller import InterfaceController


class LogModel(QtCore.QAbstractListModel):
    """Model that receives log records and exposes them to a QListView."""

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._records: list[str] = []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._records)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):  # type: ignore[override]
        if not index.isValid() or not (0 <= index.row() < len(self._records)):
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return self._records[index.row()]
        return None

    @QtCore.pyqtSlot(str)
    def append_record(self, record: str) -> None:
        self.beginInsertRows(QtCore.QModelIndex(), len(self._records), len(self._records))
        self._records.append(record)
        self.endInsertRows()


class QtLogHandler(logging.Handler):
    """Logging handler that forwards log messages to the Qt model."""

    def __init__(self, model: LogModel):
        super().__init__(level=logging.INFO)
        self.model = model

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        QtCore.QMetaObject.invokeMethod(
            self.model,
            "append_record",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, msg),
        )


class SamsungUnlockQtWindow(QtWidgets.QMainWindow):
    """Main window with tabbed layout replicating existing Tk interface."""

    def __init__(self, controller: Optional[InterfaceController] = None, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.controller = controller or InterfaceController()
        self.core = self.controller.core
        self.setWindowTitle("Samsung Unlock Pro - PyQt Edition")
        self.resize(1100, 720)
        self._build_ui()
        self._connect_logging()
        self._discovered: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)

        layout = QtWidgets.QVBoxLayout(central_widget)
        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)

        self._build_connection_tab()
        self._build_mdm_tab()
        self._build_kg_tab()
        self._build_frp_tab()
        self._build_lock_tab()
        self._build_firmware_tab()
        self._build_log_tab()

    def _build_connection_tab(self) -> None:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)

        self.connection_mode = QtWidgets.QComboBox()
        self.connection_mode.addItems(["ADB", "MTP", "Odin", "USB Raw", "EDL", "Serial", "Fastboot"])
        self.connection_mode.setCurrentIndex(0)
        form.addRow("Modo de Conexão:", self.connection_mode)

        self.devices_view = QtWidgets.QListWidget()
        form.addRow("Dispositivos detectados:", self.devices_view)
        refresh_btn = QtWidgets.QPushButton("Atualizar")
        refresh_btn.clicked.connect(lambda: self._refresh_devices(auto=False))
        form.addRow(refresh_btn)

        self.device_model = QtWidgets.QLineEdit()
        self.device_model.setPlaceholderText("Ex: SM-A546E ou modelo equivalente")
        form.addRow("Modelo:", self.device_model)

        self.device_serial = QtWidgets.QLineEdit()
        self.device_serial.setPlaceholderText("Número de série/IMEI para perfis automáticos")
        form.addRow("Serial:", self.device_serial)

        self.auto_connect = QtWidgets.QCheckBox("Auto conectar assim que plugado")
        self.auto_connect.setChecked(True)
        form.addRow(self.auto_connect)

        button_layout = QtWidgets.QHBoxLayout()
        self.connect_button = QtWidgets.QPushButton("Conectar")
        self.disconnect_button = QtWidgets.QPushButton("Desconectar")
        self.info_button = QtWidgets.QPushButton("Obter informações")
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        button_layout.addWidget(self.info_button)
        form.addRow(button_layout)

        self.device_info_box = QtWidgets.QTextEdit()
        self.device_info_box.setReadOnly(True)
        self.device_info_box.setPlaceholderText("Marca, modelo, serial e versão aparecerão aqui")
        form.addRow("Informações do dispositivo:", self.device_info_box)

        self.connection_progress = QtWidgets.QProgressBar()
        self.connection_progress.setRange(0, 100)
        form.addRow("Progresso:", self.connection_progress)

        self.connection_status = QtWidgets.QLabel("Desconectado")
        form.addRow("Status:", self.connection_status)

        helper = QtWidgets.QLabel(
            "Dica: ADB para aparelhos ligados, EDL com test-point para emergência, USB Raw antes do boot. "
            "Informe modelo/serial para o ajuste automático do perfil de chipset."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: gray;")
        form.addRow(helper)

        self.connection_log = QtWidgets.QTextEdit()
        self.connection_log.setReadOnly(True)
        self.connection_log.setPlaceholderText("Logs de conexão, detecções e portas aparecerão aqui")
        self.connection_log.setMaximumHeight(150)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.connection_log.setFont(font)
        form.addRow("Logs:", self.connection_log)

        self.connect_button.clicked.connect(self._connect_device)
        self.disconnect_button.clicked.connect(self._disconnect_device)
        self.info_button.clicked.connect(self._show_device_information)

        self._refresh_devices(auto=False)
        self._start_auto_refresh()

        self.tab_widget.addTab(widget, "Conexão")

    def _build_firmware_tab(self) -> None:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)

        self.archive_path = QtWidgets.QLineEdit()
        self.archive_path.setPlaceholderText("Selecione o .tar.md5 ou pacote multi-marca")
        self.dest_path = QtWidgets.QLineEdit()
        self.dest_path.setPlaceholderText("Pasta opcional para saída Odin-ready")

        browse_archive = QtWidgets.QPushButton("Selecionar pacote")
        browse_dest = QtWidgets.QPushButton("Selecionar destino")

        browse_archive.clicked.connect(self._browse_archive)
        browse_dest.clicked.connect(self._browse_dest)

        form.addRow("Pacote de firmware:", self.archive_path)
        form.addRow("Destino (opcional):", self.dest_path)
        form.addRow(browse_archive, browse_dest)

        self.sanitize_samsung = QtWidgets.QPushButton("Sanitizar Samsung (.tar.md5)")
        self.sanitize_multi = QtWidgets.QPushButton("Neutralizar Multi-Marca")
        self.sanitize_status = QtWidgets.QLabel("Pronto")

        self.sanitize_samsung.clicked.connect(lambda: self._run_sanitization(self.controller.sanitize_firmware))
        self.sanitize_multi.clicked.connect(lambda: self._run_sanitization(self.controller.sanitize_multi_brand))

        form.addRow(self.sanitize_samsung)
        form.addRow(self.sanitize_multi)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.cancel_button = QtWidgets.QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self._cancel_sanitization)
        progress_layout = QtWidgets.QHBoxLayout()
        progress_layout.addWidget(self.progress)
        progress_layout.addWidget(self.cancel_button)
        form.addRow(progress_layout)

        form.addRow("Status:", self.sanitize_status)

        self.fw_log = QtWidgets.QTextEdit()
        self.fw_log.setReadOnly(True)
        form.addRow("Logs:", self.fw_log)

        helper = QtWidgets.QLabel(
            "Sequência: escolha o pacote original, defina destino (opcional) e acione a neutralização. "
            "O fluxo limpa Google/MDM/FRP e re-assina para evitar rejeição no Odin."
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: gray;")
        form.addRow(helper)

        self.tab_widget.addTab(widget, "Firmware")

    def _build_mdm_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        description = QtWidgets.QLabel("Remoção de MDM Persistente")
        description.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(description)

        self.mdm_button = QtWidgets.QPushButton("Remover MDM")
        layout.addWidget(self.mdm_button)

        self.mdm_progress = QtWidgets.QProgressBar()
        self.mdm_progress.setRange(0, 100)
        layout.addWidget(self.mdm_progress)

        self.mdm_status = QtWidgets.QLabel("Pronto para remover MDM")
        self.mdm_status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.mdm_status)

        self.mdm_button.clicked.connect(self._remove_mdm)

        self.tab_widget.addTab(widget, "Remoção MDM")

    def _build_kg_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        description = QtWidgets.QLabel("Bypass KG Lock")
        description.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(description)

        self.kg_button = QtWidgets.QPushButton("Executar Bypass KG Lock")
        layout.addWidget(self.kg_button)

        self.kg_progress = QtWidgets.QProgressBar()
        self.kg_progress.setRange(0, 100)
        layout.addWidget(self.kg_progress)

        self.kg_status = QtWidgets.QLabel("Pronto para bypass KG Lock")
        self.kg_status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.kg_status)

        self.kg_button.clicked.connect(self._bypass_kg)

        self.tab_widget.addTab(widget, "KG Lock Bypass")

    def _build_frp_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        description = QtWidgets.QLabel("Bypass FRP Android 14")
        description.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(description)

        self.frp_button = QtWidgets.QPushButton("Executar Bypass FRP")
        layout.addWidget(self.frp_button)

        self.frp_progress = QtWidgets.QProgressBar()
        self.frp_progress.setRange(0, 100)
        layout.addWidget(self.frp_progress)

        self.frp_status = QtWidgets.QLabel("Pronto para bypass FRP")
        self.frp_status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.frp_status)

        self.frp_button.clicked.connect(self._bypass_frp)

        self.tab_widget.addTab(widget, "FRP Bypass")

    def _build_lock_tab(self) -> None:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)

        self.lock_type = QtWidgets.QComboBox()
        self.lock_type.addItems(["Automático", "PIN", "Senha", "Padrão"])
        form.addRow("Tipo de Bloqueio:", self.lock_type)

        self.lock_button = QtWidgets.QPushButton("Remover Bloqueio")
        self.hardreset_button = QtWidgets.QPushButton("Hard reset (multi-estratégia)")
        form.addRow(self.lock_button)
        form.addRow(self.hardreset_button)

        chipset_row1 = QtWidgets.QHBoxLayout()
        self.hardreset_qc_button = QtWidgets.QPushButton("Hard reset Qualcomm")
        self.hardreset_mtk_button = QtWidgets.QPushButton("Hard reset MTK")
        chipset_row1.addWidget(self.hardreset_qc_button)
        chipset_row1.addWidget(self.hardreset_mtk_button)
        form.addRow(chipset_row1)

        chipset_row2 = QtWidgets.QHBoxLayout()
        self.hardreset_exynos_button = QtWidgets.QPushButton("Hard reset Exynos")
        self.hardreset_unisoc_button = QtWidgets.QPushButton("Hard reset Unisoc/SPD")
        chipset_row2.addWidget(self.hardreset_exynos_button)
        chipset_row2.addWidget(self.hardreset_unisoc_button)
        form.addRow(chipset_row2)

        self.controlled_reset_button = QtWidgets.QPushButton("Reset controlado (sem wipe)")
        form.addRow(self.controlled_reset_button)

        self.lock_progress = QtWidgets.QProgressBar()
        self.lock_progress.setRange(0, 100)
        form.addRow("Progresso:", self.lock_progress)

        self.lock_status = QtWidgets.QLabel("Pronto")
        form.addRow("Status:", self.lock_status)

        self.lock_button.clicked.connect(self._remove_lock)
        self.hardreset_button.clicked.connect(self._hard_reset)
        self.hardreset_qc_button.clicked.connect(lambda: self._hard_reset_chipset("qualcomm"))
        self.hardreset_mtk_button.clicked.connect(lambda: self._hard_reset_chipset("mtk"))
        self.hardreset_exynos_button.clicked.connect(lambda: self._hard_reset_chipset("exynos"))
        self.hardreset_unisoc_button.clicked.connect(lambda: self._hard_reset_chipset("unisoc"))
        self.controlled_reset_button.clicked.connect(self._controlled_reset)

        self.tab_widget.addTab(widget, "Remoção de Bloqueio")

    def _build_log_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        self.log_model = LogModel(widget)
        self.log_view = QtWidgets.QListView()
        self.log_view.setModel(self.log_model)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.log_view.setFont(font)
        layout.addWidget(self.log_view)

        self.tab_widget.addTab(widget, "Logs")

    # ------------------------------------------------------------------
    # Logging integration
    # ------------------------------------------------------------------
    def _connect_logging(self) -> None:
        handler = QtLogHandler(self.log_model)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(handler)

    def _start_auto_refresh(self) -> None:
        self.discovery_timer = QtCore.QTimer(self)
        self.discovery_timer.setInterval(2500)
        self.discovery_timer.timeout.connect(lambda: self._refresh_devices(auto=True))
        self.discovery_timer.start()
        self._append_connection_log("Monitor de detecção automática iniciado")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _connect_device(self) -> None:
        def task():
            try:
                selected_items = self.devices_view.selectedItems()
                chosen_label = selected_items[0].text() if selected_items else None
                info = self._discovered.get(chosen_label, {}) if hasattr(self, "_discovered") else {}
                model = info.get("model", self.device_model.text())
                serial = info.get("serial", self.device_serial.text())
                mode = info.get("connection_type", self.connection_mode.currentText())
                extra = {k: v for k, v in info.items() if k not in {"model", "serial", "connection_type"}}

                self._update_progress_bar(self.connection_progress, 10)
                self._update_status(self.connection_status, "Tentando conectar...")

                success = self.controller.connect(model, serial, mode, extra=extra)
                if not success:
                    self._update_status(self.connection_status, "Aguardando dispositivo...")
                    success = self.controller.wait_and_connect(
                        model,
                        serial,
                        mode,
                        extra=extra,
                        progress_cb=lambda v: self._update_progress_bar(self.connection_progress, v),
                    )

                if success:
                    identity = self.controller.fetch_identity()
                    if identity.get("model"):
                        self._update_line(self.device_model, identity.get("model"))
                    if identity.get("serial"):
                        self._update_line(self.device_serial, identity.get("serial"))
                    self._update_progress_bar(self.connection_progress, 100)
                    self._update_status(self.connection_status, "Conectado!")
                    self._append_connection_log(
                        f"Conexão ativa via {mode} - {serial or identity.get('serial') or 'sem serial'}"
                    )
                    self._show_info("Sucesso", "Dispositivo conectado!")
                else:
                    self._update_progress_bar(self.connection_progress, 0)
                    self._update_status(self.connection_status, "Falha na conexão")
                    self._append_connection_log("Falha ao conectar dispositivo")
                    self._show_error("Erro", "Falha na conexão")
            except Exception as exc:  # pragma: no cover - defensive
                logging.exception("Falha ao conectar dispositivo")
                self._update_progress_bar(self.connection_progress, 0)
                self._update_status(self.connection_status, f"Erro: {exc}")
                self._append_connection_log(f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _update_line(self, widget: QtWidgets.QLineEdit, value: str) -> None:
        QtCore.QMetaObject.invokeMethod(widget, "setText", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, value))

    def _refresh_devices(self, auto: bool = True) -> None:
        devices = self.controller.discover_devices()
        new_map = {d.get("label", f"Dev{i}"): d for i, d in enumerate(devices)}

        previous = getattr(self, "_discovered", {})
        added = set(new_map) - set(previous)
        removed = set(previous) - set(new_map)

        if not auto or added or removed:
            self.devices_view.clear()
            for label in new_map:
                self.devices_view.addItem(label)

        self._discovered = new_map

        for label in sorted(added):
            self._append_connection_log(f"Detectado: {label}")
            info = new_map[label]
            display_model = info.get("model") or info.get("brand")
            if display_model:
                self._update_line(self.device_model, display_model)
            if info.get("serial"):
                self._update_line(self.device_serial, info.get("serial", ""))
            if getattr(self, "auto_connect", None) and self.auto_connect.isChecked():
                threading.Thread(
                    target=lambda: self.controller.wait_and_connect(
                        info.get("model", self.device_model.text()),
                        info.get("serial", self.device_serial.text()),
                        info.get("connection_type", self.connection_mode.currentText()),
                        extra={k: v for k, v in info.items() if k not in {"model", "serial", "connection_type", "label"}},
                        progress_cb=lambda v: self._update_progress_bar(self.connection_progress, v),
                    ),
                    daemon=True,
                ).start()
        for label in sorted(removed):
            self._append_connection_log(f"Removido: {label}")

    def _show_device_information(self) -> None:
        info = self.controller.device_information()
        if not info:
            self._show_warning("Informações", "Nenhum dado disponível. Conecte um dispositivo.")
            return
        lines = [f"{k}: {v}" for k, v in info.items() if v]
        QtCore.QMetaObject.invokeMethod(
            self.device_info_box,
            "setPlainText",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, "\n".join(lines)),
        )

    def _disconnect_device(self) -> None:
        self._update_status(self.connection_status, "Desconectado")
        self.controller.disconnect()
        self._append_connection_log("Desconectado do dispositivo")
        self._show_info("Info", "Dispositivo desconectado")

    def _remove_mdm(self) -> None:
        def task():
            try:
                self._update_status(self.mdm_status, "Removendo MDM...")
                self._update_progress_bar(self.mdm_progress, 15)
                self._append_connection_log("MDM: rotina iniciada")
                if self.controller.remove_mdm():
                    self._update_progress_bar(self.mdm_progress, 100)
                    self._update_status(self.mdm_status, "MDM removido com sucesso!")
                    self._show_info("Sucesso", "MDM removido com sucesso!")
                else:
                    self._update_progress_bar(self.mdm_progress, 0)
                    self._update_status(self.mdm_status, "Falha ao remover MDM")
                    self._show_error("Erro", "Falha ao remover MDM")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha ao remover MDM")
                self._update_progress_bar(self.mdm_progress, 0)
                self._update_status(self.mdm_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _bypass_kg(self) -> None:
        def task():
            try:
                self._update_status(self.kg_status, "Executando bypass KG Lock...")
                self._update_progress_bar(self.kg_progress, 20)
                self._append_connection_log("KG: preparando bypass")
                if self.controller.bypass_kg():
                    self._update_progress_bar(self.kg_progress, 100)
                    self._update_status(self.kg_status, "KG Lock bypassado com sucesso!")
                    self._show_info("Sucesso", "KG Lock bypassado com sucesso!")
                else:
                    self._update_progress_bar(self.kg_progress, 0)
                    self._update_status(self.kg_status, "Falha no bypass KG Lock")
                    self._show_error("Erro", "Falha no bypass KG Lock")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha no bypass KG Lock")
                self._update_progress_bar(self.kg_progress, 0)
                self._update_status(self.kg_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _bypass_frp(self) -> None:
        def task():
            try:
                self._update_status(self.frp_status, "Executando bypass FRP...")
                self._update_progress_bar(self.frp_progress, 25)
                self._append_connection_log("FRP: iniciando rotina")
                if self.controller.bypass_frp():
                    self._update_progress_bar(self.frp_progress, 100)
                    self._update_status(self.frp_status, "FRP bypassado com sucesso!")
                    self._show_info("Sucesso", "FRP bypassado com sucesso!")
                else:
                    self._update_progress_bar(self.frp_progress, 0)
                    self._update_status(self.frp_status, "Falha no bypass FRP")
                    self._show_error("Erro", "Falha no bypass FRP")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha no bypass FRP")
                self._update_progress_bar(self.frp_progress, 0)
                self._update_status(self.frp_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _remove_lock(self) -> None:
        def task():
            try:
                self._update_status(self.lock_status, "Removendo bloqueio...")
                self._update_progress_bar(self.lock_progress, 30)
                self._append_connection_log("Tela: sequência de desbloqueio iniciada")
                lock_type = self.lock_type.currentText()
                if lock_type == "Automático":
                    lock_type = None
                if self.controller.remove_lock(lock_type):
                    self._update_progress_bar(self.lock_progress, 100)
                    self._update_status(self.lock_status, "Bloqueio removido com sucesso!")
                    self._show_info("Sucesso", "Bloqueio removido com sucesso!")
                else:
                    self._update_progress_bar(self.lock_progress, 0)
                    self._update_status(self.lock_status, "Falha ao remover bloqueio")
                    self._show_error("Erro", "Falha ao remover bloqueio")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha na remoção de bloqueio")
                self._update_progress_bar(self.lock_progress, 0)
                self._update_status(self.lock_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _hard_reset(self) -> None:
        def task():
            try:
                self._update_status(self.lock_status, "Executando hard reset...")
                self._update_progress_bar(self.lock_progress, 40)
                if self.controller.hard_reset():
                    self._update_progress_bar(self.lock_progress, 100)
                    self._update_status(self.lock_status, "Hard reset concluído")
                    self._show_info("Sucesso", "Hard reset executado")
                else:
                    self._update_progress_bar(self.lock_progress, 0)
                    self._update_status(self.lock_status, "Hard reset falhou")
                    self._show_error("Erro", "Hard reset falhou")
            except Exception as exc:
                logging.exception("Hard reset falhou")
                self._update_progress_bar(self.lock_progress, 0)
                self._update_status(self.lock_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _hard_reset_chipset(self, chipset: str) -> None:
        def task():
            try:
                self._update_status(self.lock_status, f"Hard reset dirigido ({chipset})...")
                self._update_progress_bar(self.lock_progress, 35)
                if self.controller.hard_reset_chipset(chipset):
                    self._update_progress_bar(self.lock_progress, 100)
                    self._update_status(self.lock_status, f"Hard reset {chipset} concluído")
                    self._show_info("Sucesso", f"Hard reset ({chipset}) executado")
                else:
                    self._update_progress_bar(self.lock_progress, 0)
                    self._update_status(self.lock_status, "Hard reset dirigido falhou")
                    self._show_error("Erro", "Hard reset dirigido falhou")
            except Exception as exc:
                logging.exception("Hard reset dirigido falhou")
                self._update_progress_bar(self.lock_progress, 0)
                self._update_status(self.lock_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _controlled_reset(self) -> None:
        def task():
            try:
                self._update_status(self.lock_status, "Reset controlado em andamento...")
                self._update_progress_bar(self.lock_progress, 25)
                if self.controller.controlled_reset():
                    self._update_progress_bar(self.lock_progress, 100)
                    self._update_status(self.lock_status, "Reset controlado concluído")
                    self._show_info("Sucesso", "Senha removida sem wipe")
                else:
                    self._update_progress_bar(self.lock_progress, 0)
                    self._update_status(self.lock_status, "Reset controlado falhou")
                    self._show_error("Erro", "Reset controlado falhou")
            except Exception as exc:
                logging.exception("Reset controlado falhou")
                self._update_progress_bar(self.lock_progress, 0)
                self._update_status(self.lock_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _update_status(self, label: QtWidgets.QLabel, message: str) -> None:
        QtCore.QMetaObject.invokeMethod(label, "setText", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, message))

    def _update_progress_bar(self, bar: QtWidgets.QProgressBar, value: int) -> None:
        QtCore.QMetaObject.invokeMethod(bar, "setValue", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(int, value))

    def _append_connection_log(self, message: str) -> None:
        if not hasattr(self, "connection_log"):
            return
        QtCore.QMetaObject.invokeMethod(
            self.connection_log,
            "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, message),
        )

    def _show_info(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.information(self, title, message)

    def _show_error(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, title, message)

    def _browse_archive(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Selecionar firmware")
        if path:
            self.archive_path.setText(path)

    def _browse_dest(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Selecionar destino")
        if path:
            self.dest_path.setText(path)

    def _run_sanitization(self, handler) -> None:
        archive = self.archive_path.text()
        destination = self.dest_path.text() or None
        if not archive:
            self._show_error("Arquivo", "Escolha um pacote de firmware")
            return

        def task():
            try:
                self._cancel_event = threading.Event()
                self._update_status(self.sanitize_status, "Processando...")
                ok = handler(archive, destination, progress_cb=self._update_progress, cancel_event=self._cancel_event)
                if ok:
                    self._update_status(self.sanitize_status, "Pacote neutralizado e assinado")
                    self._show_info("Sucesso", "Pacote pronto para uso no Odin")
                else:
                    self._update_status(self.sanitize_status, "Falha na neutralização")
                    self._show_error("Erro", "Falha ao processar firmware")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha ao sanitizar firmware")
                if str(exc) == "Operação cancelada":
                    self._update_status(self.sanitize_status, "Operação cancelada")
                else:
                    self._update_status(self.sanitize_status, f"Erro: {exc}")
                    self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _cancel_sanitization(self) -> None:
        if hasattr(self, "_cancel_event"):
            self._cancel_event.set()
            self._update_status(self.sanitize_status, "Cancelando...")

    def _update_progress(self, value: int) -> None:
        QtCore.QMetaObject.invokeMethod(
            self.progress,
            "setValue",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(int, value),
        )
        QtCore.QMetaObject.invokeMethod(
            self.fw_log,
            "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, f"Progresso: {value}%"),
        )


def run_pyqt_gui() -> None:
    """Entry point for launching the PyQt5 interface."""
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = SamsungUnlockQtWindow()
    window.show()
    sys.exit(app.exec_())
