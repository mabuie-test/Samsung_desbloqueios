CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2
LDFLAGS ?=

BIN = samsung_unlock
SRC = samsung_unlock.c

all: $(BIN)

$(BIN): $(SRC)
	$(CC) $(CFLAGS) $(SRC) -o $(BIN) $(LDFLAGS)

clean:
	rm -f $(BIN)

.PHONY: all clean
