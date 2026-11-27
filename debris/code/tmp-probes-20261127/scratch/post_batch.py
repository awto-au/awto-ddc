import re, subprocess, sys, time
W = "/mnt/2tb/git/awto-dan/scripts/gh_claudia.py"
txt = open("tmp/scratch/issues-batch.md").read()
parts = re.split(r"^### ", txt, flags=re.M)[1:]
log = open("tmp/logs/post_batch.log", "a")
for p in parts:
    head, _, body = p.partition("\n")
    body = body.strip() + "\n"
    if head.startswith("NEW "):
        title = head[4:].strip()
        r = subprocess.run(["python", W, "gh", "issue", "create", "--repo", "awto-au/awto-ddc", "--title", title, "--body", body], capture_output=True, text=True)
    else:
        num = re.match(r"COMMENT #(\d+)", head).group(1)
        r = subprocess.run(["python", W, "gh", "issue", "comment", num, "--repo", "awto-au/awto-ddc", "--body", body], capture_output=True, text=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {head[:70]} rc={r.returncode} {r.stdout.strip()} {r.stderr.strip()[:200]}"
    print(line); log.write(line + "\n")
