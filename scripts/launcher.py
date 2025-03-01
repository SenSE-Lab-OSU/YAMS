from argparse import ArgumentParser
import subprocess

if __name__ == '__main__':
    parser = ArgumentParser("YAMS launcher")
    parser.add_argument('-U', '--update', action="store_true")

    args = parser.parse_args()

    print(args)

    if not args.update:
        subprocess.call("python -m venv .venv", shell=True)
        subprocess.call("source .venv/bin/activate", shell=True)