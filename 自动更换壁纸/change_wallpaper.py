
import ctypes
import os
import random
import functools
import schedule

index = 0


def change_background(picture_path: str) -> None:
    ctypes.windll.user32.SystemParametersInfoW(20, 0, picture_path, 3)


def get_pictures(dir_path: str) -> list:
    return [os.path.join(root, name)
            for root, dirs, files in os.walk(dir_path, topdown=False)
            for name in files
            if name.endswith('jpg') or name.endswith('png')]


def log(text):
    def decorator(f):
        @functools.wraps(f)
        def wrap(*args, **kwargs):
            p = f(*args, **kwargs)
            print(f'{text}: {p}')
            return p

        return wrap

    return decorator


@log(f'DESKTOP_BG_IMG switch to')
def change_background_job(dir_path) -> None:
    if dir_path.__class__.__name__ == 'list':
        dir_path = dir_path[0]
    pictures = get_pictures(dir_path)
    index = random.randint(0, len(pictures) - 1)
    change_background(pictures[index])
    return pictures[index]


def scheduler(job: staticmethod, interval, arg_num, *args) -> None:
    if arg_num <= 0:
        schedule.every(interval).seconds.do(job)
    else:
        schedule.every(interval).seconds.do(job, [args[i] for i in range(arg_num)])
    while True:
        schedule.run_pending()


if __name__ == '__main__':
    scheduler(change_background_job, 60, 1, r'C:\Users\Administrator\Downloads')