import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import logging

class SamsungUnlockGUI:
    def __init__(self, root):
        self.root = root
        self.core = SamsungUnlockCore()
        self.setup_gui()
    
    def setup_gui(self):
        """Configura interface gráfica"""
        self.root.title("Samsung Unlock Pro - Tool Avançada")
        self.root.geometry("1000x700")
        
        # Abas principais
        self.notebook = ttk.Notebook(self.root)
        
        # Aba de Conexão
        self.connection_frame = ttk.Frame(self.notebook)
        self.setup_connection_tab()
        
        # Aba de MDM
        self.mdm_frame = ttk.Frame(self.notebook)
        self.setup_mdm_tab()
        
        # Aba KG Lock
        self.kg_frame = ttk.Frame(self.notebook)
        self.setup_kg_tab()
        
        # Aba FRP Bypass
        self.frp_frame = ttk.Frame(self.notebook)
        self.setup_frp_tab()
        
        # Aba de Remoção de Bloqueio
        self.lock_removal_frame = ttk.Frame(self.notebook)
        self.setup_lock_removal_tab()
        
        # Aba de Logs
        self.log_frame = ttk.Frame(self.notebook)
        self.setup_log_tab()
        
        self.notebook.add(self.connection_frame, text="Conexão")
        self.notebook.add(self.mdm_frame, text="Remoção MDM")
        self.notebook.add(self.kg_frame, text="KG Lock Bypass")
        self.notebook.add(self.frp_frame, text="FRP Bypass")
        self.notebook.add(self.lock_removal_frame, text="Remoção de Bloqueio")
        self.notebook.add(self.log_frame, text="Logs")
        self.notebook.pack(expand=1, fill="both")
    
    def setup_connection_tab(self):
        """Configura aba de conexão"""
        ttk.Label(self.connection_frame, text="Modo de Conexão:").grid(row=0, column=0)
        self.connection_mode = ttk.Combobox(self.connection_frame, 
                                          values=["ADB", "USB Raw", "EDL", "Serial"])
        self.connection_mode.grid(row=0, column=1)
        
        ttk.Label(self.connection_frame, text="Modelo:").grid(row=1, column=0)
        self.device_model = ttk.Entry(self.connection_frame)
        self.device_model.grid(row=1, column=1)
        
        ttk.Label(self.connection_frame, text="Serial:").grid(row=2, column=0)
        self.device_serial = ttk.Entry(self.connection_frame)
        self.device_serial.grid(row=2, column=1)
        
        ttk.Button(self.connection_frame, text="Conectar", 
                  command=self.connect_device).grid(row=3, column=0)
        
        ttk.Button(self.connection_frame, text="Desconectar", 
                  command=self.disconnect_device).grid(row=3, column=1)
        
        self.connection_status = ttk.Label(self.connection_frame, text="Desconectado")
        self.connection_status.grid(row=4, column=0, columnspan=2)
    
    def setup_mdm_tab(self):
        """Configura aba de remoção de MDM"""
        ttk.Label(self.mdm_frame, text="Remoção de MDM Persistente").grid(row=0, column=0, columnspan=2)
        
        ttk.Button(self.mdm_frame, text="Remover MDM", 
                  command=self.remove_mdm).grid(row=1, column=0)
        
        self.mdm_status = ttk.Label(self.mdm_frame, text="Pronto para remover MDM")
        self.mdm_status.grid(row=2, column=0, columnspan=2)
    
    def setup_kg_tab(self):
        """Configura aba de bypass KG Lock"""
        ttk.Label(self.kg_frame, text="Bypass KG Lock").grid(row=0, column=0, columnspan=2)
        
        ttk.Button(self.kg_frame, text="Executar Bypass KG Lock", 
                  command=self.bypass_kg_lock).grid(row=1, column=0)
        
        self.kg_status = ttk.Label(self.kg_frame, text="Pronto para bypass KG Lock")
        self.kg_status.grid(row=2, column=0, columnspan=2)
    
    def setup_frp_tab(self):
        """Configura aba de bypass FRP"""
        ttk.Label(self.frp_frame, text="Bypass FRP Android 14").grid(row=0, column=0, columnspan=2)
        
        ttk.Button(self.frp_frame, text="Executar Bypass FRP", 
                  command=self.bypass_frp).grid(row=1, column=0)
        
        self.frp_status = ttk.Label(self.frp_frame, text="Pronto para bypass FRP")
        self.frp_status.grid(row=2, column=0, columnspan=2)
    
    def setup_lock_removal_tab(self):
        """Configura aba de remoção de bloqueio de tela"""
        ttk.Label(self.lock_removal_frame, text="Tipo de Bloqueio:").grid(row=0, column=0)
        
        self.lock_type = ttk.Combobox(self.lock_removal_frame, 
                                    values=["Automático", "PIN", "Senha", "Padrão"])
        self.lock_type.grid(row=0, column=1)
        self.lock_type.current(0)
        
        ttk.Button(self.lock_removal_frame, text="Remover Bloqueio", 
                  command=self.remove_lock).grid(row=1, column=0, columnspan=2)
        
        self.lock_status = ttk.Label(self.lock_removal_frame, text="Pronto")
        self.lock_status.grid(row=2, column=0, columnspan=2)
    
    def setup_log_tab(self):
        """Configura aba de logs"""
        self.log_text = scrolledtext.ScrolledText(self.log_frame, width=100, height=30)
        self.log_text.pack(expand=True, fill='both')
        
        # Configurar handler de logging para a interface
        log_handler = TextHandler(self.log_text)
        log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        log_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(log_handler)
    
    def connect_device(self):
        """Conecta ao dispositivo em thread separada"""
        def connect_thread():
            try:
                device_info = {
                    'model': self.device_model.get(),
                    'serial': self.device_serial.get(),
                    'connection_type': self.connection_mode.get()
                }
                
                if self.core.connection_handler.establish_connection(device_info):
                    self.connection_status.config(text="Conectado!")
                    messagebox.showinfo("Sucesso", "Dispositivo conectado!")
                else:
                    self.connection_status.config(text="Falha na conexão")
                    messagebox.showerror("Erro", "Falha na conexão")
            except Exception as e:
                self.connection_status.config(text=f"Erro: {str(e)}")
                messagebox.showerror("Erro", str(e))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def disconnect_device(self):
        """Desconecta do dispositivo"""
        # Implementar desconexão
        self.connection_status.config(text="Desconectado")
        messagebox.showinfo("Info", "Dispositivo desconectado")
    
    def remove_mdm(self):
        """Executa remoção de MDM em thread separada"""
        def remove_mdm_thread():
            try:
                self.mdm_status.config(text="Removendo MDM...")
                
                if self.core.mdm_remover.remove_mdm_persistence():
                    self.mdm_status.config(text="MDM removido com sucesso!")
                    messagebox.showinfo("Sucesso", "MDM removido com sucesso!")
                else:
                    self.mdm_status.config(text="Falha ao remover MDM")
                    messagebox.showerror("Erro", "Falha ao remover MDM")
                    
            except Exception as e:
                self.mdm_status.config(text=f"Erro: {str(e)}")
                messagebox.showerror("Erro", str(e))
        
        threading.Thread(target=remove_mdm_thread, daemon=True).start()
    
    def bypass_kg_lock(self):
        """Executa bypass KG Lock em thread separada"""
        def bypass_kg_thread():
            try:
                self.kg_status.config(text="Executando bypass KG Lock...")
                
                if self.core.kg_lock_bypass.execute_kg_lock_bypass():
                    self.kg_status.config(text="KG Lock bypassado com sucesso!")
                    messagebox.showinfo("Sucesso", "KG Lock bypassado com sucesso!")
                else:
                    self.kg_status.config(text="Falha no bypass KG Lock")
                    messagebox.showerror("Erro", "Falha no bypass KG Lock")
                    
            except Exception as e:
                self.kg_status.config(text=f"Erro: {str(e)}")
                messagebox.showerror("Erro", str(e))
        
        threading.Thread(target=bypass_kg_thread, daemon=True).start()
    
    def bypass_frp(self):
        """Executa bypass FRP em thread separada"""
        def bypass_frp_thread():
            try:
                self.frp_status.config(text="Executando bypass FRP...")
                
                if self.core.frp_bypass.execute_advanced_bypass():
                    self.frp_status.config(text="FRP bypassado com sucesso!")
                    messagebox.showinfo("Sucesso", "FRP bypassado com sucesso!")
                else:
                    self.frp_status.config(text="Falha no bypass FRP")
                    messagebox.showerror("Erro", "Falha no bypass FRP")
                    
            except Exception as e:
                self.frp_status.config(text=f"Erro: {str(e)}")
                messagebox.showerror("Erro", str(e))
        
        threading.Thread(target=bypass_frp_thread, daemon=True).start()
    
    def remove_lock(self):
        """Executa remoção de bloqueio em thread separada"""
        def remove_lock_thread():
            try:
                self.lock_status.config(text="Removendo bloqueio...")
                
                lock_type = self.lock_type.get()
                if lock_type == "Automático":
                    lock_type = None
                
                if self.core.remove_screen_lock(lock_type):
                    self.lock_status.config(text="Bloqueio removido com sucesso!")
                    messagebox.showinfo("Sucesso", "Bloqueio removido com sucesso!")
                else:
                    self.lock_status.config(text="Falha ao remover bloqueio")
                    messagebox.showerror("Erro", "Falha ao remover bloqueio")
                    
            except Exception as e:
                self.lock_status.config(text=f"Erro: {str(e)}")
                messagebox.showerror("Erro", str(e))
        
        threading.Thread(target=remove_lock_thread, daemon=True).start()

class TextHandler(logging.Handler):
    """Handler de logging para exibir logs na interface gráfica"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state='normal')
        self.text_widget.insert(tk.END, msg + '\n')
        self.text_widget.see(tk.END)
        self.text_widget.configure(state='disabled')
