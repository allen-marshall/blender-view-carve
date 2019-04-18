"""Contains menu extensions added by this plugin."""


def vp_object_menu_extension(self, context):
    """Menu extension function defining extensions to the 3D viewport's Object menu."""
    self.layout.separator()
    self.layout.operator('view_carve.stencil')
