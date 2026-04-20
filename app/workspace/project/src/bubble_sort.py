#!/usr/bin/env python3
"""
冒泡排序算法实现
"""

def bubble_sort(arr):
    """
    冒泡排序算法
    
    参数:
        arr: 待排序的列表
        
    返回:
        排序后的新列表（原列表不会被修改）
    """
    # 创建副本，避免修改原列表
    result = arr.copy()
    n = len(result)
    
    # 如果列表为空或只有一个元素，直接返回
    if n <= 1:
        return result
    
    # 外层循环控制排序轮数
    for i in range(n - 1):
        # 标记本轮是否有交换发生
        swapped = False
        
        # 内层循环进行相邻元素比较和交换
        # 每轮结束后，最大的元素会"冒泡"到末尾
        for j in range(0, n - i - 1):
            if result[j] > result[j + 1]:
                # 交换相邻元素
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        
        # 如果本轮没有发生交换，说明列表已经有序，提前结束
        if not swapped:
            break
    
    return result


def bubble_sort_inplace(arr):
    """
    原地冒泡排序算法（会修改原列表）
    
    参数:
        arr: 待排序的列表
        
    返回:
        排序后的列表（原列表会被修改）
    """
    n = len(arr)
    
    # 如果列表为空或只有一个元素，直接返回
    if n <= 1:
        return arr
    
    # 外层循环控制排序轮数
    for i in range(n - 1):
        # 标记本轮是否有交换发生
        swapped = False
        
        # 内层循环进行相邻元素比较和交换
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                # 交换相邻元素
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        
        # 如果本轮没有发生交换，说明列表已经有序，提前结束
        if not swapped:
            break
    
    return arr


if __name__ == "__main__":
    # 测试代码
    test_cases = [
        [64, 34, 25, 12, 22, 11, 90],
        [5, 2, 8, 1, 9],
        [1, 2, 3, 4, 5],  # 已经有序
        [5, 4, 3, 2, 1],  # 逆序
        [3, 1, 4, 1, 5, 9, 2, 6, 5],  # 包含重复元素
        [42],  # 单个元素
        []  # 空列表
    ]
    
    print("冒泡排序测试:")
    print("-" * 50)
    
    for i, test_arr in enumerate(test_cases):
        original = test_arr.copy()
        sorted_arr = bubble_sort(test_arr)
        expected = sorted(test_arr)
        
        print(f"测试用例 {i+1}: {original}")
        print(f"排序结果: {sorted_arr}")
        print(f"预期结果: {expected}")
        print(f"是否正确: {sorted_arr == expected}")
        print("-" * 30)