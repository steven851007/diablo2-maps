all: shotread templates.json clearroute
shotread: shotread.swift
	swiftc -O shotread.swift -o shotread
clearroute: clearroute.c
	$(CC) -O3 -Wall -Wextra -o clearroute clearroute.c -lm
templates.json: build_templates.py casc.py
	python3 -I build_templates.py
test:
	python3 test_synthetic.py
.PHONY: all test
