#pragma once
#include <cstdint>
// Application-owned diagnostic state; this is not the Kyty controller ABI.
struct NovaDiagnosticPad {
 uint32_t buttons=0;
 uint8_t left_stick_x=128,left_stick_y=128,right_stick_x=128,right_stick_y=128,analog_buttons_l2=0,analog_buttons_r2=0;
 bool connected=false;uint8_t connected_count=0;uint64_t timestamp=0;
 float orientation_w=1;
 struct {uint8_t touch_num=0;struct {uint16_t x=0,y=0;uint8_t id=0;} touch[1];} touch_data;
};
