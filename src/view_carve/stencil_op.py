"""Contains the Viewport Stencil Carve operator."""

import traceback

import math

import bpy
import mathutils

from . import util_mesh
from . import mesh_project


# Threshold to use for finding overlapping geometry in boolean operations.
# TODO: Make this configurable?
_BOOLEAN_OP_THRESHOLD = 0.000001

# Extra projection distance added to ensure that stencil meshes completely cut through the target object.
_PROJECT_DIST_PADDING = 1

# Types of carver objects that are supported.
_SUPPORTED_CARVER_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'GPENCIL'}


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
    prop_subtract_only: bpy.props.BoolProperty(name='Subtract Only',
                                               description='Subtract geometry instead of splitting into multiple objects',
                                               default=False)
    prop_union_carves: bpy.props.BoolProperty(name='Union Carves',
                                              description='Make a single combined carve from all carver objects',
                                              default=False)
    prop_delete_carvers: bpy.props.BoolProperty(name='Delete Carver Objects',
                                                description='Delete objects used for carving', default=False)

    # Blender metadata.
    bl_idname = 'view_carve.stencil'
    bl_label = 'Viewport Stencil Carve'
    bl_description = 'Separate a mesh object based on other objects projected through the current view'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Make sure we are in Object Mode with at least two selected objects.
        if context is None \
                or not hasattr(context, 'region_data') or context.region_data is None \
                or not hasattr(context, 'scene') or context.scene is None \
                or not hasattr(context.scene, 'collection') or context.scene.collection is None \
                or not hasattr(context.scene.collection, 'objects') or context.scene.collection.objects is None \
                or not hasattr(context, 'view_layer') or context.view_layer is None \
                or not hasattr(context.view_layer, 'objects') or context.view_layer.objects is None \
                or not hasattr(context.view_layer.objects, 'active') or context.view_layer.objects.active is None \
                or not hasattr(context, 'selected_objects') or context.selected_objects is None \
                or len(list(context.selected_objects)) < 2 \
                or not hasattr(context, 'mode') or context.mode != 'OBJECT':
            return False

        # Make sure the carve target (active object) is a mesh object with no modifiers.
        if context.view_layer.objects.active.type != 'MESH' \
                or len(list(context.view_layer.objects.active.modifiers)) != 0:
            return False

        # Make sure the carver objects (non-active selected objects) are of supported types.
        for selected_obj in list(context.selected_objects):
            if selected_obj is not context.view_layer.objects.active \
                    and selected_obj.type not in _SUPPORTED_CARVER_TYPES:
                return False

        return True

    def execute(self, context):
        new_objs = []
        stencil_mesh_objs = []
        try:
            # Find the carver objects.
            orig_target = context.view_layer.objects.active
            carver_objs = [obj for obj in list(context.selected_objects) if obj is not orig_target]

            # Determine where the viewport camera is in world space.
            view_matrix_inv = context.region_data.view_matrix.inverted()
            cam_pt = (view_matrix_inv @ mathutils.Vector((0, 0, 0, 1))).to_3d()

            # Determine projection distance required to make the stencil meshes cut through the active object.
            bb_pts = [mathutils.Vector(bb_pt) for bb_pt in orig_target.bound_box]
            project_dist = math.sqrt(max([(bb_pt - cam_pt).length_squared for bb_pt in bb_pts])) + _PROJECT_DIST_PADDING

            # Create stencil mesh objects from the carver objects. (Only one stencil mesh will be created if we are in
            # Union Carves mode.)
            stencil_mesh_objs = mesh_project.carvers_to_stencil_meshes(context.region_data.view_matrix,
                                                                       not context.region_data.is_perspective,
                                                                       project_dist, carver_objs,
                                                                       self.prop_delete_carvers, self.prop_union_carves,
                                                                       context)

            # Apply each stencil mesh.
            target_name = orig_target.name
            targets = [orig_target]
            for stencil_mesh_obj in stencil_mesh_objs:
                new_targets = []
                for target in targets:
                    new_target = self._separate_obj(context, target, stencil_mesh_obj, target_name)
                    if new_target is not None:
                        new_targets.append(new_target)
                        new_objs.append(new_target)
                targets += new_targets

            # Remove any objects that have been made empty by the boolean operations.
            for target in targets:
                if len(list(target.data.vertices)) == 0:
                    if target is orig_target:
                        orig_target = None
                    bpy.data.objects.remove(target)
                    new_objs.remove(target)

            # Set the final selection to something that makes sense for the operation.
            bpy.ops.object.select_all(action='DESELECT')
            for new_obj in new_objs:
                new_obj.select_set(True)
            if orig_target is not None:
                orig_target.select_set(True)
            context.view_layer.objects.active = orig_target

            return {'FINISHED'}

        except Exception as e:
            # In case of error, try to clean up any partial results owned by Blender.
            for new_obj in new_objs:
                bpy.data.objects.remove(new_obj)

            self.report({'ERROR'}, str(e))
            traceback.print_exc()

            return {'CANCELLED'}

        finally:
            # Clean up intermediate objects that were created, whether there was an error or not.
            for stencil_mesh_obj in stencil_mesh_objs:
                bpy.data.objects.remove(stencil_mesh_obj)

    def _separate_obj(self, context, target, stencil_mesh_obj, base_target_name):
        """Separates a mesh object using the specified stencil mesh.
        Modifies the original target mesh using the stencil.
        Returns the new mesh object obtained by cutting off a piece of the target, or None if no object was generated.
        context - The Blender context.
        target - The mesh object to carve.
        stencil_mesh_obj - The mesh object to use for boolean operations on the target.
        base_target_name - The base name to use for the new mesh object.
        """
        target_data_copy = None
        new_target = None
        try:
            # If we are not in Subtract Only mode, we will need a copy of the target mesh data to create the new object.
            if not self.prop_subtract_only:
                target_data_copy = target.data.copy()

            # Apply boolean modifier to the original target object.
            util_mesh.apply_boolean_op(context, target, stencil_mesh_obj, 'DIFFERENCE', _BOOLEAN_OP_THRESHOLD)

            # If we are not in Subtract Only mode, create a new object and apply the opposite boolean modifier.
            if not self.prop_subtract_only:
                new_target = bpy.data.objects.new(base_target_name, target_data_copy)
                context.scene.collection.objects.link(new_target)

                util_mesh.apply_boolean_op(context, new_target, stencil_mesh_obj, 'INTERSECT', _BOOLEAN_OP_THRESHOLD)

            return new_target

        except Exception as e:
            # Try to clean up.
            if new_target is not None:
                bpy.data.objects.remove(new_target)
            if target_data_copy is not None:
                bpy.data.meshes.remove(target_data_copy)

            raise e
