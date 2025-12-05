#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void print_usage(const char *prog) {
    fprintf(stderr,
            "Uso: %s [opções]\n"
            "  --diag                     Verifica dependências e permissões básicas\n"
            "  --list                     Lista dispositivos detectados pelo ADB\n"
            "  --reboot [modo]            Reboot pelo ADB (normal, recovery, download)\n"
            "  --push <local> <remoto>    Envia ficheiro com adb push\n"
            "  --pull <remoto> <local>    Copia ficheiro com adb pull\n"
            "  --shell ""<cmd>""           Executa comando shell no dispositivo via ADB\n"
            "  --enable-mtp               Ativa MTP + ADB para facilitar transferências\n"
            "  --help                     Mostra esta ajuda\n",
            prog);
}

static int run_and_stream(const char *cmd) {
    FILE *fp = popen(cmd, "r");
    if (!fp) {
        perror("popen");
        return -errno;
    }

    char buffer[512];
    while (fgets(buffer, sizeof(buffer), fp)) {
        fputs(buffer, stdout);
    }

    int status = pclose(fp);
    if (status == -1) {
        perror("pclose");
        return -errno;
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    return -1;
}

static bool command_exists(const char *cmd) {
    char probe[256];
    snprintf(probe, sizeof(probe), "command -v %s > /dev/null 2>&1", cmd);
    int ret = system(probe);
    return ret == 0;
}

static int ensure_adb(void) {
    if (!command_exists("adb")) {
        fprintf(stderr, "ADB não encontrado no PATH. Instale o Android Platform Tools.\n");
        return -1;
    }
    return 0;
}

static int list_devices(void) {
    if (ensure_adb() < 0) {
        return -1;
    }
    return run_and_stream("adb devices -l");
}

static int reboot_device(const char *mode) {
    if (ensure_adb() < 0) {
        return -1;
    }

    char cmd[128];
    if (mode && strlen(mode) > 0) {
        snprintf(cmd, sizeof(cmd), "adb reboot %s", mode);
    } else {
        snprintf(cmd, sizeof(cmd), "adb reboot");
    }
    return run_and_stream(cmd);
}

static int adb_push(const char *local, const char *remote) {
    if (ensure_adb() < 0) {
        return -1;
    }
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "adb push '%s' '%s'", local, remote);
    return run_and_stream(cmd);
}

static int adb_pull(const char *remote, const char *local) {
    if (ensure_adb() < 0) {
        return -1;
    }
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "adb pull '%s' '%s'", remote, local);
    return run_and_stream(cmd);
}

static int adb_shell(const char *shell_cmd) {
    if (ensure_adb() < 0) {
        return -1;
    }
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "adb shell \"%s\"", shell_cmd);
    return run_and_stream(cmd);
}

static int enable_mtp(void) {
    if (ensure_adb() < 0) {
        return -1;
    }
    return adb_shell("svc usb setFunctions mtp,adb");
}

static int diag(void) {
    printf("=== Diagnóstico rápido ===\n");
    printf("Sistema: %s\n", (sizeof(void *) == 8) ? "64-bit" : "32-bit");
    printf("Usuário efetivo: %d\n", geteuid());
    printf("ADB presente: %s\n", command_exists("adb") ? "sim" : "não");
    printf("libusb disponível: %s\n", command_exists("lsusb") ? "sim (lsusb)" : "não detectada");
    printf("==========================\n");
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    int i = 1;
    int ret = 0;
    while (i < argc) {
        if (strcmp(argv[i], "--help") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--diag") == 0) {
            ret = diag();
            i += 1;
        } else if (strcmp(argv[i], "--list") == 0) {
            ret = list_devices();
            i += 1;
        } else if (strcmp(argv[i], "--reboot") == 0) {
            const char *mode = NULL;
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                mode = argv[i + 1];
                i += 2;
            } else {
                i += 1;
            }
            ret = reboot_device(mode);
        } else if (strcmp(argv[i], "--push") == 0) {
            if (i + 2 >= argc) {
                fprintf(stderr, "--push requer <local> <remoto>\n");
                return 1;
            }
            ret = adb_push(argv[i + 1], argv[i + 2]);
            i += 3;
        } else if (strcmp(argv[i], "--pull") == 0) {
            if (i + 2 >= argc) {
                fprintf(stderr, "--pull requer <remoto> <local>\n");
                return 1;
            }
            ret = adb_pull(argv[i + 1], argv[i + 2]);
            i += 3;
        } else if (strcmp(argv[i], "--shell") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "--shell requer comando\n");
                return 1;
            }
            ret = adb_shell(argv[i + 1]);
            i += 2;
        } else if (strcmp(argv[i], "--enable-mtp") == 0) {
            ret = enable_mtp();
            i += 1;
        } else {
            fprintf(stderr, "Opção desconhecida: %s\n", argv[i]);
            print_usage(argv[0]);
            return 1;
        }

        if (ret != 0) {
            fprintf(stderr, "Operação falhou com código %d\n", ret);
            return ret;
        }
    }

    return ret;
}
