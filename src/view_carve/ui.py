import bpy

class CarvePanel(bpy.types.Panel):
  """Panel for accessing mesh carving tools."""
  bl_idname = 'view_carve.CarvePanel'
  bl_label = 'Mesh Carving'
  bl_category = 'Sculpt'
  bl_space_type = 'VIEW_3D'
  bl_region_type = 'TOOLS'
  bl_context = 'objectmode'
  
  def draw(self, context):
    self.layout.operator('view_carve.carve')