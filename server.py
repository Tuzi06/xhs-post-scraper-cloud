from copy import deepcopy
import math
from flask import Flask,request
from multiprocessing import Process,Manager
from bs4 import BeautifulSoup as bs
import time,requests,traceback,datetime,json,random,sys

from language_detection import text_detection
from scraper import getUser,grabing
class Scraper():
    def __init__(self,scraperNum,dburl,goal):
        self.scraperNum = scraperNum
        self.dburl = dburl
        self.headers = json.load(open('headers.json','r'))
        self.cookies = json.load(open('cookies.json','r'))
        self.goal = goal
        self.start = time.perf_counter()
        # requests.get('https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend',headers = self.headers['htmlHeaders'])

    def manager(self,userlinkPool,userInfoPipline,state,cookies):
        lasttime = self.start
        lastprogress = 0

        if requests.get(f'{self.dburl}/state').content.decode("utf-8") == 'cold':
            requests.get(f'{self.dburl}/start')
        if state.value == 'cold':
            state.value ='started'
            print(datetime.datetime.now(),'\n')
            requests.get(f'{self.dburl}/start')    
            num = requests.get(f'{self.dburl}/count').content.decode("utf-8")
            requestnum = self.goal- int(num) # the num of post we need 
            print(f"{requestnum} post need be scrapped \n\n")
            
        else:
            num = requests.get(f'{self.dburl}/count').content.decode("utf-8")
            requestnum = self.goal- int(num) # the num of post we need 
        while True:
                progress= int(requests.get(f'{self.dburl}/count').content.decode("utf-8"))
                if progress>=self.goal:
                    if not userInfoPipline.empty() or not userlinkPool.empty():
                        while not userInfoPipline.empty():
                            userInfoPipline.get()
                        while not userlinkPool.empty():
                            userlinkPool.get()
                    end = time.perf_counter()
                    sys.stdout.write("\033[K") 
                    print('\r Time is %4f hours '%((end -self.start)/3600),end = '\r')
                    return 
                current = time.perf_counter()
                
                percent = ("{0:." + str(2) + "f}").format(100 * (progress/ float(int(num)+requestnum)))
                speed =  ("{0:." + str(2) + "f}").format((progress-lastprogress)/(current-lasttime))
                print(f'\r progress: {percent}% Completed, speed: {speed} p/s, len of both queue: {userlinkPool.qsize()}/{userInfoPipline.qsize()}  ', end = '\r')
                lasttime = current
                lastprogress = progress 
                try:
                    cookie = cookies.pop(random.randint(0,len(cookies)-1))
                except:
                    continue
                if userInfoPipline.qsize() >= 1:
                    self.postPageScraper(userInfoPipline,cookie)
                elif userlinkPool.qsize() >= 1:
                    self.userPageScraper(userlinkPool,userInfoPipline)
                else:
                    res = self.homePageScraper(userlinkPool,cookie)
                    if res == 'empty':
                        progress= int(requests.get(f'{self.dburl}/count').content.decode("utf-8"))
                        if (int(progress)+random.randint(0,100))%37==0:
                            cookies.append(cookie)
                            cookie = self.updateCookie("https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend")
                cookies.append(cookie) 
    
        
    def homePageScraper(self,userlinkPool,cookie):
        url = "https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend"
        headers = deepcopy(self.headers['htmlHeaders'])
        try:
            headers['cookie'] = cookie
            response = requests.get(url ,headers = headers)
            response = self.antiDetect(response,url,'home')

            html = bs(response.content,'html.parser')
            userlinks =[title['href']for title in html.findAll('a',class_='author')]
    
            filtered = requests.get(f'{self.dburl}/checkExist',json = {'data':userlinks}).json()
            for userlink in filtered:
                userlinkPool.put('https://www.xiaohongshu.com/user/profile/'+userlink)
            if len(filtered)!=0:
                requests.post(f'{self.dburl}/addlog',json ={'id':'users','data':[userlink.split('/')[-1] for userlink in filtered]})
            if len(userlinks) == 0:
                return 'empty'
            return 'success'
        except:
            # traceback.print_exc()
            return 'fail'

    def userPageScraper(self,userlinkPool,userInfoPipline): 
        if userlinkPool.empty():
            return
        headers = deepcopy(self.headers['htmlHeaders'])
        userlink = userlinkPool.get()
        try:
            response = requests.get(userlink,headers = headers)
            response = self.antiDetect(response,userlink,'user')
            soup = bs(response.content,'html.parser')
            userInfo = getUser(soup)   
            linklist =soup.findAll('a','cover ld mask')
            if ('万' in userInfo['follow'] or '千' in userInfo['follow']) and '万' in userInfo['like'] and len(linklist)>=10:
                userInfo['longID'] = userlink.split('/')[-1]
                userInfoPipline.put({'userInfo':userInfo,'links':[link['href'] for link in linklist[:10]]})
        except:
            traceback.print_exc()   
            return      
            
    def postPageScraper(self,userInfoPipline,cookie):
        if userInfoPipline.empty():
            return 
        headers = deepcopy(self.headers['htmlHeaders'])
        headers['cookie'] = cookie
        userInfo,links = userInfoPipline.get().values()
        idx = 0
        posts=[]
        for link in links:
            try:
                url = 'https://www.xiaohongshu.com'+link
                response = requests.get(url,headers = headers)
                response = self.antiDetect(response,url,'post')
                print(url)
                soup = bs(response.content.decode('utf-8'),'html.parser')
                idx,post= grabing(soup,self,userInfo,idx)
                if not post:
                    continue
                post['url'] = url
                posts.append(post)
            except:
                traceback.print_exc()
                # print('fail on post')
                continue
                # return
        if len(posts)!=0:
            try:
                userInfo['posts'] = requests.post(f"{self.dburl}/insert",json = {'id':'posts','data':posts}).json()
            except:
                userInfo['posts'] = []
            
            requests.post(f"{self.dburl}/insert",json = {'id':'users','data':userInfo})       

    def antiDetect(self,response,url,stage):
        if 'https://www.xiaohongshu.com/website-login/error?redirectPath=' in response.url or response.status_code != 200:
            # time.sleep(2)
            if response.status_code != 200:
                print(response.status_code,'  ',stage)
            headers=deepcopy(self.headers['htmlHeaders'])
            headers['cookie'] = random.choice(self.cookies)
            response = requests.get(url,headers = headers)
        return response
    
    def updateCookie(self,url):
        try:
            response= requests.get(url,headers = self.headers['htmlHeaders'])
            newAd = response.headers['Set-Cookie'].split('; ')[0]
            newCookie = [newAd] + self.headers['cookie'].split('; ')[1:]
            newCookie = '; '.join(newCookie)
            return newCookie
        except:
            return random.choice(self.cookies)
        
app = Flask(__name__)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/run')
def run():
    global userInfoPipline,userlinkPool,cookies,state
    userInfoPipline = Manager().Queue()
    userlinkPool = Manager().Queue()
    state = Manager().Value(str,'cold')
    scraperNum,dburl,goal = request.get_json().values()
    scraper = Scraper(scraperNum,dburl,goal)
    cookies = Manager().list(scraper.cookies)

    for _ in range(scraper.scraperNum):
        Process(target = scraper.manager,args=[userlinkPool,userInfoPipline,state,cookies]).start()
        time.sleep(1)
    return 'started'

@app.route('/poolState')
def poolState():
    return str(f"userInfoQueue:{userlinkPool.qsize()}, postQueue:{userInfoPipline.qsize()}")
    
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=3000)

    # docker run -d -p 4444:4444 -e SE_NODE_MAX_SESSIONS=40 -e SE_NODE_OVERRIDE_MAX_SESSIONS=true -e SE_NODE_SESSION_TIMEOUT=86400 selenium/standalone-chrome
    # docker run -d -p 4444:4444 -e SE_NODE_MAX_SESSIONS=40 -e SE_NODE_OVERRIDE_MAX_SESSIONS=true -e SE_NODE_SESSION_TIMEOUT=864000 seleniarm/standalone-chromium

    # docker kill $(docker ps -q)
    # docker buildx build --platform linux/amd64 -t tuzi06/scraper-x86:latest --push .
    # docker buildx build  -t tuzi06/scraper-arm:latest --push .
    # docker rm $(docker ps --filter status=exited -q) 