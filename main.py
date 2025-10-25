#!/usr/bin/env python3
"""
Samsung Unlock Pro - Ferramenta Avançada de Desbloqueio
Versão Completa com Todas as Funcionalidades
"""

import logging
import sys
import os
from core.system_controller import SamsungUnlockCore
from interfaces.gui_interface import SamsungUnlockGUI
import tkinter as tk

def setup_logging():
    """Configura o sistema de logging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('samsung_unlock.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """Função principal da aplicação"""
    print("Samsung Unlock Pro - Inicializando...")
    setup_logging()
    
    # Verificar se é root (para algumas operações)
    if os.geteuid() != 0:
        print("Algumas funcionalidades podem requerer privilégios de root")
    
    # Inicializar o sistema
    try:
        # Modo GUI
        if len(sys.argv) == 1 or '--gui' in sys.argv:
            root = tk.Tk()
            app = SamsungUnlockGUI(root)
            root.mainloop()

        elif '--pyqt' in sys.argv:
            from interfaces.pyqt_interface import run_pyqt_gui

            run_pyqt_gui()
        
        # Modo CLI
        elif '--cli' in sys.argv:
            from interfaces.cli_interface import SamsungUnlockCLI
            cli = SamsungUnlockCLI()
            cli.run()
        
        # Modo API
        elif '--api' in sys.argv:
            from interfaces.api_rest import run_api_server
            run_api_server()
        
        else:
            print("Modo de uso:")
            print("  --gui   : Interface gráfica Tkinter (padrão)")
            print("  --pyqt  : Interface gráfica avançada em PyQt5")
            print("  --cli   : Interface de linha de comando")
            print("  --api   : Modo servidor API REST")
            print("  --help  : Mostra esta ajuda")
    
    except Exception as e:
        logging.error(f"Erro fatal na inicialização: {str(e)}")
        print(f"Erro: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
