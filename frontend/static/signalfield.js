/* Signal Field — ambient WebGL background for the research workspace.
   Adapted from the shader-background technique used by React Bits'
   LightTunnel/GradientWaves (radial fragment shader driven by a handful of
   uniforms, rendered via a tiny WebGL2 lib), rewritten from scratch for this
   project: different geometry (converging signal lines, not a tunnel or
   waves — it reads as data streaming toward a point, which is what the agent
   actually does), Shutdown's own amber/cyan palette instead of purple/pink,
   and tuned to sit at low opacity behind real content rather than as a
   full-bleed hero. Runs on `ogl` (~5KB WebGL micro-library, vendored as its
   own ESM source tree, no bundler needed) rather than three.js — this is a
   flat shader plane, not a 3D scene, so the heavier engine buys nothing.

   Loaded as a native ES module; failure anywhere (no WebGL2, ogl missing)
   is caught and the caller just doesn't get a background — never a page
   crash over a decorative layer. */

import { Renderer, Program, Mesh, Triangle } from "/static/vendor/ogl/index.js";

const VERT = `#version 300 es
in vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
`;

// Converging signal lines: streams of light drift inward toward a focal
// point and pulse outward along their length -- evidence flowing toward a
// verdict, rendered abstractly. Two accent colors (amber = control plane,
// cyan = meta plane) interleave across the lines rather than one flat hue,
// so the field itself hints at the two-plane architecture without a label.
const FRAG = `#version 300 es
precision highp float;
uniform vec2  iResolution;
uniform float iTime;
uniform vec3  uAmber;
uniform vec3  uCyan;
uniform float uDensity;
uniform float uSpeed;
uniform float uOpacity;
uniform vec2  uMouse;
out vec4 fragColor;

float hash(float n) { return fract(sin(n) * 43758.5453123); }

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
  uv -= uMouse * 0.06;

  float r = length(uv) + 0.0001;
  float a = atan(uv.y, uv.x);

  float lines = uDensity;
  float slot = floor((a / 6.28318 + 0.5) * lines);
  float within = fract((a / 6.28318 + 0.5) * lines) - 0.5;

  float rnd = hash(slot);
  float speed = (0.35 + rnd * 0.5) * uSpeed;
  float depth = -log(r);
  float travel = fract(depth * 0.6 - iTime * speed + rnd * 4.0);

  float core = smoothstep(0.05, 0.0, abs(within)) * (1.0 - smoothstep(0.0, 1.0, r * 1.6));
  float pulse = smoothstep(0.14, 0.0, abs(travel - 0.5)) * core;

  vec3 col = mix(uAmber, uCyan, hash(slot + 7.0));
  // edge0 < edge1 required by spec -- the reversed form here previously
  // produced undefined (driver-dependent) results, which is part of why
  // this rendered as near-nothing rather than a visible fade
  float fade = 1.0 - smoothstep(0.05, 1.35, r);

  vec3 out_ = col * (core * 0.32 + pulse * 1.6) * fade;
  float alpha = (core * 0.22 + pulse * 1.0) * fade * uOpacity;

  fragColor = vec4(out_, alpha);
}
`;

export function mountSignalField(canvas, opts = {}) {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return { stop() {} };
  }

  let renderer, program, mesh, raf, running = true;
  try {
    renderer = new Renderer({ canvas, alpha: true, antialias: false, dpr: Math.min(window.devicePixelRatio || 1, 1.75) });
    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);

    program = new Program(gl, {
      vertex: VERT,
      fragment: FRAG,
      uniforms: {
        iResolution: { value: [1, 1] },
        iTime: { value: 0 },
        uAmber: { value: opts.amber || [0.204, 0.329, 0.820] },  /* --control indigo */
        uCyan: { value: opts.cyan || [0.486, 0.361, 0.749] },    /* --meta violet */
        uDensity: { value: opts.density ?? 26 },
        uSpeed: { value: opts.speed ?? 0.5 },
        uOpacity: { value: opts.opacity ?? 0.55 },
        uMouse: { value: [0, 0] },
      },
      transparent: true,
    });
    mesh = new Mesh(gl, { geometry: new Triangle(gl), program });
  } catch {
    return { stop() {} }; // no WebGL2 -- degrade to nothing, silently
  }

  const mouse = { x: 0, y: 0 };
  const onMove = (e) => {
    const r = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    mouse.y = -((e.clientY - r.top) / r.height - 0.5) * 2;
  };
  window.addEventListener("pointermove", onMove, { passive: true });

  const resize = () => {
    const parent = canvas.parentElement;
    const w = parent ? parent.clientWidth : window.innerWidth;
    const h = parent ? parent.clientHeight : 320;
    renderer.setSize(w, h);
    program.uniforms.iResolution.value = [gl_w(renderer), gl_h(renderer)];
  };
  const gl_w = (r) => r.gl.drawingBufferWidth;
  const gl_h = (r) => r.gl.drawingBufferHeight;
  const ro = new ResizeObserver(resize);
  if (canvas.parentElement) ro.observe(canvas.parentElement);
  resize();

  // pause off-screen and on hidden tabs -- an ambient background should not
  // burn a laptop's battery for a panel the presenter has scrolled past
  let visible = true;
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.01 });
  io.observe(canvas);
  const onVis = () => { visible = !document.hidden && visible; };
  document.addEventListener("visibilitychange", onVis);

  const t0 = performance.now();
  const lerp = (a, b, t) => a + (b - a) * t;
  let mx = 0, my = 0;

  const tick = (t) => {
    if (!running) return;
    raf = requestAnimationFrame(tick);
    if (!visible || document.hidden) return;
    mx = lerp(mx, mouse.x, 0.04);
    my = lerp(my, mouse.y, 0.04);
    program.uniforms.iTime.value = (t - t0) * 0.001;
    program.uniforms.uMouse.value = [mx, my];
    renderer.render({ scene: mesh });
  };
  raf = requestAnimationFrame(tick);

  return {
    stop() {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVis);
    },
  };
}
