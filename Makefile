# Define variables
MPY_CROSS = ../micropython/mpy-cross/build/mpy-cross

# Default target
all: telnetd124.mpy

# Rule to create .mpy from .py
telnetd124.mpy: telnetd.py
	$(MPY_CROSS) $< -o $@

# Clean up
clean:
	rm -f $(OUT)

# Phony targets
.PHONY: all clean

