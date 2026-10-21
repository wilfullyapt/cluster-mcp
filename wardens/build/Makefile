# Wardens static C build (musl + libcurl)

CC ?= musl-gcc
CFLAGS = -Wall -Wextra -O2 -static
LDFLAGS = -static -lcurl -lssl -lcrypto -lz

all: collector runner

collector: ../collector/main.c ../collector/lxc.c ../collector/permissions.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

runner: ../runner/main.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f collector runner

.PHONY: all clean
