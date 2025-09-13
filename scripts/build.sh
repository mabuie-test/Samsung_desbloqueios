#!/bin/bash
# build.sh - Script de construção completa

echo "Construindo Samsung Unlock Pro - Versão Completa"

# Configurar ambiente
export PYTHONPATH=$(pwd)
export LD_LIBRARY_PATH=$(pwd)/libs:$LD_LIBRARY_PATH

# Instalar dependências Python
pip3 install -r requirements.txt --upgrade

# Compilar módulos nativos
echo "Compilando módulos nativos..."
gcc -shared -o core/kernel_module.so -fPIC core/kernel_module.c $(python3-config --includes --ldflags)
gcc -o drivers/usb_driver/usb_controller -lusb-1.0 drivers/usb_driver/usb_controller.c

# Compilar exploits
echo "Compilando exploits..."
for exploit in resources/exploits/*.c; do
    gcc -o "${exploit%.c}" "$exploit"
done

# Compilar módulos de análise de padrões
echo "Compilando módulos de análise..."
gcc -shared -o utils/pattern_analyzer/pattern_matcher.so -fPIC utils/pattern_analyzer/pattern_matcher.c

# Configurar permissoes
chmod +x scripts/*.sh
chmod 755 drivers/*/*

# Criar diretórios necessários
mkdir -p logs backups resources/temp resources/backup resources/security_patterns

# Verificar requisitos
echo "Verificando requisitos do sistema..."
if ! command -v adb &> /dev/null; then
    echo "ADB não encontrado. Instalando..."
    apt-get install android-tools-adb
fi

if ! command -v fastboot &> /dev/null; then
    echo "Fastboot não encontrado. Instalando..."
    apt-get install android-tools-fastboot
fi

# Baixar padrões de segurança adicionais
echo "Baixando padrões de segurança..."
wget -O resources/security_patterns/common_patterns.txt https://example.com/patterns/common_patterns.txt
wget -O resources/security_patterns/device_specific.txt https://example.com/patterns/device_specific.txt

echo "Build completo! Execute: python3 main.py"
