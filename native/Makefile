CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2 -std=c11
LDFLAGS ?=

USB_AVAILABLE := $(shell pkg-config --exists libusb-1.0 && echo yes)
ifeq ($(USB_AVAILABLE),yes)
USB_CFLAGS := $(shell pkg-config --cflags libusb-1.0)
USB_LIBS := $(shell pkg-config --libs libusb-1.0)
else
USB_CFLAGS :=
USB_LIBS :=
endif

BIN = samsung_unlock
SRC = samsung_unlock.c usb_controller.c edl_controller.c kernel_module.c pattern_matcher.c

all: $(BIN)

$(BIN): $(SRC)
	$(CC) $(CFLAGS) $(USB_CFLAGS) $(SRC) -o $(BIN) $(LDFLAGS) $(USB_LIBS)

clean:
	rm -f $(BIN)

.PHONY: all clean
