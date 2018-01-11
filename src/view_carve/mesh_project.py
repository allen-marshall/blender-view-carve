import math

import bpy
import mathutils

# TODO: Improve docstrings.

_DIST_SQ_ZERO_THRESHOLD = 0.000000001

def carver_to_carve_obj(context, carver, view_point, view_dir, project_dist):
  try:
    # Get the face points for constructing the carve mesh.
    if isinstance(carver, bpy.types.GPencilStroke):
      face_pts = _gPencil_stroke_to_face_pts(context, carver)
    elif isinstance(carver, bpy.types.Object) and carver.type == 'CURVE':
      face_pts = _curve_obj_to_face_pts(context, carver)
    elif isinstance(carver, bpy.types.Object) and carver.type == 'MESH':
      face_pts = _mesh_obj_to_face_pts(context, carver)
    else:
      raise ValueError('Invalid carver object')
    
    if face_pts is None:
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

def _gPencil_stroke_to_face_pts(context, stroke):
  if len(list(stroke.points)) == 0:
    return None
  
  pts = [mathutils.Vector(point.co) for point in stroke.points]
  
  # If the first and last points are too close together, discard the last point.
  if (pts[-1] - pts[0]).length_squared < _DIST_SQ_ZERO_THRESHOLD:
    pts = pts[:-1]
  
  return pts

def _curve_obj_to_face_pts(context, obj):
  # TODO
  return None

def _mesh_obj_to_face_pts(context, obj):
  # TODO
  pass

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