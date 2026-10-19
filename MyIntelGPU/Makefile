# Makefile MyIntelGPU.kext (Lilu Plugin + OC)

TARGET  = MyIntelGPU
CLASS   = MyIntelGPU

SDK_DIR ?= $(HOME)/MacKernelSDK
SDK_XCRUN := $(shell xcrun --show-sdk-path 2>/dev/null)

CXXFLAGS = -std=c++14 \
           -Wall -Wextra \
           -Wno-deprecated-declarations \
           -Wno-inconsistent-missing-override \
           -I$(SDK_DIR)/Headers \
           -I$(SDK_XCRUN)/usr/include

LDFLAGS  = -Xlinker -kext \
           -Xlinker -dead_strip \
           -Xlinker -x

SRC = MyIntelGPU.cpp MyIntelFramebuffer.cpp MyIntelAccelerator.cpp \
      MyIntelRing.cpp MyIntelEDIDParser.cpp
OBJ = $(SRC:.cpp=.o)

.PHONY: all clean install load unload log version sizecheck strip_binary

.DEFAULT_GOAL := all

all: $(TARGET).kext/Contents/MacOS/$(TARGET)
                                 
%.o: %.cpp
$(CXX) $(CXXFLAGS) -c -o $@ $<

$(TARGET).kext/Contents/Info.plist: Info.plist
    mkdir -p "$(TARGET).kext/Contents"
    cp Info.plist "$@"

$(TARGET).kext/Contents/MacOS/$(TARGET): $(OBJ) $(TARGET).kext/Contents/Info.plist
    mkdir -p "$(TARGET).kext/Contents/MacOS"
    $(CXX) $(CXXFLAGS) $(LDFLAGS) -o "$@" $(OBJ)
    strip -x -S "$@"
    ls -la "$(TARGET).kext/Contents/MacOS/"

clean:
    rm -rf $(TARGET).kext $(OBJ)

install: all
    sudo chown -R root:wheel $(TARGET).kext
    sudo cp -R $(TARGET).kext /Library/Extensions/
    sudo kextutil -v /Library/Extensions/$(TARGET).kext

load: all
    sudo chown -R root:wheel $(TARGET).kext
    sudo kextutil -v $(TARGET).kext

unload:
    sudo kextunload -b com.pongpan-bk.MyIntelGPU || true

log:
    sudo dmesg | grep -i "MyIntelGPU" | tail -50

version:
    @echo "Target       : $(TARGET)"
    @echo "Sources      : $(SRC)"
    @echo "Compiler     : $(CXX)"
    @echo "SDK Path     : $(SDK_XCRUN)"

strip_binary:
    @echo "Stripping symbols from binary..."
    strip -x -S $(TARGET).kext/Contents/MacOS/$(TARGET)
    @ls -la $(TARGET).kext/Contents/MacOS/$(TARGET)
    @echo "Binary stripped. Symbols removed for distribution."

sizecheck:
    @maxsize=200000; \
    actual=$$(stat -f%z "$(TARGET).kext/Contents/MacOS/$(TARGET)" 2>/dev/null || echo 0); \
    if [ "$$actual" -gt "$$maxsize" ]; then \
        echo "WARNING: Binary $$actual bytes exceeds $$maxsize — check for bloat"; \
    else \
        echo "Size check: $$actual bytes (limit $$maxsize) — OK"; \
    fi
