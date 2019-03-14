"""Functionality for projecting objects through the viewport."""


import collections

import bpy
import bmesh
import mathutils

import ordered_set

from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.collection import GeometryCollection
import shapely.ops

import triangle


def carvers_to_stencil_meshes(vp_proj_matrix, carvers, delete_carvers, union_stencils, context):
    """Projects the specified carver objects through the 3D viewport to get stencil meshes.
    Warning: This function may change the selection state of objects in the scene.
    Returns a list of newly created stencil mesh objects that have been linked to the scene. If union_stencils is true,
    the returned list will contain only one stencil object.
    Raises ValueError if the provided list of carvers contains objects with vertices that are currently behind the
        viewport camera, or if Blender is not currently in Object Mode.
    vp_proj_matrix - The viewport camera's projection matrix (in other words, a transformation matrix from world space
        to the viewport camera's 3D space).
    carvers - List of Blender objects indicating the carver objects to use.
    delete_carvers - Boolean indicating whether the carver objects should be unlinked from the scene.
    union_stencils - Boolean indicating whether to create a single unioned stencil (true), or a separate stencil for
        each carver (false).
    context - The Blender context.
    """
    if context.mode != 'OBJECT':
        raise ValueError('Not in Object Mode')

    # Convert each carver object to a 2D stencil shape.
    stencil_shapes = [_carver_to_stencil_shape(vp_proj_matrix, carver, delete_carvers, context) for carver in carvers]
    stencil_shapes = [shape for shape in stencil_shapes if shape is not None]

    # Union the 2D shapes if we are in union_stencils mode.
    if union_stencils and len(stencil_shapes) > 0:
        stencil_shapes = [shapely.ops.unary_union(stencil_shapes)]

    # Convert each 2D stencil shape to a 3D stencil mesh.
    vp_to_world_matrix = vp_proj_matrix.inverted()
    stencil_mesh_objs = []
    try:
        for shape in stencil_shapes:
            stencil_mesh_objs.append(_stencil_shape_to_stencil_mesh(vp_to_world_matrix, shape, context))
        return stencil_mesh_objs

    except Exception as e:
        # In case of error, try to clean up any partial results owned by Blender.
        for stencil_mesh_obj in stencil_mesh_objs:
            bpy.data.objects.remove(stencil_mesh_obj)

        raise e


def _carver_to_stencil_shape(vp_proj_matrix, carver, delete_carver, context):
    """Projects the specified carver object through the 3D viewport to get a 2D stencil shape.
    Warning: This function may change the selection state of objects in the scene.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived, e.g. if the carver is an empty mesh.
    Raises ValueError if the carver has vertices that are currently behind the viewport camera, or if Blender is not
    currently in Object Mode.
    vp_proj_matrix - The viewport camera's projection matrix (in other words, a transformation matrix from world space
        to the viewport camera's 3D space).
    carver - A Blender object indicating the carver geometry to use.
    delete_carver - Boolean indicating whether the carver object should be unlinked from the scene.
    context - The Blender context.
    """
    if context.mode != 'OBJECT':
        raise ValueError('Not in Object Mode')

    # If the carver is not a mesh object, convert it to a mesh object, deleting the original object if delete_carver is
    # true.
    carver_was_mesh = carver.type == 'MESH'
    if not carver_was_mesh:
        bpy.ops.object.select_all(action='DESELECT')
        carver.select = True
        context.scene.objects.active = carver
        convert_result = bpy.ops.object.convert(target='MESH', keep_original=not delete_carver)
        if convert_result != {'FINISHED'}:
            raise ValueError('Failed to convert carver to mesh')
        carver_mesh_obj = context.scene.objects.active
    else:
        carver_mesh_obj = carver

    try:
        # Convert the mesh to a 2D stencil shape.
        return _carver_mesh_to_stencil_shape(vp_proj_matrix * carver_mesh_obj.matrix_world, carver_mesh_obj.data)

    # Clean up the carver mesh object if appropriate.
    finally:
        if delete_carver or not carver_was_mesh:
            bpy.data.objects.remove(carver_mesh_obj)


def _carver_mesh_to_stencil_shape(to_vp_matrix, carver_mesh):
    """Projects the specified carver mesh through the 3D viewport to get a 2D stencil shape.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived, e.g. if the carver mesh is empty.
    Raises ValueError if the carver has vertices that are currently behind the viewport camera.
    to_vp_matrix - Transformation matrix from the mesh object's local 3D space to the viewport's 3D space.
    carver_mesh - A Blender mesh indicating the carver geometry to use.
    """
    return _faceless_carver_mesh_to_stencil_shape(to_vp_matrix, carver_mesh) if len(carver_mesh.polygons) <= 0 \
        else _faced_carver_mesh_to_stencil_shape(to_vp_matrix, carver_mesh)


def _faced_carver_mesh_to_stencil_shape(to_vp_matrix, carver_mesh):
    """Same as _carver_mesh_to_stencil_shape, but only for meshes that have at least one face."""
    # Convert individual faces into stencil shapes.

    def face_to_stencil_shape(face):
        vert_coords_3d = [carver_mesh.vertices[carver_mesh.loops[loop_idx].vertex_index]
                          for loop_idx in face.loop_indices]
        vert_coords = [_vp_plane_project_pt(to_vp_matrix, vert) for vert in vert_coords_3d]
        return Polygon(vert_coords)

    face_stencil_shapes = [face_to_stencil_shape(face) for face in carver_mesh.polygons]

    # Filter out any invalid 2D face shapes. (These can arise e.g. from non-planar faces.)
    face_stencil_shapes = [shape for shape in face_stencil_shapes if shape.is_valid()]

    if len(face_stencil_shapes) <= 0:
        return None

    # Union the face shapes together.
    stencil_shape = shapely.ops.unary_union(face_stencil_shapes)

    return stencil_shape if stencil_shape.is_valid() else None


def _faceless_carver_mesh_to_stencil_shape(to_vp_matrix, carver_mesh):
    """Same as _carver_mesh_to_stencil_shape, but only for meshes with no faces."""
    # TODO
    return None

# def _faceless_carver_mesh_to_stencil_shape(to_vp_matrix, mesh):
#     # Try to extract an open or closed path from the mesh by following edges starting from an arbitrary vertex.
#     if len(list(mesh.verts)) <= 0:
#         return None
#     start_vert = mesh.verts[0]
#     start_edges = start_vert.link_edges()
#     start_edges.index_update()
#     if len(start_edges) not in {1, 2}:
#         return None
#     (looped, pts_before) = _follow_edges(start_vert, start_edges[0])
#     pts_after = [] if looped else (_follow_edges(start_vert, start_edges[1])[1] if len(start_edges) > 1 else [])
#     if pts_before is None or pts_after is None:
#         return None
#
#     # If the path does not include all vertices, the mesh is not path-shaped.
#     if len(pts_before) + len(pts_after) + 1 != len(mesh.verts):
#         return None
#
#     pts_before.reverse()
#     pts = [_vp_plane_project_pt(to_vp_matrix, pt) for pt in pts_before + [start_vert.co] + pts_after]
#
#     # Try to convert the path to a 2D shape in the viewport, closing the path if it is open. This can fail, e.g. due to
#     # a self-intersecting path.
#     stencil_shape = Polygon(pts)
#
#     return stencil_shape if stencil_shape.is_valid() else None
#
#
# def _follow_edges(start_vert, start_edge):
#     pts = []
#     prev_vert = start_vert
#     curr_vert = start_edge.other_vert(start_vert)
#     curr_edges = curr_vert.link_edges
#     curr_edges.index_update()
#     while len(curr_edges) > 1 and curr_vert != start_vert:
#         if len(curr_edges) != 2:
#             return False, None
#         else:
#             pts.append(curr_vert.co)
#
#             other_vert0 = curr_edges[0].other_vert(curr_vert)
#             other_vert1 = curr_edges[1].other_vert(curr_vert)
#             next_vert = other_vert0 if other_vert0 != prev_vert else other_vert1
#
#             prev_vert = curr_vert
#             curr_vert = next_vert
#             curr_edges = curr_vert.link_edges
#
#     if curr_vert != start_vert:
#         pts.append(curr_vert.co)
#         return False, pts
#     else:
#         return True, pts


def _stencil_shape_to_stencil_mesh(from_vp_matrix, shape, context):
    """Creates a stencil mesh object by projecting the specified 2D shape into 3D space through the viewport camera.
    Returns a newly created stencil mesh object that has been linked to the scene. Returns None if shape is None.
    from_vp_matrix - Transformation matrix from the viewport's 3D space to world space.
    shape - The shape to convert, as returned by _carver_to_stencil_shape.
    context - The Blender context.
    """
    if shape is None:
        return None

    # Triangulate the stencil shape so we don't have to worry about holes in polygons.
    triangulated_shape = _triangulate_stencil_shape(shape)
    vertices_2d = triangulated_shape['vertices'].tolist()
    triangles_2d = triangulated_shape['triangles'].tolist()
    num_vertices_2d = len(vertices_2d)

    # Build the 3D vertices.
    vertices = [_vp_plane_project_pt_inv(from_vp_matrix, pt, True) for pt in vertices_2d] \
        + [_vp_plane_project_pt_inv(from_vp_matrix, pt, False) for pt in vertices_2d]

    # Build the faces for the near-camera and far-from-camera parts of the mesh.
    faces = triangles_2d \
        + [(tri[0] + num_vertices_2d, tri[1] + num_vertices_2d, tri[2] + num_vertices_2d) for tri in triangles_2d]

    # Find the 2D edges, and count the number of (triangular) faces attached to each edge. Edges with only one face are
    # boundary edges of the shape and will require bridge faces in the 3D mesh.
    edge_counts = collections.Counter()
    for tri in triangles_2d:
        edge_0 = {tri[0], tri[1]}
        edge_1 = {tri[1], tri[2]}
        edge_2 = {tri[2], tri[0]}
        edge_counts.update((edge_0, edge_1, edge_2))

    # Build the 3D edges and the faces that bridge the near-camera and far-from-camera parts of the mesh.
    edges = []
    for edge_set, count in edge_counts.items():
        edge = tuple(edge_set)
        edges.append(edge)
        if count > 1:
            faces.append((edge[0], edge[1], edge[1] + num_vertices_2d, edge[0] + num_vertices_2d))

    # Build a Blender mesh object from the computed geometry data, freeing the Python data as early as possible.

    mesh = bpy.data.meshes.new('viewCarveTemp_stencilMesh')
    mesh_obj = None
    try:
        mesh.from_pydata(vertices, edges, faces)
        mesh.calc_normals_split()
        mesh.update()
        if not mesh.validate():
            raise ValueError('Somehow created invalid mesh; cannot continue')

        mesh_obj = bpy.data.objects.new('viewCarveTemp_stencilMeshObj', mesh)
        context.scene.objects.link(mesh_obj)
        return mesh_obj

    except Exception as e:
        # In case of error, try to clean up any partial results owned by Blender.
        if mesh_obj is not None:
            bpy.data.objects.remove(mesh_obj)
        bpy.data.meshes.remove(mesh)

        raise e


def _triangulate_stencil_shape(shape):
    """Converts a 2D stencil shape as returned by _carver_to_stencil_shape into a triangulated form.
    Intended for use in constructing stencil meshes from 2D stencil shapes.
    Returns the triangulated shape in the format used by the triangle library. Returns None if shape is None.
    shape - The 2D stencil shape to convert.
    """
    if shape is None:
        return None

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
