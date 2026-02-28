import traceback
import sys

try:
    import clawlite.gateway.server
    print("OK")
except Exception as e:
    traceback.print_exc()
