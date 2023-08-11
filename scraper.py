from flask import Flask,request,jsonify
import os,logging,time,pickle,queue,requests,json 
from multiprocessing import Process,Pipe
from lowlevel.ins import findPicture,run

class Scraper:
    def __init__(self) -> None:
        self.userState = 'idle'
        self.dataState = 'idle'
        self.parent, self.child = Pipe() # pipe for passing users name to getShortCode and update UserState
        self.codeParent,self.codeChild = Pipe() # pipe for return the shorCode list
        self.postParent,self.postChild = Pipe() # pipe for passing html to getData and update dataState
        self.resParent,self.resChild = Pipe()
        self.stop = False

    def getShortCode(self, pipe):
        self.child = pipe
        while not self.stop:
            job = self.child.recv()
            if job != None:
                self.child.send('busy')
                user,_ = job.values()
                username = 'tuzi06'
                password = 'rbckHhji06FbJTa00y'
                proxy = f"http://{username}:{password}@ca.smartproxy.com:20001"
                response = requests.get(f"{user}?__a=1&__d=dis",proxies={'http':proxy,'https':proxy})
                
                print(response.status_code)
                if response.status_code == 200:  
                    shortCodes = [node['node']['shortcode'] for node in (json.loads(response.text))['graphql']['user']['edge_felix_video_timeline']['edges']]
                    print(shortCodes)   
                    self.codeParent.send(shortCodes)
                    print('done')
                    self.child.send('idle')
                   
                else:
                    self.child.send('scraping-detected')

    def getData(self,pipe):
        self.postChild = pipe
        while not self.stop:
            job = self.postChild.recv()
            if job != None:
                # print(job)
                self.postChild.send('busy')
                # data = job
                # html,user,pics = job.get('html','user','pics')
                print(job.get('user'))
                post = run(job['html'],job['user'],job['pics'])
                print(type(post))
                self.resParent.send(post)
                self.postChild.send('idle')

app = Flask(__name__)

@app.route('/start')
def start_child_process(): #Gunicorn does not allow the creation of new processes before the app creation, so we need to define this route
    global scraper
    scraper = Scraper()
    Process(target = scraper.getShortCode, args = [scraper.child]).start()
    Process(target = scraper.getData, args = [scraper.postChild]).start()
    return "Scraper running"

@app.route('/stop')
def stop():
    scraper.stop = True
    return 'stopped'

@app.route('/userJob')
def process_userjob():
    print(request.args)
    scraper.parent.send(request.args)
    while True:
        shortCodes = scraper.codeChild.recv()
        if shortCodes != None:
            break
    print(shortCodes)
    if shortCodes:
        return jsonify(result = shortCodes)

@app.route('/dataJob',methods=['POST'])
def process_dataJob():
    scraper.postParent.send(request.get_json())
    while True:
        post= scraper.resChild.recv()
        if post != None:
            break
        time.sleep(3)
    return jsonify(result=post)
    
@app.route('/download')
def store_posts():
    return jsonify(result = scraper.posts)

@app.route('/reset')
def reset_post():
    scraper.posts = []


@app.route('/state')
def current_state():
    try:
        process,_ = request.args.values()
        if process == "user":
                if scraper.parent.poll(timeout=3): #checks if there are new messages from the child process
                    scraper.userState = scraper.parent.recv() # updates the state in such case
                return scraper.userState
        elif process == 'data':
            if scraper.postParent.poll(timeout=3): #checks if there are new messages from the child process
                scraper.dataState = scraper.postParent.recv() # updates the state in such case
            return scraper.dataState
    except:
        return "not-started"
 

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)