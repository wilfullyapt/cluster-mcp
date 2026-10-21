# Wardens build
#
# Default: dynamic link with system gcc + libcurl (lab / easy CI).
# Static musl: make STATIC=1 CC=musl-gcc
#
# Outputs land in this directory: ./collector ./runner

CC ?= gcc
STATIC ?= 0

CFLAGS = -Wall -Wextra -O2 -I../shared
LDFLAGS =
LIBS = -lcurl

ifeq ($(STATIC),1)
CFLAGS += -static
LDFLAGS += -static
LIBS = -lcurl -lssl -lcrypto -lz -ldl -pthread
endif

.PHONY: all clean collector runner

all: collector runner

collector: ../collector/main.c ../collector/lxc.c ../collector/permissions.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LIBS)

runner: ../runner/main.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f collector runner
