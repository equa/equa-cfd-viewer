/*
 * The whole appearance pipeline, in about forty lines of GLSL.
 *
 * This is the payoff of the split: anything that is a *transfer function* in
 * VTK is a *uniform* here, and a uniform is instant. Colour map, colour range,
 * band count and the opacity ramp therefore cost no round trip and no
 * re-extraction -- where the Trame path has to rebuild a
 * vtkColorTransferFunction and re-serialise it, and could not do the opacity
 * ramp at all (the discretizable CTF does not serialise to vtk.js; reverted).
 *
 * The price, and it is real: every setting the shader owns is a setting the
 * server does not know. A server-side render (a report PNG) will not match this
 * view unless these values travel with the render request.
 */

export const VERT = /* glsl */`
  attribute float scalar;
  attribute float travel;
  uniform float uTubeRadius;
  varying float vScalar;
  varying float vTravel;
  varying vec3 vNormal;
  varying vec3 vViewPos;
  void main() {
    vScalar = scalar;
    vTravel = travel;
    vNormal = normalize(normalMatrix * normal);
    // Tube geometry arrives as CENTRELINE points whose normal is the ring's
    // radial direction, so this displacement is the tube itself -- which is why
    // the width slider moves no vertices. 0 everywhere else: an exact no-op,
    // since it then adds normal * 0.
    vec3 placed = position + normal * uTubeRadius;
    vec4 mv = modelViewMatrix * vec4(placed, 1.0);
    vViewPos = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }`

/* One arrow mesh (along +X, length 1) instanced at every anchor the server
 * sent. Size and length-by-magnitude are uniforms, so neither refetches. The
 * scale is uniform in all three axes, as vtkGlyph3D's is. */
export const VERT_GLYPH = /* glsl */`
  attribute vec3 offset;
  attribute vec3 vector;
  attribute float scalar;
  uniform float uGlyphSize;
  uniform float uGlyphRef;
  uniform float uScaleBy;
  varying float vScalar;
  varying float vTravel;
  varying vec3 vNormal;
  varying vec3 vViewPos;
  void main() {
    float m = length(vector);
    vec3 x = m > 0.0 ? vector / m : vec3(1.0, 0.0, 0.0);
    vec3 up = abs(x.z) < 0.9 ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);
    vec3 y = normalize(cross(up, x));
    mat3 turn = mat3(x, y, cross(x, y));
    // A zero vector (a no-slip wall) has no direction to show: no arrow.
    float size = m > 0.0 ? uGlyphSize * mix(1.0, m / uGlyphRef, uScaleBy) : 0.0;
    vScalar = scalar;
    vTravel = 0.0;
    vNormal = normalize(normalMatrix * (turn * normal));
    vec3 placed = offset + turn * (position * size);
    vec4 mv = modelViewMatrix * vec4(placed, 1.0);
    vViewPos = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }`

export const VERT_LINE = /* glsl */`
  attribute float scalar;
  attribute float travel;
  varying float vScalar;
  varying float vTravel;
  void main() {
    vScalar = scalar;
    vTravel = travel;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }`

/* Discrete colour bands are a quantisation of the *lookup coordinate*, not of
 * the table: t -> the centre of its band. Sampling the smooth 256-entry LUT at
 * (i+0.5)/N returns exactly cmap((i+0.5)/N), which is the colour FoamViz bakes
 * into transfer-function plateau i -- so the two renderers band identically
 * rather than merely similarly. */
/* Comets riding the streamlines.
 *
 * An animated dash pattern, which is all a "particle" needs to be: `travel` is
 * per-vertex transport time along the streamline (server/scene.py bakes it from
 * vtkStreamTracer's own IntegrationTime), so a pulse at a fixed phase offset
 * advances at the LOCAL FLOW SPEED without anything moving on the CPU. No
 * particle buffer, no re-seeding, no per-frame JS: one uniform.
 *
 * Because travel is real transport time and not arc length, comets speed up
 * where the flow is fast -- ~32x variation along the demo case's streamlines --
 * which is the point. It also gives the streamlines something they simply did
 * not have before: a visible DIRECTION. A static streamline is
 * direction-ambiguous.
 *
 * `fract` of (phase - travel) puts the head at f == 0 and the tail just behind
 * it: a point slightly upstream has slightly larger f, so an exponential decay
 * in f trails the comet upstream, which is the way a tail points.
 *
 * uComets == 0 must be an exact no-op -- glow 0 and dim 1, so the fragment is
 * bit-identical to the un-animated one.
 */
const COMET = /* glsl */`
  uniform float uComets;
  uniform float uCometPhase;
  uniform float uCometPeriod;
  uniform float uCometTail;
  uniform float uCometDim;
  varying float vTravel;

  float cometGlow() {
    if (uComets < 0.5) return 0.0;
    return exp(-fract((uCometPhase - vTravel) / uCometPeriod) * uCometTail);
  }
  // Between comets the line dims, so the comets read as bright objects on a
  // faint path rather than as brightness noise along a solid one.
  float cometDim() { return mix(1.0, uCometDim, uComets); }
  // A modest lift toward white: enough to read as a comet head, not enough to
  // throw away the field colour the line is carrying.
  vec3 cometTint(vec3 base, float glow) { return mix(base, vec3(1.0), glow * 0.6); }`

const BAND = /* glsl */`
  float band(float t, float n) {
    if (n < 1.5) return t;
    return (min(floor(t * n), n - 1.0) + 0.5) / n;
  }`

/* Presentation shading: GGX key highlight plus a procedural studio surround
 * (bright overhead, dark floor, one softbox) reflected with Fresnel. World z is
 * up, so the surround is looked up in world space. */
const STUDIO = /* glsl */`
  const float PI = 3.14159265;
  // Two softboxes fixed to the camera, like the key and fill: one over the
  // viewer's shoulder (sheen on faces turned to the camera), one high behind
  // the subject (sheen on floors seen at a glance). Sky/ground from world z.
  float softbox(vec3 r, vec3 dir, float rough) {
    return pow(max(dot(r, normalize(dir)), 0.0), mix(60.0, 2.0, rough));
  }
  vec3 studio(vec3 rv, vec3 rw, float rough) {
    float w = 0.1 + rough;
    vec3 c = mix(vec3(0.05), vec3(0.55, 0.58, 0.64), smoothstep(-w, w, rw.z));
    float boxes = softbox(rv, vec3(-0.4, 0.5, 0.75), rough)
                + softbox(rv, vec3(0.15, 0.6, -0.8), rough);
    return c + vec3(boxes) * mix(1.4, 0.3, rough);
  }
  // three.js's RoomEnvironment, pre-blurred per roughness (PMREM). It is y-up
  // and the case is z-up, hence the swizzle.
  uniform samplerCube uEnvMap;
  uniform float uEnvLod;
  uniform float uEnvMix;
  uniform float uEnvIntensity;
  vec3 room(vec3 rw, vec3 nw, float rough) {
    vec3 d = normalize(mix(rw, nw, rough * rough * rough * rough));
    float mip = uEnvLod * rough * (2.0 - rough);
    return textureLod(uEnvMap, vec3(d.x, d.z, -d.y), mip).rgb * uEnvIntensity;
  }
  vec3 present(vec3 base, float shade, vec3 n) {
    vec3 v = normalize(-vViewPos);
    if (dot(n, v) < 0.0) n = -n;
    vec3 nw = (vec4(n, 0.0) * viewMatrix).xyz;
    vec3 rv = reflect(-v, n);
    vec3 rw = (vec4(rv, 0.0) * viewMatrix).xyz;
    vec3 L = normalize(vec3(0.35, 0.65, 0.55));
    vec3 h = normalize(L + v);
    float ndl = max(dot(n, L), 0.0);
    float ndv = max(dot(n, v), 1e-3);
    float ndh = max(dot(n, h), 0.0);
    float ldh = max(dot(L, h), 1e-3);
    float a = max(uRoughness * uRoughness, 0.002);
    float dd = ndh * ndh * (a * a - 1.0) + 1.0;
    float D = a * a / (PI * dd * dd);
    float spec = D * ndl * 0.25 / (ldh * ldh);
    float f0 = 0.04 + 0.08 * uSpecular;
    float fv = f0 + (max(1.0 - uRoughness, f0) - f0) * pow(1.0 - ndv, 5.0);
    // The analysis shading stays the base, so no face turns darker than it was.
    vec3 diffuse = base * shade * mix(0.9, 1.1, nw.z * 0.5 + 0.5);
    vec3 env = mix(studio(rv, rw, uRoughness), room(rw, nw, uRoughness), uEnvMix);
    vec3 gloss = uSpecular * (vec3(spec) * f0 + fv * env);
    return diffuse * (1.0 - fv) + gloss;
  }`

/* Two-sided key + fill over an ambient floor, so no face reads as black -- the
 * rule vtkLightKit follows, hence abs() on the dots. uDiffuse scales the
 * directional part, uAmbient the floor: together they are the Lighting panel. */
export const FRAG = /* glsl */`
  uniform sampler2D uLut;
  uniform vec2 uRange;
  uniform float uOpacity;
  uniform float uAmbient;
  uniform float uDiffuse;
  uniform float uBands;
  uniform float uOpacityMap;
  // 1 = colour by the field, 0 = flat uFlat (the Trame app's "Colour by field"
  // off, where the shell is a neutral grey so the slice inside it reads).
  uniform float uColored;
  uniform vec3 uFlat;
  // 1 only when the geometry really carries a scalar attribute. Without this
  // guard a scalar-less part would read vScalar == 0: the lowest colour, and
  // invisible under the opacity ramp.
  uniform float uHasScalar;
  uniform float uNormalOut;
  // Presentation mode: 0 keeps the exact LUT colour, 1 adds gloss.
  uniform float uPresent;
  uniform float uRoughness;
  uniform float uSpecular;
  varying float vScalar;
  varying vec3 vNormal;
  varying vec3 vViewPos;
  ${BAND}
  ${COMET}
  ${STUDIO}
  void main() {
    float t = clamp((vScalar - uRange.x) / max(uRange.y - uRange.x, 1e-12), 0.0, 1.0);
    vec3 base = mix(uFlat, texture2D(uLut, vec2(band(t, uBands), 0.5)).rgb, uColored * uHasScalar);
    vec3 n = normalize(vNormal);
    float key = abs(dot(n, normalize(vec3(0.35, 0.65, 0.55))));
    float fill = abs(dot(n, normalize(vec3(-0.6, -0.25, 0.5)))) * 0.35;
    float shade = uAmbient + uDiffuse * (key + fill);
    vec3 lit = base * shade;
    if (uPresent > 0.5) lit = present(base, shade, n);
    // Colour-map-weighted opacity, linear: alpha follows the *unbanded* t, so
    // the ramp stays a function of the value the way ParaView's own opacity
    // transfer function is, independent of how the colours are banded.
    float alpha = uOpacity * mix(1.0, t, uOpacityMap * uHasScalar);
    float glow = cometGlow();
    alpha *= mix(cometDim(), 1.0, glow);
    if (alpha < 0.01) discard;  // transparent fragments must not blend or occlude
    // Ambient occlusion's normal pass: the view-space normal, packed as
    // MeshNormalMaterial does, so glyphs and tubes occlude where they are drawn.
    if (uNormalOut > 0.5) {
      vec3 nn = dot(n, vViewPos) > 0.0 ? -n : n;
      gl_FragColor = vec4(nn * 0.5 + 0.5, 1.0);
      return;
    }
    gl_FragColor = vec4(cometTint(lit, glow), alpha);
  }`

export const FRAG_LINE = /* glsl */`
  uniform sampler2D uLut;
  uniform vec2 uRange;
  uniform float uOpacity;
  uniform float uBands;
  uniform float uOpacityMap;
  uniform float uColored;
  uniform vec3 uFlat;
  uniform float uHasScalar;
  uniform float uNormalOut;
  varying float vScalar;
  ${BAND}
  ${COMET}
  void main() {
    float t = clamp((vScalar - uRange.x) / max(uRange.y - uRange.x, 1e-12), 0.0, 1.0);
    float alpha = uOpacity * mix(1.0, t, uOpacityMap * uHasScalar);
    float glow = cometGlow();
    alpha *= mix(cometDim(), 1.0, glow);
    if (alpha < 0.01) discard;
    // A line has no surface: in the normal pass it faces the camera.
    if (uNormalOut > 0.5) {
      gl_FragColor = vec4(0.5, 0.5, 1.0, 1.0);
      return;
    }
    vec3 base = mix(uFlat, texture2D(uLut, vec2(band(t, uBands), 0.5)).rgb, uColored * uHasScalar);
    gl_FragColor = vec4(cometTint(base, glow), alpha);
  }`
