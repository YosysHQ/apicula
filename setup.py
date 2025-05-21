import setuptools

with open("readme.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Apycula",
    author="Pepijn de Vos",
    author_email="pepijndevos@gmail.com",
    description="Open Source tools for Gowin FPGAs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/YosysHQ/apicula",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'crc',
    ],
    python_requires='>=3.6',
    package_data={
        'apycula': ['*.pickle']
    },
    entry_points={
        'console_scripts': [
            'gowin_pack=apycula.gowin_pack:main',
            'gowin_unpack=apycula.gowin_unpack:main',
            'gowin_pll=apycula.gowin_pll:main',
        ],
    },
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
)
