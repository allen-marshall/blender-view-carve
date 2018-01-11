# TODO: Improve docstrings.

def find_active_gPencil_frame(context):
  if hasattr(context.scene, 'grease_pencil') and context.scene.grease_pencil is not None:
    layer = context.scene.grease_pencil.layers.active
    if layer is not None:
      return layer.active_frame
  
  return None