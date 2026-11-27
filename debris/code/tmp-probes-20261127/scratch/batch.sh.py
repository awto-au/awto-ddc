import subprocess
for a in ["isp 1 10","isp 2 10","isp 3 10","sleepwake 3 10","sleepwake 1 5","switch 3 10"]:
    subprocess.run(["python3","tmp/scratch/episode.py",*a.split()], cwd="/mnt/2tb/git/awto-ddc")
