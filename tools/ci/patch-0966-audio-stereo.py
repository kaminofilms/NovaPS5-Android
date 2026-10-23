#!/usr/bin/env python3
"""0.9.66: explicit surround folding for a stereo SDL device, preserving guest timing."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'src/libs/audio.cpp'
s = path.read_text()
def edit(old, new):
    global s
    if s.count(old) != 1:
        raise SystemExit('NOVA_0966_AUDIO: source anchor changed: ' + repr(old[:90]))
    s = s.replace(old, new, 1)

edit('int         channels_num = 0;', 'int         channels_num = 0;\n\t\tbool        stereo_fold = false;')
edit('return std::min(port.channels_num, 8);', 'return port.stereo_fold ? 2u : static_cast<uint32_t>(std::min(port.channels_num, 8));')
edit('\tdesired.channels = static_cast<int>(OutputChannels(*port));', '\tport->stereo_fold = false;\n\tdesired.channels = static_cast<int>(OutputChannels(*port));')
edit('\tif (!SDL_ResumeAudioStreamDevice(port->stream)) {', '''
\t// The SDL logical stream may have 8 channels while the actual device is stereo.
\t// Explicit folding avoids SDL's generic matrix attenuating the front channels.
\tSDL_AudioSpec device_format {};
\tif (port->channels_num >= 8 &&
\t    SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(port->stream), &device_format, nullptr) &&
\t    device_format.channels >= 1 && device_format.channels <= 2) {
\t\tSDL_DestroyAudioStream(port->stream);
\t\tport->stream = nullptr;
\t\tdesired.channels = 2;
\t\tport->stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &desired, nullptr, nullptr);
\t\tif (port->stream == nullptr) {
\t\t\tSDL_QuitSubSystem(SDL_INIT_AUDIO);
\t\t\treturn false;
\t\t}
\t\tport->stereo_fold = true;
\t\tstd::fprintf(stderr, "NOVA_AUDIO_DOWNMIX: guest=%d device=%d stream=2 front_gain=1 center_surround=0.7071\\n",
\t\t             port->channels_num, device_format.channels);
\t}
\tif (!SDL_ResumeAudioStreamDevice(port->stream)) {''')
edit('\tif (!volume_changed && !reorder) {', '\tif (!volume_changed && !reorder && !port.stereo_fold && channels == output_channels) {')
edit('\t// SDL wants back speakers before side speakers; non-STD PCM has them reversed.', '''
\t// Front/center/surround weights follow the explicit PS4 stereo fold in shadPS4.
\t// Copyright 2024-2026 shadPS4 Emulator Project, GPL-2.0-or-later.
\t// Nova additionally applies each guest channel gain and folds 12-channel height pairs.
\tif (port.stereo_fold) {
\t\tfor (uint32_t frame = 0; frame < frames; ++frame) {
\t\t\tconst auto sample = [&](uint32_t ch) -> double {
\t\t\t\tconst size_t index = static_cast<size_t>(frame) * channels + ch;
\t\t\t\treturn (FormatIsFloat(port.format) ? static_cast<const float*>(data)[index]
\t\t\t\t                                 : static_cast<const int16_t*>(data)[index] / 32768.0) * scales[ch];
\t\t\t};
\t\t\tdouble left = sample(0) + 0.7071 * (sample(2) + sample(4) + sample(6));
\t\t\tdouble right = sample(1) + 0.7071 * (sample(2) + sample(5) + sample(7));
\t\t\tif (channels == 12) {
\t\t\t\tleft += 0.5 * (sample(8) + sample(10));
\t\t\t\tright += 0.5 * (sample(9) + sample(11));
\t\t\t}
\t\t\tif (FormatIsFloat(port.format)) {
\t\t\t\tauto* dst = reinterpret_cast<float*>(buffer->data());
\t\t\t\tdst[frame * 2] = static_cast<float>(std::clamp(left, -1.0, 1.0));
\t\t\t\tdst[frame * 2 + 1] = static_cast<float>(std::clamp(right, -1.0, 1.0));
\t\t\t} else {
\t\t\t\tauto* dst = reinterpret_cast<int16_t*>(buffer->data());
\t\t\t\tdst[frame * 2] = static_cast<int16_t>(std::clamp(left * 32768.0, -32768.0, 32767.0));
\t\t\t\tdst[frame * 2 + 1] = static_cast<int16_t>(std::clamp(right * 32768.0, -32768.0, 32767.0));
\t\t\t}
\t\t}
\t\treturn buffer->data();
\t}
\t// SDL wants back speakers before side speakers; non-STD PCM has them reversed.''')
path.write_text(s)
print('NOVA_0966_AUDIO: actual-device stereo fold; guest frame count/clock unchanged')
