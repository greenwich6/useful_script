
import os

testpin = open('test.txt', 'wb+')
test = testpin.read()
test1 = test.decode('gb2312')
testpin.write('hadufhuihfah')
    
testpin.close()
