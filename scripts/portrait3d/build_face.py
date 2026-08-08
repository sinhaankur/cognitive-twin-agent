"""
build_face.py — turn a photo + its depth map into a 3D relief USDZ (headless Blender).

Run by portrait.py via:
    Blender --background --python build_face.py -- <photo> <depth.png> <out.usdz>

No geometry is invented: a finely subdivided plane is displaced by the depth map
(brighter = nearer, the convention depth.py writes) and the original photo is
projected onto it as the surface color, with a little emission so the face reads
inside the orb without depending on scene lights. Exports a self-contained USDZ
(textures embedded) that SceneKit loads natively.

Deliberately a *relief*, not a full head — it stays faithful to the single photo
we actually have, and reads beautifully turning a few degrees in the orb.
"""

import sys
from pathlib import Path

import bpy


def _args():
    argv = sys.argv
    if "--" not in argv:
        raise SystemExit("usage: ... -- <photo> <depth.png> <out.usdz>")
    photo, depth, out = argv[argv.index("--") + 1:]
    return Path(photo), Path(depth), Path(out)


def main():
    photo, depth, out = _args()

    # start from a clean, empty scene (background process — user's file untouched)
    bpy.ops.wm.read_factory_settings(use_empty=True)

    img = bpy.data.images.load(str(photo))
    w, h = img.size
    aspect = (w / h) if h else 1.0

    # a plane, subdivided finely so displacement has vertices to move
    bpy.ops.mesh.primitive_plane_add(size=2.0)
    plane = bpy.context.active_object
    plane.name = "Portrait"
    plane.scale = (aspect, 1.0, 1.0)          # match the photo's shape
    bpy.ops.object.transform_apply(scale=True)

    # subdivide: enough resolution for smooth relief, capped for a light mesh
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    for _ in range(7):                         # 2^7 cuts → dense but reasonable
        bpy.ops.mesh.subdivide()
    bpy.ops.object.mode_set(mode="OBJECT")

    # UVs from the flat plane (project view) so photo + depth map line up 1:1
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15)
    bpy.ops.uv.reset()                         # plane → full 0..1 UV square
    bpy.ops.object.mode_set(mode="OBJECT")

    # displacement from the depth map
    depth_img = bpy.data.images.load(str(depth))
    depth_img.colorspace_settings.name = "Non-Color"   # heights, not color
    tex = bpy.data.textures.new("DepthTex", type="IMAGE")
    tex.image = depth_img
    disp = plane.modifiers.new("Relief", type="DISPLACE")
    disp.texture = tex
    disp.texture_coords = "UV"
    disp.strength = 0.35                       # gentle, portrait-like relief
    disp.mid_level = 0.5
    bpy.ops.object.modifier_apply(modifier=disp.name)

    # smooth the relief so it doesn't read faceted
    bpy.ops.object.shade_smooth()

    # material: the photo as color, a touch of emission so it glows in the orb
    mat = bpy.data.materials.new("PortraitMat")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out_node = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    texn = nt.nodes.new("ShaderNodeTexImage")
    texn.image = img
    nt.links.new(texn.outputs["Color"], bsdf.inputs["Base Color"])
    # a little self-emission so the face is legible against the orb's glow
    if "Emission Color" in bsdf.inputs:
        nt.links.new(texn.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.35
    bsdf.inputs["Roughness"].default_value = 0.7
    nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    plane.data.materials.append(mat)

    # export USDZ — textures embedded, native for SceneKit
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    plane.select_set(True)
    bpy.context.view_layer.objects.active = plane
    bpy.ops.wm.usd_export(
        filepath=str(out),
        selected_objects_only=True,
        export_textures=True,
        export_materials=True,
        export_uvmaps=True,
        export_normals=True,
        relative_paths=True,
    )
    print(f"[build_face] wrote {out}")


if __name__ == "__main__":
    main()
