from setuptools import setup
from Cython.Build import cythonize
from distutils.extension import Extension

ext = Extension(
    "loader",
    sources=["loader.pyx"],
)

setup(
    ext_modules=cythonize([ext], language_level=3),
    zip_safe=False,
)
