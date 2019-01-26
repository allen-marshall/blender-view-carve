import bpy


class VIEW_CARVE_OT_stencil(bpy.types.Operator):
    """Operator that carves off pieces of the active object based on other selected objects.
    Carver objects are projected through the current 3D viewport to determine how to carve.
    Properties:
    prop_subtract_only - If false, the pieces cut off from the target mesh will be left in the scene as new objects. If
        true, the pieces will be deleted, leaving only the carved target mesh. Default: False
    prop_union_carves - If true, the operator will apply all found carvers as a single cut. This option only matters
        when prop_subtract_only is false. In that case, setting prop_union_carves to true results in a maximum of one
        new object, while setting it to false can result in more than one new object. Default: False
    prop_delete_carvers - If true, the objects used for carving will be deleted. Default: False
    """
    # Blender operator properties.
    prop_subtract_only = bpy.props.BoolProperty(name='Subtract Only',
                                                description='Subtract geometry instead of splitting into multiple objects',
                                                default=False)
    prop_union_carves = bpy.props.BoolProperty(name='Union Carves',
                                               description='Make a single combined carve from all carver objects',
                                               default=False)
    prop_delete_carvers = bpy.props.BoolProperty(name='Delete Carver Objects',
                                                 description='Delete objects used for carving', default=False)

    # Blender metadata.
    bl_idname = 'view_carve.stencil'
    bl_label = 'Viewport Stencil Carve'
    bl_description = 'Separate a mesh object based on other objects projected through the current view'
    bl_options = {'REGISTER', 'UNDO'}
