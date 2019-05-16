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
import zipfile

# Regex used to extract the Blender version number from the output of the Blender '--version' command.
BLENDER_VERSION_REGEX = re.compile(r'\d+\.\d+')

# Regex used to extract the Python version number from the output of the Python '--version' command.
PYTHON_VERSION_REGEX = re.compile(r'\d+\.\d+\.\d+')


def find_python_exe(python_path):
    """Finds the Python executable within the specified Python installation.
    Returns the path to the Python executable.
    python_path - Path to the top directory of the Python installation.
    """
    def is_python_exe(dir_entry):
        return dir_entry.is_file() and os.access(dir_entry.path, os.X_OK) and not dir_entry.name.endswith('.dll') \
               and not dir_entry.name.endswith('.so') and dir_entry.name.startswith('python') \
               and dir_entry.name != 'pythonw.exe'

    python_exe_paths = [dir_entry.path for dir_entry in os.scandir(python_path) if is_python_exe(dir_entry)]
    if os.path.exists(os.path.join(python_path, 'bin')):
        python_exe_paths += [dir_entry.path for dir_entry in os.scandir(os.path.join(python_path, 'bin'))
                             if is_python_exe(dir_entry)]
    if len(python_exe_paths) != 1:
        raise ValueError('Failed to find Python executable.')
    return python_exe_paths[0]


def find_python_libs(python_path):
    """Finds the Python libraries directory within the specified Python installation.
    Returns the path to the libraries directory.
    python_path - Path to the top directory of the Python installation.
    """
    python_lib_paths = [dir_entry.path for dir_entry in os.scandir(os.path.join(python_path, 'lib'))
                        if dir_entry.is_dir()]
    if len(python_lib_paths) != 1:
        python_lib_paths = [os.path.join(python_path, 'lib')]
    return python_lib_paths[0]


def find_pip_exe(python_path, platform_is_windows):
    """Finds the Pip executable within the specified Python installation, assuming Pip is installed.
    Returns the path to the Pip executable.
    python_path - Path to the top directory of the Python installation.
    platform_is_windows - Boolean indicating whether we are installing on a Windows machine.
    """
    pip_exe_name = 'pip.exe' if platform_is_windows else 'pip'
    pip_exe_possible_paths = [os.path.join(python_path, pip_exe_name), os.path.join(python_path, 'bin', pip_exe_name),
                              os.path.join(python_path, 'Scripts', pip_exe_name),
                              os.path.join(python_path, 'scripts', pip_exe_name)]
    pip_exe_paths = [path for path in pip_exe_possible_paths if os.access(path, os.X_OK)]
    if len(pip_exe_paths) == 0:
        raise ValueError('Failed to find Pip executable.')
    return pip_exe_paths[0]


def get_blender_version(blender_path, platform_is_macos):
    """Gets the version of Blender, given the path to the Blender installation.
    Returns the Blender version as a string.
    blender_path - Path to the top directory of the Blender installation.
    platform_is_macos - Boolean indicating whether we are installing on a MacOS machine.
    """
    # Find the Blender executable.
    if platform_is_macos:
        blender_exe_path = os.path.join(blender_path, 'Contents', 'MacOS', 'blender')
    else:
        blender_exe_path = os.path.join(blender_path, 'blender')

    # Invoke the Blender executable with '--version' to get the version info.
    with os.popen(str(blender_exe_path) + ' --version') as blender_version_pipe:
        blender_version_output_line = blender_version_pipe.readline()
        blender_version_strings = re.findall(BLENDER_VERSION_REGEX, blender_version_output_line)
        if len(blender_version_strings) != 1:
            raise ValueError('Could not find version number in Blender\'s \'--version\' output.')
        return blender_version_strings[0]


def get_blender_python_paths(blender_path, blender_version, platform_is_macos):
    """Gets Python-related paths within the given Blender installation directory.
    Returns a 2-tuple containing the path to the Python installation and the path to the Python executable.
    blender_path - Path to the top directory of the Blender installation.
    blender_version - The Blender version, as a string.
    platform_is_macos - Boolean indicating whether we are installing on a MacOS machine.
    """
    # Find Blender's Python installation directory.
    if platform_is_macos:
        python_path = os.path.join(blender_path, 'Contents', 'Resources', blender_version, 'python')
    else:
        python_path = os.path.join(blender_path, blender_version, 'python')

    return python_path, find_python_exe(python_path)


def get_python_version(python_exe_path):
    """Gets version information for the given Python executable.
    Returns a 2-tuple containing the Python version as a string and a boolean indicating whether the Python executable
    is 64-bit (true) or 32-bit (false).
    python_exe_path - Path to the Python executable.
    """
    with os.popen(str(python_exe_path) + ' --version') as python_version_pipe:
        python_version_output_line = python_version_pipe.readline()
        python_version_strings = re.findall(PYTHON_VERSION_REGEX, python_version_output_line)
        if len(python_version_strings) != 1:
            raise ValueError('Could not find version number in Python\'s \'--version\' output.')
        python_version = python_version_strings[0]

        python_arch_cmd = str(python_exe_path) + ' -c "import sys; print(sys.maxsize > 2**32)"'
        with os.popen(python_arch_cmd) as python_arch_pipe:
            python_is_64bit = bool(python_arch_pipe.readline())

        return python_version, python_is_64bit


def make_temp_python(parent_dir, blender_python_path, python_version, python_is_64bit, platform_is_windows):
    """Creates a Python installation of the specified version, for temporary use in the installation process.
    Returns the path to the new Python installation.
    dir - Directory in which the Python installation should be created.
    blender_python_path - Path to the directory containing Blender's Python installation, which is assumed to have the
        same Python version and bit width as specified by python_version and python_is_64bit.
    python_version - The Python version for the new Python installation, as a string.
    python_is_64bit - Boolean indicating whether the Python interpreter should be 64-bit (true) or 32-bit (false).
    platform_is_windows - Boolean indicating whether we are installing on a Windows machine.
    """
    output_path = os.path.join(parent_dir, 'python')

    # On Windows, use NuGet to create a Python installation with all the required files.
    if platform_is_windows:
        # Download the NuGet package archive.
        print('    Downloading Python from NuGet...')
        if python_is_64bit:
            python_request_url = 'https://www.nuget.org/api/v2/package/python/{}'.format(python_version)
        else:
            python_request_url = 'https://www.nuget.org/api/v2/package/pythonx86/{}'.format(python_version)
        python_archive_path = os.path.join(parent_dir, 'python-from-nuget.zip')
        with urllib.request.urlopen(python_request_url) as python_archive_response, \
                open(python_archive_path, 'wb') as python_archive_out:
            shutil.copyfileobj(python_archive_response, python_archive_out)

        # Decompress the archive.
        print('    Decompressing Python archive...')
        with zipfile.ZipFile(python_archive_path) as python_archive_zip:
            python_archive_zip.extractall(path=os.path.join(parent_dir, 'python-from-nuget'))

        # Copy the required files from the archive.
        shutil.copytree(os.path.join(parent_dir, 'python-from-nuget', 'tools'), os.path.join(output_path, 'tools'))

        return os.path.join(output_path, 'tools')

    # On other platforms, only the Python include files are typically missing from Blender's Python installation, so we
    # just copy Python from Blender and download the include files.
    else:
        # Copy Python from Blender.
        print('    Copying Python files from Blender...')
        shutil.copytree(blender_python_path, output_path)

        # Download the Python source archive.
        print('    Downloading Python source...')
        python_src_request_url = 'https://www.python.org/ftp/python/{0}/Python-{0}.tgz'.format(python_version)
        python_src_archive_path = os.path.join(parent_dir, 'python-src.tgz')
        with urllib.request.urlopen(python_src_request_url) as python_src_archive_response, \
                open(python_src_archive_path, 'wb') as python_src_archive_out:
            shutil.copyfileobj(python_src_archive_response, python_src_archive_out)

        # Decompress the source archive.
        print('    Decompressing Python source archive...')
        python_src_path = os.path.join(parent_dir, 'python-src')
        with tarfile.open(python_src_archive_path, 'r:gz') as python_src_tar:
            python_src_tar.extractall(path=python_src_path)

        # Figure out the destination directory to which we should copy the header files.
        output_include_path = os.path.join(output_path, 'include')
        if not os.path.exists(output_include_path):
            os.mkdir(output_include_path)
        include_subpaths = [dir_entry.path for dir_entry in os.scandir(output_include_path)
                            if dir_entry.is_dir() and dir_entry.name.startswith('python')]
        if len(include_subpaths) == 1:
            output_include_path = os.path.join(output_include_path, include_subpaths[0])

        # Copy all header files from the Python source distribution into our temporary copy of Blender's Python
        # installation.
        print('    Copying header files...')
        for dir_entry in os.scandir(os.path.join(python_src_path, 'Python-{}'.format(python_version), 'Include')):
            if dir_entry.is_dir():
                dir_copy_path = os.path.join(output_include_path, dir_entry.name)
                if os.access(dir_copy_path, os.F_OK):
                    os.rmdir(dir_copy_path)
                shutil.copytree(dir_entry.path, dir_copy_path)
            else:
                shutil.copyfile(dir_entry.path, os.path.join(output_include_path, dir_entry.name))

        return output_path


def install_pip(temp_dir, python_exe_path):
    """Installs Pip for the specified Python executable.
    temp_dir - Directory in which to store temporary files generated by the operation.
    python_exe_path - Path to the Python executable.
    """
    # Download get-pip.py.
    get_pip_request_url = 'https://bootstrap.pypa.io/get-pip.py'
    get_pip_path = os.path.join(temp_dir, 'get-pip.py')
    with urllib.request.urlopen(get_pip_request_url) as get_pip_response, open(get_pip_path, 'wb') as get_pip_out:
        shutil.copyfileobj(get_pip_response, get_pip_out)

    # Run get-pip.py to install Pip.
    subprocess.run([python_exe_path, get_pip_path])


def install_dependencies(pip_exe_path):
    """Installs the plugin's dependencies using Pip.
    pip_exe_path - Path to the Pip executable.
    """
    subprocess.run([pip_exe_path, 'install', 'ordered-set'])
    subprocess.run([pip_exe_path, 'install', 'Shapely'])
    subprocess.run([pip_exe_path, 'install', 'triangle'])


def final_install(python_path, custom_blender_config_path, blender_version, platform_is_macos, platform_is_windows):
    """Performs the final installation of the plugin and its dependencies into the Blender configuration directory.
    python_path - Path to the temporary Python installation into which the dependencies were installed.
    plugin_path - Path to the plugin code.
    custom_blender_config_path - Path to the user's Blender configuration directory, or None to use the default.
    blender_version - Blender version as a string.
    platform_is_macos - Boolean indicating whether we are installing on a MacOS machine.
    platform_is_windows - Boolean indicating whether we are installing on a Windows machine.
    """
    # Find the user's Blender configuration directory.
    if custom_blender_config_path is None:
        if platform_is_windows:
            blender_config_path = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Blender Foundation',
                                               'Blender', blender_version)
        elif platform_is_macos:
            blender_config_path = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'Blender',
                                               blender_version)
        else:
            blender_config_path = os.path.join(os.path.expanduser('~'), '.config', 'blender', blender_version)
    else:
        blender_config_path = custom_blender_config_path
    blender_config_addons_path = os.path.join(blender_config_path, 'scripts', 'addons')
    blender_config_modules_path = os.path.join(blender_config_addons_path, 'modules')

    # Find the dependencies that need to be copied.
    python_site_packages_path = os.path.join(find_python_libs(python_path), 'site-packages')
    python_ordered_set_path = os.path.join(python_site_packages_path, 'ordered_set.py')
    python_shapely_path = os.path.join(python_site_packages_path, 'shapely')
    python_triangle_path = os.path.join(python_site_packages_path, 'triangle')

    # Copy the dependencies into the Blender configuration directory.
    print('    Copying dependencies to Blender config directory...')
    os.makedirs(blender_config_addons_path, exist_ok=True)
    os.makedirs(blender_config_modules_path, exist_ok=True)
    blender_config_ordered_set_path = os.path.join(blender_config_modules_path, 'ordered_set.py')
    blender_config_shapely_path = os.path.join(blender_config_modules_path, 'shapely')
    blender_config_triangle_path = os.path.join(blender_config_modules_path, 'triangle')
    if os.access(blender_config_ordered_set_path, os.F_OK):
        os.remove(blender_config_ordered_set_path)
    shutil.copyfile(python_ordered_set_path, blender_config_ordered_set_path)
    if os.access(blender_config_shapely_path, os.F_OK):
        shutil.rmtree(blender_config_shapely_path)
    shutil.copytree(python_shapely_path, blender_config_shapely_path)
    if os.access(blender_config_triangle_path, os.F_OK):
        shutil.rmtree(blender_config_triangle_path)
    shutil.copytree(python_triangle_path, blender_config_triangle_path)

    # Find the plugin's source code.
    view_carve_src_path = sys.path[0]
    if len(view_carve_src_path) == 0:
        view_carve_src_path = os.getcwd()
    view_carve_addon_src_path = os.path.join(view_carve_src_path, 'src', 'view_carve')

    # Copy the plugin code into the Blender configuration directory.
    print('    Copying View Carve to Blender config directory...')
    blender_config_view_carve_path = os.path.join(blender_config_addons_path, 'view_carve')
    if os.access(blender_config_view_carve_path, os.F_OK):
        shutil.rmtree(blender_config_view_carve_path)
    shutil.copytree(view_carve_addon_src_path, blender_config_view_carve_path)


def main():
    # Get platform information.
    platform_is_windows = sys.platform.startswith('win32') or sys.platform.startswith('cygwin')
    platform_is_macos = sys.platform.startswith('darwin')

    # Get command line arguments.
    arg_parser = argparse.ArgumentParser(description='Installer script for View Carve Blender addon')
    arg_parser.add_argument('blender_path', type=str, help='Path to the directory where Blender is installed')
    arg_parser.add_argument('-i', '--custom_install_path', type=str, help='Custom Blender configuration directory path')
    args = arg_parser.parse_args()

    # Find out what version of Blender we are using.
    print('Identifying Blender version...')
    blender_version = get_blender_version(args.blender_path, platform_is_macos)

    # Find out what version of Python Blender is using.
    print('Identifying Blender\'s Python version...')
    blender_python_path, blender_python_exe_path = get_blender_python_paths(args.blender_path, blender_version,
                                                                            platform_is_macos)
    blender_python_version, blender_python_is_64bit = get_python_version(blender_python_exe_path)

    # Create a temporary directory for storing temporary files generated by the rest of the installation process.
    with tempfile.TemporaryDirectory() as temp_dir:

        # Blender's Python installation usually lacks some files needed for installing Python dependencies that include
        # native code. For this reason, we can't just copy Blender's Python installation to install the required
        # packages. Instead, we will create a separate (temporary) Python installation of the same version that Blender
        # uses, with a combination of files taken from Blender and files downloaded from the Python website or NuGet.
        print('Creating temporary Python installation...')
        temp_python_path = make_temp_python(temp_dir, blender_python_path, blender_python_version,
                                            blender_python_is_64bit, platform_is_windows)
        temp_python_exe_path = find_python_exe(temp_python_path)

        # Install Pip into the temporary Python installation.
        print('Installing Pip...')
        install_pip(temp_dir, temp_python_exe_path)
        temp_pip_exe_path = find_pip_exe(temp_python_path, platform_is_windows)

        # Use Pip to install the plugin's dependencies.
        print('Installing dependencies with Pip...')
        install_dependencies(temp_pip_exe_path)

        # Copy the dependencies and the plugin code into the user's Blender configuration directory.
        print('Installing View Carve plugin...')
        final_install(temp_python_path, args.custom_install_path, blender_version, platform_is_macos,
                      platform_is_windows)


if __name__ == '__main__':
    main()
