def bubble_sort(arr):
    """
    冒泡排序（Bubble Sort）

    原理：重复遍历待排序序列，依次比较相邻两个元素，
    如果顺序错误就交换，直到没有需要交换的元素为止。

    时间复杂度：O(n²)  空间复杂度：O(1)
    稳定排序 | 原地排序
    """
    n = len(arr)
    # 外层循环：控制遍历轮数，每轮将当前最大值"冒泡"到末尾
    for i in range(n - 1):
        swapped = False  # 优化：标记本轮是否有交换
        # 内层循环：比较相邻元素，每轮比较次数递减（已排序的末尾不再参与）
        for j in range(n - 1 - i):
            if arr[j] > arr[j + 1]:   # 升序排列，若改为 < 则为降序
                arr[j], arr[j + 1] = arr[j + 1], arr[j]  # 交换
                swapped = True
        # 如果本轮没有任何交换，说明已经有序，提前结束
        if not swapped:
            break
    return arr


if __name__ == "__main__":
    # 测试
    test_data = [64, 34, 25, 12, 22, 11, 90]
    print("排序前:", test_data)
    sorted_data = bubble_sort(test_data.copy())
    print("排序后:", sorted_data)

    # 边界情况测试
    print("空列表:", bubble_sort([]))
    print("单元素:", bubble_sort([1]))
    print("已有序:", bubble_sort([1, 2, 3, 4, 5]))
