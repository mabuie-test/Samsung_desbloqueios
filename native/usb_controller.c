#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#if __has_include(<libusb-1.0/libusb.h>)
#define HAS_LIBUSB 1
#include <libusb-1.0/libusb.h>
#else
#define HAS_LIBUSB 0
typedef struct libusb_context libusb_context;
typedef struct libusb_device libusb_device;
typedef struct libusb_device_handle libusb_device_handle;
struct libusb_device_descriptor {
    uint8_t bLength;
    uint8_t bDescriptorType;
    uint16_t bcdUSB;
    uint8_t bDeviceClass;
    uint8_t bDeviceSubClass;
    uint8_t bDeviceProtocol;
    uint8_t bMaxPacketSize0;
    uint16_t idVendor;
    uint16_t idProduct;
    uint16_t bcdDevice;
    uint8_t iManufacturer;
    uint8_t iProduct;
    uint8_t iSerialNumber;
    uint8_t bNumConfigurations;
};
static const char *libusb_error_name(int err) {(void)err; return "libusb headers ausentes";}
static inline int libusb_set_option(libusb_context *ctx, int option, int value) {(void)ctx;(void)option;(void)value;return 0;}
#define LIBUSB_OPTION_LOG_LEVEL 0
#define LIBUSB_LOG_LEVEL_WARNING 0
#endif
#include "unlock_modules.h"

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

#if HAS_LIBUSB
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

int usb_list_devices(void) {
    if (!session.ctx && usb_initialize() < 0) {
        return -1;
    }

    libusb_device **list = NULL;
    ssize_t count = libusb_get_device_list(session.ctx, &list);
    if (count < 0) {
        fprintf(stderr, "libusb_get_device_list falhou: %s\n", libusb_error_name((int)count));
        return (int)count;
    }

    printf("=== Dispositivos USB detectados ===\n");
    for (ssize_t i = 0; i < count; i++) {
        struct libusb_device_descriptor desc;
        if (libusb_get_device_descriptor(list[i], &desc) == 0) {
            printf("%04x:%04x  Classe 0x%02x  Subclasse 0x%02x  Protocolo 0x%02x\n",
                   desc.idVendor,
                   desc.idProduct,
                   desc.bDeviceClass,
                   desc.bDeviceSubClass,
                   desc.bDeviceProtocol);
        }
    }
    printf("===================================\n");

    libusb_free_device_list(list, 1);
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

#else /* HAS_LIBUSB */

int usb_initialize(void) { return -ENOTSUP; }
int usb_open_device(uint16_t vid, uint16_t pid) {
    (void)vid;
    (void)pid;
    return -ENOTSUP;
}
int usb_list_devices(void) { return -ENOTSUP; }
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

#endif /* HAS_LIBUSB */

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
int usb_list_devices(void) { return -ENOTSUP; }
void usb_shutdown(void) {}

#endif /* _WIN32 */

/*
 * Para compilar:
 *   gcc -shared -fPIC usb_controller.c -lusb-1.0 -o libusb_controller.so (Linux)
 *   gcc -shared usb_controller.c -o libusb_controller.dll (Windows)
 */
