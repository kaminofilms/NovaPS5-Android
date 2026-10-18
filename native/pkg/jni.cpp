#include "install.h"
#include <jni.h>
#include <exception>
#include <string>
extern "C" JNIEXPORT jstring JNICALL
Java_com_kaminofilms_novaps5_PkgInstaller_extract(JNIEnv* env, jclass, jint fd, jstring destination) {
    const char* chars = env->GetStringUTFChars(destination, nullptr);
    if (!chars) return nullptr;
    const std::string output(chars);
    env->ReleaseStringUTFChars(destination, chars);
    try {
        return env->NewStringUTF(NovaPkg::Install("/proc/self/fd/" + std::to_string(fd), output).c_str());
    } catch (const std::exception& e) {
        env->ThrowNew(env->FindClass("java/io/IOException"), e.what());
        return nullptr;
    }
}
