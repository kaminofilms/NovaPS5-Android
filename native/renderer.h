#pragma once
#include <string>
#include <android/native_window.h>
namespace Nova {
std::string VulkanReport();
void StartRenderer(ANativeWindow* owned_window);
void StopRenderer();
std::string RendererStatus();
void SetPad(uint32_t buttons,float lx,float ly,float rx,float ry,float l2,float r2,int touches,float tx,float ty);
std::string PadStatus();
void ResetPad();
}
