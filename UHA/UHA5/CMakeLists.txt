cmake_minimum_required(VERSION 3.7.2)
project (UhaGate5)

add_executable(UhaGate5 rpiserp.c UHA.cpp Main.cpp LOG.cpp cJSON.c)

TARGET_LINK_LIBRARIES( UhaGate5 pthread)



 




