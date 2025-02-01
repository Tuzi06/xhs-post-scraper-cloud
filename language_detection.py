from langdetect import detect

def text_detection(txt):
    language = detect(txt)
    return language


def picture_detection():
    pass

def main():
    txt = '黑夜给了我黑色的眼睛，我却用它寻找光明。'
    print(text_detection(txt))

if __name__ == "__main__":
    main()