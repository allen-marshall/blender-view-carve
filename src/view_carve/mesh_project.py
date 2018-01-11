import math

import bpy
import bmesh
import mathutils

# TODO: Improve docstrings.

_DIST_SQ_ZERO_THRESHOLD = 0.000000001

def carver_to_carve_obj(context, carver, view_point, view_dir, project_dist, convex_hull_solid=True,
  convex_hull_curve=False):
  try:
    # Get the face points for constructing the carve mesh.
    if isinstance(carver, bpy.types.GPencilStroke):
      face_pts = _gPencil_stroke_to_face_pts(context, carver, convex_hull_curve)
    elif isinstance(carver, bpy.types.Object) and carver.type == 'CURVE':
      face_pts = _curve_obj_to_face_pts(context, carver, convex_hull_curve)
    elif isinstance(carver, bpy.types.Object) and carver.type == 'MESH':
      face_pts = _mesh_obj_to_face_pts(context, carver, convex_hull_solid, convex_hull_curve)
    else:
      raise ValueError('Invalid carver object')
    
    if face_pts is None or len(face_pts) == 0:
      return None
    
    # Create the carve mesh.
    if context.region_data.is_perspective:
      carve_mesh = _face_pts_to_carve_mesh_perspective(face_pts, view_point, view_dir, project_dist)
    else:
      carve_mesh = _face_pts_to_carve_mesh_orthographic(face_pts, view_point, view_dir, project_dist)
    
    carve_obj = bpy.data.objects.new('viewCarveTemp_carveObj', carve_mesh)
    context.scene.objects.link(carve_obj)
    return carve_obj
  
  except Exception as e:
    # Try to clean up.
    if 'carve_mesh' in locals():
      bpy.data.meshes.remove(carve_mesh)
    
    raise e

def _gPencil_stroke_to_face_pts(context, stroke, convex_hull_curve):
  if convex_hull_curve:
    return _convex_hull_face_pts(context, stroke.points)
  
  if len(list(stroke.points)) == 0:
    return None
  
  pts = [mathutils.Vector(point.co) for point in stroke.points]
  
  # If the first and last points are too close together, discard the last point.
  if (pts[-1] - pts[0]).length_squared < _DIST_SQ_ZERO_THRESHOLD:
    pts = pts[:-1]
  
  return pts

def _curve_obj_to_face_pts(context, obj, convex_hull_curve):
  try:
    # Convert into a path-shaped mesh.
    bpy.ops.object.select_all(action='DESELECT')
    obj.select = True
    context.scene.objects.active = obj
    bpy.ops.object.convert(target='MESH', keep_original=True)
    mesh_obj = context.scene.objects.active
    
    if convex_hull_curve:
      return _convex_hull_face_pts(context, mesh_obj.data.vertices)
    else:
      return _path_mesh_obj_to_face_pts(context, mesh_obj, convex_hull_curve)
  finally:
    # Clean up.
    if 'mesh_obj' in locals():
      bpy.data.meshes.remove(mesh_obj.data)
      bpy.data.objects.remove(mesh_obj)
      

def _mesh_obj_to_face_pts(context, obj, convex_hull_solid, convex_hull_curve):
  if len(list(obj.data.vertices)) == 0:
    return None
  
  # First try to treat the mesh as path-shaped.
  path_face_pts = _path_mesh_obj_to_face_pts(context, obj, convex_hull_curve)
  if path_face_pts is not None:
    return path_face_pts
  
  # If that fails (the mesh wasn't path-shaped), try to treat the mesh as solid.
  if convex_hull_solid:
    return _convex_hull_face_pts(context, obj.data.vertices)
  else:
    
    try:
      mesh_copy = obj.data.copy()
      mesh_copy.transform(context.region_data.view_matrix)
      mesh_copy.update()
      
      temp_obj = bpy.data.objects.new('viewCarveTemp_manipMeshObj', mesh_copy)
      context.scene.objects.link(temp_obj)
      
      old_mode = context.scene.objects.active.mode
      
      context.scene.objects.active = temp_obj
      bpy.ops.object.mode_set(mode='EDIT')
      bpy.ops.mesh.select_all(action='SELECT')
      bpy.ops.transform.resize(value=(1, 1, 0))
      
      bpy.ops.mesh.remove_doubles()
      bpy.ops.mesh.dissolve_degenerate()
      bpy.ops.mesh.dissolve_limited()
      
      mesh_copy.transform(context.region_data.view_matrix.inverted())
      mesh_copy.update()
      
      return _path_mesh_obj_to_face_pts(context, temp_obj, False)
      
    finally:
      # Clean up.
      if 'old_mode' in locals():
        bpy.ops.object.mode_set(mode=old_mode)
      if 'mesh_copy' in locals():
        bpy.data.meshes.remove(mesh_copy)
      if 'temp_obj' in locals():
        bpy.data.objects.remove(temp_obj)

def _path_mesh_obj_to_face_pts(context, obj, convex_hull_curve):
  try:
    if convex_hull_curve:
      return _convex_hull_face_pts(context, obj.data.vertices)
    
    if len(list(obj.data.vertices)) == 0:
      return None
    
    # Try to extract a path from the mesh by following edges starting from an arbitrary vertex.
    
    visited_vertices = {}
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    start_vert = bm.verts[0]
    start_pt = start_vert.co
    start_edges = start_vert.link_edges
    start_edges.index_update()
    if len(start_edges) not in {1, 2}:
      return None
    
    pts_before = _follow_edges(bm, start_vert, start_edges[0])
    pts_after = _follow_edges(bm, start_vert, start_edges[1]) if len(start_edges) > 1 else []
    
    if pts_before is None or pts_after is None:
      return None
    
    # If the path does not include all vertices, the mesh is not path-shaped.
    if len(pts_before) + len(pts_after) + 1 != len(list(obj.data.vertices)):
      return None
    
    pts_before.reverse()
    return pts_before + [start_pt] + pts_after
  
  finally:
    # Clean up.
    if 'bm' in locals():
      bm.free()

def _follow_edges(bm, start_vert, start_edge):
  pts = []
  prev_vert = start_vert
  curr_vert = start_edge.other_vert(start_vert)
  curr_edges = curr_vert.link_edges
  curr_edges.index_update()
  while len(curr_edges) > 1 and curr_vert != start_vert:
    if len(curr_edges) != 2:
      return None
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
  
  return pts

def _convex_hull_face_pts(context, verts):
  if len(list(verts)) == 0:
    return None
  
  # Compute convex hull in the view plane.
  plane_pts = [(context.region_data.view_matrix * mathutils.Vector(vert.co[0:2] + (1,))).to_2d() for vert in verts]
  hull_idxs = mathutils.geometry.convex_hull_2d(plane_pts)
  return [mathutils.Vector(verts[idx].co) for idx in hull_idxs]

def _face_pts_to_carve_mesh_perspective(face_pts, view_point, view_dir, project_dist):
  # Project the points to be the specified distance from the view point.
  def convert(point):
    displacement = point - view_point
    if displacement.dot(view_dir) < 0:
      raise ValueError('Carver behind camera')
    dist_sq = displacement.length_squared
    if dist_sq < _DIST_SQ_ZERO_THRESHOLD:
      raise ValueError('Carver too close to camera; cannot project')
    return view_point + displacement * project_dist / math.sqrt(dist_sq)
  projected_pts = [convert(point) for point in face_pts]
  
  # Build the mesh.
  vertices = projected_pts + [view_point]
  num_verts_in_face = len(projected_pts)
  edges = []
  faces = [tuple(range(num_verts_in_face))]
  for idx in range(num_verts_in_face):
    next_idx = (idx + 1) if (idx < num_verts_in_face - 1) else 0
    edges += [(idx, next_idx), (idx, num_verts_in_face)]
    faces += [(idx, next_idx, num_verts_in_face)]
  return _carve_mesh_from_pydata(vertices, edges, faces)

def _face_pts_to_carve_mesh_orthographic(face_pts, view_point, view_dir, project_dist):
  # Project the points into the view plane.
  pts_in_view_plane = [point - view_dir * mathutils.geometry.distance_point_to_plane(point, view_point, view_dir) for point in face_pts]
  
  # Get faces in front of and behind the view position.
  front_pts = [point + view_dir * project_dist for point in pts_in_view_plane]
  back_pts = [point - view_dir * project_dist for point in pts_in_view_plane]
  
  # Build the mesh.
  vertices = front_pts + back_pts
  num_verts_in_face = len(front_pts)
  front_face = tuple(range(num_verts_in_face))
  back_face = tuple([idx + num_verts_in_face for idx in range(num_verts_in_face)])
  edges = []
  faces = [front_face, back_face]
  for idx in range(num_verts_in_face):
    next_idx = (idx + 1) if (idx < num_verts_in_face - 1) else 0
    edges += [(idx, next_idx), (next_idx, next_idx + num_verts_in_face),
      (next_idx + num_verts_in_face, idx + num_verts_in_face), (idx + num_verts_in_face, idx)]
    faces += [(idx, next_idx, next_idx + num_verts_in_face, idx + num_verts_in_face)]
  return _carve_mesh_from_pydata(vertices, edges, faces)

def _carve_mesh_from_pydata(vertices, edges, faces):
  try:
    mesh = bpy.data.meshes.new('viewCarveTemp_carveMesh')
    mesh.from_pydata(vertices, edges, faces)
    mesh.calc_normals_split()
    mesh.update()
    if not mesh.validate():
      raise ValueError('Somehow created invalid mesh; cannot continue')
    
    return mesh
  
  except Exception as e:
    # Try to clean up.
    if 'mesh' in locals():
      bpy.data.meshes.remove(mesh)
    raise e