import bpy

from . import ui
from view_carve import carve_op

bl_info = {
  'name' : 'Projection Carving Tool',
  'description' : 'Tool for carving a mesh object based on projections of curves in the 3D viewport',
  'author' : 'Allen Marshall',
  'version' : (0, 2),
  'blender' : (2, 7, 9),
  'category' : 'Mesh',
}

classes_to_register = [carve_op.CarveOp, ui.CarvePanel,]

def register():
  for class_to_register in classes_to_register:
    bpy.utils.register_class(class_to_register)

def unregister():
  for class_to_register in classes_to_register:
    bpy.utils.unregister_class(class_to_register)

if __name__ == '__main__':
  register()