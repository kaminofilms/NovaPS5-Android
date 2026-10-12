#version 450
layout(location=0) out vec3 color;
const vec2 positions[3]=vec2[3](vec2(0.0,-0.55),vec2(0.58,0.4),vec2(-0.58,0.4));
const vec3 colors[3]=vec3[3](vec3(0.2,0.75,1.0),vec3(0.65,0.3,1.0),vec3(0.1,0.3,0.9));
void main(){gl_Position=vec4(positions[gl_VertexIndex],0.0,1.0);color=colors[gl_VertexIndex];}
