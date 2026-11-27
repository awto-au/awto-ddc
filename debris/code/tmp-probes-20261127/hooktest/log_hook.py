import sys
open("/mnt/2tb/git/awto-ddc/tmp/hooktest/in.jsonl", "a").write(sys.stdin.read().replace("\n", " ") + "\n")
