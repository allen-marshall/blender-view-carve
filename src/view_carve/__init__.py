"""Blender addon Python module - Projection Carving Tool"""

import bpy

from . import stencil_op
from . import menus

bl_info = {
    'name': 'View Carve',
    'description': 'Tool for carving a mesh object based on projections of other objects in the 3D viewport',
    'author': 'Allen Marshall',
    'version': (1, 0, 0),
    'blender': (2, 80, 0),
    'category': 'Mesh',
    'tracker_url': 'https://github.com/allen-marshall/blender-view-carve/issues',
}

basic_register, basic_unregister = bpy.utils.register_classes_factory((stencil_op.VIEW_CARVE_OT_stencil,))


def register():
    basic_register()
    bpy.types.VIEW3D_MT_object.append(menus.vp_object_menu_extension)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(menus.vp_object_menu_extension)
    basic_unregister()


if __name__ == '__main__':
    register()
