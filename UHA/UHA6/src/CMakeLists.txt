cmake_minimum_required(VERSION 3.13)
project(UhaGate6 C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# portable part (also builds the unit tests)
add_library(uhacore STATIC rpiserp.cpp outputs.cpp event_log.cpp cJSON.c)
target_compile_options(uhacore PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra>)

add_executable(UhaGate6 main.cpp gateway.cpp serial_link.cpp config.cpp log.cpp)
target_compile_options(UhaGate6 PRIVATE -Wall -Wextra)
target_link_libraries(UhaGate6 uhacore)

enable_testing()
add_executable(test_uhagate6 tests/test_main.cpp)
target_include_directories(test_uhagate6 PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(test_uhagate6 uhacore)
add_test(NAME unit COMMAND test_uhagate6)
