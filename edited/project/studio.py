import bpy, math, random, sys
from mathutils import Vector

out = sys.argv[-1]
random.seed(7)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

def mat(name, color, rough=0.6, emit=None, strength=0.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m

def wood(name, base, dark):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1, 1, 18)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"; w.bands_direction = "Z"
    w.inputs["Scale"].default_value = 2.0
    w.inputs["Distortion"].default_value = 6.0
    w.inputs["Detail"].default_value = 3.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (*dark, 1)
    cr.color_ramp.elements[1].color = (*base, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    nt.links.new(w.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.45
    return m

def box(loc, size, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.object
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(m)
    return o

def cyl(loc, r, d, m, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(location=loc, radius=r, depth=d, vertices=verts)
    o = bpy.context.object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o

def sphere(loc, r, m):
    bpy.ops.mesh.primitive_ico_sphere_add(location=loc, radius=r, subdivisions=3)
    o = bpy.context.object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o

def arealight(loc, rot, size, energy, color, shape="RECTANGLE", sy=None):
    bpy.ops.object.light_add(type="AREA", location=loc, rotation=rot)
    l = bpy.context.object.data
    l.shape = shape; l.size = size; l.size_y = sy or size
    l.energy = energy; l.color = color
    return bpy.context.object

wall = mat("wall", (0.16, 0.15, 0.145), 0.9)
floor = wood("floor", (0.22, 0.13, 0.07), (0.12, 0.07, 0.04))
oak = wood("oak", (0.55, 0.36, 0.2), (0.33, 0.2, 0.1))
dark = mat("dark", (0.03, 0.03, 0.035), 0.4)
shelfm = mat("shelf", (0.08, 0.07, 0.065), 0.5)
leaf = mat("leaf", (0.05, 0.22, 0.06), 0.55)
leaf2 = mat("leaf2", (0.09, 0.3, 0.08), 0.6)
pot = mat("pot", (0.75, 0.72, 0.68), 0.35)
potd = mat("potd", (0.12, 0.12, 0.13), 0.3)
teal = mat("teal", (0, 0, 0), 1, (0.0, 0.75, 0.85), 30)
warm = mat("warm", (0, 0, 0), 1, (1.0, 0.62, 0.3), 20)
shade = mat("shade", (0.9, 0.8, 0.65), 0.8, (1.0, 0.7, 0.4), 6)
brass = mat("brass", (0.8, 0.6, 0.3), 0.3, metal=1.0)
window = mat("window", (0, 0, 0), 1, (0.85, 0.92, 1.0), 9)
books = [mat(f"b{i}", c, 0.7) for i, c in enumerate([
    (0.55, 0.12, 0.08), (0.08, 0.2, 0.35), (0.75, 0.6, 0.35), (0.15, 0.3, 0.2),
    (0.85, 0.83, 0.78), (0.1, 0.1, 0.1), (0.45, 0.35, 0.6), (0.9, 0.5, 0.15)])]

# room
box((0, 3.1, 2.5), (14, 0.2, 5.0), wall)
box((0, 0, -0.05), (14, 12, 0.1), floor)
box((-4.0, 1.0, 2.5), (0.2, 6, 5.0), wall)
box((0, 0, 5.05), (14, 12, 0.1), wall)

# slat wall behind subject with teal cove glow
for i in range(-10, 11):
    box((i * 0.085, 2.95, 2.1), (0.055, 0.06, 4.2), oak)
box((0, 3.0, 2.1), (1.9, 0.02, 4.2), dark)
box((0, 2.9, 4.23), (1.85, 0.03, 0.03), teal)
box((-0.93, 2.98, 2.1), (0.03, 0.03, 4.2), teal)
box((0.93, 2.98, 2.1), (0.03, 0.03, 4.2), teal)

# window on the left with blinds (soft daylight source)
box((-3.88, 1.6, 1.7), (0.02, 1.6, 1.9), window)
for k in range(12):
    box((-3.82, 1.6, 0.85 + k * 0.155), (0.02, 1.62, 0.05), pot, rot=(0, math.radians(30), 0))
arealight((-3.5, 1.6, 1.8), (0, math.radians(-90), 0), 1.6, 700, (0.85, 0.92, 1.0), sy=1.9)

# tall plant back-left
cyl((-1.5, 2.2, 0.3), 0.26, 0.6, potd)
for k in range(160):
    a = random.uniform(0, 2 * math.pi); h = random.uniform(0.6, 3.1); r = random.uniform(0.05, 0.5) * min(1, h / 1.6) * 1.2
    o = sphere((-1.5 + math.cos(a) * r, 2.2 + math.sin(a) * r, h), 0.09, leaf if k % 2 else leaf2)
    o.scale = (0.35, 1.0, 0.25); o.rotation_euler = (random.uniform(-0.6, 0.6), random.uniform(-0.6, 0.6), a)
cyl((-1.5, 2.2, 1.6), 0.02, 2.4, potd)

# floor lamp left of slat wall
cyl((-1.05, 2.6, 0.8), 0.015, 1.6, brass)
cyl((-1.05, 2.6, 0.02), 0.18, 0.04, brass)
cyl((-1.05, 2.6, 1.7), 0.2, 0.3, shade)
bpy.ops.object.light_add(type="POINT", location=(-1.05, 2.6, 1.7))
bpy.context.object.data.energy = 120; bpy.context.object.data.color = (1.0, 0.7, 0.4)
bpy.context.object.data.shadow_soft_size = 0.2

# shelves on the right with books, plants, warm LED underglow
for z in (1.6, 2.2, 2.8, 3.4):
    box((1.75, 2.85, z), (1.3, 0.3, 0.04), shelfm)
    box((1.75, 2.75, z - 0.03), (1.2, 0.02, 0.015), warm)
    x = 1.15
    while x < 1.9:
        w = random.uniform(0.03, 0.07); h = random.uniform(0.2, 0.3)
        box((x, 2.88, z + 0.02 + h / 2), (w, 0.2, h), random.choice(books))
        x += w + 0.005
        if random.random() < 0.08:
            x += 0.15
    cyl((2.2, 2.85, z + 0.09), 0.07, 0.14, pot)
    for k in range(6):
        sphere((2.2 + random.uniform(-0.08, 0.08), 2.85 + random.uniform(-0.05, 0.05), z + 0.2 + random.uniform(0, 0.12)), 0.07, leaf2)

# low cabinet right with lamp
box((1.75, 2.7, 0.3), (1.4, 0.45, 0.6), shelfm)
cyl((1.3, 2.7, 0.75), 0.012, 0.3, brass)
sphere((1.3, 2.7, 0.95), 0.1, warm)
bpy.ops.object.light_add(type="POINT", location=(1.3, 2.6, 0.95))
bpy.context.object.data.energy = 25; bpy.context.object.data.color = (1.0, 0.65, 0.35)

# soft fill + top light
arealight((0, -1.5, 3.2), (math.radians(35), 0, 0), 4, 90, (1.0, 0.95, 0.9))
arealight((0, 1.5, 3.4), (0, 0, 0), 3, 40, (1.0, 0.9, 0.8))

world = bpy.data.worlds.new("w"); sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.02, 0.025, 1)

bpy.ops.object.camera_add(location=(0, -3.8, 1.25), rotation=(math.radians(92), 0, 0))
cam = bpy.context.object; sc.camera = cam
cam.data.lens = 40
cam.data.dof.use_dof = True
cam.data.dof.focus_distance = 1.3
cam.data.dof.aperture_fstop = 1.4

sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = int(sys.argv[-2])
sc.cycles.use_denoising = True
sc.render.resolution_x = 1260; sc.render.resolution_y = 2240
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
