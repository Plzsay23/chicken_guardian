from glob import glob

from setuptools import find_packages, setup

package_name = "chicken_slam"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="chicken",
    maintainer_email="chicken@todo.invalid",
    description="Chicken coop patrol robot lidar bringup and SLAM",
    license="TODO",
)
