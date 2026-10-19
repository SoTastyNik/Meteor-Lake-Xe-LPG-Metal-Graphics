# rustup environment for tcsh
if ( $?PATH ) then
    if ( "$PATH" !~ */Users/ved/Documents/iGPU Port/toolchain/cargo/bin* ) then
        setenv PATH "/Users/ved/Documents/iGPU Port/toolchain/cargo/bin:$PATH"
    endif
else
    setenv PATH "/Users/ved/Documents/iGPU Port/toolchain/cargo/bin"
endif
