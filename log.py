import datetime

filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

def log_and_print(msg):
    with open("logs/" + filename, "a+") as f:
        f.write(str(msg) + "\n")
    print(msg)
