"""Utilities for projecting objects through the viewport."""


import bpy
import bmesh
import mathutils

import ordered_set

from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.collection import GeometryCollection
import shapely.ops

import triangle


# TODO: Docstrings.


def objs_to_stencil_meshes(to_vp_matrix, objs, union_objs):
    # TODO
    pass


def _obj_to_stencil_shape(to_vp_matrix, obj):
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


def _stencil_shape_to_bmesh(from_vp_matrix, shape):
    # Triangulate the stencil shape.
    triangulated_shape = _triangulate_stencil_shape(shape)

    vertices_2d = triangulated_shape['vertices'].tolist()
    triangles_2d = triangulated_shape['triangles'].tolist()

    # Build the 3D vertices.
    vertices = [_vp_plane_project_pt_inv(from_vp_matrix, pt, True) for pt in vertices_2d] \
        + [_vp_plane_project_pt_inv(from_vp_matrix, pt, False) for pt in vertices_2d]

    # TODO: Build the 3D edges and faces, then build the BMesh.

def _triangulate_stencil_shape(shape):
    # Convert the stencil shape to the format required by the triangle library.

    vertices = ordered_set.OrderedSet()
    segments = ordered_set.OrderedSet()
    hole_pts = ordered_set.OrderedSet()

    def add_segments(coords_list):
        for idx in range(len(coords_list) - 1):
            segments.add((vertices.index(coords_list[idx]), vertices.index(coords_list[idx + 1])))

    if not isinstance(shape, (GeometryCollection, MultiPolygon)):
        shape = GeometryCollection([shape])
    for geom in shape:
        if isinstance(geom, Polygon):
            # Add vertices.
            for point in geom.exterior.coords:
                vertices.add(point)
            for interior in geom.interiors:
                for point in interior.coords:
                    vertices.add(point)

            # Add segments.
            add_segments(geom.exterior.coords)
            for interior in geom.interiors:
                add_segments(interior.coords)

            # Add holes.
            for interior in geom.interiors:
                interior_polygon = Polygon(interior.coords)
                hole_pts.add(interior_polygon.representative_point())

    shape_for_triangle_lib = {
        'vertices': vertices,
        'segments': segments,
        'holes': hole_pts
    }

    # Perform the triangulation.
    return triangle.triangulate(shape_for_triangle_lib, 'p')


def _bmesh_to_stencil_shape(to_vp_matrix, mesh):
    return _faceless_bmesh_to_stencil_shape(to_vp_matrix, mesh) if len(mesh.faces) <= 0 \
        else _faced_bmesh_to_stencil_shape(to_vp_matrix, mesh)


def _faced_bmesh_to_stencil_shape(to_vp_matrix, mesh):
    # Convert individual faces into stencil shapes.
    def face_to_stencil_shape(face):
        vert_coords = [_vp_plane_project_pt(to_vp_matrix, vert.co) for vert in face.verts]
        return Polygon(vert_coords)
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
    stencil_shape = Polygon(pts)

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


def _vp_plane_project_pt(to_vp_matrix, pt):
    """Projects a single 3D point into the viewport camera's 2D plane.
    Returns the 2D point as a 2-tuple of numbers.
    Raises ValueError if the point is behind the camera.
    to_vp_matrix - Transformation matrix from the input point's 3D space to the viewport's 3D space. This matrix is
        typically constructed by multiplying the viewport camera's perspective matrix by the local-to-world matrix of
        the object from which the input point was derived.
    pt - 3D input point to project, as a 3-tuple of numbers.
    """
    projected_pt = to_vp_matrix * mathutils.Vector((pt[0], pt[1], pt[2], 1))
    if projected_pt[2] > 0:
        raise ValueError('Carver object is behind the viewport camera')
    return projected_pt[0], projected_pt[1]


def _vp_plane_project_pt_inv(from_vp_matrix, pt, close_to_cam):
    """Projects a point in the viewport camera's 2D plane into 3D space, using a depth that is either 'close to' or 'far
    from' the viewport camera.
    Returns the 3D point as a 3-tuple of numbers.
    from_vp_matrix - Transformation matrix from the viewport's 3D space to the output point's 3D space. If the desired
        output space is world space, this matrix should be the inverse of the viewport camera's perspective matrix.
    pt - 2D input point in the viewport plane, as a 2-tuple of numbers.
    close_to_cam - Boolean indicating whether the output point should be close to the viewport camera (true) or far from
        the viewport camera (false).
    """
    vp_coord_z = 0 if close_to_cam else -1
    output_vec = from_vp_matrix * mathutils.Vector((pt[0], pt[1], vp_coord_z, 1))
    return output_vec[0], output_vec[1], output_vec[2]
