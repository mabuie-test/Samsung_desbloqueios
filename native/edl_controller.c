#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef _WIN32
#include <libusb-1.0/libusb.h>

/*
 * edl_controller.c
 * Implementação simplificada do protocolo Qualcomm EDL (Emergency Download)
 * para handshake inicial, envio de hello e troca de comandos curtos usados em
 * rotinas de recuperação/test-point. Baseia-se em libusb para permitir uso sem
 * dependências adicionais.
 */

static libusb_context *ctx = NULL;
static libusb_device_handle *dev = NULL;

int edl_init(void) {
    if (ctx) {
        return 0;
    }
    int ret = libusb_init(&ctx);
    if (ret < 0) {
        fprintf(stderr, "libusb_init falhou: %s\n", libusb_error_name(ret));
        return ret;
    }
    libusb_set_option(ctx, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING);
    return 0;
}

int edl_open(uint16_t vid, uint16_t pid) {
    if (!ctx && edl_init() < 0) {
        return -1;
    }
    dev = libusb_open_device_with_vid_pid(ctx, vid, pid);
    if (!dev) {
        fprintf(stderr, "Dispositivo EDL %04x:%04x não encontrado\n", vid, pid);
        return -ENOENT;
    }
    libusb_claim_interface(dev, 0);
    return 0;
}

int edl_hello(unsigned char *response, int length) {
    if (!dev) {
        return -ENODEV;
    }
    unsigned char hello[] = {0x7E, 0x00, 0x00, 0x07, 0x62, 0x65, 0x65, 0x66, 0x7E};
    int transferred = 0;
    int ret = libusb_bulk_transfer(dev, 0x01, hello, sizeof(hello), &transferred, 1000);
    if (ret != 0) {
        fprintf(stderr, "Falha ao enviar hello EDL: %s\n", libusb_error_name(ret));
        return ret;
    }
    ret = libusb_bulk_transfer(dev, 0x81, response, length, &transferred, 1000);
    if (ret != 0) {
        fprintf(stderr, "Falha ao receber resposta EDL: %s\n", libusb_error_name(ret));
        return ret;
    }
    return transferred;
}

int edl_execute(unsigned char *cmd, int cmd_len, unsigned char *resp, int resp_len, unsigned int timeout_ms) {
    if (!dev) {
        return -ENODEV;
    }
    int transferred = 0;
    int ret = libusb_bulk_transfer(dev, 0x01, cmd, cmd_len, &transferred, timeout_ms);
    if (ret != 0) {
        fprintf(stderr, "Falha ao enviar comando EDL: %s\n", libusb_error_name(ret));
        return ret;
    }
    ret = libusb_bulk_transfer(dev, 0x81, resp, resp_len, &transferred, timeout_ms);
    if (ret != 0) {
        fprintf(stderr, "Falha ao receber resposta EDL: %s\n", libusb_error_name(ret));
        return ret;
    }
    return transferred;
}

void edl_shutdown(void) {
    if (dev) {
        libusb_release_interface(dev, 0);
        libusb_close(dev);
        dev = NULL;
    }
    if (ctx) {
        libusb_exit(ctx);
        ctx = NULL;
    }
}

#else /* _WIN32 */

/*
 * Stub mínimo para Windows: permite compilar a DLL sem libusb, devolvendo
 * códigos de erro que mantêm o fluxo Python nos fallbacks.
 */
int edl_init(void) { return -ENOTSUP; }
int edl_open(uint16_t vid, uint16_t pid) {
    (void)vid;
    (void)pid;
    return -ENOTSUP;
}
int edl_hello(unsigned char *response, int length) {
    (void)response;
    (void)length;
    return -ENOTSUP;
}
int edl_execute(unsigned char *cmd, int cmd_len, unsigned char *resp, int resp_len, unsigned int timeout_ms) {
    (void)cmd;
    (void)cmd_len;
    (void)resp;
    (void)resp_len;
    (void)timeout_ms;
    return -ENOTSUP;
}
void edl_shutdown(void) {}

#endif /* _WIN32 */

/*
 * Para compilar:
 *   gcc -shared -fPIC edl_controller.c -lusb-1.0 -o libedl_controller.so (Linux)
 *   gcc -shared edl_controller.c -o libedl_controller.dll (Windows)
 */
