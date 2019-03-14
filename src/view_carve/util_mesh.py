"""Utilities for working with meshes and other geometric objects."""

import bpy


def apply_boolean_op(context, target, obj, operation, double_threshold):
    """Adds and immediately applies a boolean modifier to the specified target object.
    Warning: This function may change the selection state of objects in the scene.
    May not work correctly if the target has unapplied modifiers.
    Raises ValueError if Blender is not currently in Object Mode.
    context - The Blender context.
    target - The object to which the boolean modifier will be applied.
    obj - The object to use in the modifier.
    operation - Operation parameter for the boolean modifier.
    double_threshold - Threshold parameter for the boolean modifier.
    """
    mod = target.modifiers.new('viewCarveTemp_modifier', 'BOOLEAN')
    mod.operation = operation
    mod.object = obj
    mod.double_threshold = double_threshold
    context.scene.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
