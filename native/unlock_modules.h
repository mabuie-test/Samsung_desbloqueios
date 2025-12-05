#ifndef UNLOCK_MODULES_H
#define UNLOCK_MODULES_H

#include <stdint.h>

/* EDL controller */
int edl_init(void);
int edl_open(uint16_t vid, uint16_t pid);
int edl_hello(unsigned char *response, int length);
int edl_execute(unsigned char *cmd, int cmd_len, unsigned char *resp, int resp_len, unsigned int timeout_ms);
void edl_shutdown(void);

/* Kernel module interface */
int km_init(void);
int km_mount_rw(const char *mountpoint);
int km_set_flag(const char *flag);
int km_dump_ring_buffer(const char *destination);

/* USB controller */
int usb_initialize(void);
int usb_open_device(uint16_t vid, uint16_t pid);
int usb_bulk_ping(unsigned char endpoint, unsigned char *data, int length, unsigned int timeout_ms);
int usb_control_probe(uint8_t request_type, uint8_t request, uint16_t value, uint16_t index, unsigned char *data, uint16_t length, unsigned int timeout_ms);
int usb_list_devices(void);
void usb_shutdown(void);

/* Pattern matcher */
int pm_find_patterns(const char *haystack, const char **needles, char *out, size_t out_len);

#endif /* UNLOCK_MODULES_H */
