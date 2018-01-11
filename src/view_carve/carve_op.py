import math

import bpy
import mathutils

from . import find, mesh_project, util_mesh

# TODO: Improve docstrings.

_BOOLEAN_OP_THRESHOLD = 0.000001
_PROJECT_DIST_PADDING = 0.1

class CarveOp(bpy.types.Operator):
  bl_label = 'Viewport Carve'
  bl_idname = 'view_carve.carve'
  bl_description = 'Separate a mesh object based on other objects projected through the current view'
  bl_options = {'REGISTER', 'UNDO'}
  
  prop_subtract_only = bpy.props.BoolProperty(name='Subtract Only',
    description='Subtract geometry instead of splitting into multiple objects', default=False)
  prop_use_gPencil = bpy.props.BoolProperty(name='Use GPencil',
    description='Use strokes from the active grease pencil frame for carving', default=True)
  prop_use_selection = bpy.props.BoolProperty(name='Use Selected Objects',
    description='Use selected objects (other than the active object) for carving', default=True)
  prop_union_carves = bpy.props.BoolProperty(name='Union Carves',
    description='Make a single carve using the union of the carver objects/strokes.', default=False)
  prop_delete_carvers = bpy.props.BoolProperty(name='Delete Carve Objects',
    description='Delete objects and/or grease pencil strokes used for carving', default=False)
  prop_convex_hull_curve = bpy.props.BoolProperty(name='Convex Hull (Curves)',
    description='Use convex hull of curves and grease pencil strokes instead of closing them. Reduces the risk of bad geometry in the result.',
    default=False)
  prop_convex_hull_mesh = bpy.props.BoolProperty(name='Convex Hull (Meshes)',
    description='Use convex hull of non-curve-shaped meshes. Reduces the risk of bad geometry in the result.',
    default=True)
  prop_boolean_solver = bpy.props.EnumProperty(items=[
    ('BMESH', 'BMesh', 'BMesh', 0),
    ('CARVE', 'Carve', 'Carve', 1)],
    name='Boolean Solver', description='Solver to use for Boolean mesh operations', default='BMESH')
  
  @classmethod
  def poll(cls, context):
    if context is None \
      or not hasattr(context, 'region_data') or context.region_data is None \
      or not hasattr(context, 'scene') or context.scene is None \
      or not hasattr(context.scene, 'objects') or context.scene.objects is None \
      or not hasattr(context.scene.objects, 'active') or context.scene.objects.active is None \
      or not hasattr(context, 'selected_objects') or context.selected_objects is None \
      or len(list(context.selected_objects)) == 0 \
      or not hasattr(context, 'mode') or context.mode != 'OBJECT' \
      or context.scene.objects.active.type != 'MESH' \
      or len(list(context.scene.objects.active.data.vertices)) == 0:
      return False
    
    return True
  
  def execute(self, context):
    try:
      orig_target = context.scene.objects.active
      target_name = orig_target.name
      targets = [orig_target]
      new_objs = []
      
      # Warn if the target has modifiers already.
      if len(list(orig_target.modifiers)) != 0:
        self.report({'WARNING'}, 'Active object has unapplied modifiers. Operation may not work correctly.')
      
      # Determine where the viewer is in world space.
      view_matrix_inverse = context.region_data.view_matrix.inverted()
      view_point = (view_matrix_inverse * mathutils.Vector((0, 0, 0, 1))).to_3d()
      view_dir = (view_matrix_inverse * mathutils.Vector((0, 0, -1, 0))).to_3d()
      
      # Determine projection distance required to make the separation meshes cut through the active object.
      bb_pts = [mathutils.Vector(bb_pt) for bb_pt in orig_target.bound_box]
      project_dist = self._max_dist_through_bound_box(view_point, bb_pts) + _PROJECT_DIST_PADDING
      
      # Find the objects and/or grease pencil strokes to use for creating carve meshes.
      carvers = self._find_carvers(context, orig_target)
      
      if not carvers:
        self.report({'INFO'}, 'Nothing found to carve with. Operator will have no effect.')
        return {'FINISHED'}
      
      # Create carve mesh objects.
      carve_objs = [mesh_project.carver_to_carve_obj(context, carver, view_point, view_dir, project_dist,
        self.prop_convex_hull_mesh, self.prop_convex_hull_curve) for carver in carvers]
      carve_objs = [o for o in carve_objs if o is not None]
      
      # Union the carve meshes if we are in Union Carves mode.
      if self.prop_union_carves and len(carve_objs) > 0:
        single_carve = util_mesh.union_objects(context, carve_objs, self.prop_boolean_solver, _BOOLEAN_OP_THRESHOLD,
          delete=True, delete_data=True)
        carve_objs = [single_carve]
      
      # Apply each carve mesh.
      for carve_obj in carve_objs:
        new_targets = []
        for target in targets:
          new_target = self._separate_obj(context, target, carve_obj, target_name)
          if new_target is not None:
            new_targets.append(new_target)
            new_objs.append(new_target)
        targets += new_targets
      
      # Remove any objects that have been made empty by the boolean operations.
      for target in targets:
        if len(list(target.data.vertices)) == 0:
          mesh = target.data
          if target == orig_target:
            orig_target = None
          bpy.data.objects.remove(target)
          bpy.data.meshes.remove(mesh)
          new_objs.remove(target)
      
      # Delete carver objects and/or grease pencil strokes if we are in Delete Carve Objects mode.
      if self.prop_delete_carvers:
        if self.prop_use_gPencil:
          self._clear_gPencil_frame(context)
        for carver in carvers:
          if isinstance(carver, bpy.types.Object):
            bpy.data.objects.remove(carver)
      
      # Set the final selection to something that makes sense for the operation.
      bpy.ops.object.select_all(action='DESELECT')
      for new_obj in new_objs:
        new_obj.select = True
      if orig_target is not None:
        orig_target.select = True
        context.scene.objects.active = orig_target
      else:
        context.scene.objects.active = None
    
      return {'FINISHED'}
    
    except Exception as e:
      # Try to clean up.
      if 'new_objs' in locals():
        for new_obj in new_objs:
          mesh = new_obj.data
          bpy.data.objects.remove(new_obj)
          bpy.data.meshes.remove(mesh)
      
      self.report({'ERROR'}, str(e))
      raise e
    
    finally:
      # Clean up intermediate objects that were created.
      if 'carve_objs' in locals():
        for carve_obj in carve_objs:
          mesh = carve_obj.data
          bpy.data.objects.remove(carve_obj)
          bpy.data.meshes.remove(mesh)
  
  def _max_dist_through_bound_box(self, view_point, bb_pts):
    return math.sqrt(max([(bb_pt - view_point).length_squared for bb_pt in bb_pts]))
  
  def _clear_gPencil_frame(self, context):
    frame = find.find_active_gPencil_frame(context)
    if frame is not None:
      frame.clear()
  
  def _find_carvers(self, context, target):
    carvers = []
    
    # Find selected objects for carving.
    if self.prop_use_selection:
      for sel_obj in context.selected_objects:
        if sel_obj != target:
          if sel_obj.type in ['CURVE', 'MESH']:
            carvers.append(sel_obj)
          else:
            self.report({'INFO'}, 'Ignoring selected object of type {}'.format(sel_obj.type))
    
    # Find grease pencil strokes for carving.
    if self.prop_use_gPencil:
      frame = find.find_active_gPencil_frame(context)
      if frame is not None:
        carvers += list(frame.strokes)
    
    return carvers
  
  def _separate_obj(self, context, target, carve_obj, base_target_name):
    try:
      
      # If we are not in Subtract Only mode, we will need a copy of the target mesh data to create the new object.
      if not self.prop_subtract_only:
        target_data_copy = target.data.copy()
      
      # Apply boolean modifier to the original target object.
      util_mesh.apply_boolean_op(context, target, carve_obj, 'DIFFERENCE', self.prop_boolean_solver,
        _BOOLEAN_OP_THRESHOLD)
      
      # If we are not in Subtract Only mode, create a new object and apply the opposite boolean modifier.
      new_target = None
      if not self.prop_subtract_only:
        new_target = bpy.data.objects.new(base_target_name, target_data_copy)
        context.scene.objects.link(new_target)
        
        util_mesh.apply_boolean_op(context, new_target, carve_obj, 'INTERSECT', self.prop_boolean_solver,
          _BOOLEAN_OP_THRESHOLD)
      
      return new_target
      
    except Exception as e:
      # Try to clean up.
      if 'new_target' in locals() and new_target is not None:
        bpy.data.objects.remove(new_target)
      if 'target_data_copy' in locals() and target_data_copy is not None:
        bpy.data.meshes.remove(target_data_copy)
      
      raise e