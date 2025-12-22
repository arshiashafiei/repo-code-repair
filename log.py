import datetime


def log_and_print(msg):
    filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "a") as f:
        f.write(msg + "\n")
    print(msg)
