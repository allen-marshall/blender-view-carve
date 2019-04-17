"""Contains the Viewport Stencil Carve operator."""

import traceback

import math

import bpy
import mathutils

from . import util_mesh
from . import mesh_project

# Extra projection distance added to ensure that stencil meshes completely cut through the target object.
_PROJECT_DIST_PADDING = 1

# Types of carver objects that are supported.
_SUPPORTED_CARVER_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'GPENCIL'}


class VIEW_CARVE_OT_stencil(bpy.types.Operator):
    """Operator that carves off pieces of the active object based on other selected objects.
    Carver objects are projected through the current 3D viewport to determine how to carve.
    Properties:
    prop_pieces_to_keep - Determines whether to keep only the pieces obtained by Boolean subtraction, only the pieces
        obtained by Boolean intersection, or both. Default: Keep all pieces.
    prop_union_carves - If true, the operator will apply all found carvers as a single cut. This option only matters
        when prop_subtract_only is false. In that case, setting prop_union_carves to true results in a maximum of one
        new object, while setting it to false can result in more than one new object. Default: False
    prop_delete_carvers - If true, the objects used for carving will be deleted. Default: False
    prop_overlap_threshold - Overlap threshold to use in Boolean operations invoked by this operator.
    """
    # Blender operator properties.
    prop_pieces_to_keep: bpy.props.EnumProperty(
        items=[('DIFFERENCE', 'Difference', 'Keep only the piece obtained by subtracting the stencil(s).'),
         ('INTERSECTION', 'Intersection', 'Keep only the piece obtained by intersecting with the stencil(s).'),
         ('ALL', 'All', 'Keep all pieces.')], name='Pieces to Keep',
        description='Determines which pieces from the cut are kept', default='ALL')
    prop_union_carves: bpy.props.BoolProperty(name='Union Carves',
                                              description='Make a single combined carve from all carver objects',
                                              default=False)
    prop_delete_carvers: bpy.props.BoolProperty(name='Delete Carver Objects',
                                                description='Delete objects used for carving', default=False)
    prop_overlap_threshold: bpy.props.FloatProperty(name='Overlap Threshold',
                                                    description='Overlap threshold for Boolean operations', min=0.0,
                                                    precision=6, unit='LENGTH', subtype='DISTANCE', default=0.000001)

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
        # If we are keeping all pieces, we need to copy the target mesh and perform both intersection and difference.
        if self.prop_pieces_to_keep == 'ALL':
            target_data_copy = None
            new_target = None
            try:
                # Copy the target.
                target_data_copy = target.data.copy()
                new_target = bpy.data.objects.new(base_target_name, target_data_copy)
                context.scene.collection.objects.link(new_target)

                # Perform difference on the old copy and intersection on the new copy.
                util_mesh.apply_boolean_op(context, target, stencil_mesh_obj, 'DIFFERENCE', self.prop_overlap_threshold)
                util_mesh.apply_boolean_op(context, new_target, stencil_mesh_obj, 'INTERSECT',
                                           self.prop_overlap_threshold)

                return new_target

            except Exception as e:
                # Try to clean up.
                if new_target is not None:
                    bpy.data.objects.remove(new_target)
                if target_data_copy is not None:
                    bpy.data.meshes.remove(target_data_copy)

                raise e

        # If we are keeping only one piece, we can just convert the existing target into that piece instead of making a
        # copy.
        else:
            util_mesh.apply_boolean_op(context, target, stencil_mesh_obj,
                                       'DIFFERENCE' if self.prop_pieces_to_keep == 'DIFFERENCE' else 'INTERSECT',
                                       self.prop_overlap_threshold)
            return None
