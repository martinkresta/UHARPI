cmake_minimum_required(VERSION 3.7.2)
project (UhaGate4)

add_executable(UhaGate4 rpiserp.c UHA.cpp Main.cpp LOG.cpp cJSON.c)

TARGET_LINK_LIBRARIES( UhaGate4 pthread)



 




