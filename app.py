import multiprocessing
import sys
import traceback

multiprocessing.freeze_support()

status = 0
try:
    from yams.__main__ import main
    main()
except Exception:
    traceback.print_exc()
    status = 1

# Only pause when a human is watching; in CI the process must actually exit
# so a startup failure can't masquerade as a running app.
if sys.stdin is not None and sys.stdin.isatty():
    input("Press Enter to exit...")

sys.exit(status)
