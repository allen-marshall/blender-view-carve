Installing the View Carve Addon
===============================

The View Carve addon depends on the following Python libraries:

- `ordered-set <https://pypi.org/project/ordered-set/>`_ (tested with version 3.1)
- `Shapely <https://pypi.org/project/Shapely/>`_ (tested with version 1.6.4.post2)
- `triangle <https://pypi.org/project/triangle/>`_ (tested with version 20190115.1)

For the addon to function, these libraries must be available in Blender's Python environment. Unfortunately, installing
Python libraries in Blender is not straightforward, especially when the libraries include native components. There are
several ways to achieve it, each with some drawbacks. This documentation covers one way.

Step 1: Find Out What Python Version Blender Uses
-------------------------------------------------

First you need to know what version of Python your installation of Blender is using. Open Blender, then click on the
"Scripting" tab at the top of the window. You should see a console panel that starts with the text
"PYTHON INTERACTIVE CONSOLE" followed by a version number (e.g. "3.7.0"). This version number is the Python version that
Blender is using.

TODO: Finish these instructions
-------------------------------