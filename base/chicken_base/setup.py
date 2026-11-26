from setuptools import find_packages, setup

package_name = 'chicken_base'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/base.launch.py']),
        ('share/' + package_name + '/config', ['config/params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='chicken',
    maintainer_email='chicken@todo.invalid',
    description='Chicken coop patrol robot base/drive control (M500 chassis serial driver and teleop)',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'base_node = chicken_base.base_node:main',
            'teleop_keyboard = chicken_base.teleop_keyboard:main',
            'light_node = chicken_base.light_node:main',
        ],
    },
)
