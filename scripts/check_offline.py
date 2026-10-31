"""Check model inference with Python network connections disabled."""
from result_automation.selftest import offline_check


if __name__ == "__main__":
    print(offline_check())
