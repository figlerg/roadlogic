from setuptools import find_packages, setup
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='syma',
    version='0.0.1',
    description='Library for symbolic automata.',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/nickovic/syma',
    author='Dejan Nickovic',
    author_email='dejan.nickovic@ait.ac.at',
    license='BSD',
    python_requires='>=3.5',
    install_requires=['z3-solver', 'pandas', 'numpy', 'networkx'],
    packages=find_packages(),

    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.5',
	    'Programming Language :: Python :: 3.6',
	    'Programming Language :: Python :: 3.7',
        'Programming Language :: C++',
    ],
)