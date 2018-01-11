import bpy

# TODO: Improve docstrings.

def union_objects(context, objs, solver, double_threshold, delete=False, delete_data=False):
  try:
    # Start with an empty mesh object.
    new_mesh = bpy.data.meshes.new('viewCarveTemp_mesh')
    new_obj = bpy.data.objects.new('viewCarveTemp_meshObj', new_mesh)
    context.scene.objects.link(new_obj)
    
    for obj in objs:
      apply_boolean_op(context, new_obj, obj, 'UNION', solver, double_threshold)
    
    if delete:
      for obj in objs:
        data = obj.data if hasattr(obj, 'data') else None
        bpy.data.objects.remove(obj)
        if delete_data and data is not None:
          bpy.data.meshes.remove(data)
    
    return new_obj
  
  except Exception as e:
    # Try to clean up.
    if 'new_obj' in locals():
      bpy.data.objects.remove(new_obj)
    if 'new_mesh' in locals():
      bpy.data.meshes.remove(new_mesh)
    
    raise e

def apply_boolean_op(context, target, obj, operation, solver, double_threshold):
  """Adds and immediately applies a boolean modifier to the specified target object.
  May not work correctly if the target has unapplied modifiers."""
  context.scene.objects.active = target
  mod = target.modifiers.new('curveSepTemp_modifier', 'BOOLEAN')
  mod.operation = operation
  mod.object = obj
  mod.solver = solver
  mod.double_threshold = double_threshold
  bpy.ops.object.modifier_apply(modifier=mod.name)