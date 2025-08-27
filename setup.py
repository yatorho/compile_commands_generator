from setuptools import find_packages, setup

setup(
    name="compile_commands_generator",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": ["compile_commands=compile_commands_generator.cli:main"]
    },
    python_requires=">=3.8",
)
