#!/bin/bash
# FFmpeg 7.1 static libraries for Android arm64, configured like Kyty's ext-ffmpeg-core (only the
# codecs/demuxers Kyty uses), packaged as a directory Kyty's FFMPEG_PREBUILT_DIR accepts.
#   build-android-ffmpeg.sh <workdir> <outdir>
set -euo pipefail
work=$(realpath -m "$1"); out=$(realpath -m "$2")
NDK=${ANDROID_NDK:-${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-}}}
API=${ANDROID_API:-33}
TC=$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin
[[ -x $TC/clang ]] || { echo "Android NDK not found"; exit 2; }
if [[ -f $out/lib/libavcodec.a && -f $out/include/libavcodec/avcodec.h ]]; then echo "FFmpeg cached"; exit 0; fi
mkdir -p "$work"; cd "$work"
[[ -d ffmpeg ]] || git clone -q --depth 1 -b n7.1 https://github.com/FFmpeg/FFmpeg.git ffmpeg
cd ffmpeg
opts=(--enable-decoder=aac --enable-decoder=aac_latm --enable-decoder=atrac3 --enable-decoder=atrac3p --enable-decoder=atrac9
      --enable-decoder=mp3 --enable-decoder=pcm_s16le --enable-decoder=pcm_s8 --enable-decoder=h264 --enable-decoder=mpeg4
      --enable-decoder=mpeg2video --enable-decoder=mjpeg --enable-decoder=mjpegb --enable-decoder=hevc --enable-decoder=vp8
      --enable-decoder=vp9 --enable-decoder=opus --enable-decoder=vorbis --enable-encoder=pcm_s16le --enable-encoder=ffv1
      --enable-encoder=mpeg4 --enable-encoder=ljpeg --enable-encoder=mjpeg --enable-muxer=avi
      --enable-demuxer=h265 --enable-demuxer=h264 --enable-demuxer=m4v --enable-demuxer=mp3 --enable-demuxer=mpegvideo
      --enable-demuxer=mpegps --enable-demuxer=mjpeg --enable-demuxer=mov --enable-demuxer=avi --enable-demuxer=aac
      --enable-demuxer=pmp --enable-demuxer=oma --enable-demuxer=pcm_s16le --enable-demuxer=pcm_s8 --enable-demuxer=wav
      --enable-demuxer=matroska --enable-parser=h264 --enable-parser=mpeg4video --enable-parser=mpegaudio
      --enable-parser=mpegvideo --enable-parser=mjpeg --enable-parser=aac --enable-parser=aac_latm --enable-parser=vp8
      --enable-parser=vp9 --enable-parser=opus --enable-parser=vorbis --enable-protocol=file --enable-bsf=mjpeg2jpeg)
./configure --prefix="$out" --target-os=android --arch=aarch64 --cpu=armv8-a --enable-cross-compile \
    --cc="$TC/aarch64-linux-android$API-clang" --cxx="$TC/aarch64-linux-android$API-clang++" \
    --ar="$TC/llvm-ar" --nm="$TC/llvm-nm" --ranlib="$TC/llvm-ranlib" --strip="$TC/llvm-strip" \
    --enable-pic --disable-doc --disable-programs --enable-static --disable-shared --disable-autodetect \
    --enable-runtime-cpudetect --disable-everything --disable-debug "${opts[@]}" \
    --extra-cflags="-O2" > "$work/ffmpeg-configure.txt" 2>&1 || { tail -40 "$work/ffmpeg-configure.txt"; tail -60 ffbuild/config.log; exit 1; }
make -j"$(nproc)" > "$work/ffmpeg-build.txt" 2>&1 || { grep -E "error" "$work/ffmpeg-build.txt" | head -40; exit 1; }
make install > /dev/null
mkdir -p "$out/share/ffmpeg"; cp COPYING.LGPLv2.1 LICENSE.md "$out/share/ffmpeg/"
ls -la "$out/lib"
