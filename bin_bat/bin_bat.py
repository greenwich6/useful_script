'''
Author: GreenwichJ
Date: 2022-05-21 21:32:43
LastEditTime: 2022-05-21 23:50:40
LastEditors: GreenwichJ
Description: shadowrunner
FilePath: \useful_script\bin_bat\bin_bat.py
Life of Code
'''


import struct
import os
import binascii

if __name__ == '__main__':
    filepath = r'D:\GitHub\useful_script\bin_bat\test.bin'
    size = os.path.getsize(filepath)  # 获得文件大小
    binfile = open(filepath, 'rb')  # 打开二进制文件
    temp = binfile.read()
    binfile.close()
 #   newbin = binascii.hexlify(temp)#解码 变成字符串
    temp = temp.replace(bytes(31), bytes(32))  # 替换字符串
    print(temp)
    newbin = binascii.unhexlify(temp)[::-1]  # 反转回二进制
    with open(filepath, "wb") as n:
        n.write(newbin)  # 重新写入
        n.close()
