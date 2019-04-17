"""Functionality for projecting objects through the viewport."""


import collections

import bpy
import bmesh
import mathutils

import ordered_set

from shapely.geometry import LineString, LinearRing, Polygon, MultiPolygon
from shapely.geometry.collection import GeometryCollection
import shapely.ops

import triangle


def carvers_to_stencil_meshes(vp_view_matrix, is_orthographic, far_dist, carvers, delete_carvers, union_stencils,
                              context):
    """Projects the specified carver objects through the 3D viewport to get stencil meshes.
    Warning: This function may change the selection state of objects in the scene.
    Returns a list of newly created stencil mesh objects that have been linked to the scene. If union_stencils is true,
    the returned list will contain only one stencil object.
    Raises ValueError if the provided list of carvers contains objects with vertices that are currently behind the
        viewport camera, or if Blender is not currently in Object Mode.
    vp_view_matrix - The viewport camera's view matrix (in other words, a transformation matrix from world space
        to the viewport camera's 3D space).
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    far_dist - Minimum distance from the camera that the 'far' part of the stencil mesh needs to have.
    carvers - List of Blender objects indicating the carver objects to use.
    delete_carvers - Boolean indicating whether the carver objects should be unlinked from the scene.
    union_stencils - Boolean indicating whether to create a single unioned stencil (true), or a separate stencil for
        each carver (false).
    context - The Blender context.
    """
    if context.mode != 'OBJECT':
        raise ValueError('Not in Object Mode')

    # Convert each carver object to a 2D stencil shape.
    stencil_shapes = [_carver_to_stencil_shape(vp_view_matrix, is_orthographic, carver, delete_carvers, context)
                      for carver in carvers]
    stencil_shapes = [shape for shape in stencil_shapes if shape is not None]

    # Union the 2D shapes if we are in union_stencils mode.
    if union_stencils and len(stencil_shapes) > 0:
        stencil_shapes = [shapely.ops.unary_union(stencil_shapes)]

    # Convert each 2D stencil shape to a 3D stencil mesh.
    vp_to_world_matrix = vp_view_matrix.inverted()
    stencil_mesh_objs = []
    try:
        for shape in stencil_shapes:
            stencil_mesh_obj = _stencil_shape_to_stencil_mesh(vp_to_world_matrix, is_orthographic, far_dist, shape,
                                                              context)
            if stencil_mesh_obj is not None:
                stencil_mesh_objs.append(stencil_mesh_obj)
        return stencil_mesh_objs

    except Exception as e:
        # In case of error, try to clean up any partial results owned by Blender.
        for stencil_mesh_obj in stencil_mesh_objs:
            bpy.data.objects.remove(stencil_mesh_obj)

        raise e


def _carver_to_stencil_shape(vp_view_matrix, is_orthographic, carver, delete_carver, context):
    """Projects the specified carver object through the 3D viewport to get a 2D stencil shape.
    Warning: This function may change the selection state of objects in the scene.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived, e.g. if the carver is an empty mesh.
    Raises ValueError if the carver has vertices that are currently behind the viewport camera, or if Blender is not
    currently in Object Mode.
    vp_view_matrix - The viewport camera's view matrix (in other words, a transformation matrix from world space
        to the viewport camera's 3D space).
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    carver - A Blender object indicating the carver geometry to use.
    delete_carver - Boolean indicating whether the carver object should be unlinked from the scene.
    context - The Blender context.
    """
    if context.mode != 'OBJECT':
        raise ValueError('Not in Object Mode')

    # Special case for grease pencil carvers.
    if carver.type == 'GPENCIL':
        try:
            return _carver_gpencil_obj_to_stencil_shape(vp_view_matrix @ carver.matrix_world, is_orthographic, carver)
        finally:
            if delete_carver:
                bpy.data.objects.remove(carver)

    # Handle other types of carvers.
    else:
        # If the carver is not a mesh object, convert it to a mesh object, deleting the original object if delete_carver
        # is true.
        carver_was_mesh = carver.type == 'MESH'
        if not carver_was_mesh:
            bpy.ops.object.select_all(action='DESELECT')
            carver.select_set(True)
            context.view_layer.objects.active = carver
            convert_result = bpy.ops.object.convert(target='MESH', keep_original=not delete_carver)
            if convert_result != {'FINISHED'}:
                raise ValueError('Failed to convert carver to mesh')
            carver_mesh_obj = context.view_layer.objects.active
        else:
            carver_mesh_obj = carver

        try:
            # Convert the mesh to a 2D stencil shape.
            return _carver_mesh_to_stencil_shape(vp_view_matrix @ carver_mesh_obj.matrix_world, is_orthographic,
                                                 carver_mesh_obj.data)

        finally:
            if delete_carver or not carver_was_mesh:
                bpy.data.objects.remove(carver_mesh_obj)


def _carver_mesh_to_stencil_shape(to_cam_matrix, is_orthographic, carver_mesh):
    """Projects the specified carver mesh through the 3D viewport to get a 2D stencil shape.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived, e.g. if the carver mesh is empty.
    Raises ValueError if the carver has vertices that are currently behind the viewport camera.
    to_cam_matrix - Transformation matrix from the mesh object's local 3D space to the camera's 3D space.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    carver_mesh - A Blender mesh indicating the carver geometry to use.
    """
    return _faceless_carver_mesh_to_stencil_shape(to_cam_matrix, is_orthographic, carver_mesh) \
        if len(carver_mesh.polygons) <= 0 \
        else _faced_carver_mesh_to_stencil_shape(to_cam_matrix, is_orthographic, carver_mesh)


def _faced_carver_mesh_to_stencil_shape(to_cam_matrix, is_orthographic, carver_mesh):
    """Same as _carver_mesh_to_stencil_shape, but only for meshes that have at least one face."""
    # Convert individual faces into stencil shapes.

    def face_to_stencil_shape(face):
        vert_coords_3d = [carver_mesh.vertices[carver_mesh.loops[loop_idx].vertex_index].co
                          for loop_idx in face.loop_indices]
        vert_coords = [_vp_plane_project_pt(to_cam_matrix, is_orthographic, vert) for vert in vert_coords_3d]
        return Polygon(vert_coords)

    face_stencil_shapes = [face_to_stencil_shape(face) for face in carver_mesh.polygons]

    # Filter out any invalid 2D face shapes. (These can arise e.g. from non-planar faces.)
    face_stencil_shapes = [shape for shape in face_stencil_shapes if shape.is_valid]

    if len(face_stencil_shapes) <= 0:
        return None

    # Union the face shapes together.
    stencil_shape = shapely.ops.unary_union(face_stencil_shapes)

    return stencil_shape if stencil_shape.is_valid else None


def _faceless_carver_mesh_to_stencil_shape(to_cam_matrix, is_orthographic, carver_mesh):
    """Same as _carver_mesh_to_stencil_shape, but only for meshes with no faces."""
    # Extract zero or more path shapes from the mesh by following edges. Paths may be open or closed.

    carver_bmesh = bmesh.new()
    carver_bmesh.from_mesh(carver_mesh)

    if len(list(carver_bmesh.verts)) <= 0:
        return None

    vert_paths = []
    start_verts_to_ignore = set()
    for start_vert in carver_bmesh.verts:
        start_edges = start_vert.link_edges
        start_edges.index_update()
        if len(start_edges) in {1, 2} and start_vert not in start_verts_to_ignore:
            vert_path = [start_vert]
            path_finished = False
            curr_vert = start_vert
            curr_edge = start_edges[0]
            while not path_finished:
                next_vert = curr_edge.other_vert(curr_vert)
                next_edges = next_vert.link_edges
                next_edges.index_update()
                vert_path.append(next_vert)
                if next_vert == start_vert or len(next_edges) != 2:
                    path_finished = True
                else:
                    curr_edge = next_edges[0] if next_edges[0].other_vert(next_vert) != curr_vert else next_edges[1]
                    curr_vert = next_vert
            vert_paths.append(vert_path)
            start_verts_to_ignore.update(vert_path)

    # Generate the 2D shape.

    paths = [[vert.co for vert in vert_path] for vert_path in vert_paths]

    del vert_paths
    del start_verts_to_ignore
    carver_bmesh.free()

    return _paths_to_stencil_shape(to_cam_matrix, is_orthographic, paths)


def _carver_gpencil_obj_to_stencil_shape(to_cam_matrix, is_orthographic, carver_gpencil):
    """Projects the specified carver grease pencil object through the 3D viewport to get a 2D stencil shape.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived.
    Raises ValueError if the carver object's strokes have vertices that are behind the viewport camera.
    to_cam_matrix - Transformation matrix from the grease pencil object's local 3D space to the camera's 3D space.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    carver_gpencil - A Blender grease pencil object indicating the carver geometry to use.
    """
    # Extract a path from each stroke in the grease pencil object.
    paths = []
    for layer in carver_gpencil.data.layers:
        for stroke in layer.active_frame.strokes:
            path = [pt.co for pt in stroke.points]
            if stroke.draw_cyclic and len(path) > 1 and path[0] != path[-1]:
                path.append(path[0])
            paths.append(path)

    # Generate the 2D shape.
    return _paths_to_stencil_shape(to_cam_matrix, is_orthographic, paths)


def _paths_to_stencil_shape(to_cam_matrix, is_orthographic, paths):
    """Projects the specified 3D paths through the viewport to get a stencil shape.
    Returns the 2D stencil shape as a Shapely shape consisting of one or more polygons. Returns None if no polygons
    could be derived.
    Raises ValueError if the paths have vertices that are behind the viewport camera.
    to_cam_matrix - Transformation matrix from the paths' local 3D space to the camera's 3D space.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    paths - list of lists of 3-tuples indicating the path points in 3D space.
    """
    # Project paths into the viewport camera's 2D space.
    paths_2d = [[_vp_plane_project_pt(to_cam_matrix, is_orthographic, pt) for pt in path] for path in paths]

    # Convert the 2D paths to Shapely polygons.
    def path_to_shape(path):
        linear_ring = LinearRing(path)
        if linear_ring.is_valid:
            return MultiPolygon(shapely.ops.polygonize([linear_ring]))
        else:
            line_string = LineString(path)
            if line_string.is_simple and path[0] != path[-1]:
                line_string = LineString(path + [path[0]])
            # For self-intersecting paths, we want to create a polygon for each region enclosed by the path. The code
            # here uses a bit of a hack to achieve this.
            return MultiPolygon(shapely.ops.polygonize([shapely.ops.unary_union([line_string])]))
    shape = shapely.ops.unary_union([path_to_shape(path) for path in paths_2d])

    return shape if shape.is_valid and not shape.is_empty else None


def _stencil_shape_to_stencil_mesh(from_cam_matrix, is_orthographic, far_dist, shape, context):
    """Creates a stencil mesh object by projecting the specified 2D shape into 3D space through the viewport camera.
    Warning: This function may change the selection state of objects in the scene.
    Returns a newly created stencil mesh object that has been linked to the scene. Returns None if shape is None or
    cannot be converted to a stencil mesh.
    from_cam_matrix - Transformation matrix from the viewport camera's 3D space to world space.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    far_dist - Minimum distance from the camera that the 'far' part of the stencil mesh needs to have.
    shape - The shape to convert, as returned by _carver_to_stencil_shape.
    context - The Blender context.
    """
    if shape is None:
        return None

    # Triangulate the stencil shape so we don't have to worry about holes in polygons.
    triangulated_shape = _triangulate_stencil_shape(shape)
    if triangulated_shape is None:
        return None
    vertices_2d = triangulated_shape['vertices'].tolist()
    triangles_2d = triangulated_shape['triangles'].tolist()
    num_vertices_2d = len(vertices_2d)

    # Build the 3D vertices.
    vertices = [_vp_plane_project_pt_inv(from_cam_matrix, is_orthographic, far_dist, pt, False) for pt in vertices_2d]
    if is_orthographic:
        vertices += [_vp_plane_project_pt_inv(from_cam_matrix, is_orthographic, far_dist, pt, True)
                     for pt in vertices_2d]
    else:
        vertices.append(_vp_plane_project_pt_inv(from_cam_matrix, is_orthographic, far_dist, (0, 0), True))

    # Build the faces for the near-camera and far-from-camera parts of the mesh.
    faces = triangles_2d.copy()
    if is_orthographic:
        faces += [(tri[0] + num_vertices_2d, tri[1] + num_vertices_2d, tri[2] + num_vertices_2d)
                  for tri in triangles_2d]

    # Find the 2D edges, and count the number of (triangular) faces attached to each edge. Edges with only one face are
    # boundary edges of the shape and will require bridge faces in the 3D mesh.
    edge_counts = collections.Counter()
    for tri in triangles_2d:
        edge_0 = frozenset((tri[0], tri[1]))
        edge_1 = frozenset((tri[1], tri[2]))
        edge_2 = frozenset((tri[2], tri[0]))
        edge_counts.update((edge_0, edge_1, edge_2))

    # Build the 3D edges and the faces that bridge the near-camera and far-from-camera parts of the mesh.
    edges = []
    for edge_set, count in edge_counts.items():
        edge = tuple(edge_set)
        edges.append(edge)
        if is_orthographic:
            edges.append((edge[0] + num_vertices_2d, edge[1] + num_vertices_2d))
            if count == 1:
                faces.append((edge[0], edge[1], edge[1] + num_vertices_2d, edge[0] + num_vertices_2d))
        elif count == 1:
            faces.append((edge[0], edge[1], num_vertices_2d))

    # Build a Blender mesh object from the computed geometry data, freeing the Python data as early as possible.

    mesh = bpy.data.meshes.new('viewCarveTemp_stencilMesh')
    mesh_obj = None
    try:
        mesh.from_pydata(vertices, edges, faces)
        mesh.update()
        if not mesh.validate():
            raise ValueError('Somehow created invalid mesh; cannot continue')

        mesh_obj = bpy.data.objects.new('viewCarveTemp_stencilMeshObj', mesh)
        context.scene.collection.objects.link(mesh_obj)

        # Set consistent normals for the mesh.
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent()
        bpy.ops.object.mode_set(mode='OBJECT')

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
    Returns the triangulated shape in the format used by the triangle library, or None if the shape cannot be
    triangulated.
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
                hole_pt = interior_polygon.representative_point()
                hole_pts.add((hole_pt.x, hole_pt.y))

    if len(vertices) <= 0 or len(segments) <= 0:
        return None

    shape_for_triangle_lib = {
        'vertices': [list(vert) for vert in vertices],
        'segments': [list(seg) for seg in segments]
    }
    if len(hole_pts) > 0:
        shape_for_triangle_lib['holes'] = [list(hole) for hole in hole_pts]

    # Perform the triangulation.
    return triangle.triangulate(shape_for_triangle_lib, 'p')


def _vp_plane_project_pt(to_cam_matrix, is_orthographic, pt):
    """Projects a single 3D point into the viewport camera's 2D plane.
    Returns the 2D point as a 2-tuple of numbers.
    Raises ValueError if the point is behind the camera.
    to_cam_matrix - Transformation matrix from the input point's 3D space to the 3D space relative to the camera.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    pt - 3D input point to project, as a 3-tuple of numbers.
    """
    projected_pt = to_cam_matrix @ mathutils.Vector((pt[0], pt[1], pt[2], 1))
    if is_orthographic:
        return projected_pt[0], projected_pt[1]
    else:
        if projected_pt[2] >= 0:
            raise ValueError('Carver object is behind the viewport camera')
        return projected_pt[0] / -projected_pt[2], projected_pt[1] / -projected_pt[2]


def _vp_plane_project_pt_inv(from_cam_matrix, is_orthographic, far_dist, pt, close_to_cam):
    """Projects a point in the viewport camera's 2D plane into 3D space, using a depth that is either 'close to' or 'far
    from' the viewport camera.
    Returns the 3D point as a 3-tuple of numbers.
    from_cam_matrix - Transformation matrix from the viewport camera's 3D space to the output point's 3D space. If the
        desired output space is world space, this matrix should be the inverse of the viewport camera's view matrix.
    is_orthographic - Boolean indicating whether the viewport camera is orthographic (true) or perspective (false).
    far_dist - Lower bound on the distance of the result from the camera if close_to_cam is false. The resulting point
        will be in a plane perpendicular to the camera's facing direction, with the plane's distance from the camera
        equal to this distance.
    pt - 2D input point in the viewport plane, as a 2-tuple of numbers.
    close_to_cam - Boolean indicating whether the output point should be close to the viewport camera (true) or far from
        the viewport camera (false).
    """
    if is_orthographic:
        view_space_output = mathutils.Vector((pt[0], pt[1], far_dist if close_to_cam else -far_dist, 1))
    elif close_to_cam:
        view_space_output = mathutils.Vector((0, 0, 0, 1))
    else:
        view_space_output = mathutils.Vector((pt[0] * far_dist, pt[1] * far_dist, -far_dist, 1))

    output_vec = from_cam_matrix @ view_space_output
    return output_vec[0], output_vec[1], output_vec[2]
