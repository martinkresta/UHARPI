cmake_minimum_required(VERSION 3.7.2)
project (BmsMon)

add_executable(BmsMon BMS.cpp BmsTest.cpp cJSON.c UHA.cpp)

find_library(wiringPi_LIB wiringPi)
target_link_libraries(BmsMon ${wiringPi_LIB})

 




