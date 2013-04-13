CC=gcc
UNAME := $(shell uname)
SRCS = $(wildcard *.c)
HDRS = $(wildcard *.h)
ifeq ($(UNAME), Linux)
    CFLAGS=-Wall -W -pedantic -O3 -mpopcnt -std=c99
endif

ifeq ($(UNAME), Darwin)
    CFLAGS=-Wall -W -pedantic -O3 -std=c99
endif 

prime: $(SRCS) $(HDRS)
	echo Buidling with $(CFLAGS)
	$(CC) -o prime $(CFLAGS) $(SRCS)

clean:
	rm prime
