# Sentinel QSG Heatmap Refactor Plan

## 1. Analysis of the Current Heatmap Implementation
- **Geometry inefficiency:** Each heatmap cell is drawn as six independent triangles (likely two quads + outlines), producing 6× the vertex count and QSG geometry nodes per cell. With millions of cells visible, this explodes the scene graph node count and prevents the renderer thread from batching, leaving the GUI thread CPU-bound due to node creation and updates.
- **Batching failure:** QSG batches draw calls when adjacent nodes share the same `QSGMaterial` and compatible `QSGGeometry` layouts. Per-cell nodes with unique materials/geometry break batch merging, leading to thousands of draw calls per frame and high command submission overhead.
- **Overdraw and index duplication:** Six triangles per cell increase overdraw and cause redundant edge fragments. Indices/vertices are duplicated instead of sharing a single quad per cell.
- **CPU-bound hotspots:**
  - QML/GUI thread spends time instantiating and marking many QSG nodes dirty each frame.
  - Renderer thread spends time building batches, validating materials, and uploading many small VBOs/IBOs instead of streaming a compact buffer.
- **GPU-bound symptoms:** Fragment load increases because of 6-triangle cells and possible per-fragment blending, but the primary bottleneck is CPU-side submission; GPU utilization is low while FPS is capped by scene graph traversal.
- **Memory layout issues:** Per-cell objects likely store state in AoS structures (structs with position, color, age) causing cache misses when iterating. Frequent allocations/reallocations of node/geometry buffers create allocator churn and poor CPU cache locality.
- **Transform overhead:** Per-node transforms applied on CPU for every cell; lack of instancing means coordinate mapping happens per-vertex instead of per-instance uniform/attribute.
- **Threading limitations:** Prior use of `QQuickWidget` forces the render loop onto the GUI thread. Migrating to `QQuickView` + `createWindowContainer` enables Qt’s threaded render loop, but the current node structure remains incompatible with efficient batching.

## 2. Target Architecture for the New Heatmap Renderer
- **Single quad + instancing:** Define one static unit quad (two triangles) in a shared `QSGGeometry` with 4 vertices and 6 indices. All cells are rendered as instances via per-instance attributes (position, size, color/intensity/age) in an instance buffer.
- **Data structures:**
  - `HeatmapInstance` SoA buffers: arrays for `center`, `size`, `color/intensity`, `age/opacity`, `flags/LOD`.
  - GPU buffers: one static VBO/IBO for the quad; one dynamic/streamed VBO for instance data; optional SSBO/UBO for palette/parameters.
  - `HeatmapMaterial : QSGMaterial` holding shader, palette texture/SSBO handles, and uniforms (time, zoom, alpha).
  - `HeatmapNode : QSGGeometryNode` owning the quad geometry and referencing the instanced material; overrides `QSGGeometryNode::setGeometry` with `QSGGeometry::AttributeSet` that includes instance divisor.
- **Material + node cooperation:**
  - `QSGMaterialType` ensures nodes with identical materials batch together.
  - `QSGMaterialShader` sets up vertex attribute layouts, enables instancing via `QSGGeometry::setVertexDataPattern(QSGGeometry::StaticPattern)` for quad and `QSGGeometry::setInstanceCount(n)` for instances.
- **Draw-call expectations:** One draw call per heatmap layer per frame (or per LOD tier) instead of per cell. Qt SG will merge all nodes with the same material into a single batch for the layer.
- **LOD strategy:**
  - High zoom: render per-tick cells with full opacity and age-based fading.
  - Medium zoom: collapse multiple ticks into a single aggregated instance (e.g., per-Δt bin) to cap instance count.
  - Low zoom: fall back to columnar bars/volume strips; limit instance count to budget (e.g., 50k visible). LOD selection occurs CPU-side before uploading instance buffer.

## 3. Shader & Material Design
- **Per-instance attributes:**
  - `vec2 center` (price/time mapped to normalized device coordinates or scene coords).
  - `vec2 size` (width/height in scene coords after zoom scaling).
  - `vec4 colorIntensity` (RGB ramp index/intensity packed; e.g., RGB = palette index/gradient parameter, A = base opacity).
  - `float age` (seconds since tick for decay).
  - `float value` (volume/size to drive ramp and alpha).
- **Vertex shader:**
  - Expand unit quad by `size` around `center`; apply view/projection matrix from QSG (scenegraph provides matrix via `qt_Matrix` uniform in RHI/GL modes).
  - Pass `value`, `age`, and derived intensity to fragment shader.
- **Fragment shader:**
  - Sample 1D palette texture or use procedural ramp; compute opacity from `value` and `age` decay (e.g., exp falloff).
  - Premultiply alpha and output to support Qt blending (`QSGMaterial::Blending` flag).
  - Optional gridline mask via smoothstep for thin borders without extra geometry.
- **Qt SG integration:**
  - Implement `HeatmapMaterialShader` derived from `QSGMaterialShader` with `updateUniformData` (RHI) to push palette parameters, time uniform, zoom.
  - Set `flags()` to `Blending | RequiresDeterminant` as needed.
- **Dynamic updates:**
  - Maintain dirty flags on instance buffer regions; call `markDirty(DirtyMaterial)` when palette/uniforms change, `markDirty(DirtyGeometry)` when instance count or buffer changes.
  - Use partial buffer updates via `QSGDynamicInstanceBuffer` or direct RHI buffer update in `updateSampledImage/compile` depending on API (GL vs RHI).

## 4. Dataflow Integration
- **Subscription:** Heatmap renderer subscribes to the existing tick/volume stream (already efficient) via a lock-free ring buffer or signal/slot feeding a staging queue owned by the render-side adaptor.
- **Update pattern:**
  - UI thread collects incoming ticks into a frame-local vector, applies LOD/binning, and writes into a persistently mapped instance buffer segment.
  - Avoid recreating `QSGGeometry` or nodes; only update instance count and mapped data.
  - Use double-buffered instance VBOs (`front` consumed by render thread, `back` written by UI thread) to avoid stalls; swap on `QSGNode::update`.
- **GPU buffer management:**
  - Create dynamic VBO with `QSGGeometry::DynamicPattern` (or RHI `Usage::Dynamic`).
  - Use persistent mapping when available; fall back to `QSGRendererInterface::updateBuffer` with orphaning.
  - Align instance stride to 16 bytes for cache friendliness and driver alignment.

## 5. View Transformations
- **Mapping:** CPU computes price→y and time→x mapping into scene coordinates; pass transformation matrix (scale + translation) as uniform. Alternatively pass viewport rect and let vertex shader transform normalized values.
- **GPU-side transform:** Vertex shader multiplies `center` by view/projection matrix; `size` scaled by zoom factors (uniform) to avoid CPU-side recomputation of per-instance vertex positions.
- **Zoom & pan:** On zoom/pan, only update a few uniforms (scale/offset) instead of re-uploading all instance positions. If price/time bins change LOD, rebuild instance buffer once per zoom step.

## 6. Memory & Cache Optimization
- **SoA layout:** Separate arrays for `centerX`, `centerY`, `sizeX`, `sizeY`, `intensity`, `age`, `value` to improve SIMD pre-processing and minimize cache misses when filtering/LOD’ing.
- **VBO layout:** Interleave only what GPU needs per instance (e.g., `vec2 center`, `vec2 size`, `vec2 valueAge`, `vec4 color`), aligned to 16-byte boundaries; avoid padding-heavy structs on CPU.
- **Allocation strategy:** Pre-allocate maximum visible instances (budgeted by viewport size and LOD cap). Reuse buffers; rely on write-discard (orphan) rather than reallocating.
- **Limits:** Cap historical depth per view (e.g., 2–5 minutes at tick-level) and clamp maximum visible instances (e.g., 100k–200k) to ensure single-draw budgets fit GPU caches and keep 120–240 FPS.

## 7. Testing Plan
- **FPS measurement:** Integrate a lightweight frame timer on the render thread (e.g., `QSGRendererInterface::invalidate` hooks or QQuickWindow frame signals) and log FPS while panning/zooming.
- **Stall detection:** Use Qt’s `QQuickWindow::beforeRendering/afterRendering` signals to timestamp render-pass durations; detect spikes > frame budget (8.3 ms for 120 FPS, 4.1 ms for 240 FPS).
- **GPU timing:** For GL: use `GL_TIMESTAMP` queries inserted in `HeatmapMaterialShader::updateSampledImage`. For RHI: use `QRhiCommandBuffer::beginComputePass` timestamp queries if supported.
- **Load tests:** Synthetic tick generator to push 1M+ points per second; verify no frame drops and stable memory footprint.

## 8. Migration Path
- **Removal:** Delete per-cell QSG nodes/triangle meshes, per-cell materials, and any CPU-side path that rebuilds geometry each frame.
- **First steps:**
  1) Introduce `HeatmapMaterial` + `HeatmapMaterialShader` with static quad geometry and instancing enabled.
  2) Add instance buffer management with double-buffering and dirty flags.
  3) Integrate into existing QML/scene graph entry point replacing old node tree.
  4) Add palette handling and age-based fade.
  5) Implement LOD binning pipeline.
- **Optional QSGRenderNode:** If RHI limitations prevent efficient instancing, consider `QSGRenderNode` to issue custom RHI/GL draw; keep API boundary so the node can switch between `QSGGeometryNode` and `QSGRenderNode` implementations.
- **Incremental compilation:** Keep old renderer behind a feature flag; build the new node in parallel, then switch the QML component to use the new item once stable. Maintain interface compatibility for data feed.

## 9. Risk Analysis
- **Qt pitfalls:**
  - QSG nodes must be created on the GUI thread; rendering happens on the render thread. Ensure instance buffers are updated only in `updatePaintNode` with thread-safe handoff.
  - `QQuickWidget` must be avoided to keep threaded rendering; ensure `QQuickView` + `createWindowContainer` is used everywhere.
  - Shader compilation differences between GL, Vulkan, D3D11, Metal via QRhi; use GLSL 4.50 with `#version 450` and rely on Qt shader tools for cross-compilation (`qmlcachegen` or `qsb`).
- **Synchronization hazards:** Double-buffer instance data; avoid sharing mapped buffers across threads. Use atomics or ring buffers for tick ingestion; never block the render thread.
- **Driver quirks:**
  - Windows/D3D11 may impose 16-byte alignment and smaller max instance strides—validate with `QRhi::supportedFeature`. 
  - macOS/Metal may require separate buffers for vertex + instance data; test via RHI backend selection.
  - Integrated GPUs have smaller buffer mapping bandwidth; keep instance payload minimal and employ LOD aggressively.
- **QML binding churn:** Avoid exposing per-cell properties to QML; keep renderer as a C++ item with minimal bindings (palette, zoom, opacity) to reduce binding recalculations on UI thread.
