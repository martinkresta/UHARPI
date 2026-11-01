cmake_minimum_required(VERSION 3.7.2)
project (UhaGate2)

add_executable(UhaGate2 rpiserp.c UHA.cpp Main.cpp cJSON.c)

TARGET_LINK_LIBRARIES( UhaGate2 pthread)



 




