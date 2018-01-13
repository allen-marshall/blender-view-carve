def find_active_gPencil_frame(context):
  """Finds the active grease pencil frame in the current context.
  Returns: The active grease pencil frame, or None if no active frame was found.
  context - The Blender context"""
  if hasattr(context.scene, 'grease_pencil') and context.scene.grease_pencil is not None:
    layer = context.scene.grease_pencil.layers.active
    if layer is not None:
      return layer.active_frame
  
  return None