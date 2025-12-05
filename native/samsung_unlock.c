#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "unlock_modules.h"

#define MAX_SCAN_SIZE (2 * 1024 * 1024)

static void print_usage(const char *prog) {
    fprintf(stderr,
            "Uso: %s [opções]\n"
            "  --diag                     Verifica dependências e permissões básicas\n"
            "  --list                     Lista dispositivos detectados pelo ADB\n"
            "  --reboot [modo]            Reboot pelo ADB (normal, recovery, download)\n"
            "  --push <local> <remoto>    Envia ficheiro com adb push\n"
            "  --pull <remoto> <local>    Copia ficheiro com adb pull\n"
            "  --shell \"<cmd>\"           Executa comando shell no dispositivo via ADB\n"
            "  --enable-mtp               Ativa MTP + ADB para facilitar transferências\n"
            "  --usb-scan                 Lista dispositivos USB via libusb (modo nativo)\n"
            "  --edl-handshake <vid> <pid>Realiza hello EDL num dispositivo Qualcomm\n"
            "  --km-mount <ponto>         Usa módulo de kernel para montar partição RW\n"
            "  --km-flag <flag>           Define flag interna no módulo de kernel\n"
            "  --pm-scan <ficheiro>       Analisa ficheiro de log à procura de padrões\n"
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
    struct stat st;
    printf("Acesso ao /dev/bus/usb: %s\n", (stat("/dev/bus/usb", &st) == 0) ? "ok" : "indisponível");
    printf("==========================\n");
    return 0;
}

static int perform_usb_scan(void) {
    int ret = usb_list_devices();
    if (ret < 0) {
        fprintf(stderr, "Varredura USB falhou: %d\n", ret);
    }
    return ret;
}

static int perform_edl_handshake(uint16_t vid, uint16_t pid) {
    int ret = edl_init();
    if (ret < 0) {
        fprintf(stderr, "Falha a iniciar libusb para EDL: %d\n", ret);
        return ret;
    }

    ret = edl_open(vid, pid);
    if (ret < 0) {
        fprintf(stderr, "Não foi possível abrir o dispositivo EDL %04x:%04x (%d)\n", vid, pid, ret);
        return ret;
    }

    unsigned char response[64] = {0};
    ret = edl_hello(response, sizeof(response));
    if (ret < 0) {
        fprintf(stderr, "Hello EDL falhou (%d)\n", ret);
        edl_shutdown();
        return ret;
    }

    printf("Resposta EDL (%d bytes): ", ret);
    for (int i = 0; i < ret; i++) {
        printf("%02x ", response[i]);
    }
    printf("\n");

    edl_shutdown();
    return 0;
}

static int perform_km_mount(const char *mountpoint) {
    int ret = km_init();
    if (ret < 0) {
        fprintf(stderr, "km_init falhou: %d\n", ret);
        return ret;
    }
    ret = km_mount_rw(mountpoint);
    if (ret < 0) {
        fprintf(stderr, "Montagem RW falhou: %d\n", ret);
    }
    return ret;
}

static int perform_km_flag(const char *flag) {
    int ret = km_init();
    if (ret < 0) {
        fprintf(stderr, "km_init falhou: %d\n", ret);
        return ret;
    }
    ret = km_set_flag(flag);
    if (ret < 0) {
        fprintf(stderr, "Definir flag falhou: %d\n", ret);
    }
    return ret;
}

static char *read_file(const char *path, size_t *out_size) {
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        perror("fopen");
        return NULL;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return NULL;
    }
    long len = ftell(fp);
    if (len < 0 || len > MAX_SCAN_SIZE) {
        fclose(fp);
        fprintf(stderr, "Ficheiro demasiado grande ou inválido: %ld\n", len);
        return NULL;
    }
    rewind(fp);
    char *buffer = malloc((size_t)len + 1);
    if (!buffer) {
        fclose(fp);
        return NULL;
    }
    size_t read = fread(buffer, 1, (size_t)len, fp);
    fclose(fp);
    buffer[read] = '\0';
    if (out_size) {
        *out_size = read;
    }
    return buffer;
}

static int perform_pattern_scan(const char *path) {
    size_t sz = 0;
    char *content = read_file(path, &sz);
    if (!content) {
        return -1;
    }

    char matches[256];
    int ret = pm_find_patterns(content, NULL, matches, sizeof(matches));
    if (ret < 0) {
        fprintf(stderr, "Varredura falhou\n");
        free(content);
        return ret;
    }

    if (matches[0] == '\0') {
        printf("Nenhum padrão crítico encontrado em %s (tamanho %zu bytes)\n", path, sz);
    } else {
        printf("Padrões encontrados em %s: %s\n", path, matches);
    }
    free(content);
    return 0;
}

static int parse_hex(const char *s, uint16_t *out) {
    char *end = NULL;
    long v = strtol(s, &end, 16);
    if (!end || *end != '\0' || v < 0 || v > 0xFFFF) {
        return -1;
    }
    *out = (uint16_t)v;
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
        } else if (strcmp(argv[i], "--usb-scan") == 0) {
            ret = perform_usb_scan();
            i += 1;
        } else if (strcmp(argv[i], "--edl-handshake") == 0) {
            if (i + 2 >= argc) {
                fprintf(stderr, "--edl-handshake requer VID e PID em hexadecimal\n");
                return 1;
            }
            uint16_t vid = 0, pid = 0;
            if (parse_hex(argv[i + 1], &vid) < 0 || parse_hex(argv[i + 2], &pid) < 0) {
                fprintf(stderr, "VID/PID inválidos, use formato hexadecimal (ex: 05c6 9008)\n");
                return 1;
            }
            ret = perform_edl_handshake(vid, pid);
            i += 3;
        } else if (strcmp(argv[i], "--km-mount") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "--km-mount requer o ponto de montagem\n");
                return 1;
            }
            ret = perform_km_mount(argv[i + 1]);
            i += 2;
        } else if (strcmp(argv[i], "--km-flag") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "--km-flag requer a flag\n");
                return 1;
            }
            ret = perform_km_flag(argv[i + 1]);
            i += 2;
        } else if (strcmp(argv[i], "--pm-scan") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "--pm-scan requer o caminho para o ficheiro\n");
                return 1;
            }
            ret = perform_pattern_scan(argv[i + 1]);
            i += 2;
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
