#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * pattern_matcher.c
 * Varredura simples de padrões em buffers grandes com uma janela deslizante.
 * Voltado para análise rápida de logs de segurança, procurando sequências
 * que indicam integridade, falhas de verificação ou tentativas de bloqueio.
 */

static const char *default_patterns[] = {
    "verity",
    "dm-verity",
    "boot_fail",
    "secureboot",
    "kgsl",
    "frp",
    "vaultkeeper",
    "edl",
    NULL
};

int pm_find_patterns(const char *haystack, const char **needles, char *out, size_t out_len) {
    if (!haystack || !out || out_len == 0) {
        return -1;
    }
    if (!needles) {
        needles = default_patterns;
    }

    size_t written = 0;
    for (const char **ptr = needles; *ptr != NULL; ptr++) {
        const char *needle = *ptr;
        if (strstr(haystack, needle) != NULL) {
            size_t len = strlen(needle);
            if (written + len + 1 >= out_len) {
                break;
            }
            memcpy(out + written, needle, len);
            written += len;
            out[written++] = ',';
        }
    }
    if (written > 0) {
        out[written - 1] = '\0';
    } else {
        out[0] = '\0';
    }
    return (int)written;
}

/*
 * Para compilar:
 *   gcc -shared -fPIC pattern_matcher.c -o libpattern_matcher.so
 */
