import * as THREE from 'three'

/*
 * The ground at z = 0: a line every metre, a stronger one every 5 m, fading
 * with distance from the camera. Plain three.js port of drei's <Grid> with the
 * settings of @equa/ui's SceneGrid, so the viewer and the building product
 * share one floor. Lines come from world position, so the plane can follow the
 * camera without the pattern swimming.
 */

const VERT = /* glsl */`
  varying vec3 vWorld;
  void main() {
    vec4 w = modelMatrix * vec4(position, 1.0);
    vWorld = w.xyz;
    gl_Position = projectionMatrix * viewMatrix * w;
  }`

const FRAG = /* glsl */`
  uniform float uCellSize;
  uniform float uCellThickness;
  uniform vec3 uCellColor;
  uniform float uSectionSize;
  uniform float uSectionThickness;
  uniform vec3 uSectionColor;
  uniform float uFadeDistance;
  uniform float uFadeStrength;
  varying vec3 vWorld;
  float grid(float size, float thickness) {
    vec2 r = vWorld.xy / size;
    vec2 g = abs(fract(r - 0.5) - 0.5) / fwidth(r);
    float line = min(g.x, g.y) + 1.0 - thickness;
    return 1.0 - min(line, 1.0);
  }
  void main() {
    float g1 = grid(uCellSize, uCellThickness);
    float g2 = grid(uSectionSize, uSectionThickness);
    float d = 1.0 - min(distance(cameraPosition.xy, vWorld.xy) / uFadeDistance, 1.0);
    vec3 color = mix(uCellColor, uSectionColor, min(1.0, uSectionThickness * g2));
    float alpha = (g1 + g2) * pow(d, uFadeStrength);
    alpha = mix(0.75 * alpha, alpha, g2);
    if (alpha <= 0.0) discard;
    gl_FragColor = vec4(color, alpha);
  }`

// SceneGrid's values (equa-ui web/src/scene/scene-grid.tsx).
const SETTINGS = {
  cellSize: 1, cellThickness: 0.6, sectionSize: 5, sectionThickness: 1,
  fadeDistance: 60, fadeStrength: 1.5,
}

export function makeGroundGrid() {
  const s = SETTINGS
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uCellSize: { value: s.cellSize },
      uCellThickness: { value: s.cellThickness },
      uCellColor: { value: new THREE.Color() },
      uSectionSize: { value: s.sectionSize },
      uSectionThickness: { value: s.sectionThickness },
      uSectionColor: { value: new THREE.Color() },
      uFadeDistance: { value: s.fadeDistance },
      uFadeStrength: { value: s.fadeStrength },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    // Behind any surface at z = 0 whatever the camera's depth precision.
    polygonOffset: true,
    polygonOffsetFactor: 4,
    polygonOffsetUnits: 4,
  })
  const size = 2 * s.fadeDistance
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), material)
  // 1 mm down keeps a floor at z = 0 from flickering with it.
  mesh.position.z = -0.001
  mesh.frustumCulled = false
  mesh.renderOrder = -1
  mesh.userData.follow = (camera) => {
    mesh.position.x = camera.position.x
    mesh.position.y = camera.position.y
  }
  mesh.userData.setColors = (cell, section) => {
    material.uniforms.uCellColor.value.set(cell)
    material.uniforms.uSectionColor.value.set(section)
  }
  return mesh
}
