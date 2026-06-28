/* chrome-bg.js — flowing liquid-metal background.
   A single full-screen fragment shader produces a slow, brushed-chrome field
   (the "Silver Surfer" atmosphere). Falls back silently if WebGL is absent or
   reduced-motion is requested. Pointer adds a faint parallax to the light. */

(function () {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || prefersReduced) { if (canvas) canvas.style.display = 'none'; return; }

  const gl = canvas.getContext('webgl', { antialias: false, alpha: true, premultipliedAlpha: false });
  if (!gl) { canvas.style.display = 'none'; return; }

  const vert = `
    attribute vec2 p;
    void main(){ gl_Position = vec4(p, 0.0, 1.0); }
  `;

  // Domain-warped fractal noise shaded as anisotropic chrome.
  const frag = `
    precision highp float;
    uniform vec2  u_res;
    uniform float u_time;
    uniform vec2  u_mouse;

    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    float noise(vec2 p){
      vec2 i = floor(p), f = fract(p);
      vec2 u = f*f*(3.0-2.0*f);
      return mix(mix(hash(i+vec2(0,0)), hash(i+vec2(1,0)), u.x),
                 mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
    }
    float fbm(vec2 p){
      float v = 0.0, a = 0.5;
      mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
      for(int i=0;i<5;i++){ v += a*noise(p); p = m*p; a *= 0.5; }
      return v;
    }

    void main(){
      vec2 uv = gl_FragCoord.xy / u_res.xy;
      vec2 p = (gl_FragCoord.xy - 0.5*u_res.xy) / u_res.y;
      float t = u_time * 0.025;

      // domain warp for the brushed-metal flow
      vec2 q = vec2(fbm(p*1.4 + t), fbm(p*1.4 - t + 5.2));
      vec2 r = vec2(fbm(p*2.0 + q*1.8 + vec2(1.7,9.2) + t*0.6),
                    fbm(p*2.0 + q*1.8 + vec2(8.3,2.8) - t*0.6));
      float f = fbm(p*1.6 + r*1.4);

      // mouse-driven light direction
      vec2 ld = normalize(vec2(0.4 + u_mouse.x*0.5, 0.8 - u_mouse.y*0.4));
      float spec = pow(max(0.0, dot(normalize(vec2(r.x, r.y)), ld)), 3.0);

      // chrome ramp
      float m = smoothstep(0.15, 0.95, f);
      vec3 dark  = vec3(0.024, 0.027, 0.035);
      vec3 steel = vec3(0.30, 0.33, 0.39);
      vec3 light = vec3(0.78, 0.81, 0.88);
      vec3 col = mix(dark, steel, m);
      col = mix(col, light, spec * 0.5 * m);

      // faint cyan-steel rim in highlights
      col += vec3(0.04, 0.07, 0.10) * spec * m;

      // heavy vignette so UI stays readable
      float vig = smoothstep(1.25, 0.25, length(p));
      col *= mix(0.25, 1.0, vig);

      // keep it subtle — this is atmosphere, not the subject
      gl_FragColor = vec4(col, 0.92);
    }
  `;

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('shader', gl.getShaderInfoLog(s)); return null;
    }
    return s;
  }
  const vs = compile(gl.VERTEX_SHADER, vert);
  const fs = compile(gl.FRAGMENT_SHADER, frag);
  if (!vs || !fs) { canvas.style.display = 'none'; return; }

  const prog = gl.createProgram();
  gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
  gl.useProgram(prog);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(prog, 'p');
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

  const uRes = gl.getUniformLocation(prog, 'u_res');
  const uTime = gl.getUniformLocation(prog, 'u_time');
  const uMouse = gl.getUniformLocation(prog, 'u_mouse');

  let mouse = [0, 0], target = [0, 0];
  window.addEventListener('pointermove', (e) => {
    target = [(e.clientX / innerWidth) * 2 - 1, (e.clientY / innerHeight) * 2 - 1];
  }, { passive: true });

  const DPR = Math.min(window.devicePixelRatio || 1, 1.5);
  function resize() {
    canvas.width = Math.floor(innerWidth * DPR);
    canvas.height = Math.floor(innerHeight * DPR);
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  resize();
  window.addEventListener('resize', resize);

  const start = performance.now();
  let raf;
  function frameLoop(now) {
    mouse[0] += (target[0] - mouse[0]) * 0.04;
    mouse[1] += (target[1] - mouse[1]) * 0.04;
    gl.uniform2f(uRes, canvas.width, canvas.height);
    gl.uniform1f(uTime, (now - start) / 1000);
    gl.uniform2f(uMouse, mouse[0], mouse[1]);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    raf = requestAnimationFrame(frameLoop);
  }
  // pause when tab hidden (save battery)
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else raf = requestAnimationFrame(frameLoop);
  });
  raf = requestAnimationFrame(frameLoop);
})();
