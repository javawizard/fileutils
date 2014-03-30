from setuptools import setup

setup(
    name="fileutils",
    version="0.2.2",
    description="An object-oriented file access library",
    author="Alexander Boyd",
    author_email="alex@opengroove.org",
    setup_requires=["nose>=1.0"],
    packages=["fileutils"],
    tests_require=["coverage"]
)
