
import sys,time
from selenium import webdriver    #模拟浏览器行为的库

#下载图片
def downloadImg(driver):

    crop_button = driver.find_element_by_xpath('/html/body/aside/div/div[1]/div[3]/ul/li[2]/a')  # 定位元素--裁剪图片
    crop_button.click()

    size_bt = driver.find_element_by_xpath('//*[@id="respicker-form"]/div/table/tbody/tr[2]/td[1]/label')#选择尺寸
    size_bt.click()

    download_bt = driver.find_element_by_xpath('//*[@id="respicker-form"]/button')
    download_bt.click()  # 点击下载按钮
    time.sleep(1)
    determin_bt = driver.find_element_by_xpath('//*[@id="overlay"]/section/div/a[2]')
    determin_bt.click()  # 点击确认按钮
    time.sleep(1)

#遍历图片预览页下载
def gotoOverview(xpathOfImg,driver,handle):
    driver.find_element_by_xpath(xpathOfImg).click()#点击图片进入下载页面
    handles = driver.window_handles#获取当前所有窗口页签句柄
    for newhandle in handles:
        if newhandle != handle:
            driver.switch_to.window(newhandle)
            downloadImg(driver)
            driver.close()
            driver.switch_to.window(handle)



if __name__=='__main__':
    num = 24 #下载图片的数量
    url = 'https://wallhaven.cc/search?categories=110&purity=100&topRange=6M&sorting=toplist&order=desc&page=1'
    driver = webdriver.Chrome('C:\Python310\Tools\chromedriver.exe')#chromedriver的存放目录
    driver.implicitly_wait(30)
    driver.get(url) #进入网站
    handle = driver.current_window_handle#获得当前窗口句柄
    xpath_name = '//*[@id="thumbs"]/section/ul/li[1]/figure/a'

    for x in range(1,num+1):
        xpath_name = '//*[@id="thumbs"]/section/ul/li['+str(x)+']/figure/a'
        print('已下载：',x,'/',num)
        gotoOverview(xpath_name,driver,handle)
    driver.quit()#退出浏览器
    print('下载完毕！')
