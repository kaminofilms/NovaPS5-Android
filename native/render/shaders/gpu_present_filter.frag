#version 450
// Nova 0997: presentation upscaling filter (final stretch of the game frame to the screen).
// mode 1: bicubic (Catmull-Rom). mode 2: sharp, edge-safe bicubic in the spirit of yuzu's
// ScaleForce option: Catmull-Rom sharpness, clamped to the 2x2 source neighbourhood so edges stay
// crisp without halos or ringing. Written for Nova; not derived from other emulators' shaders.
layout(location = 0) in vec2 uv;
layout(location = 0) out vec4 color;
layout(binding = 0) uniform sampler2D source;
layout(push_constant) uniform Filter {
	uint mode;
};

vec4 CatmullRom(float t) {
	const float t2 = t * t;
	const float t3 = t2 * t;
	return vec4(-0.5 * t3 + t2 - 0.5 * t,
	            1.5 * t3 - 2.5 * t2 + 1.0,
	            -1.5 * t3 + 2.0 * t2 + 0.5 * t,
	            0.5 * t3 - 0.5 * t2);
}

void main() {
	const ivec2 size = textureSize(source, 0);
	const vec2  pos  = uv * vec2(size) - 0.5;
	const vec2  base = floor(pos);
	const vec2  f    = pos - base;
	const vec4  wx   = CatmullRom(f.x);
	const vec4  wy   = CatmullRom(f.y);
	vec4 sum = vec4(0.0);
	vec4 lo  = vec4(1e30);
	vec4 hi  = vec4(-1e30);
	for (int j = 0; j < 4; ++j) {
		for (int i = 0; i < 4; ++i) {
			const ivec2 p = clamp(ivec2(base) + ivec2(i - 1, j - 1), ivec2(0), size - 1);
			const vec4  c = texelFetch(source, p, 0);
			sum += c * (wx[i] * wy[j]);
			if (i >= 1 && i <= 2 && j >= 1 && j <= 2) {
				lo = min(lo, c);
				hi = max(hi, c);
			}
		}
	}
	color = mode == 2u ? clamp(sum, lo, hi) : clamp(sum, vec4(0.0), vec4(1.0));
}
