#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

if __name__ == '__main__':
    # Regex used to extract the Blender version number from the output of the Blender '--version' command.
    BLENDER_VERSION_REGEX = re.compile(r'\d+\.\d+')

    # Regex used to extract the Python version number from the output of the Python '--version' command.
    PYTHON_VERSION_REGEX = re.compile(r'\d+\.\d+\.\d+')

    # Get command line arguments.
    arg_parser = argparse.ArgumentParser(description='Installer script for View Carve Blender addon')
    arg_parser.add_argument('blender_path', type=str, help='Path to the directory where Blender is installed')
    args = arg_parser.parse_args()

    # Find out what version of Blender we are using.
    print('Identifying Blender version...')
    blender_exe_path = os.path.join(args.blender_path, 'blender')
    blender_version_cmd = str(blender_exe_path) + ' --version'
    with os.popen(blender_version_cmd) as blender_version_pipe:
        blender_version_output_line = blender_version_pipe.readline()
        blender_version_strings = re.findall(BLENDER_VERSION_REGEX, blender_version_output_line)
        if len(blender_version_strings) != 1:
            raise ValueError('Failed to determine Blender version.')
        blender_version_string = blender_version_strings[0]

    # Find out what version of Python Blender is using.
    print('Identifying Blender\'s Python version...')
    python_path = os.path.join(args.blender_path, blender_version_string, 'python')
    python_bin_path = os.path.join(python_path, 'bin')
    python_exe_paths = [dir_entry.path for dir_entry in os.scandir(python_bin_path)
                        if dir_entry.is_file() and os.access(dir_entry.path, os.X_OK)
                        and dir_entry.name.startswith('python')]
    if len(python_exe_paths) != 1:
        raise ValueError('Failed to find Blender\'s Python executable.')
    python_exe_path = python_exe_paths[0]
    python_version_cmd = str(python_exe_path) + ' --version'
    with os.popen(python_version_cmd) as python_version_pipe:
        python_version_output_line = python_version_pipe.readline()
        python_version_strings = re.findall(PYTHON_VERSION_REGEX, python_version_output_line)
        if len(python_version_strings) != 1:
            raise ValueError('Failed to determine Blender\'s Python version.')
        python_version_string = python_version_strings[0]

    # Create a temporary directory for storing temporary files generated by the rest of the installation process.
    with tempfile.TemporaryDirectory() as temp_dir:

        # Create a copy of Blender's Python installation, so that we can compile the dependencies without having to
        # change Blender's files.
        print('Making temporary copy of Blender\'s Python installation...')
        python_copy_path = os.path.join(temp_dir, 'blender-python')
        shutil.copytree(python_path, python_copy_path)

        # By default, Blender's Python installation lacks some header files needed for installing Python packages that
        # include native code. We need to restore these headers by downloading them from the Python website.

        # Download the Python source archive.
        print('Downloading Python source...')
        python_src_request_url = 'https://www.python.org/ftp/python/{0}/Python-{0}.tgz'.format(python_version_string)
        python_src_archive_path = os.path.join(temp_dir, 'python-src.tgz')
        with urllib.request.urlopen(python_src_request_url) as python_src_archive_response,\
                open(python_src_archive_path, 'wb') as python_src_archive_out:
            shutil.copyfileobj(python_src_archive_response, python_src_archive_out)

        # Decompress the Python source archive.
        print('Decompressing Python source...')
        python_src_path = os.path.join(temp_dir, 'python-src')
        with tarfile.open(python_src_archive_path, 'r:gz') as python_src_tar:
            python_src_tar.extractall(python_src_path)

        # Copy all header files from the Python source distribution into our temporary copy of Blender's Python
        # installation.
        print('Copying header files...')
        python_src_include_path = os.path.join(python_src_path, 'Python-{}'.format(python_version_string), 'Include')
        python_copy_include_path = os.path.join(python_copy_path, 'include')
        if not os.path.exists(python_copy_include_path):
            os.mkdir(python_copy_include_path)
        for dir_entry in os.scandir(python_src_include_path):
            if dir_entry.is_dir():
                dir_copy_path = os.path.join(python_copy_include_path, dir_entry.name)
                if os.access(dir_copy_path, os.F_OK):
                    os.rmdir(dir_copy_path)
                shutil.copytree(dir_entry.path, dir_copy_path)
            else:
                shutil.copyfile(dir_entry.path, os.path.join(python_copy_include_path, dir_entry.name))

        # Next, we install Pip into our temporary copy of Blender's Python.

        # Download get-pip.py.
        print('Downloading get-pip.py...')
        get_pip_request_url = 'https://bootstrap.pypa.io/get-pip.py'
        get_pip_path = os.path.join(temp_dir, 'get-pip.py')
        with urllib.request.urlopen(get_pip_request_url) as get_pip_response, open(get_pip_path, 'wb') as get_pip_out:
            shutil.copyfileobj(get_pip_response, get_pip_out)

        # Run get-pip.py to install Pip.
        print('Installing Pip...')
        python_copy_exe_path = os.path.join(python_copy_path, 'bin', os.path.split(python_exe_path)[1])
        subprocess.run([python_copy_exe_path, get_pip_path])

        # Now that Pip is installed, use it to install our dependencies.
        print('Getting dependencies with Pip...')
        pip_exe_path = os.path.join(python_copy_path, 'bin', 'pip')
        subprocess.run([pip_exe_path, 'install', 'ordered-set==3.1'])
        subprocess.run([pip_exe_path, 'install', 'Shapely==1.6.4.post2'])
        subprocess.run([pip_exe_path, 'install', 'triangle==20190115.1'])
        python_copy_lib_paths = [dir_entry.path for dir_entry in os.scandir(os.path.join(python_copy_path, 'lib'))
                                 if dir_entry.is_dir() and dir_entry.name.startswith('python')]
        if len(python_copy_lib_paths) != 1:
            raise ValueError('Failed to find Python library directory.')
        python_copy_lib_path = os.path.join(python_copy_lib_paths[0], 'site-packages')
        python_copy_ordered_set_path = os.path.join(python_copy_lib_path, 'ordered_set.py')
        python_copy_shapely_path = os.path.join(python_copy_lib_path, 'shapely')
        python_copy_triangle_path = os.path.join(python_copy_lib_path, 'triangle')

        # Next, we need to copy the dependencies and the View Carve code into the user's Blender configuration
        # directory.

        # Find the (platform-dependent) Blender configuration directory for the user.
        if sys.platform.startswith('win32') or sys.platform.startswith('cygwin'):
            blender_config_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation',
                                               'Blender', blender_version_string)
        elif sys.platform.startswith('darwin'):
            blender_config_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Blender',
                                               blender_version_string)
        else:
            blender_config_path = os.path.join(os.path.expanduser('~'), '.config', 'blender', blender_version_string)

        # Copy the dependencies into the user's Blender configuration directory.
        print('Copying dependencies to user\'s Blender config folder...')

        blender_config_modules_path = os.path.join(blender_config_path, 'scripts', 'addons', 'modules')
        blender_config_addons_path = os.path.join(blender_config_path, 'scripts', 'addons')
        os.makedirs(blender_config_modules_path, exist_ok=True)
        os.makedirs(blender_config_addons_path, exist_ok=True)
        blender_config_ordered_set_path = os.path.join(blender_config_modules_path, 'ordered_set.py')
        blender_config_shapely_path = os.path.join(blender_config_modules_path, 'shapely')
        blender_config_triangle_path = os.path.join(blender_config_modules_path, 'triangle')
        if os.access(blender_config_ordered_set_path, os.F_OK):
            os.remove(blender_config_ordered_set_path)
        shutil.copyfile(python_copy_ordered_set_path, blender_config_ordered_set_path)
        if os.access(blender_config_shapely_path, os.F_OK):
            shutil.rmtree(blender_config_shapely_path)
        shutil.copytree(python_copy_shapely_path, blender_config_shapely_path)
        if os.access(blender_config_triangle_path, os.F_OK):
            shutil.rmtree(blender_config_triangle_path)
        shutil.copytree(python_copy_triangle_path, blender_config_triangle_path)

        # Copy the View Carve code into the user's Blender configuration directory.
        print('Copying View Carve to user\'s Blender config folder...')
        view_carve_src_path = sys.path[0]
        if len(view_carve_src_path) == 0:
            view_carve_src_path = os.getcwd()
        view_carve_addon_src_path = os.path.join(view_carve_src_path, 'src', 'view_carve')
        blender_config_view_carve_path = os.path.join(blender_config_addons_path, 'view_carve')
        if os.access(blender_config_view_carve_path, os.F_OK):
            shutil.rmtree(blender_config_view_carve_path)
        shutil.copytree(view_carve_addon_src_path, blender_config_view_carve_path)

        print('Done.')
