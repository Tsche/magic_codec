from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()

        name = "magic_codec.pth"
        input_file = Path("src") / name
        output_file = Path(self.build_lib) / name

        # install path configuration file
        self.copy_file(str(input_file), str(output_file), preserve_mode=0)


setup(
    name="magic_codec",
    version="0.0.1",
    description="Extensible codec that can be used to drastically change the behavior of the Python interpreter.",
    author="Tsche",
    author_email="contact@palliate.io",
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    include_package_data=True,
    cmdclass={"build_py": BuildPy},
    # TODO: enable, required for declarative macros
    # extras_require={
    #     # optional dependency for PEG parsing and declarative macros
    #     'peg': ["pegen==0.3.0"]
    # },
    install_requires = ["colorama==0.4.6"],
    entry_points = {
        'console_scripts': ['magic-macro=magic_codec.macro.__main__:main'],
    }
)
