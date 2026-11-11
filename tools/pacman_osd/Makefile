CC ?= cc
CFLAGS = -std=c99 -O2 -Wall -Wextra -Werror -Iinclude -Igenerated

.PHONY: all generate test emulator clean
all: build/native-check build/demo-trace
generate:
	python3 tools/generate_assets.py
build:
	mkdir -p build
build/native-check: src/pm_osd.c generated/pm_assets.c tests/native.c include/pm_osd.h generated/pm_assets.h | build
	$(CC) $(CFLAGS) src/pm_osd.c generated/pm_assets.c tests/native.c -o $@
build/demo-trace: src/pm_osd.c src/pm_rtd_port.c generated/pm_assets.c demo/trace.c include/pm_osd.h generated/pm_assets.h | build
	$(CC) $(CFLAGS) src/pm_osd.c src/pm_rtd_port.c generated/pm_assets.c demo/trace.c -o $@
test: all
	python3 tests/check_assets.py
	./build/native-check
	./build/demo-trace build/trace.txt
build/emu-runner: demo/emu_runner.c third_party/emu8051/core.c third_party/emu8051/opcodes.c third_party/emu8051/disasm.c third_party/emu8051/emu8051.h | build
	$(CC) -std=c99 -O2 -Ithird_party/emu8051 third_party/emu8051/core.c third_party/emu8051/opcodes.c third_party/emu8051/disasm.c demo/emu_runner.c -o $@
emulator: test build/emu-runner
	python3 tools/build_8051_app.py
	./build/emu-runner build/patch-app.bin build/8051-trace.txt
	python3 tests/check_8051.py
clean:
	rm -rf build
