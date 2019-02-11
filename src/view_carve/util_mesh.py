import bpy


def union_objects(context, objs, solver, double_threshold, delete=False, delete_data=False):
    """Creates a new object containing the boolean union of the specified objects.
    Returns: The new object
    context - The Blender context
    objs - Mesh objects to union
    solver - Solver parameter for the boolean modifiers
    double_threshold - Threshold parameter for the boolean modifiers
    delete - If true, the objects in objs will be deleted after the union is performed.
    delete_data - If true, the mesh data associated with the objects in objs will be deleted after the union is
      performed."""
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
    May not work correctly if the target has unapplied modifiers.
    context - The Blender context
    target - The object to which the boolean modifier will be applied
    obj - The object to use in the modifier
    operation - Operation parameter for the boolean modifier
    solver - Solver parameter for the boolean modifier
    double_threshold - Threshold parameter for the boolean modifier"""
    context.scene.objects.active = target
    mod = target.modifiers.new('curveSepTemp_modifier', 'BOOLEAN')
    mod.operation = operation
    mod.object = obj
    mod.solver = solver
    mod.double_threshold = double_threshold
    bpy.ops.object.modifier_apply(modifier=mod.name)