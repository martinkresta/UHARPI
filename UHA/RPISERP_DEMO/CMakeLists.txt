cmake_minimum_required(VERSION 3.7.2)
project (UhaGate)

add_executable(UhaGate UHA.cpp Main.cpp cJSON.c)

find_library(wiringPi_LIB wiringPi)
target_link_libraries(UhaGate ${wiringPi_LIB})

 




