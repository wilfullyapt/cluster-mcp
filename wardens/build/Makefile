# Wardens build
#
# Collector is a local bridge binary (stdout JSON). No libcurl.
# Static musl: make STATIC=1 CC=musl-gcc
#
# Outputs land in this directory: ./collector ./runner

CC ?= gcc
STATIC ?= 0

CFLAGS = -Wall -Wextra -O2 -I../shared
LDFLAGS =

ifeq ($(STATIC),1)
CFLAGS += -static
LDFLAGS += -static
endif

.PHONY: all clean collector runner

all: collector runner

collector: ../collector/main.c ../collector/lxc.c ../collector/permissions.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

runner: ../runner/main.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f collector runner
