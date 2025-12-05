#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#include <libusb-1.0/libusb.h>

/*
 * usb_controller.c
 * Camada de comunicação USB de baixo nível voltada a testes rápidos e
 * transferência de blocos binários utilizados durante EDL ou interações
 * proprietárias. Este código prioriza um fluxo simples baseado em libusb.
 */

typedef struct {
    libusb_context *ctx;
    libusb_device_handle *handle;
} usb_session;

static usb_session session = {0};

int usb_initialize(void) {
    int ret = libusb_init(&session.ctx);
    if (ret < 0) {
        fprintf(stderr, "libusb_init falhou: %s\n", libusb_error_name(ret));
        return ret;
    }
    libusb_set_option(session.ctx, LIBUSB_OPTION_LOG_LEVEL, LIBUSB_LOG_LEVEL_WARNING);
    return 0;
}

int usb_open_device(uint16_t vid, uint16_t pid) {
    if (!session.ctx && usb_initialize() < 0) {
        return -1;
    }
    session.handle = libusb_open_device_with_vid_pid(session.ctx, vid, pid);
    if (!session.handle) {
        fprintf(stderr, "Dispositivo %04x:%04x não encontrado\n", vid, pid);
        return -ENOENT;
    }
    libusb_claim_interface(session.handle, 0);
    return 0;
}

int usb_bulk_ping(unsigned char endpoint, unsigned char *data, int length, unsigned int timeout_ms) {
    if (!session.handle) {
        return -ENODEV;
    }
    int transferred = 0;
    int ret = libusb_bulk_transfer(session.handle, endpoint, data, length, &transferred, timeout_ms);
    if (ret != 0) {
        fprintf(stderr, "usb_bulk_transfer falhou: %s\n", libusb_error_name(ret));
        return ret;
    }
    return transferred;
}

int usb_control_probe(uint8_t request_type, uint8_t request, uint16_t value, uint16_t index, unsigned char *data, uint16_t length, unsigned int timeout_ms) {
    if (!session.handle) {
        return -ENODEV;
    }
    int ret = libusb_control_transfer(session.handle, request_type, request, value, index, data, length, timeout_ms);
    if (ret < 0) {
        fprintf(stderr, "usb_control_transfer falhou: %s\n", libusb_error_name(ret));
    }
    return ret;
}

void usb_shutdown(void) {
    if (session.handle) {
        libusb_release_interface(session.handle, 0);
        libusb_close(session.handle);
        session.handle = NULL;
    }
    if (session.ctx) {
        libusb_exit(session.ctx);
        session.ctx = NULL;
    }
}

#else /* _WIN32 */

/*
 * Stub para Windows: retorna códigos de erro conhecidos para permitir que o
 * Python identifique a ausência de libusb e siga pelos fallbacks.
 */
int usb_initialize(void) { return -ENOTSUP; }
int usb_open_device(uint16_t vid, uint16_t pid) {
    (void)vid;
    (void)pid;
    return -ENOTSUP;
}
int usb_bulk_ping(unsigned char endpoint, unsigned char *data, int length, unsigned int timeout_ms) {
    (void)endpoint;
    (void)data;
    (void)length;
    (void)timeout_ms;
    return -ENOTSUP;
}
int usb_control_probe(uint8_t request_type, uint8_t request, uint16_t value, uint16_t index, unsigned char *data, uint16_t length, unsigned int timeout_ms) {
    (void)request_type;
    (void)request;
    (void)value;
    (void)index;
    (void)data;
    (void)length;
    (void)timeout_ms;
    return -ENOTSUP;
}
void usb_shutdown(void) {}

#endif /* _WIN32 */

/*
 * Para compilar:
 *   gcc -shared -fPIC usb_controller.c -lusb-1.0 -o libusb_controller.so (Linux)
 *   gcc -shared usb_controller.c -o libusb_controller.dll (Windows)
 */
