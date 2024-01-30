from flask import Flask,request
from multiprocessing import Process,Manager
from bs4 import BeautifulSoup as bs
import time,requests,traceback,datetime

from lowlevel.scraper import getUser,grabing
class Scraper():
    def __init__(self,userScrapers,postScrapers):
        self.state = 'ready'
        self.userScraper = userScrapers
        self.postScraper = postScrapers
        self.headers = {
            'authority': 'www.xiaohongshu.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9',
            'cache-control': 'max-age=0',
            'cookie': 'abRequestId=0327e24d-58ec-5bec-a12a-388673237539; webBuild=4.1.6; a1=18d5c1af5d75ja3rdveqz7hi1g67old4bb5g9849v30000189236; webId=b293846ef2110fc76d0620697120b100; gid=yYf2SyD8yKDjyYf2Sy0i2DY4fW2V0qFfhdAu2jhWx3ykKkq8Wl1f4j888yYjJqK8qDfJ88fJ; cache_feeds=[]; xsecappid=xhs-pc-web; websectiga=7750c37de43b7be9de8ed9ff8ea0e576519e8cd2157322eb972ecb429a7735d4; web_session=030037a28a0a8d00f66c28c5c1224a5435187e; unread={%22ub%22:%22658b9e2a0000000015001605%22%2C%22ue%22:%22659cbc54000000001500225e%22%2C%22uc%22:29}; sec_poison_id=33c56913-1aad-402b-a4ff-2c5c15fa0719',
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            }

    def antiDetect(self,response,url):
        if 'https://www.xiaohongshu.com/website-login/error?redirectPath=' in response.url:
            time.sleep(5)
            response = requests.get(url,headers = self.headers)
        return response
    
    def homePageScraper(self,userlinkPool):
        start = time.perf_counter()
        print(datetime.datetime.now(),'\n')
        requests.get('http://127.0.0.1:3001/start')    
        num = requests.get('http://127.0.0.1:3001/count').content.decode("utf-8")
        requestnum = 10000 - int(num) # the num of post we need 
        print(f"{requestnum} post need be scrapped")
        while True:
            if userlinkPool.qsize()>5:
                time.sleep(1)
                continue
            time.sleep(1)
            try:
                url = "https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend"
                response = requests.get(url ,headers = self.headers)
                response = self.antiDetect(response,url)
                # self.headers = response.headers
                html = bs(response.content,'html.parser')
                # print(html.prettify())
                # open('a.html','w').write(html.prettify())
                # time.sleep(5)
                # return 
                userlinks = ['https://www.xiaohongshu.com'+title['href']for title in html.findAll('a',class_='author')]
                for userlink in userlinks:
                    userlinkPool.put(userlink)
                progress= int(requests.get('http://127.0.0.1:3001/count').content.decode("utf-8"))
                percent = ("{0:." + str(2) + "f}").format(100 * (progress/ float(requestnum)))
                print(f'\r progress: {percent}% Complete', end = '\r')
                if progress>= requestnum:
                    end = time.perf_counter()
                    print('\n Time is %4f hours'%((end - start)/3600)) 
                    break 
            except:
                continue

    def userPageScraper(self,userlinkPool,userInfoPipline,userLog): 
        while True:
            if userlinkPool.empty() or userInfoPipline.qsize()>10:
                time.sleep(1)
                continue
            userlink = userlinkPool.get()
            if userlink in userLog:
                continue
            userLog.append(userlink)
            try:
                response = requests.get(userlink,headers = self.headers)
                response = self.antiDetect(response,userlink)
                # self.headers = response.headers
                soup = bs(response.content,'html.parser')
                userInfo = getUser(soup)    
                if ('W' in userInfo['follow'] or 'K' in userInfo['follow']) and 'W' in userInfo['like']:
                    linklist =soup.findAll('a','title')
                    if len(linklist)>=10:
                        userInfo.pop('like')
                        userInfo.pop('follow')
                        # print(userInfo)
                        userInfoPipline.put({'userInfo':userInfo,'links':[link['href'] for link in linklist[:10]]})
                # return 
            except:
                # print(response.url)
                # traceback.print_exc()
                # return 
                # print('fail on users')
                continue
            
    def postPageScrapers(self,userInfoPipline):
        while True:
            if userInfoPipline.empty():
                time.sleep(1)
                continue
            userInfo,links = userInfoPipline.get().values()
            idx = 0
            userInfo['posts'] = []
            for link in links:
                try:
                    url = 'https://www.xiaohongshu.com'+link
                    response = requests.get(url,headers = self.headers)
                    response = self.antiDetect(response,url)

                    soup = bs(response.content.decode('utf-8'),'html.parser')
                    idx,post= grabing(soup,self.headers,userInfo,idx)
                except:
                    # traceback.print_exc()
                    # return
                    # print('fail on post')
                    continue
                post['url'] = url
                id = requests.get(f"http://127.0.0.1:3001/insert",json = {'id':'posts','data':post}).content.decode("utf-8")
                userInfo['posts'].append(id)
            requests.get(f"http://127.0.0.1:3001/insert",json = {'id':'users','data':userInfo})
            

app = Flask(__name__)

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/start')
def start():
    global userInfoPipline,userlinkPool,posts,userLog,scraper,processes
    userInfoPipline =Manager().Queue()
    userlinkPool =Manager().Queue()
    print(userInfoPipline.qsize(),userlinkPool.qsize())
    posts = Manager().list()
    userScrapers,postScrapers,userlog = request.get_json().values()
    userLog = Manager().list(userlog)
    scraper = Scraper(userScrapers,postScrapers)
    processes = []
    processes.append(Process(target = scraper.homePageScraper,args=[userlinkPool]))
    for _ in range(scraper.userScraper):
        processes.append(Process(target=scraper.userPageScraper,args=[userlinkPool,userInfoPipline,userLog]))
    for _ in range (scraper.postScraper):
         processes.append(Process(target=scraper.postPageScrapers,args=[userInfoPipline]))
    for process in processes:
        process.start()
    return 'finish starting'

@app.route('/state')
def fetchState():
    try:
        if userlinkPool.qsize()>15:
            return 'full'
        else:
            return 'ready'
    except:
        return 'cold'

@app.route('/download')
def download():
    return list(posts)

@app.route('/progress')
def checkProgress():
    return str(len(posts))

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