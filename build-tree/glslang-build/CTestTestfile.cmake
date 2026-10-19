# CMake generated Testfile for 
# Source directory: /Users/ved/igpu-build/glslang
# Build directory: /Users/ved/igpu-build/glslang-build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[glslang-testsuite]=] "bash" "runtests" "/Users/ved/igpu-build/glslang-build/localResults" "/Users/ved/igpu-build/glslang-build/StandAlone/glslang" "/Users/ved/igpu-build/glslang-build/StandAlone/spirv-remap")
set_tests_properties([=[glslang-testsuite]=] PROPERTIES  WORKING_DIRECTORY "/Users/ved/igpu-build/glslang/Test/" _BACKTRACE_TRIPLES "/Users/ved/igpu-build/glslang/CMakeLists.txt;351;add_test;/Users/ved/igpu-build/glslang/CMakeLists.txt;0;")
subdirs("External")
subdirs("SPIRV")
subdirs("glslang")
subdirs("StandAlone")
subdirs("gtests")
