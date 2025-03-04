cmake_minimum_required(VERSION 3.7.2)
project (UhaGate3)

add_executable(UhaGate3 rpiserp.c UHA.cpp Main.cpp cJSON.c)

TARGET_LINK_LIBRARIES( UhaGate3 pthread)



 




