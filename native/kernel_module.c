#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "unlock_modules.h"

#ifndef _WIN32
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

/*
 * kernel_module.c
 * Interface de usuário para um módulo de kernel hipotético responsável por
 * operações privilegiadas (ex.: remount de partições, ajustes de SELinux e
 * buffers de debug). A implementação utiliza um dispositivo de caractere
 * (/dev/samsung_unlock_kmod) exposto pelo módulo para simplificar a ponte
 * com o espaço de usuário.
 */

#define DEVICE_PATH "/dev/samsung_unlock_kmod"
#define IOCTL_ENABLE_PRIVILEGES _IO('k', 1)
#define IOCTL_MOUNT_RW _IOW('k', 2, char *)
#define IOCTL_SET_FLAG _IOW('k', 3, char *)

static int open_device(void) {
    int fd = open(DEVICE_PATH, O_RDWR);
    if (fd < 0) {
        perror("open_device");
    }
    return fd;
}

int km_init(void) {
    int fd = open_device();
    if (fd < 0) {
        return -errno;
    }
    int result = ioctl(fd, IOCTL_ENABLE_PRIVILEGES, NULL);
    close(fd);
    return result;
}

int km_mount_rw(const char *mountpoint) {
    int fd = open_device();
    if (fd < 0) {
        return -errno;
    }
    int result = ioctl(fd, IOCTL_MOUNT_RW, mountpoint);
    close(fd);
    return result;
}

int km_set_flag(const char *flag) {
    int fd = open_device();
    if (fd < 0) {
        return -errno;
    }
    int result = ioctl(fd, IOCTL_SET_FLAG, flag);
    close(fd);
    return result;
}

int km_dump_ring_buffer(const char *destination) {
    int fd = open_device();
    if (fd < 0) {
        return -errno;
    }

    FILE *out = fopen(destination, "w");
    if (!out) {
        close(fd);
        return -errno;
    }

    /* exemplo simples de leitura de ring buffer exposto via mmap */
    size_t sz = 4096;
    char *mapped = (char *)mmap(NULL, sz, PROT_READ, MAP_SHARED, fd, 0);
    if (mapped == MAP_FAILED) {
        fclose(out);
        close(fd);
        return -errno;
    }

    fwrite(mapped, 1, sz, out);
    munmap(mapped, sz);
    fclose(out);
    close(fd);
    return 0;
}

#else /* _WIN32 */

/*
 * Versão mínima para Windows: expõe as mesmas funções retornando erros
 * explícitos para permitir compilação e linkage mesmo sem o módulo de kernel
 * Linux. As rotinas Python usarão o fallback automaticamente.
 */
int km_init(void) { return -ENOTSUP; }
int km_mount_rw(const char *mountpoint) {
    (void)mountpoint;
    return -ENOTSUP;
}
int km_set_flag(const char *flag) {
    (void)flag;
    return -ENOTSUP;
}
int km_dump_ring_buffer(const char *destination) {
    (void)destination;
    return -ENOTSUP;
}

#endif /* _WIN32 */

/*
 * Para compilar:
 *   gcc -shared -fPIC kernel_module.c -o libkernel_module.so (Linux)
 *   gcc -shared kernel_module.c -o libkernel_module.dll (Windows)
 */
