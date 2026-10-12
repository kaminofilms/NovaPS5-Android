#include <jni.h>
#include <android/native_window_jni.h>
#include "cpu_block.h"
#include "probe.h"
#include "renderer.h"
#include <vector>
#include <sstream>
extern "C" {
JNIEXPORT jstring JNICALL Java_com_kaminofilms_novaps5_NativeBridge_vulkanReport(JNIEnv* e,jclass){auto s=Nova::VulkanReport();return e->NewStringUTF(s.c_str());}
JNIEXPORT jstring JNICALL Java_com_kaminofilms_novaps5_NativeBridge_cpuTest(JNIEnv* e,jclass){auto s=Nova::RunCpuSmokeTest();return e->NewStringUTF(s.c_str());}
JNIEXPORT jstring JNICALL Java_com_kaminofilms_novaps5_NativeBridge_inspectElf(JNIEnv* e,jclass,jbyteArray array){auto size=e->GetArrayLength(array);std::vector<uint8_t> data(size);e->GetByteArrayRegion(array,0,size,reinterpret_cast<jbyte*>(data.data()));auto p=Nova::InspectElf(data.data(),data.size());std::ostringstream s;s<<p.message<<"\nMachine: "<<p.machine<<" • type: 0x"<<std::hex<<p.type<<" • entry: 0x"<<p.entry<<std::dec<<" • program headers: "<<p.segments;return e->NewStringUTF(s.str().c_str());}
JNIEXPORT void JNICALL Java_com_kaminofilms_novaps5_NativeBridge_startRenderer(JNIEnv* e,jclass,jobject surface){Nova::ResetPad();Nova::StartRenderer(ANativeWindow_fromSurface(e,surface));}
JNIEXPORT void JNICALL Java_com_kaminofilms_novaps5_NativeBridge_stopRenderer(JNIEnv*,jclass){Nova::StopRenderer();Nova::ResetPad();}
JNIEXPORT jstring JNICALL Java_com_kaminofilms_novaps5_NativeBridge_rendererStatus(JNIEnv* e,jclass){auto s=Nova::RendererStatus();return e->NewStringUTF(s.c_str());}
JNIEXPORT jstring JNICALL Java_com_kaminofilms_novaps5_NativeBridge_padStatus(JNIEnv* e,jclass){auto s=Nova::PadStatus();return e->NewStringUTF(s.c_str());}
JNIEXPORT void JNICALL Java_com_kaminofilms_novaps5_NativeBridge_setPad(JNIEnv*,jclass,jint buttons,jfloat lx,jfloat ly,jfloat rx,jfloat ry,jfloat l2,jfloat r2,jint touches,jfloat tx,jfloat ty){Nova::SetPad(buttons,lx,ly,rx,ry,l2,r2,touches,tx,ty);}
}
