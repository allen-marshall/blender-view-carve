Using the View Carve Addon
==========================

Basic Information
-----------------

Once installed, the View Carve addon adds a new operator called "Viewport Stencil Carve" to Blender. The operator can be
accessed from the Object menu in the 3D viewport. To use the operator, you must select all the objects you want to use
as stencils, along with the target mesh object to be cut. The target mesh should be the last object selected, i.e. the
active object. The operator cannot be applied if the target mesh or stencil object(s) have unapplied modifiers. The
following types of objects can be used as stencils:

- Grease Pencil objects
- Curves
- Meshes
- Surfaces
- Text objects

The following screenshots show the result of using some Grease Pencil strokes and meshes as stencils to cut a cube:

TODO: Insert screenshot example here.

Operator Options
----------------

The following properties can be set in the operator properties panel after applying the Viewport Stencil Carve operator:

- Pieces to Keep. This property determines which pieces resulting from the cut will be kept or discarded. The default
  value of All will cause the target mesh to be cut into pieces, with all pieces kept as separate objects. With the other
  two possible values, only one piece will be kept. If the property is set to Difference, only the piece that lies outside
  all the stencils will be kept. If the property is set to Intersection, only the piece that lies inside all the stencils
  will be kept. (In the case of Intersection, if the stencils don't all overlap, there will be no piece to keep, and the
  target mesh will simply be deleted.)
- Union Carves. When enabled, this property causes all the stencils to be treated as if they were a single stencil
  object, obtained by taking the Boolean union of the stencils. This property is only relevant if Pieces to Keep is All
  and there are multiple stencil objects. When this property is enabled, the cut will result in at most two pieces.
- Delete Carvers. When enabled, this property causes the stencil objects to be deleted after they have been used to cut
  the target mesh. This can be convenient if you created the stencil objects for the sole purpose of acting as stencils.
- Overlap Threshold. This property controls the Overlap Threshold parameter for the Boolean operations that the Viewport
  Stencil Carve operator uses internally. It can usually be left at its default value.

Notes on Stroke and Curve Behavior
----------------------------------

When using Grease Pencil or Curve objects as stencils, there are a few things to consider:

- If the curve is closed or intersects itself (or appears to do so in the viewport's projection), the region enclosed by
  the curve is used as the stencil. Otherwise, the curve will be auto-closed, i.e. treated as if its first and last points
  were joined by a straight line. The following screenshots show some examples of this behavior.

TODO: Insert screenshot examples here.

- If the curve encloses multiple contiguous regions before or after auto-closing (or appears to do so in the viewport's
  projection), the cut may behave strangely, or may not happen at all. To avoid this issue, it is recommended that you do
  not use stencil curves that self-intersect at more than one point (before or after auto-closing). The following
  screenshots show some examples of cases where the issue may arise.

TODO: Insert screenshot examples here.