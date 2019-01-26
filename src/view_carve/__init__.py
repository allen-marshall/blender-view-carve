import bpy

from . import ui
from . import carve_op

bl_info = {
    'name': 'Projection Carving Tool',
    'description': 'Tool for carving a mesh object based on projections of other objects in the 3D viewport',
    'author': 'Allen Marshall',
    'version': (0, 4),
    'blender': (2, 80, 0),
    'category': 'Mesh',
    'tracker_url': 'https://github.com/allen-marshall/blender-view-carve/issues',
}

register, unregister = bpy.utils.register_classes_factory((carve_op.CarveOp, ui.CarvePanel,))

if __name__ == '__main__':
    register()
