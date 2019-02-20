"""Utilities for projecting objects through the viewport."""

import bpy
import bmesh
import mathutils

import shapely.geometry
import shapely.ops


# TODO: Docstrings.


def _bmesh_to_stencil_shape(to_vp_matrix, mesh):
    return _faceless_bmesh_to_stencil_shape(to_vp_matrix, mesh) if len(mesh.faces) <= 0 \
        else _faced_bmesh_to_stencil_shape(to_vp_matrix, mesh)


def _faced_bmesh_to_stencil_shape(to_vp_matrix, mesh):
    # Convert individual faces into stencil shapes.
    def face_to_stencil_shape(face):
        vert_coords = [_vp_plane_project_pt(to_vp_matrix, vert.co) for vert in face.verts]
        return shapely.geometry.Polygon(vert_coords)
    face_stencil_shapes = [face_to_stencil_shape(face) for face in mesh.faces]

    # Filter out any invalid face shapes. (These can arise e.g. from non-planar faces.)
    face_stencil_shapes = [shape for shape in face_stencil_shapes if shape.is_valid()]

    # Union the face shapes together.
    stencil_shape = shapely.ops.unary_union(face_stencil_shapes)

    return stencil_shape if stencil_shape.is_valid() else None


def _faceless_bmesh_to_stencil_shape(to_vp_matrix, mesh):
    # Try to extract an open or closed path from the mesh by following edges starting from an arbitrary vertex.
    if len(list(mesh.verts)) <= 0:
        return None
    start_vert = mesh.verts[0]
    start_edges = start_vert.link_edges()
    start_edges.index_update()
    if len(start_edges) not in {1, 2}:
        return None
    (looped, pts_before) = _follow_edges(start_vert, start_edges[0])
    pts_after = [] if looped else (_follow_edges(start_vert, start_edges[1])[1] if len(start_edges) > 1 else [])
    if pts_before is None or pts_after is None:
        return None

    # If the path does not include all vertices, the mesh is not path-shaped.
    if len(pts_before) + len(pts_after) + 1 != len(mesh.verts):
        return None

    pts_before.reverse()
    pts = [_vp_plane_project_pt(to_vp_matrix, pt) for pt in pts_before + [start_vert.co] + pts_after]

    # Try to convert the path to a 2D shape in the viewport, closing the path if it is open. This can fail, e.g. due to
    # a self-intersecting path.
    stencil_shape = shapely.geometry.Polygon(pts)

    return stencil_shape if stencil_shape.is_valid() else None

def _follow_edges(start_vert, start_edge):
    pts = []
    prev_vert = start_vert
    curr_vert = start_edge.other_vert(start_vert)
    curr_edges = curr_vert.link_edges
    curr_edges.index_update()
    while len(curr_edges) > 1 and curr_vert != start_vert:
        if len(curr_edges) != 2:
            return False, None
        else:
            pts.append(curr_vert.co)

            other_vert0 = curr_edges[0].other_vert(curr_vert)
            other_vert1 = curr_edges[1].other_vert(curr_vert)
            next_vert = other_vert0 if other_vert0 != prev_vert else other_vert1

            prev_vert = curr_vert
            curr_vert = next_vert
            curr_edges = curr_vert.link_edges

    if curr_vert != start_vert:
        pts.append(curr_vert.co)
        return False, pts
    else:
        return True, pts


def _vp_stencil_shape(to_vp_matrix, obj):
    # TODO: Clean up extra meshes and BMeshes created in this function.

    # Get the object's shape data as a BMesh.
    if obj.type != 'MESH':
        bpy.ops.object.select_all(action='DESELECT')
        obj.select = True
        bpy.context.scene.objects.active = obj
        bpy.ops.object.convert(target='MESH', keep_original=True)
        mesh_obj = bpy.context.scene.objects.active
        if mesh_obj.type != 'MESH':
            # TODO: Probably raise an exception.
            return None
        bmesh_data = bmesh.new()
        bmesh_data.from_mesh(mesh_obj.data)
    else:
        bmesh_data = bmesh.new()
        bmesh_data.from_mesh(obj.data)

    # Convert the BMesh to a stencil shape.
    return _bmesh_to_stencil_shape(to_vp_matrix * obj.matrix_world, bmesh_data)


def _vp_plane_project_pt(to_vp_matrix, pt):
    """Projects a single 3D point into the viewport camera's 2D plane.
    Returns the 2D point as a 2-tuple of numbers.
    Raises ValueError if the point is behind the camera.
    view_perspective_matrix - Perspective matrix of the viewport camera.
    pt - 3D point to project, in world space, as a 3-tuple of numbers.
    """
    projected_pt = to_vp_matrix * mathutils.Vector((pt[0], pt[1], pt[2], 1))
    if projected_pt[2] > 0:
        raise ValueError('Carver object is behind the viewport camera')
    return projected_pt[0], projected_pt[1]


def _vp_plane_project_pt_inv(from_vp_matrix, project_dist, pt):
    # TODO
    return None
