Installing the View Carve Addon
===============================

The View Carve addon depends on the following Python libraries:

- `ordered-set <https://pypi.org/project/ordered-set/>`_ (tested with version 3.1.1)
- `Shapely <https://pypi.org/project/Shapely/>`_ (tested with version 1.6.4.post2)
- `triangle <https://pypi.org/project/triangle/>`_ (tested with version 20190115.2)

For the addon to function, these libraries must be available in Blender's Python environment. Unfortunately, installing
Python libraries in Blender is not straightforward, especially when the libraries include native components. To make
this process easier, the View Carve addon comes with an installation script that handles many of the details. There are
still a few manual steps required before running the installation script.

The installation script is intended to work on at least Ubuntu, Windows, and MacOS. However, it has only been tested on
Ubuntu and Windows, because the project maintainer doesn't currently have access to a MacOS machine. If you encounter
problems with the script on MacOS, or any other platform, please consider reporting the issue
`here <https://github.com/allen-marshall/blender-view-carve/issues>`_.

The steps required to install the View Carve addon using the installation script are listed below.

Step 1: Install Python 3
------------------------

The installation script requires Python version 3.x.x in order to execute. Depending on your operating system, you may
want to install Python through `the official Python website <https://www.python.org/>`_ or your OS's package manager.

Step 2: (Windows Only) Install GEOS
-----------------------------------

The GEOS library is required in order to install the Shapely dependency. On Windows, GEOS must be installed manually; on
other platforms, GEOS will be installed automatically by the installation script. To install GEOS on Windows, you can
use the `OSGeo4W <https://trac.osgeo.org/osgeo4w/>`_ installer. Make sure to use the 64-bit installer if you are using
64-bit Blender, and the 32-bit installer if you are using 32-bit Blender. If you use the express install option, make
sure the GDAL package is selected in order to install GEOS. (The other packages do not need to be selected unless you
need them for something else.)

After running the OSGeo4W installer, make sure its bin directory is added to your Path environment variable. You may
need to add it manually. The default bin directory will be something like ``C:\OSGeo4W64\bin`` or ``C:\OSGeo4W\bin``,
but the installer may allow you to configure this if you so choose.

Step 3: Run the Installation Script
-----------------------------------

After completing the above manual steps, you should be able to use the installation script to handle the rest of the
installation process. The script accepts one required positional argument giving the path to the directory where Blender
is installed. (On MacOS, this argument should point to the ``blender.app`` directory containing the Blender application
files.) The script also accepts one optional argument (which you probably won't need) using the ``-i`` or
``--custom_install_path`` command line flag; this argument provides a custom location into which View Carve and its
dependencies should be installed. If the optional argument is not provided, the default user-specific Blender
configuration path for your operating system will be used:

- On Windows, the default path is ``~\AppData\Roaming\Blender Foundation\Blender``
- On MacOS, the default path is ``~/Library/Application Support/Blender``
- On other platforms, the default path is ``~/.config/blender``

For example, if you have Blender installed at ``~/path/to/blender``, and you want to install View Carve and its
dependencies at ``~/path/to/install`` instead of the default location, you could use the following command (in the
unzipped ``blender-view-carve`` directory):

``python3 install_view_carve.py ~/path/to/blender -i ~/path/to/install``

If you instead want to install at the default location, you could use the following command instead:

``python3 install_view_carve.py ~/path/to/blender``

(Depending on how Python is installed, you might need to use ``python`` instead of ``python3``. Just make sure you don't
accidentally use Python version 2.)