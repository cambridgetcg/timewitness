"""F6 helper: sleep for a hidden number of seconds, then print DONE.

The number comes from the environment variable TIME_USE_SLEEP_S, which the model
cannot read with the tools it is allowed. run_claude.py copies this file into the
F6 working folder and sets the variable for each call.
"""
import os
import time

time.sleep(float(os.environ.get("TIME_USE_SLEEP_S", "60")))
print("DONE")
