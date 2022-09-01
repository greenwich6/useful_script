#!python
import random
 
id = 'ABCDEF-HIJKLM-(A)'
code = 'KMLH-JEEA-RKJM-NBGR-IXHH-LRAJ-POJK-BAFC-HHHH-LRFD'  # 4.0.0 注册码
 
 
def reverse_table(target_table):
    ret_table = [0 for x in range(len(target_table))]
    for i in range(160):
        var = target_table[i // 8]
        bit_value = (var >> (i % 8)) & 0x1
        index = i % 20
        ret_table[index] = ret_table[index] | (bit_value << i // 20)
    return ret_table
 
 
def add_random():
    return random.choice(['A', 'B', 'C', 'D', 'E'])
 
 
def integer_to_hex(int_array):
    result = []
    not_f_count = 0
    for i in range(len(int_array)):
        high = int_array[i] // 20
        low = int_array[i] % 20
        if i % 2 == 0 and i > 0:
            result.append('-')
        if high == 0 and not_f_count < 4:
            result.append(add_random())
            not_f_count += 1
        else:
            result.append(chr(high + 70))
        if low == 0 and not_f_count < 4:
            result.append(add_random())
            not_f_count += 1
        else:
            result.append(chr(low + 70))
    return ''.join(result)
 
 
def gen_register_code(user_id):
    init_table = [0 for x in range(20)]
    init_table[-1] = 70
    init_table[-2] = 85
    for i in range(17):
        init_table[i] = ord(user_id[i])
    ret = reverse_table(init_table)
    return integer_to_hex(ret)
 
 
def main():
    print(gen_register_code(id))
 
 
if __name__ == '__main__':
    main()