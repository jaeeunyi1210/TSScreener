import os
import sys
import subprocess
from datetime import datetime

def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(p.stdout)
    if p.stderr.strip():
        print("STDERR:", p.stderr, file=sys.stderr)
    return p.returncode

def main():
    start = datetime.now()
    print("=== Daily Update Start ===")
    print("Start:", start.isoformat(timespec="seconds"))
    print("CWD:", os.getcwd())
    print("Python:", sys.executable)

    # 1) 가격 갱신
    rc = run([sys.executable, "fetch_stooq.py"])
    if rc != 0:
        print("fetch_stooq.py failed. stop.")
        sys.exit(rc)

    # 2) AI 점수 갱신 (파일이 있을 때만)
    # build_ai_scores.py는 아직 안 만들었거나 API 키 없을 수 있으니 optional
    if os.path.exists("build_ai_scores.py"):
        rc2 = run([sys.executable, "build_ai_scores.py"])
        if rc2 != 0:
            print("build_ai_scores.py failed. (prices updated already) continuing...")
    else:
        print("\n(build_ai_scores.py not found - skip AI score update)")

    end = datetime.now()
    print("\n=== Daily Update Done ===")
    print("End:", end.isoformat(timespec="seconds"))
    print("Elapsed:", str(end - start))

if __name__ == "__main__":
    main()
