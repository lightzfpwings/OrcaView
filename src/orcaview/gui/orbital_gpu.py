"""Hardware rendering of the orbital overlay with persistent indexed meshes."""

from functools import lru_cache
import logging
import struct

from PySide6.QtGui import QImage

from .orbital_raster import phase_indices


_LOG = logging.getLogger(__name__)
_SHADER = """
struct Scene {
    x: vec4f, y: vec4f, z: vec4f, light: vec4f, positive: vec4f, negative: vec4f,
    screen: vec4f,
};
@group(0) @binding(0) var<uniform> scene: Scene;
struct Vertex {
    @builtin(position) position: vec4f,
    @location(0) normal: vec3f,
    @location(1) color: vec3f,
};
@vertex fn vs(@location(0) position: vec3f, @location(1) normal: vec3f,
              @builtin(instance_index) phase: u32) -> Vertex {
    let p = vec4f(position, 1.0);
    return Vertex(vec4f(dot(p, scene.x), dot(p, scene.y), dot(p, scene.z), 1.0),
                  normal, select(scene.negative.rgb, scene.positive.rgb, phase == 0u));
}
@fragment fn fs(v: Vertex) -> @location(0) vec4f {
    let t = clamp(dot(normalize(v.normal), scene.light.xyz), 0.0, 1.0);
    let rgb = min(vec3f(1.0), v.color*(0.52 + 0.48*t) + vec3f(42.0/255.0*t*t));
    return vec4f(rgb*0.8, 0.8);
}

struct Capsule {
    @builtin(position) position: vec4f,
    @location(0) @interpolate(linear, sample) xy: vec2f,
    @location(1) @interpolate(flat) a: vec4f,
    @location(2) @interpolate(flat) b: vec3f,
};
@vertex fn molecule_vs(@location(0) a: vec4f, @location(1) b: vec3f,
                       @builtin(vertex_index) corner: u32) -> Capsule {
    let lo = min(a.xy, b.xy) - a.w;
    let hi = max(a.xy, b.xy) + a.w;
    let xy = select(lo, hi, vec2<bool>((corner & 1u) != 0u, (corner & 2u) != 0u));
    return Capsule(vec4f(xy*scene.screen.xy + vec2f(-1, 1), 0.5, 1), xy, a, b);
}
@fragment fn molecule_fs(v: Capsule) -> @builtin(frag_depth) f32 {
    let delta = v.b - v.a.xyz;
    let offset = v.xy - v.a.xy;
    let len = length(delta.xy);
    var disk = v.a.w*v.a.w-dot(offset, offset);
    var z = max(v.a.z, v.b.z);
    if len > 0.000001 {
        let axis = delta.xy/len;
        let along = dot(offset, axis);
        let across = dot(offset, vec2f(axis.y, -axis.x));
        let span = v.a.w*v.a.w-across*across;
        let t = clamp(along+delta.z/length(delta)*sqrt(max(0.0, span)), 0.0, len);
        disk = span-(along-t)*(along-t);
        z = v.a.z+delta.z*t/len;
    }
    if disk < 0.0 { discard; }
    return clamp(0.5+(z+sqrt(disk))*scene.screen.z, 0.0, 1.0);
}
"""


def preferred_adapters(adapters):
    priority = {"DiscreteGPU": 0, "IntegratedGPU": 1, "VirtualGPU": 2, "Unknown": 3}
    hardware = [a for a in adapters if a.info["adapter_type"] in priority]
    return sorted(hardware, key=lambda a: priority[a.info["adapter_type"]])


@lru_cache(maxsize=1)
def _device():
    import wgpu

    for adapter in preferred_adapters(wgpu.gpu.enumerate_adapters_sync()):
        try:
            device = adapter.request_device_sync()
        except (wgpu.GPUError, RuntimeError, OSError) as exc:
            _LOG.info("Cannot open orbital GPU %s: %s", adapter.summary, exc)
            continue
        name = adapter.info["device"] or adapter.info["description"]
        return device, f"{name} ({adapter.info['backend_type']}, {adapter.info['adapter_type']})"
    return None


class OrbitalGpu:
    def __init__(self, device, name):
        import wgpu

        self.device, self.name = device, name
        self.wgpu = wgpu
        shader = device.create_shader_module(code=_SHADER)
        self.pipeline = device.create_render_pipeline(
            layout="auto",
            vertex={"module": shader, "entry_point": "vs", "buffers": [{
                "array_stride": 24,
                "attributes": [{"format": "float32x3", "offset": 0, "shader_location": 0},
                               {"format": "float32x3", "offset": 12, "shader_location": 1}]}]},
            primitive={"topology": "triangle-list", "front_face": "ccw", "cull_mode": "back"},
            depth_stencil={"format": "depth24plus", "depth_write_enabled": True, "depth_compare": "less-equal"},
            multisample={"count": 4},
            fragment={"module": shader, "entry_point": "fs", "targets": [{"format": "rgba8unorm"}]})
        self.molecule_pipeline = device.create_render_pipeline(
            layout="auto",
            vertex={"module": shader, "entry_point": "molecule_vs", "buffers": [{
                "array_stride": 28, "step_mode": "instance",
                "attributes": [{"format": "float32x4", "offset": 0, "shader_location": 0},
                               {"format": "float32x3", "offset": 16, "shader_location": 1}]}]},
            primitive={"topology": "triangle-strip"},
            depth_stencil={"format": "depth24plus", "depth_write_enabled": True, "depth_compare": "less-equal"},
            multisample={"count": 4},
            fragment={"module": shader, "entry_point": "molecule_fs", "targets": [
                {"format": "rgba8unorm", "write_mask": 0}]})
        self.uniform = device.create_buffer(size=112, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        uniform_binding = [{"binding": 0, "resource": {"buffer": self.uniform}}]
        self.bindings = device.create_bind_group(layout=self.pipeline.get_bind_group_layout(0),
                                                 entries=uniform_binding)
        self.molecule_bindings = device.create_bind_group(layout=self.molecule_pipeline.get_bind_group_layout(0),
                                                          entries=uniform_binding)
        self.instances = None
        self.mesh = self.vertex = self.index = None
        self.targets = ()
        self.size = None

    def clear_mesh(self):
        for buffer in (self.vertex, self.index):
            if buffer is not None:
                buffer.destroy()
        self.mesh = self.vertex = self.index = None

    def close(self):
        self.clear_mesh()
        for texture in self.targets:
            texture.destroy()
        self.targets = ()
        self.uniform.destroy()
        if self.instances is not None:
            self.instances.destroy()
            self.instances = None

    def _upload(self, mesh, center):
        import numpy as np

        self.clear_mesh()
        vertices = np.empty((len(mesh.vertices), 6), dtype=np.float32)
        vertices[:, :3] = np.asarray(mesh.vertices) - center
        vertices[:, 3:] = mesh.normals
        phases = phase_indices(mesh)
        self.positive_count = len(phases[1])
        self.negative_count = len(phases[-1])
        phases[1].extend(phases[-1])
        self.vertex = self.device.create_buffer_with_data(data=vertices, usage=self.wgpu.BufferUsage.VERTEX)
        self.index = self.device.create_buffer_with_data(data=phases[1], usage=self.wgpu.BufferUsage.INDEX)
        self.mesh, self.origin = mesh, center

    def _resize(self, size):
        for texture in self.targets:
            texture.destroy()
        usage = self.wgpu.TextureUsage
        self.color = self.device.create_texture(size=size, format="rgba8unorm",
                                                 usage=usage.RENDER_ATTACHMENT | usage.COPY_SRC)
        msaa, depth = (self.device.create_texture(size=size, format=fmt, sample_count=4, usage=usage.RENDER_ATTACHMENT)
                       for fmt in ("rgba8unorm", "depth24plus"))
        self.targets = self.color, msaa, depth
        self.resolved, self.msaa, self.depth = (t.create_view() for t in self.targets)
        self.size = size

    def render(self, mesh, center, radius, axes, scale, ox, oy, width, height, dpr, colors, capsules=()):
        if mesh is not self.mesh:
            self._upload(mesh, center)
        size = (max(1, round(width*dpr)), max(1, round(height*dpr)), 1)
        if self.size != size:
            self._resize(size)
        origin = tuple(a-b for a, b in zip(self.origin, center))
        x, y, z = zip(*axes)
        scene = []
        for row, factor, shift in ((x, 2*scale/width, 2*ox/width-1), (y, 2*scale/height, 1-2*oy/height),
                                   (z, -.48/max(radius, 1e-8), .5)):
            scene.extend(factor*r for r in row)
            scene.append(shift+factor*sum(r*s for r, s in zip(row, origin)))
        scene.extend((-.35*a+.46*b+.81*c) for a, b, c in axes)
        scene.append(0.)
        scene.extend(colors[1])
        scene.extend(colors[-1])
        scene.extend((2/width, -2/height, -.48/(scale*max(radius, 1e-8)), 0.))
        queue = self.device.queue
        queue.write_buffer(self.uniform, 0, struct.pack("<28f", *scene))
        if capsules:
            import numpy as np

            data = np.asarray([(ax, ay, az, r, bx, by, bz) for ax, ay, az, bx, by, bz, r in capsules], dtype='f')
            if self.instances is None or self.instances.size < data.nbytes:
                if self.instances is not None:
                    self.instances.destroy()
                self.instances = self.device.create_buffer(size=data.nbytes, usage=self.wgpu.BufferUsage.VERTEX |
                                                          self.wgpu.BufferUsage.COPY_DST)
            queue.write_buffer(self.instances, 0, data)
        encoder = self.device.create_command_encoder()
        draw = encoder.begin_render_pass(color_attachments=[{
            "view": self.msaa, "resolve_target": self.resolved, "clear_value": (0, 0, 0, 0),
            "load_op": "clear", "store_op": "discard"}], depth_stencil_attachment={
                "view": self.depth, "depth_clear_value": 1., "depth_load_op": "clear", "depth_store_op": "discard"})
        if capsules:
            draw.set_pipeline(self.molecule_pipeline)
            draw.set_bind_group(0, self.molecule_bindings)
            draw.set_vertex_buffer(0, self.instances)
            draw.draw(4, len(capsules))
        draw.set_pipeline(self.pipeline)
        draw.set_bind_group(0, self.bindings)
        draw.set_vertex_buffer(0, self.vertex)
        draw.set_index_buffer(self.index, "uint32")
        draw.draw_indexed(self.positive_count)
        draw.draw_indexed(self.negative_count, 1, self.positive_count, 0, 1)
        draw.end()
        queue.submit([encoder.finish()])
        pitch = size[0]*4
        pixels = queue.read_texture({"texture": self.color}, {"bytes_per_row": pitch}, size)
        return QImage(pixels, size[0], size[1], pitch, QImage.Format.Format_RGBA8888_Premultiplied).copy()


def create_renderer():
    try:
        import wgpu
    except (ImportError, OSError):
        return None
    try:
        result = _device()
        return OrbitalGpu(*result) if result else None
    except (wgpu.GPUError, OSError, RuntimeError, ImportError, ValueError) as exc:
        _LOG.warning("Hardware orbital rendering unavailable: %s", exc)
        return None
