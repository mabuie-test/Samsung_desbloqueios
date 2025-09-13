# Samsung_desbloqueios
Ferramenta para desbloqueio de FRP, MDM, e KG Lock para Samsung até Android 14.
# Samsung Unlock Pro - Ferramenta Avançada de Desbloqueio

## 📋 Visão Geral

O Samsung Unlock Pro é uma aplicação modular e complexa desenvolvida para dispositivos Samsung que permite realizar diversas operações de desbloqueio e remoção de restrições. A ferramenta foi projetada com arquitetura modular para permitir expansão e manutenção facilitada.

## ⚠️ Aviso Legal

**ESTE SOFTWARE É FORNECIDO APENAS PARA FINS EDUCACIONAIS E DE PESQUISA.** O uso desta ferramenta em dispositivos sem a devida autorização pode violar termos de serviço e leis locais. Sempre obtenha permissão apropriada antes de realizar qualquer modificação em dispositivos.

## ✨ Funcionalidades Principais

- 🔓 Remoção de MDM (Mobile Device Management) persistente
- 🔒 Bypass de KG Lock (Knox Guard) até as versões mais recentes
- 📱 Bypass de FRP (Factory Reset Protection) até Android 14
- 🔑 Remoção de bloqueios de tela (PIN, padrão, senha) sem formatação
- 📶 Múltiplos métodos de conexão (ADB, USB Raw, EDL, Serial)
- 🛡️ Sistema de segurança avançado com criptografia
- 📊 Interface gráfica intuitiva e linha de comando

## 🖥️ Requisitos do Sistema

### Software:
- Python 3.8 ou superior
- ADB (Android Debug Bridge) instalado
- Drivers Samsung USB instalados
- Linux (recomendado) ou Windows com WSL

### Hardware:
- Cabo USB de alta qualidade
- Computador com pelo menos 4GB de RAM
- Portas USB funcionando adequadamente

## 🚀 Instalação

### Método 1: Instalação Automática
```bash
# Clone o repositório
git clone https://github.com/seuusuario/samsung-unlock-pro.git
cd samsung-unlock-pro

# Execute o script de instalação
chmod +x scripts/install.sh
./scripts/install.sh
```

### Método 2: Instalação Manual
```bash
# Clone o repositório
git clone https://github.com/seuusuario/samsung-unlock-pro.git
cd samsung-unlock-pro

# Instale as dependências Python
pip3 install -r requirements.txt

# Compile os módulos nativos
chmod +x scripts/build.sh
./scripts/build.sh

# Configure as permissões
chmod +x drivers/usb_driver/usb_controller
```

## 📖 Guia de Uso

### 1. Conexão com o Dispositivo

#### Via Interface Gráfica:
1. Execute o programa: `python3 main.py --gui`
2. Na aba "Conexão", selecione o modo de conexão
3. Insira o modelo e serial do dispositivo
4. Clique em "Conectar"

#### Via Linha de Comando:
```bash
python3 main.py --cli
connect --model SM-G998B --serial R58M40KMZ0E --connection adb
```

### 2. Remoção de MDM Persistente

1. Conecte-se ao dispositivo
2. Na aba "Remoção MDM", clique em "Remover MDM"
3. Aguarde o processo ser concluído
4. Verifique o status na interface

### 3. Bypass de KG Lock

1. Certifique-se de que o dispositivo está conectado
2. Navegue até a aba "KG Lock Bypass"
3. Clique em "Executar Bypass KG Lock"
4. Aguarde a conclusão do processo

### 4. Bypass de FRP (Android 14)

1. Conecte o dispositivo no modo de recuperação
2. Acesse a aba "FRP Bypass"
3. Selecione "Executar Bypass FRP"
4. Siga as instruções específicas para seu modelo

### 5. Remoção de Bloqueio de Tela

1. Conecte o dispositivo
2. Na aba "Remoção de Bloqueio", selecione o tipo de bloqueio
3. Clique em "Remover Bloqueio"
4. Aguarde a conclusão sem formatar o dispositivo

### 6. Operações Avançadas

#### Modo EDL (Emergency Download):
```bash
python3 main.py --cli
connect --model SM-G998B --connection edl
force_edl_mode
```

#### Modo de Recuperação:
```bash
python3 main.py --cli
connect --model SM-G998B --connection adb
reboot recovery
```

## 🏗️ Arquitetura do Sistema

### Por que usamos código C no programa?

O sistema incorpora módulos em C por várias razões importantes:

1. **Desempenho**: Operações de baixo nível exigem a velocidade do C
2. **Acesso direto ao hardware**: Manipulação de portas USB e protocolos
3. **Manipulação de memória**: Acesso direto à memória do dispositivo
4. **Driver personalizado**: Implementação de drivers específicos
5. **Exploração de vulnerabilidades**: Alguns exploits requerem precisão de C

### Estrutura de Módulos em C:

1. **kernel_module.c**: Interface com o kernel para operações privilegiadas
2. **usb_controller.c**: Controle de comunicação USB de baixo nível
3. **pattern_matcher.c**: Análise de padrões de segurança com alta performance
4. **edl_controller.c**: Implementação do protocolo Emergency Download

## 🔧 Troubleshooting

### Problemas Comuns e Soluções:

1. **Dispositivo não é detectado**
   - Verifique os drivers USB
   - Teste com cabo USB diferente
   - Execute como administrador/root

2. **Falha na conexão ADB**
   - Ative a depuração USB no dispositivo
   - Execute `adb kill-server && adb start-server`

3. **Erro de permissão insuficiente**
   - Execute o programa com privilégios de root
   - Verifique as permissões do usuário no grupo plugdev

4. **Falha no bypass do KG Lock**
   - Verifique se o modelo é suportado
   - Tente métodos alternativos de conexão

5. **Bloqueio após várias tentativas**
   - Aguarde 24 horas antes de novas tentativas
   - Use métodos de hardware alternativos

## 📊 Modelos Suportados

| Modelo | Android Max | Knox | Status |
|--------|-------------|------|--------|
| SM-G998B | 14 | 3.3 | ✅ Suportado |
| SM-S901B | 14 | 3.3 | ✅ Suportado |
| SM-F936B | 13 | 3.2 | ✅ Suportado |
| SM-X800 | 13 | 3.1 | ⚠️ Experimental |
| SM-A136B | 12 | 2.5 | ✅ Suportado |

## 🆘 Suporte

Para obter suporte:

1. Consulte a documentação em `/docs/`
2. Verifique issues no GitHub
3. Entre em contato com a equipe de desenvolvimento
4. Consulte fóruns especializados

## 📜 Licença

Este projeto é distribuído sob a licença GPLv3. Veja o arquivo `LICENSE` para mais detalhes.

## 🔄 Atualizações

Para atualizar para a versão mais recente:

```bash
cd samsung-unlock-pro
git pull origin main
./scripts/build.sh
```

## 🤝 Contribuição

Contribuições são bem-vindas! Por favor:

1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📞 Contato

Para questões relacionadas ao projeto:

- Email: desenvolvimento@exemplo.com
- Site: https://www.exemplo.com
- Discord: https://discord.gg/exemplo

---

**Nota**: Este software está em desenvolvimento constante. Novas funcionalidades e melhorias são adicionadas regularmente. Sempre verifique se está usando a versão mais recente antes de realizar operações críticas.
