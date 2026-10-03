import os
import time
import argparse
import numpy as np
import moderngl
import imageio
from seleniumbase import Driver, SB

# Shadertoy GLSL Wrapper
SHADER_WRAPPER = """
#version 330

out vec4 fragColor;

uniform vec3      iResolution;           // viewport resolution (in pixels)
uniform float     iTime;                 // shader playback time (in seconds)
uniform float     iTimeDelta;            // render time (in seconds)
uniform int       iFrame;                // shader playback frame
uniform vec4      iMouse;                // mouse pixel coords

// --- Injected Shadertoy Code ---
{shadertoy_code}
// -------------------------------

void main() {
    mainImage(fragColor, gl_FragCoord.xy);
}
"""

VERTEX_SHADER = """
#version 330
in vec2 in_position;
void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

def extract_shader_code(url: str) -> str:
    print(f"Loading {url} ...")
    with SB(uc=True, headless=False) as sb:
        sb.goto(url)
        sb.wait_for_element(".CodeMirror", timeout=30)
        code = sb.execute_script("return document.querySelector('.CodeMirror').CodeMirror.getValue();")
        return code

def render_shader_to_gif(shader_code: str, output_path: str, width: int = 512, height: int = 288, duration_sec: int = 3, fps: int = 30):
    print(f"Rendering shader to {output_path} ({width}x{height}, {fps}fps, {duration_sec}s)...")

    # Initialize Moderngl standalone context
    ctx = moderngl.create_standalone_context()

    # Setup offscreen rendering
    fbo = ctx.framebuffer(
        color_attachments=[ctx.texture((width, height), 4)]
    )
    fbo.use()

    # Compile the shader program
    fragment_shader = SHADER_WRAPPER.format(shadertoy_code=shader_code)
    try:
        prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=fragment_shader)
    except Exception as e:
        print("Failed to compile shader!")
        print(e)
        return

    # Setup full-screen quad
    vertices = np.array([
        -1.0, -1.0,
         1.0, -1.0,
        -1.0,  1.0,
         1.0,  1.0,
    ], dtype='f4')
    vbo = ctx.buffer(vertices)
    vao = ctx.vertex_array(prog, [(vbo, '2f', 'in_position')])

    # Render loop
    frames = []
    total_frames = duration_sec * fps

    for frame_idx in range(total_frames):
        current_time = frame_idx / fps

        # Update uniforms
        if 'iResolution' in prog:
            prog['iResolution'].value = (width, height, 1.0)
        if 'iTime' in prog:
            prog['iTime'].value = current_time
        if 'iTimeDelta' in prog:
            prog['iTimeDelta'].value = 1.0 / fps
        if 'iFrame' in prog:
            prog['iFrame'].value = frame_idx
        if 'iMouse' in prog:
            prog['iMouse'].value = (0.0, 0.0, 0.0, 0.0)

        ctx.clear()
        vao.render(moderngl.TRIANGLE_STRIP)

        # Read pixels
        data = fbo.read(components=3, alignment=1)
        image = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))
        # Flip vertically because OpenGL renders upside down relative to image coords
        image = np.flipud(image)
        frames.append(image)

    print(f"Saving GIF to {output_path}...")
    imageio.mimsave(output_path, frames, fps=fps)
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape and render Shadertoy shaders to GIF")
    parser.add_argument("urls", nargs='+', help="One or more Shadertoy URLs")
    parser.add_argument("--outdir", default=".", help="Output directory for GIFs")

    args = parser.parse_args()

    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    for url in args.urls:
        shader_id = url.rstrip('/').split('/')[-1]
        try:
            code = extract_shader_code(url)
            if code:
                out_path = os.path.join(args.outdir, f"{shader_id}.gif")
                render_shader_to_gif(code, out_path)
            else:
                print(f"Failed to extract code from {url}")
        except Exception as e:
            print(f"Error processing {url}: {e}")
