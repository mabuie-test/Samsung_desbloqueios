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
        self.connection_mode.addItems(["ADB", "USB Raw", "EDL", "Serial"])
        form.addRow("Modo de Conexão:", self.connection_mode)

        self.device_model = QtWidgets.QLineEdit()
        form.addRow("Modelo:", self.device_model)

        self.device_serial = QtWidgets.QLineEdit()
        form.addRow("Serial:", self.device_serial)

        button_layout = QtWidgets.QHBoxLayout()
        self.connect_button = QtWidgets.QPushButton("Conectar")
        self.disconnect_button = QtWidgets.QPushButton("Desconectar")
        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.disconnect_button)
        form.addRow(button_layout)

        self.connection_status = QtWidgets.QLabel("Desconectado")
        form.addRow("Status:", self.connection_status)

        self.connect_button.clicked.connect(self._connect_device)
        self.disconnect_button.clicked.connect(self._disconnect_device)

        self.tab_widget.addTab(widget, "Conexão")

    def _build_firmware_tab(self) -> None:
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(widget)

        self.archive_path = QtWidgets.QLineEdit()
        self.dest_path = QtWidgets.QLineEdit()

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
        form.addRow("Status:", self.sanitize_status)

        self.tab_widget.addTab(widget, "Firmware")

    def _build_mdm_tab(self) -> None:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        description = QtWidgets.QLabel("Remoção de MDM Persistente")
        description.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(description)

        self.mdm_button = QtWidgets.QPushButton("Remover MDM")
        layout.addWidget(self.mdm_button)

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
        form.addRow(self.lock_button)

        self.lock_status = QtWidgets.QLabel("Pronto")
        form.addRow("Status:", self.lock_status)

        self.lock_button.clicked.connect(self._remove_lock)

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

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _connect_device(self) -> None:
        def task():
            try:
                device_info = {
                    "model": self.device_model.text(),
                    "serial": self.device_serial.text(),
                    "connection_type": self.connection_mode.currentText(),
                }
                if self.controller.connect(
                    device_info["model"], device_info["serial"], device_info["connection_type"]
                ):
                    self._update_status(self.connection_status, "Conectado!")
                    self._show_info("Sucesso", "Dispositivo conectado!")
                else:
                    self._update_status(self.connection_status, "Falha na conexão")
                    self._show_error("Erro", "Falha na conexão")
            except Exception as exc:  # pragma: no cover - defensive
                logging.exception("Falha ao conectar dispositivo")
                self._update_status(self.connection_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _disconnect_device(self) -> None:
        self._update_status(self.connection_status, "Desconectado")
        self.controller.disconnect()
        self._show_info("Info", "Dispositivo desconectado")

    def _remove_mdm(self) -> None:
        def task():
            try:
                self._update_status(self.mdm_status, "Removendo MDM...")
                if self.controller.remove_mdm():
                    self._update_status(self.mdm_status, "MDM removido com sucesso!")
                    self._show_info("Sucesso", "MDM removido com sucesso!")
                else:
                    self._update_status(self.mdm_status, "Falha ao remover MDM")
                    self._show_error("Erro", "Falha ao remover MDM")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha ao remover MDM")
                self._update_status(self.mdm_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _bypass_kg(self) -> None:
        def task():
            try:
                self._update_status(self.kg_status, "Executando bypass KG Lock...")
                if self.controller.bypass_kg():
                    self._update_status(self.kg_status, "KG Lock bypassado com sucesso!")
                    self._show_info("Sucesso", "KG Lock bypassado com sucesso!")
                else:
                    self._update_status(self.kg_status, "Falha no bypass KG Lock")
                    self._show_error("Erro", "Falha no bypass KG Lock")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha no bypass KG Lock")
                self._update_status(self.kg_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _bypass_frp(self) -> None:
        def task():
            try:
                self._update_status(self.frp_status, "Executando bypass FRP...")
                if self.controller.bypass_frp():
                    self._update_status(self.frp_status, "FRP bypassado com sucesso!")
                    self._show_info("Sucesso", "FRP bypassado com sucesso!")
                else:
                    self._update_status(self.frp_status, "Falha no bypass FRP")
                    self._show_error("Erro", "Falha no bypass FRP")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha no bypass FRP")
                self._update_status(self.frp_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _remove_lock(self) -> None:
        def task():
            try:
                self._update_status(self.lock_status, "Removendo bloqueio...")
                lock_type = self.lock_type.currentText()
                if lock_type == "Automático":
                    lock_type = None
                if self.controller.remove_lock(lock_type):
                    self._update_status(self.lock_status, "Bloqueio removido com sucesso!")
                    self._show_info("Sucesso", "Bloqueio removido com sucesso!")
                else:
                    self._update_status(self.lock_status, "Falha ao remover bloqueio")
                    self._show_error("Erro", "Falha ao remover bloqueio")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha na remoção de bloqueio")
                self._update_status(self.lock_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _update_status(self, label: QtWidgets.QLabel, message: str) -> None:
        QtCore.QMetaObject.invokeMethod(label, "setText", QtCore.Qt.QueuedConnection, QtCore.Q_ARG(str, message))

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
                self._update_status(self.sanitize_status, "Processando...")
                ok = handler(archive, destination)
                if ok:
                    self._update_status(self.sanitize_status, "Pacote neutralizado e assinado")
                    self._show_info("Sucesso", "Pacote pronto para uso no Odin")
                else:
                    self._update_status(self.sanitize_status, "Falha na neutralização")
                    self._show_error("Erro", "Falha ao processar firmware")
            except Exception as exc:  # pragma: no cover
                logging.exception("Falha ao sanitizar firmware")
                self._update_status(self.sanitize_status, f"Erro: {exc}")
                self._show_error("Erro", str(exc))

        threading.Thread(target=task, daemon=True).start()


def run_pyqt_gui() -> None:
    """Entry point for launching the PyQt5 interface."""
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = SamsungUnlockQtWindow()
    window.show()
    sys.exit(app.exec_())
