CFLAGS ?= -O3 -mcpu=native -Wall -Wextra
TABLE ?= data/seeds.idx

seedfinder: seedfinder.c gen.h files.h
	$(CC) $(CFLAGS) -o $@ seedfinder.c -lpthread -lm
table: seedfinder
	mkdir -p data && ./seedfinder build $(TABLE)
test: seedfinder
	python3 -I test/run.py
clean:
	rm -f seedfinder
.PHONY: table test clean
