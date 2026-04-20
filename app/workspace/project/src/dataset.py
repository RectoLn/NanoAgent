"""
测试数据集模块
构造多种测试场景的列表数据
"""

import random


def get_random_list(size=20):
    """
    生成随机乱序列表
    
    参数:
        size: 列表大小，默认20
        
    返回:
        随机乱序的列表
    """
    random.seed(42)  # 设置种子以保证测试可重复
    return [random.randint(0, 100) for _ in range(size)]


def get_ascending_list(size=20):
    """
    生成已正序排列的列表
    
    参数:
        size: 列表大小，默认20
        
    返回:
        已正序排列的列表
    """
    return list(range(1, size + 1))


def get_descending_list(size=20):
    """
    生成已逆序排列的列表
    
    参数:
        size: 列表大小，默认20
        
    返回:
        已逆序排列的列表
    """
    return list(range(size, 0, -1))


def get_duplicate_list(size=20):
    """
    生成包含重复元素的列表
    
    参数:
        size: 列表大小，默认20
        
    返回:
        包含重复元素的列表
    """
    random.seed(100)  # 设置种子以保证测试可重复
    return [random.choice([1, 2, 3, 5, 8, 13, 21]) for _ in range(size)]


def get_single_element_list():
    """
    生成只有一个元素的列表
    
    返回:
        只有一个元素的列表
    """
    return [42]


def get_empty_list():
    """
    生成空列表
    
    返回:
        空列表
    """
    return []


def print_all_datasets():
    """
    打印所有数据集内容
    """
    datasets = {
        "随机乱序列表（20个元素）": get_random_list(),
        "正序列表（20个元素）": get_ascending_list(),
        "逆序列表（20个元素）": get_descending_list(),
        "包含重复元素的列表": get_duplicate_list(),
        "只有一个元素的列表": get_single_element_list(),
        "空列表": get_empty_list()
    }
    
    print("=" * 60)
    print("所有测试数据集")
    print("=" * 60)
    
    for name, data in datasets.items():
        print(f"\n{name}:")
        print(f"  {data}")
        print(f"  长度: {len(data)}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print_all_datasets()
