"""
冒泡排序算法实现模块
"""


def bubble_sort(arr):
    """
    对输入列表进行冒泡排序（原地排序）
    
    参数:
        arr: 待排序的列表
        
    返回:
        排序后的列表（返回同一个列表对象的引用）
    """
    # 为了不修改原列表，先创建一个副本
    result = arr.copy()
    n = len(result)
    
    # 外层循环：需要比较的轮数
    for i in range(n):
        # 标志位，用于优化：如果某一轮没有发生交换，说明已经有序，可以提前结束
        swapped = False
        
        # 内层循环：每轮比较相邻元素，将最大值"冒泡"到最后
        for j in range(0, n - i - 1):
            # 如果当前元素大于下一个元素，交换它们的位置
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        
        # 如果没有发生交换，数组已经有序，直接返回
        if not swapped:
            break
    
    return result


if __name__ == "__main__":
    # 测试代码
    test_list = [64, 34, 25, 12, 22, 11, 90]
    print(f"原始列表: {test_list}")
    print(f"排序后: {bubble_sort(test_list)}")
