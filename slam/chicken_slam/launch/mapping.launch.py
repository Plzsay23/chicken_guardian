"""라이다 + slam_toolbox 맵핑.

odom:=ekf (기본)  robot_localization EKF 가 /odom + /imu/data_raw 로 odom -> base_link 를 낸다.
                  base_node(chicken_base) 가 따로 떠 있어야 한다.
odom:=fake        odom -> base_link 를 항등 변환으로 고정한다. 제자리 테스트용.
foxglove:=true (기본) 이면 foxglove_bridge 를 8765 포트로 띄운다 — 모니터 없이 원격으로 본다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.substitutions import PythonExpression
from launch.launch_description_sources import (AnyLaunchDescriptionSource,
                                                PythonLaunchDescriptionSource)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("chicken_slam")
    odom = LaunchConfiguration("odom")
    use_fake = IfCondition(PythonExpression(["'", odom, "' == 'fake'"]))
    use_ekf = IfCondition(PythonExpression(["'", odom, "' == 'ekf'"]))

    lidar = Node(
        package="ydlidar_ros2_driver",
        executable="ydlidar_ros2_driver_node",
        name="ydlidar_ros2_driver_node",
        output="screen",
        parameters=[os.path.join(share, "config", "lidar.yaml")],
    )

    # 장착 위치 실측 확인됨(2026-10-08, base 파트+사람): 라이다 회전 중심이 base_link(=보드 IMU)
    # 기준 앞 13 cm, 위 6 cm, 좌우 0(정면 정렬). 줄자 실측으로 확인됨, 추정치 아님.
    # URDF 가 생기면 integration 으로 옮긴다
    laser_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_tf_base_to_laser",
        arguments=["--x", "0.13", "--z", "0.06",
                   "--frame-id", "base_link", "--child-frame-id", "laser_frame"],
    )

    odom_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_tf_fake_odom",
        arguments=["--frame-id", "odom", "--child-frame-id", "base_link"],
        condition=use_fake,
    )

    # base_link 원점을 보드 IMU 위치로 잡았다 — imu_link 는 base_link 와 같다
    imu_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_tf_base_to_imu",
        arguments=["--frame-id", "base_link", "--child-frame-id", "imu_link"],
    )

    ekf = Node(
        package="robot_localization",
        executable="ekf_node",
        name="ekf_filter_node",
        output="screen",
        parameters=[os.path.join(share, "config", "ekf.yaml")],
        condition=use_ekf,
    )

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory("slam_toolbox"), "launch", "online_async_launch.py")),
        launch_arguments={
            "slam_params_file": os.path.join(share, "config", "slam_toolbox.yaml"),
            "use_sim_time": "false",
        }.items(),
    )

    foxglove = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(os.path.join(
            get_package_share_directory("foxglove_bridge"), "launch", "foxglove_bridge_launch.xml")),
        condition=IfCondition(LaunchConfiguration("foxglove")),
    )

    return LaunchDescription([
        DeclareLaunchArgument("odom", default_value="ekf", choices=["ekf", "fake"]),
        DeclareLaunchArgument("foxglove", default_value="true"),
        lidar, laser_tf, imu_tf, odom_tf, ekf, slam, foxglove,
    ])
