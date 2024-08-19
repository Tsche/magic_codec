import os
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()

        name = "magic_codec.pth"
        # install path configuration file
        self.copy_file(name, os.path.join(self.build_lib, name), preserve_mode=0)

setup(
   name="magic_codec",
   cmdclass={"build_py": BuildPy},
   package_dir={'': 'src'},
   packages=find_packages(
        where='src',
    ),
   version="0.0.1"
)

print("SETUP")